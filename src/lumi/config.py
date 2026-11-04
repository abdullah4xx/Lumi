"""Paths and persistent user configuration (~/.config/lumi/config.json)."""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger("lumi.config")


def _xdg(env: str, default: str) -> Path:
    return Path(os.environ.get(env) or Path.home() / default)


def _app_dir(env: str, default: str) -> Path:
    parent = _xdg(env, default)
    legacy = parent / "vapourwall"
    current = parent / "lumi"
    if legacy.exists() and not current.exists():
        try:
            legacy.rename(current)
            logger.info("Migrated %s to %s", legacy, current)
        except OSError as exc:
            logger.warning("Could not migrate %s to %s: %s", legacy, current, exc)
            return legacy
    return current


CONFIG_DIR = _app_dir("XDG_CONFIG_HOME", ".config")
CACHE_DIR = _app_dir("XDG_CACHE_HOME", ".cache")
DATA_DIR = _app_dir("XDG_DATA_HOME", ".local/share")
CONFIG_PATH = CONFIG_DIR / "config.json"
LEGACY_CONFIG_PATH = _xdg("XDG_CONFIG_HOME", ".config") / "vapourwall" / "config.json"
THUMB_DIR = CACHE_DIR / "thumbs"
WALLPAPER_DIR = DATA_DIR / "wallpapers"

THEMES = ["dark", "system", "light"]
PICTURE_OPTIONS = ["zoom", "scaled", "stretched", "centered", "spanned", "wallpaper"]
AI_BACKENDS = ["auto", "clip", "heuristic", "gemini"]
LANGUAGES = ["ar", "en", "system"]
APPLY_TARGETS = ["both", "desktop", "lockscreen"]
RENDER_PIXEL_BUDGETS = (4_000_000, 8_000_000, 12_000_000)
_GEMINI_MODEL_RE = re.compile(r"^gemini-[A-Za-z0-9._-]{1,93}$")

DEFAULT_REDDIT_SUBS = [
    "wallpapers", "WallpaperEngine", "Ultrawidewallpapers", "Animewallpaper", "EarthPorn",
]

API_KEY_NAMES = [
    "wallhaven", "unsplash", "pexels", "pixabay", "alphacoders", "flickr", "nasa",
    "rijksmuseum", "tmdb", "fanart", "openverse_id", "openverse_secret", "gemini",
]
SOURCE_CATALOG_VERSION = 4
NEW_OFFICIAL_SOURCE_KEYS = (
    "met", "artic", "rijksmuseum", "openverse", "tmdb", "anilist", "kitsu", "fanart",
)
NEW_VERIFIED_SCRAPER_KEYS = (
    "wallhaven_web", "konachan_web", "yande_web", "safebooru_web", "gelbooru_web",
)
NEW_DEFAULT_API_SOURCE_KEYS = ("danbooru",)

DEFAULTS: Dict[str, Any] = {
    "theme": "light",
    "ui_style": 2,
    "language": "ar",
    "adaptive_colors": True,
    "sync_gnome_accent": True,
    "apply_target": "both",
    "picture_options": "zoom",
    "safe_search": True,
    "landscape_only": True,
    "min_long_side": 3840,
    "verified_only": False,
    "strict_ai_filter": False,
    "filter_real_humans": True,
    "filter_non_islamic_religions": True,
    "ai_backend": "auto",
    "gemini_model": "gemini-3.5-flash",
    "render_pixel_budget": 8_000_000,
    "enabled_sources": None,          # None = every source's own default
    "reddit_subs": DEFAULT_REDDIT_SUBS,
    "api_keys": {name: "" for name in API_KEY_NAMES},
    "blocked_domains": [],
    "dismissed_ids": [],
    "auto_change_enabled": False,
    "auto_change_interval": 3600,
    "auto_change_source": "favorites",
    "day_night_dual": False,
    "day_wallpaper": "",
    "night_wallpaper": "",
    "local_folder": "",
    "local_folders": [],
    "local_imported_wallpapers": [],
    "custom_urls": [],
    "web_companion_enabled": False,
    "web_companion_port": 5910,
    "battery_saver_enabled": False,
    "dock_blur_enabled": False,
    "history": [],
}


