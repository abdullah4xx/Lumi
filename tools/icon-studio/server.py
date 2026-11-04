#!/usr/bin/env python3
"""Loopback-only preview and save server for the Lumi icon studio."""

from __future__ import annotations

import io
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Literal, TypedDict
from urllib.parse import urlsplit

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
STUDIO_DIR = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 5187
ICON_THEME_ROOT = Path.home() / ".local/share/icons/hicolor"
ICON_CORNER_RADIUS = 112
SIZES = (16, 24, 32, 48, 64, 96, 128, 256, 512)
DEFAULTS = {
    "centerWidth": 176,
    "centerHeight": 80,
    "edgeHeight": 208,
    "curve": 92,
    "backgroundColor": "#ffffff",
    "fillMode": "solid",
    "fillColor": "#111111",
    "gradientStart": "#111111",
    "gradientMiddle": "#111111",
    "gradientEnd": "#111111",
    "gradientAngle": 0,
}
LIMITS = {
    "centerWidth": (80, 320),
    "centerHeight": (24, 192),
    "edgeHeight": (64, 320),
    "curve": (0, 100),
    "gradientAngle": (0, 360),
}
COLOR_KEYS = ("backgroundColor", "fillColor", "gradientStart", "gradientMiddle", "gradientEnd")
COLOR_PATTERN = re.compile(r"#[0-9a-fA-F]{6}\Z")


class IconDesign(TypedDict):
    centerWidth: int
    centerHeight: int
    edgeHeight: int
    curve: int
    backgroundColor: str
    fillMode: Literal["solid", "gradient"]
    fillColor: str
    gradientStart: str
    gradientMiddle: str
    gradientEnd: str
    gradientAngle: int


def validate_shape(data: object) -> IconDesign:
    expected_keys = set(LIMITS) | set(COLOR_KEYS) | {"fillMode"}
    if not isinstance(data, dict) or set(data) != expected_keys:
        raise ValueError("The icon design parameters are incomplete.")

    numbers: dict[str, int] = {}
    for key, (minimum, maximum) in LIMITS.items():
        value = data[key]
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ValueError(f"{key} must be an integer from {minimum} to {maximum}.")
        numbers[key] = value
    color_values: dict[str, str] = {}
    for key in COLOR_KEYS:
        value = data[key]
        if not isinstance(value, str) or not COLOR_PATTERN.fullmatch(value):
            raise ValueError(f"{key} must be a six-digit hex color.")
        color_values[key] = value.lower()
    fill_mode = data["fillMode"]
    if fill_mode not in ("solid", "gradient"):
        raise ValueError("fillMode must be solid or gradient.")
    return {
        "centerWidth": numbers["centerWidth"],
        "centerHeight": numbers["centerHeight"],
        "edgeHeight": numbers["edgeHeight"],
        "curve": numbers["curve"],
        "backgroundColor": color_values["backgroundColor"],
        "fillMode": fill_mode,
        "fillColor": color_values["fillColor"],
        "gradientStart": color_values["gradientStart"],
        "gradientMiddle": color_values["gradientMiddle"],
        "gradientEnd": color_values["gradientEnd"],
        "gradientAngle": numbers["gradientAngle"],
    }


def make_path(shape: IconDesign) -> str:
    center = 256
    left = (512 - shape["centerWidth"]) / 2
    right = 512 - left
    center_top = center - shape["centerHeight"] / 2
    center_bottom = center + shape["centerHeight"] / 2
    edge_top = center - shape["edgeHeight"] / 2
    edge_bottom = center + shape["edgeHeight"] / 2
    curve = 0.18 + (shape["curve"] / 100) * 0.28
    outer_control = left * curve
    inner_control = left * (1 - curve)
    f = lambda value: f"{value:.2f}".rstrip("0").rstrip(".")

    return " ".join(
        (
            f"M 0 {f(edge_top)}",
            f"C {f(outer_control)} {f(edge_top)}, {f(inner_control)} {f(center_top)}, {f(left)} {f(center_top)}",
            f"H {f(right)}",
            f"C {f(right + outer_control)} {f(center_top)}, {f(512 - outer_control)} {f(edge_top)}, 512 {f(edge_top)}",
            f"V {f(edge_bottom)}",
            f"C {f(512 - outer_control)} {f(edge_bottom)}, {f(right + outer_control)} {f(center_bottom)}, {f(right)} {f(center_bottom)}",
            f"H {f(left)}",
            f"C {f(inner_control)} {f(center_bottom)}, {f(outer_control)} {f(edge_bottom)}, 0 {f(edge_bottom)} Z",
        )
    )


