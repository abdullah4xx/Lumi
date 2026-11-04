"""GitHub release check: tells the user when a newer .deb has been published."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Tuple

from . import REPO, __version__

_VER = re.compile(r"(\d+(?:\.\d+)*)(?:[-+.]?build\.?(\d+))?")


def parse_version(text: str) -> Tuple[Tuple[int, ...], int]:
    """'v1.2.3' -> ((1,2,3), 0);  '1.2.3+build7' / 'v1.2.3-build7' -> ((1,2,3), 7)."""
    m = _VER.search(text or "")
    if not m:
        return (0,), 0
    return tuple(int(x) for x in m.group(1).split(".")), int(m.group(2) or 0)


def is_newer(candidate: str, current: str = __version__) -> bool:
    a, b = parse_version(candidate), parse_version(current)
    base_a = a[0] + (0,) * (len(b[0]) - len(a[0]))
    base_b = b[0] + (0,) * (len(a[0]) - len(b[0]))
    return (base_a, a[1]) > (base_b, b[1])


@dataclass
class Release:
    tag: str
    page_url: str
    deb_url: str


async def latest_release(http, repo: str = REPO) -> Optional[Release]:
    """Newest published release, or None when the repo has none yet. Raises HttpError on network problems."""
    data = await http.get_json(f"https://api.github.com/repos/{repo}/releases/latest",
                               headers={"Accept": "application/vnd.github+json"})
    tag = str(data.get("tag_name") or "")
    if not tag:
        return None
    deb = next((a.get("browser_download_url", "") for a in data.get("assets", [])
                if str(a.get("name", "")).endswith(".deb")), "")
    return Release(tag, str(data.get("html_url") or f"https://github.com/{repo}/releases"), deb)


async def check(http, repo: str = REPO) -> Optional[Release]:
    """The newer release if there is one, else None."""
    rel = await latest_release(http, repo)
    return rel if rel and is_newer(rel.tag) else None
