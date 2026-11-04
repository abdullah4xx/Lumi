import importlib.util
import io
import json
import stat
import sys
import tempfile
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import patch

from PIL import Image


SERVER_PATH = Path(__file__).resolve().parents[1] / "tools/icon-studio/server.py"
SPEC = importlib.util.spec_from_file_location("lumi_icon_studio_server", SERVER_PATH)
assert SPEC and SPEC.loader
server = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = server
SPEC.loader.exec_module(server)


class IconStudioTests(unittest.TestCase):
    def test_shape_geometry_is_unchanged_and_image_corners_are_rounded(self):
        shape = server.validate_shape(server.DEFAULTS)
        path = server.make_path(shape)

        self.assertTrue(path.startswith("M 0 152 C 73.52 152,"))
        svg = server.make_svg(shape).decode("utf-8")
        self.assertIn('rx="112"', svg)
        self.assertIn('clip-path="url(#icon-bounds)"', svg)
        png = Image.open(io.BytesIO(server.make_pngs(shape)[512]))
        self.assertEqual(png.size, (512, 512))
        self.assertEqual(png.mode, "RGBA")
        self.assertEqual(png.getpixel((0, 0))[3], 0)
        self.assertEqual(png.getpixel((256, 256))[3], 255)

    def test_apply_updates_project_and_user_launcher_assets_without_restoring_legacy_icon(self):
        shape = server.validate_shape(server.DEFAULTS)
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            project_root = temporary_root / "project"
            icon_theme_root = temporary_root / "icons"
            with (
                patch.object(server, "ROOT", project_root),
                patch.object(server, "ICON_THEME_ROOT", icon_theme_root),
                patch.object(server.shutil, "which", return_value=None),
            ):
                warnings = server.apply_icon(shape)

            self.assertTrue((project_root / "ui/img/lumi-icon.svg").is_file())
            self.assertTrue((project_root / "build/icon.png").is_file())
            self.assertEqual(stat.S_IMODE((project_root / "build/icon.png").stat().st_mode), 0o644)
            for size in server.SIZES:
                icon_path = icon_theme_root / f"{size}x{size}/apps/lumi-desktop.png"
                with Image.open(icon_path) as icon:
                    self.assertEqual(icon.size, (size, size))
                self.assertEqual(stat.S_IMODE(icon_path.stat().st_mode), 0o644)
            self.assertFalse((icon_theme_root / "512x512/apps/lumi.png").exists())
            self.assertEqual(len(warnings), 1)
            self.assertIn("gtk-update-icon-cache is unavailable", warnings[0])

    def test_apply_endpoint_returns_cache_refresh_warnings(self):
        http_server = ThreadingHTTPServer((server.HOST, 0), server.IconStudioHandler)
        port = http_server.server_address[1]
        thread = Thread(target=http_server.serve_forever, daemon=True)
        thread.start()
        try:
            with (
                patch.object(server, "PORT", port),
                patch.object(
                    server,
                    "apply_icon",
                    return_value=["Cache refresh needs a desktop restart."],
                ) as apply,
            ):
                connection = HTTPConnection(server.HOST, port, timeout=2)
                body = json.dumps(server.DEFAULTS).encode("utf-8")
                connection.request(
                    "POST",
                    "/api/apply",
                    body=body,
                    headers={
                        "Content-Type": "application/json",
                        "Origin": f"http://{server.HOST}:{port}",
                    },
                )
                response = connection.getresponse()
                result = json.loads(response.read())
                connection.close()

            self.assertEqual(response.status, 200)
            self.assertEqual(
                result,
                {"ok": True, "warnings": ["Cache refresh needs a desktop restart."]},
            )
            apply.assert_called_once_with(server.validate_shape(server.DEFAULTS))
        finally:
            http_server.shutdown()
            http_server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