def make_svg(shape: IconDesign) -> bytes:
    path = make_path(shape)
    fill = shape["fillColor"]
    gradient = ""
    if shape["fillMode"] == "gradient":
        angle = math.radians(int(shape["gradientAngle"]))
        dx = math.cos(angle) / 2
        dy = math.sin(angle) / 2
        x1, y1, x2, y2 = (0.5 - dx, 0.5 - dy, 0.5 + dx, 0.5 + dy)
        gradient = (
            f'<linearGradient id="mark-gradient" x1="{x1:.4f}" y1="{y1:.4f}" '
            f'x2="{x2:.4f}" y2="{y2:.4f}">'
            f'<stop offset="0" stop-color="{shape["gradientStart"]}"/>'
            f'<stop offset=".5" stop-color="{shape["gradientMiddle"]}"/>'
            f'<stop offset="1" stop-color="{shape["gradientEnd"]}"/>'
            "</linearGradient>"
        )
        fill = "url(#mark-gradient)"
    markup = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">'
        f'<defs><clipPath id="icon-bounds"><rect width="512" height="512" rx="{ICON_CORNER_RADIUS}"/></clipPath>{gradient}</defs>'
        '<g clip-path="url(#icon-bounds)">'
        f'<rect width="512" height="512" fill="{shape["backgroundColor"]}"/>'
        f'<path d="{path}" fill="{fill}"/>'
        "</g></svg>\n"
    )
    return markup.encode("utf-8")


def cubic_points(
    start: tuple[float, float],
    control1: tuple[float, float],
    control2: tuple[float, float],
    end: tuple[float, float],
    scale: int,
    steps: int = 36,
) -> list[tuple[int, int]]:
    points = []
    for index in range(1, steps + 1):
        t = index / steps
        inverse = 1 - t
        x = (
            inverse**3 * start[0]
            + 3 * inverse**2 * t * control1[0]
            + 3 * inverse * t**2 * control2[0]
            + t**3 * end[0]
        )
        y = (
            inverse**3 * start[1]
            + 3 * inverse**2 * t * control1[1]
            + 3 * inverse * t**2 * control2[1]
            + t**3 * end[1]
        )
        points.append((round(x * scale), round(y * scale)))
    return points


def color_tuple(color: str) -> tuple[int, int, int]:
    return tuple(int(color[offset : offset + 2], 16) for offset in (1, 3, 5))


def make_gradient(
    size: int,
    start_color: str,
    middle_color: str,
    end_color: str,
    angle: int,
) -> Image.Image:
    radians = math.radians(angle)
    dx = math.cos(radians)
    dy = math.sin(radians)
    center = (size - 1) / 2
    length = math.ceil((size - 1) * (abs(dx) + abs(dy)) + 2)
    colors = (color_tuple(start_color), color_tuple(middle_color), color_tuple(end_color))
    row = Image.new("RGB", (length, 1))
    pixels = []
    for index in range(length):
        position = index / max(length - 1, 1)
        segment = min(int(position * 2), 1)
        progress = position * 2 - segment
        pixels.append(
            tuple(
                round(first + (last - first) * progress)
                for first, last in zip(colors[segment], colors[segment + 1])
            )
        )
    row.putdata(pixels)
    source = row.resize((length, size), Image.Resampling.BICUBIC)
    offset = (length - 1) / 2 - dx * center - dy * center
    return source.transform(
        (size, size),
        Image.Transform.AFFINE,
        (dx, dy, offset, 0, 0, size / 2),
        resample=Image.Resampling.BICUBIC,
    )


