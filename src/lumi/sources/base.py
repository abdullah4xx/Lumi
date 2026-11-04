"""Source plugin base class, request context and small parsing helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from ..models import Wallpaper

KIND_API = "api"                 # documented public API
KIND_KEY = "key"                 # documented API that needs the user's own key
KIND_EXPERIMENTAL = "experimental"   # scraping / unofficial endpoints; may break


@dataclass
class Context:
    http: Any                    # lumi.http.Http (or a test double)
    cfg: Dict[str, Any]          # Config.snapshot()

    def key(self, name: str) -> str:
        return (self.cfg.get("api_keys") or {}).get(name, "")

    @property
    def min_long(self) -> int:
        return int(self.cfg.get("min_long_side", 3840))

    def meets_min(self, w: Optional[int], h: Optional[int]) -> bool:
        """Unknown size passes (checked after download); known size must be 4K-class."""
        if not w or not h:
            return True
        if self.cfg.get("landscape_only", True) and w < h:
            return False
        return max(w, h) >= self.min_long


class Source:
    key = ""
    name = ""
    kind = KIND_API
    description = ""
    homepage = ""
    key_name: Optional[str] = None     # entry in Config api_keys
    key_required = False
    required_keys: Tuple[str, ...] = ()
    hosts: Tuple[str, ...] = ()        # image hosts we allow (suffix match)
    default_enabled = True
    supports_query = True
    min_interval = 0.0                 # seconds between requests

    async def search(self, ctx: Context, query: str, page: int, category: Optional[str]) -> List[Wallpaper]:
        raise NotImplementedError

    async def resolve(self, ctx: Context, wp: Wallpaper) -> str:
        """Return the real full-resolution URL (default: wp.url)."""
        return wp.url

    async def on_use(self, ctx: Context, wp: Wallpaper) -> None:
        """Called when a wallpaper is applied/downloaded (e.g. Unsplash download tracking)."""

    def host_ok(self, url: str) -> bool:
        parsed = urlparse(url or "")
        host = (parsed.hostname or "").lower()
        return parsed.scheme == "https" and any(host == h or host.endswith("." + h) for h in self.hosts)


# ----------------------------------------------------------------- helpers
def to_int(value: Any) -> Optional[int]:
    try:
        n = int(float(value))
        return n if n > 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    return unescape(_TAG_RE.sub("", text or "")).strip()


def clip(text: Any, n: int = 120) -> str:
    s = str(text or "").strip()
    return s if len(s) <= n else s[: n - 1] + "\u2026"


def ext_is_image(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith((".jpg", ".jpeg", ".png", ".webp"))