class Config:
    """Thread-safe JSON-backed settings."""

    def __init__(self, path: Path = CONFIG_PATH):
        self.path = path
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = copy.deepcopy(DEFAULTS)
        self.load()

    # ------------------------------------------------------------ io
    def load(self) -> None:
        with self._lock:
            data = copy.deepcopy(DEFAULTS)
            migrate_sources = False
            try:
                config_path = self.path
                if not config_path.exists() and self.path == CONFIG_PATH:
                    config_path = LEGACY_CONFIG_PATH
                if config_path.exists():
                    loaded = json.loads(config_path.read_text())
                    if isinstance(loaded, dict):
                        catalog_version = loaded.get("source_catalog_version", 0)
                        migrate_sources = not isinstance(catalog_version, int) or catalog_version < SOURCE_CATALOG_VERSION
                        for k, v in loaded.items():
                            if k in DEFAULTS:
                                data[k] = v
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Could not read config, using defaults: %s", exc)
            if migrate_sources:
                enabled = data.get("enabled_sources")
                if isinstance(enabled, list):
                    data["enabled_sources"] = list(dict.fromkeys([
                        *enabled, *NEW_OFFICIAL_SOURCE_KEYS, *NEW_VERIFIED_SCRAPER_KEYS,
                        *NEW_DEFAULT_API_SOURCE_KEYS,
                    ]))
                data["source_catalog_version"] = SOURCE_CATALOG_VERSION
            self._data = self._validated(data)

    def save(self) -> None:
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".config-")
                try:
                    with os.fdopen(fd, "w") as fh:
                        json.dump(self._data, fh, indent=2)
                    os.chmod(tmp, 0o600)              # holds API keys
                    os.replace(tmp, self.path)
                except BaseException:
                    try:
                        os.unlink(tmp)
                    except OSError:
                        pass
                    raise
            except (OSError, TypeError, ValueError) as exc:
                logger.warning("Could not save config: %s", exc)

    @staticmethod
    def _validated(d: Dict[str, Any]) -> Dict[str, Any]:
        if d.get("ui_style") != 2:               # 1.5.0: new light 'Noteefy' look
            d["theme"] = "light"
            d["ui_style"] = 2
        if d.get("theme") not in THEMES:
            d["theme"] = DEFAULTS["theme"]
        if d.get("language") not in LANGUAGES:
            d["language"] = DEFAULTS["language"]
        if d.get("picture_options") not in PICTURE_OPTIONS:
            d["picture_options"] = "zoom"
        if d.get("apply_target") not in APPLY_TARGETS:
            d["apply_target"] = "both"
        if d.get("ai_backend") not in AI_BACKENDS:
            d["ai_backend"] = "auto"
        if not isinstance(d.get("gemini_model"), str) or not _GEMINI_MODEL_RE.fullmatch(d["gemini_model"]):
            d["gemini_model"] = DEFAULTS["gemini_model"]
        if d.get("render_pixel_budget") not in RENDER_PIXEL_BUDGETS:
            d["render_pixel_budget"] = DEFAULTS["render_pixel_budget"]
        for k in ("adaptive_colors", "safe_search", "landscape_only", "verified_only",
                  "strict_ai_filter", "sync_gnome_accent", "filter_real_humans",
                  "filter_non_islamic_religions", "auto_change_enabled", "day_night_dual",
                  "battery_saver_enabled", "dock_blur_enabled", "web_companion_enabled"):
            if not isinstance(d.get(k), bool):
                d[k] = DEFAULTS.get(k, False)
        try:
            d["min_long_side"] = max(1280, min(7680, int(d.get("min_long_side", 3840))))
        except (TypeError, ValueError, OverflowError):
            d["min_long_side"] = 3840
        try:
            d["auto_change_interval"] = max(60, min(604800, int(d.get("auto_change_interval", 3600))))
        except (TypeError, ValueError, OverflowError):
            d["auto_change_interval"] = 3600
        if not isinstance(d.get("auto_change_source"), str) or d["auto_change_source"] == "Islamic Art":
            d["auto_change_source"] = "favorites"
        if not isinstance(d.get("day_wallpaper"), str):
            d["day_wallpaper"] = ""
        if not isinstance(d.get("night_wallpaper"), str):
            d["night_wallpaper"] = ""
        if not isinstance(d.get("local_folder"), str):
            d["local_folder"] = ""
        if not isinstance(d.get("blocked_domains"), list):
            d["blocked_domains"] = []
        else:
            d["blocked_domains"] = [str(x).strip().lower() for x in d["blocked_domains"] if str(x).strip()]
        if not isinstance(d.get("dismissed_ids"), list):
            d["dismissed_ids"] = []
        else:
            d["dismissed_ids"] = [str(x).strip() for x in d["dismissed_ids"] if str(x).strip()][:500]
        if not isinstance(d.get("history"), list):
            d["history"] = []
        else:
            d["history"] = d["history"][:50]
        if d.get("enabled_sources") is not None and not isinstance(d["enabled_sources"], list):
            d["enabled_sources"] = None
        subs = d.get("reddit_subs")
        if not isinstance(subs, list) or not all(isinstance(s, str) and s.replace("_", "").isalnum() for s in subs) or not subs:
            d["reddit_subs"] = list(DEFAULT_REDDIT_SUBS)
        keys = d.get("api_keys") if isinstance(d.get("api_keys"), dict) else {}
        d["api_keys"] = {n: (keys.get(n) if isinstance(keys.get(n), str) else "").strip() for n in API_KEY_NAMES}
        if d.get("enabled_sources") is not None:
            d["enabled_sources"] = [k for k in d["enabled_sources"] if isinstance(k, str)]
        for key in ("local_folders", "local_imported_wallpapers", "custom_urls"):
            if not isinstance(d.get(key), list):
                d[key] = copy.deepcopy(DEFAULTS[key])
        return d

    # ------------------------------------------------------------ access
    def get(self, key: str) -> Any:
        with self._lock:
            return copy.deepcopy(self._data[key])

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value
            self._data = self._validated(self._data)
        self.save()

    def api_key(self, name: str) -> str:
        with self._lock:
            return self._data["api_keys"].get(name, "")

    def set_api_key(self, name: str, value: str) -> None:
        with self._lock:
            self._data["api_keys"][name] = value.strip()
        self.save()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._data)

    def source_enabled(self, key: str, default: bool) -> bool:
        with self._lock:
            enabled: List[str] | None = self._data["enabled_sources"]
        return default if enabled is None else key in enabled

    def set_source_enabled(self, key: str, on: bool, all_keys_default: Dict[str, bool]) -> None:
        with self._lock:
            enabled = self._data["enabled_sources"]
            if enabled is None:
                enabled = [k for k, d in all_keys_default.items() if d]
            enabled = [k for k in enabled if k != key]
            if on:
                enabled.append(key)
            self._data["enabled_sources"] = enabled
        self.save()

    def is_blocked_url(self, url: str) -> bool:
        if not url:
            return False
        u = url.lower()
        with self._lock:
            blocked = self._data.get("blocked_domains", [])
        for b in blocked:
            if b and b in u:
                return True
        return False

    def is_dismissed(self, uid: str) -> bool:
        with self._lock:
            return uid in self._data.get("dismissed_ids", [])

    def dismiss_id(self, uid: str) -> None:
        with self._lock:
            curr = list(self._data.get("dismissed_ids", []))
            if uid not in curr:
                curr.append(uid)
                self._data["dismissed_ids"] = curr[-500:]
        self.save()

    def add_custom_url(self, url: str) -> None:
        u = url.strip()
        if not u:
            return
        with self._lock:
            urls = list(self._data.get("custom_urls", []))
            if u not in urls:
                urls.append(u)
                self._data["custom_urls"] = urls
        self.save()

    def remove_custom_url(self, url: str) -> None:
        with self._lock:
            urls = [u for u in self._data.get("custom_urls", []) if u != url]
            self._data["custom_urls"] = urls
        self.save()

    def add_history_entry(self, item: Dict[str, Any]) -> None:
        with self._lock:
            hist = list(self._data.get("history", []))
            # Remove any duplicate uid first
            uid = item.get("uid")
            hist = [h for h in hist if h.get("uid") != uid]
            hist.insert(0, item)
            self._data["history"] = hist[:30]
        self.save()


def saved_dir() -> Path:
    """Where the Save button copies wallpapers: <Pictures>/Lumi (honours a localised Pictures folder)."""
    pictures = None
    try:
        for line in (Path.home() / ".config" / "user-dirs.dirs").read_text(encoding="utf-8").splitlines():
            if line.startswith("XDG_PICTURES_DIR="):
                pictures = line.split("=", 1)[1].strip().strip('"').replace("$HOME", str(Path.home()))
                break
    except OSError:
        pass
    return Path(pictures or Path.home() / "Pictures") / "Lumi"
