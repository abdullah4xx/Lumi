"""Local wallpaper importer and directory scanner/watcher."""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

from PIL import Image

from .config import THUMB_DIR, Config
from .models import Wallpaper

logger = logging.getLogger("lumi.local")

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".avif", ".jxl"}


def is_image_file(path: Path) -> bool:
    if path.suffix.lower() in SUPPORTED_EXTENSIONS:
        return True
    mime, _ = mimetypes.guess_type(str(path))
    return bool(mime and mime.startswith("image/"))


def make_local_thumb(image_path: Path, thumb_dir: Path = THUMB_DIR, size: tuple = (480, 270)) -> Optional[Path]:
    """Generate or retrieve a cached thumbnail for a local image file."""
    try:
        thumb_dir.mkdir(parents=True, exist_ok=True)
        h = hashlib.sha1(str(image_path.resolve()).encode("utf-8")).hexdigest()[:16]
        thumb_path = thumb_dir / f"local_{h}_{image_path.stem[:30]}.jpg"
        if thumb_path.exists() and thumb_path.stat().st_mtime >= image_path.stat().st_mtime:
            return thumb_path

        with Image.open(image_path) as im:
            try:
                im.draft("RGB", (size[0] * 2, size[1] * 2))      # JPEG: decode at reduced size (4K files open ~10x faster)
            except Exception:
                pass
            im = im.convert("RGB")
            im.thumbnail(size, Image.Resampling.LANCZOS)
            thumb_path_tmp = thumb_path.with_suffix(".tmp")
            im.save(thumb_path_tmp, format="JPEG", quality=85)
            thumb_path_tmp.replace(thumb_path)
            return thumb_path
    except Exception as exc:
        logger.debug("Failed to create thumb for %s: %s", image_path, exc)
        return None


def inspect_local_image(path: Path) -> Optional[Wallpaper]:
    """Inspect local image file and create a Wallpaper model."""
    try:
        path = Path(path).resolve()
        if not path.is_file() or not is_image_file(path):
            return None

        width, height = None, None
        try:
            with Image.open(path) as im:
                width, height = im.size
        except Exception:
            pass

        file_id = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:12]
        thumb = make_local_thumb(path)
        thumb_url = str(thumb) if thumb else str(path)

        title = re.sub(r"[_-][0-9a-f]{8}$", "", path.stem).replace("_", " ").replace("-", " ").title()   # drop the download hash
        return Wallpaper(
            id=file_id,
            source="local",
            url=str(path),
            thumb_url=thumb_url,
            width=width,
            height=height,
            title=title,
            author="Local File",
            page_url=str(path.parent),
            tags=("local", "imported"),
            extra={"path": str(path), "size": f"{path.stat().st_size}"},
        )
    except Exception as exc:
        logger.warning("Error inspecting local image %s: %s", path, exc)
        return None


class LocalManager:
    """Manages imported local wallpapers and watched directories."""

    def __init__(self, config: Config):
        self.config = config
        self._watchers: List[Any] = []
        self._on_change_callbacks: List[Callable[[], None]] = []

    def scan_folders(self, folders: Optional[List[str]] = None) -> List[Wallpaper]:
        """Scan configured local folders and return discovered wallpapers."""
        if folders is None:
            folders = self.config.get("local_folders") or []

        single_folder = self.config.get("local_folder")
        if single_folder and single_folder not in folders:
            folders.append(single_folder)

        results: List[Wallpaper] = []
        seen_paths: Set[str] = set()

        # 1. Directly imported images from config
        imported = self.config.get("local_imported_wallpapers") or []
        for d in imported:
            if isinstance(d, dict) and "path" in d:
                p = Path(d["path"])
                if p.is_file() and str(p) not in seen_paths:
                    wp = inspect_local_image(p)
                    if wp:
                        seen_paths.add(str(p))
                        results.append(wp)

        # 2. Files inside watched directories
        for folder_str in folders:
            try:
                folder = Path(folder_str).expanduser().resolve()
                if not folder.is_dir():
                    continue
                for item in folder.iterdir():
                    if item.is_file() and is_image_file(item) and str(item) not in seen_paths:
                        wp = inspect_local_image(item)
                        if wp:
                            seen_paths.add(str(item))
                            results.append(wp)
            except Exception as exc:
                logger.warning("Failed scanning folder %s: %s", folder_str, exc)

        return results

    def import_files(self, file_paths: List[Path]) -> List[Wallpaper]:
        """Import specific image files and save them to config."""
        imported_entries = list(self.config.get("local_imported_wallpapers") or [])
        known_paths = {e.get("path") for e in imported_entries if isinstance(e, dict)}

        new_wallpapers = []
        for p in file_paths:
            path = Path(p).resolve()
            if path.is_file() and is_image_file(path):
                wp = inspect_local_image(path)
                if wp:
                    new_wallpapers.append(wp)
                    if str(path) not in known_paths:
                        imported_entries.append({"path": str(path), "id": wp.id, "title": wp.title})
                        known_paths.add(str(path))

        self.config.set("local_imported_wallpapers", imported_entries)
        return new_wallpapers

    def remove_imported(self, path_str: str) -> None:
        """Remove a file from the imported list."""
        imported_entries = [e for e in (self.config.get("local_imported_wallpapers") or [])
                            if isinstance(e, dict) and e.get("path") != path_str]
        self.config.set("local_imported_wallpapers", imported_entries)

    def add_folder(self, folder_path: str) -> bool:
        """Add a directory to watched local folders."""
        folders = list(self.config.get("local_folders") or [])
        resolved = str(Path(folder_path).expanduser().resolve())
        if resolved not in folders and Path(resolved).is_dir():
            folders.append(resolved)
            self.config.set("local_folders", folders)
            return True
        return False

    def remove_folder(self, folder_path: str) -> bool:
        """Remove a directory from watched local folders."""
        folders = list(self.config.get("local_folders") or [])
        resolved = str(Path(folder_path).expanduser().resolve())
        if resolved in folders:
            folders.remove(resolved)
            self.config.set("local_folders", folders)
            return True
        return False
