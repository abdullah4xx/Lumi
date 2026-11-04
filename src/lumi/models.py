"""Shared data types: wallpapers and the smart categories."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional, Tuple

CATEGORIES = [
    "Nature", "Anime", "Cyberpunk", "Minimalist", "Abstract",
    "Digital Art", "Sci-Fi", "Dark/AMOLED", "Space", "Architecture", "Games",
]

# Search phrase used to bias every source when a category is selected.
CATEGORY_QUERIES = {
    "Anime": "anime",
    "Nature": "nature landscape",
    "Cyberpunk": "cyberpunk neon city",
    "Minimalist": "minimalist",
    "Abstract": "abstract",
    "Digital Art": "digital art",
    "Sci-Fi": "sci-fi futuristic",
    "Dark/AMOLED": "dark amoled black",
    "Space": "space galaxy nebula",
    "Architecture": "architecture building",
    "Games": "video games game art",
}


@dataclass(frozen=True)
class Wallpaper:
    id: str
    source: str                      # Source.key
    url: str                         # full-resolution URL (see Source.resolve)
    thumb_url: str
    width: Optional[int] = None      # None = unknown until downloaded
    height: Optional[int] = None
    title: str = ""
    author: str = ""
    page_url: str = ""
    tags: Tuple[str, ...] = ()
    extra: Dict[str, str] = field(default_factory=dict, compare=False, hash=False)

    @property
    def uid(self) -> str:
        return f"{self.source}:{self.id}"

    @property
    def resolution(self) -> str:
        if self.width and self.height:
            return f"{self.width}\u00d7{self.height}"
        return "\u2014"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["tags"] = list(self.tags)
        return d

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Wallpaper":
        return Wallpaper(
            id=str(d["id"]), source=str(d["source"]), url=str(d["url"]),
            thumb_url=str(d.get("thumb_url", "")),
            width=d.get("width"), height=d.get("height"),
            title=str(d.get("title", "")), author=str(d.get("author", "")),
            page_url=str(d.get("page_url", "")),
            tags=tuple(str(t) for t in d.get("tags", ())),
            extra={str(k): str(v) for k, v in (d.get("extra") or {}).items()},
        )
