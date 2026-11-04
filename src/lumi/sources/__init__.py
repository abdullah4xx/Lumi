"""Source registry. Importing this package registers every source."""

from __future__ import annotations

from typing import Dict, List

from .apis import (AlphaCoders, ArtStation, Bing, Danbooru, Desktoppr, DeviantArt, EarthView, Flickr, NasaApod,
                   NasaLibrary, Pexels, Picsum, Pixabay, Reddit, Unsplash, Wallhaven, Wikimedia)
from .base import KIND_API, KIND_EXPERIMENTAL, KIND_KEY, Context, Source
from .scrapers import (FourKWallpapers, GelbooruHtml, HDWallpapers, KonachanHtml, SafebooruHtml, SimpleDesktops,
                       WallpaperFlare, WallpapersCraft, WallpapersWide, WallhavenHtml, YandeHtml)
from .official import (AniList, ArtInstitute, FanartTV, Kitsu, MetMuseum, Openverse, Rijksmuseum, Tmdb)
from .universal import CustomUrlSource

# Numbers follow the original brief. InterfaceLift (#16 in its list) is not
# included: its downloads need a per-session token and cannot be automated.
_CLASSES = [
    Wallhaven, WallhavenHtml, KonachanHtml, YandeHtml, SafebooruHtml, GelbooruHtml, Danbooru, Picsum, Unsplash, Pexels, Pixabay, Reddit, Wikimedia, Bing, NasaApod, ArtStation, DeviantArt,
    AlphaCoders, FourKWallpapers, HDWallpapers, WallpapersCraft, WallpaperFlare, SimpleDesktops, Desktoppr,
    WallpapersWide, EarthView, Flickr, NasaLibrary,
    MetMuseum, ArtInstitute, Rijksmuseum, Openverse, Tmdb, AniList, Kitsu, FanartTV,
]

_VERIFIED_WEBSITE_SCRAPER_KEYS = {
    "wallhaven_web", "konachan_web", "yande_web", "safebooru_web", "gelbooru_web",
}


def build_registry() -> Dict[str, Source]:
    """Fresh instances (some sources keep pagination state)."""
    sources = {cls.key: cls() for cls in _CLASSES}
    for key, source in sources.items():
        if source.kind == KIND_EXPERIMENTAL:
            source.default_enabled = key in _VERIFIED_WEBSITE_SCRAPER_KEYS
    return sources


def source_keys() -> List[str]:
    return [cls.key for cls in _CLASSES]


__all__ = ["Context", "Source", "CustomUrlSource", "build_registry", "source_keys", "KIND_API", "KIND_KEY", "KIND_EXPERIMENTAL"]