def make_pngs(shape: IconDesign) -> dict[int, bytes]:
    scale = 4
    center = 256
    left = (512 - shape["centerWidth"]) / 2
    right = 512 - left
    center_top = center - shape["centerHeight"] / 2
    center_bottom = center + shape["centerHeight"] / 2
    edge_top = center - shape["edgeHeight"] / 2
    edge_bottom = center + shape["edgeHeight"] / 2
    curve = 0.18 + (shape["curve"] / 100) * 0.28
    outer_control = left * curve
    inner_control = left * (1 - curve)

    points = [(0, round(edge_top * scale))]
    points += cubic_points(
        (0, edge_top),
        (outer_control, edge_top),
        (inner_control, center_top),
        (left, center_top),
        scale,
    )
    points.append((round(right * scale), round(center_top * scale)))
    points += cubic_points(
        (right, center_top),
        (right + outer_control, center_top),
        (512 - outer_control, edge_top),
        (512, edge_top),
        scale,
    )
    points.append((512 * scale, round(edge_bottom * scale)))
    points += cubic_points(
        (512, edge_bottom),
        (512 - outer_control, edge_bottom),
        (right + outer_control, center_bottom),
        (right, center_bottom),
        scale,
    )
    points.append((round(left * scale), round(center_bottom * scale)))
    points += cubic_points(
        (left, center_bottom),
        (inner_control, center_bottom),
        (outer_control, edge_bottom),
        (0, edge_bottom),
        scale,
    )

    high_res = Image.new("L", (512 * scale, 512 * scale), 0)
    ImageDraw.Draw(high_res).polygon(points, fill=255)
    outer_mask_high = Image.new("L", (512 * scale, 512 * scale), 0)
    ImageDraw.Draw(outer_mask_high).rounded_rectangle(
        (0, 0, 512 * scale - 1, 512 * scale - 1),
        radius=ICON_CORNER_RADIUS * scale,
        fill=255,
    )
    images: dict[int, bytes] = {}
    for size in SIZES:
        mask = high_res.resize((size, size), Image.Resampling.LANCZOS)
        outer_mask = outer_mask_high.resize((size, size), Image.Resampling.LANCZOS)
        image = Image.new("RGBA", (size, size), color_tuple(str(shape["backgroundColor"])) + (255,))
        if shape["fillMode"] == "gradient":
            fill = make_gradient(
                size,
                str(shape["gradientStart"]),
                str(shape["gradientMiddle"]),
                str(shape["gradientEnd"]),
                int(shape["gradientAngle"]),
            )
        else:
            fill = Image.new("RGB", (size, size), color_tuple(str(shape["fillColor"])))
        image.paste(fill, (0, 0), mask)
        image.putalpha(outer_mask)
        output = io.BytesIO()
        image.save(output, format="PNG", optimize=True)
        images[size] = output.getvalue()
    return images


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
            temporary_path = temporary.name
            temporary.write(content)
            temporary.flush()
            os.fchmod(temporary.fileno(), 0o644)
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def apply_icon(shape: IconDesign) -> list[str]:
    svg = make_svg(shape)
    pngs = make_pngs(shape)
    writes = {
        ROOT / "ui/img/lumi-icon.svg": svg,
        ROOT / "ui/img/lumi-icon.png": pngs[512],
        ROOT / "build/icon.png": pngs[512],
    }
    for size, data in pngs.items():
        writes[ROOT / f"build/icons/{size}x{size}.png"] = data
        writes[ICON_THEME_ROOT / f"{size}x{size}/apps/lumi-desktop.png"] = data
    for path, content in writes.items():
        atomic_write(path, content)

    cache_tool = shutil.which("gtk-update-icon-cache")
    if not cache_tool:
        return ["gtk-update-icon-cache is unavailable; restart the desktop shell to refresh the launcher icon."]
    try:
        result = subprocess.run(
            [cache_tool, "--force", "--ignore-theme-index", str(ICON_THEME_ROOT)],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        return [f"Could not refresh the icon-theme cache: {error}"]
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit status {result.returncode}"
        return [f"Could not refresh the icon-theme cache: {detail}"]
    return []


class IconStudioHandler(BaseHTTPRequestHandler):
    server_version = "LumiIconStudio/1.0"

    def do_GET(self) -> None:
        if urlsplit(self.path).path not in ("/", "/index.html"):
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write((STUDIO_DIR / "index.html").read_bytes())

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/api/apply":
            self.send_error(404)
            return
        if self.headers.get("Host") not in (f"{HOST}:{PORT}", f"localhost:{PORT}"):
            self.send_error(403, "Invalid host")
            return
        if self.headers.get("Origin") not in (f"http://{HOST}:{PORT}", f"http://localhost:{PORT}"):
            self.send_error(403, "Invalid origin")
            return
        if self.headers.get_content_type() != "application/json":
            self.send_error(415, "Expected application/json")
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400, "Invalid content length")
            return
        if not 0 < content_length <= 2048:
            self.send_error(413, "Request body is too large or empty")
            return

        try:
            data = json.loads(self.rfile.read(content_length))
            shape = validate_shape(data)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
            self.send_json(400, {"error": str(error)})
            return

        try:
            warnings = apply_icon(shape)
        except OSError as error:
            self.send_json(500, {"error": f"Could not write icon assets: {error}"})
            return
        self.send_json(200, {"ok": True, "warnings": warnings})

    def send_json(self, status_code: int, data: dict[str, object]) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), IconStudioHandler)
    print(f"Lumi Icon Studio: http://{HOST}:{PORT}")
    print("Press Ctrl+C to stop the local server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nIcon Studio stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
