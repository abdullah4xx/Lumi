"""GNOME integration: apply a wallpaper through org.gnome.desktop.background."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

SCHEMA = "org.gnome.desktop.background"
SCREENSAVER_SCHEMA = "org.gnome.desktop.screensaver"
INTERFACE_SCHEMA = "org.gnome.desktop.interface"

GNOME_ACCENTS = ("blue", "teal", "green", "yellow", "orange", "red", "pink", "purple", "slate", "brown")


class ApplyError(Exception):
    pass


def _settings(schema_name: str = SCHEMA):
    from gi.repository import Gio

    source = Gio.SettingsSchemaSource.get_default()
    if source is None or source.lookup(schema_name, True) is None:
        raise ApplyError(f"Desktop settings schema not found: {schema_name}")
    return Gio.Settings.new(schema_name)


def set_gnome_accent_color(accent_name: str) -> bool:
    """Set the system-wide GNOME accent color (Ubuntu 22.04+ / GNOME 42+)."""
    from gi.repository import Gio

    if accent_name not in GNOME_ACCENTS:
        return False
    try:
        settings = _settings(INTERFACE_SCHEMA)
        if "accent-color" in settings.list_keys():
            settings.set_string("accent-color", accent_name)
            Gio.Settings.sync()
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def apply_wallpaper(path: Path, picture_options: str = "zoom", target: str = "both") -> None:
    """Set the wallpaper to ``path`` (desktop, lockscreen, or both)."""
    from gi.repository import Gio

    if not Path(path).is_file():
        raise ApplyError("The wallpaper file is missing.")
    uri = Gio.File.new_for_path(str(path)).get_uri()      # escapes spaces / unicode correctly

    # 1. Desktop background
    if target in ("both", "desktop"):
        settings = _settings(SCHEMA)
        keys = settings.list_keys()
        settings.set_string("picture-options", picture_options)
        settings.set_string("picture-uri", uri)
        if "picture-uri-dark" in keys:
            settings.set_string("picture-uri-dark", uri)
        Gio.Settings.sync()

    # 2. Lock screen / screensaver background
    if target in ("both", "lockscreen"):
        try:
            s_settings = _settings(SCREENSAVER_SCHEMA)
            s_keys = s_settings.list_keys()
            if "picture-options" in s_keys:
                s_settings.set_string("picture-options", picture_options)
            if "picture-uri" in s_keys:
                s_settings.set_string("picture-uri", uri)
            Gio.Settings.sync()
        except Exception:  # noqa: BLE001
            pass


def apply_day_night_wallpapers(day_path: Optional[Path], night_path: Optional[Path], picture_options: str = "zoom") -> None:
    """Set distinct light (day) and dark (night) wallpapers."""
    from gi.repository import Gio

    settings = _settings(SCHEMA)
    keys = settings.list_keys()
    settings.set_string("picture-options", picture_options)
    if day_path and Path(day_path).is_file():
        day_uri = Gio.File.new_for_path(str(day_path)).get_uri()
        settings.set_string("picture-uri", day_uri)
    if night_path and Path(night_path).is_file() and "picture-uri-dark" in keys:
        night_uri = Gio.File.new_for_path(str(night_path)).get_uri()
        settings.set_string("picture-uri-dark", night_uri)
    Gio.Settings.sync()


def current_wallpaper(prefer_dark: bool = False) -> Optional[Path]:
    from gi.repository import Gio

    try:
        settings = _settings()
        uri = ""
        if prefer_dark and "picture-uri-dark" in settings.list_keys():
            uri = settings.get_string("picture-uri-dark")
        uri = uri or settings.get_string("picture-uri")
    except ApplyError:
        return None
    if not uri:
        return None
    f = Gio.File.new_for_uri(uri)
    p = f.get_path()
    return Path(p) if p else None
