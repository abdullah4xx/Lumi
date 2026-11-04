"""Aggregator engine: fans a search out to every enabled source, then downloads."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import random
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set
from urllib.parse import urlparse

from PIL import Image, ImageOps

from .classifier import matches_content_filter
from .config import THUMB_DIR, WALLPAPER_DIR, Config, saved_dir
from .http import Http, HttpError
from .imaging import EXT_FOR_FORMAT, validate_image
from .models import CATEGORY_QUERIES, Wallpaper
from .query import translate_query
from .sources import Context, CustomUrlSource, Source, build_registry
from .sources.base import ext_is_image
from .sources.plugins import CustomScraperRegistry, PluginError, PluginSource
from .sources.universal import UniversalWebScraper

logger = logging.getLogger("lumi.engine")

MAX_FULL_BYTES = 120 * 1024 * 1024
MAX_THUMB_BYTES = 8 * 1024 * 1024
THUMB_SIZE = (900, 900)
THUMB_QUALITY = 82
MAX_PREVIEW_BYTES = 30 * 1024 * 1024
MAX_PREVIEW_CACHE_BYTES = 256 * 1024 * 1024
SOURCE_TIMEOUT = 30


@dataclass
class Status:
    state: str           # "ok" | "error" | "skipped"
    count: int = 0
    message: str = ""


@dataclass
class FullImage:
    path: Path
    width: int
    height: int


def _short(exc: Exception) -> str:
    return (str(exc) or exc.__class__.__name__)[:120]


def _safe_name(text: str) -> str:
    """Filesystem-safe and collision-free: a short hash of the raw text keeps 'a/b' and 'a_b' apart."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", text)[:60].strip(".") or "image"
    return f"{safe}_{hashlib.sha1(text.encode()).hexdigest()[:8]}"


def _tmp_path(dest: Path) -> Path:
    """Unique temp name so two simultaneous downloads of one image never write the same file."""
    return dest.with_name(f"{dest.stem}.{uuid.uuid4().hex[:8]}.part")


def _write_thumbnail(source: Path, destination: Path) -> None:
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image)
        image.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        image.save(destination, format="WEBP", quality=THUMB_QUALITY, method=5)


MAX_WALLPAPER_CACHE = 1024 * 1024 * 1024       # 1 GB of downloaded full-size images


def prune_downloads(keep: Optional[Path] = None, max_bytes: int = MAX_WALLPAPER_CACHE, clear_all: bool = False) -> int:
    """Delete stale .part files and old full-size images (oldest first) beyond ``max_bytes``.
    The file in ``keep`` (the wallpaper GNOME is using right now) is never removed. Returns bytes freed."""
    freed = 0
    if not WALLPAPER_DIR.exists():
        return 0
    files = []
    for p in WALLPAPER_DIR.iterdir():
        try:
            if not p.is_file():
                continue
            st = p.stat()
        except OSError:
            continue
        if p.suffix == ".part":
            if clear_all or time.time() - st.st_mtime > 3600:
                try:
                    p.unlink()
                    freed += st.st_size
                except OSError:
                    pass
            continue
        if keep is not None and p.resolve() == Path(keep).resolve():
            continue
        files.append((st.st_mtime, st.st_size, p))
    total = sum(f[1] for f in files)
    for _mtime, size, p in sorted(files):
        if not clear_all and total <= max_bytes:
            break
        try:
            p.unlink()
            total -= size
            freed += size
        except OSError:
            pass
    return freed


class Engine:
    def __init__(self, config: Config, http: Optional[Http] = None):
        self.config = config
        self.http = http or Http()
        self.sources: Dict[str, Source] = build_registry()
        self.sources["custom_url"] = CustomUrlSource()
        self._custom_scrapers = CustomScraperRegistry()
        self.reload_custom_scrapers()
        self._inflight: Dict[str, "asyncio.Future"] = {}      # one download per wallpaper, however many callers

    # ------------------------------------------------------------ helpers
    def reload_custom_scrapers(self) -> None:
        for key in [
            key for key, source in self.sources.items()
            if isinstance(source, PluginSource)
        ]:
            self.sources.pop(key, None)
        for key, source in self._custom_scrapers.load_all().items():
            if key in self.sources:
                logger.warning("Ignoring scraper plugin with a reserved source id: %s", key)
                continue
            self.sources[key] = source

    def install_scraper_plugin(self, filename: str, content: bytes) -> PluginSource:
        source = self._custom_scrapers.install(filename, content)
        if source.key in self.sources and not isinstance(self.sources[source.key], PluginSource):
            self._custom_scrapers.remove(source.key)
            raise PluginError("That scraper ID is already used by a built-in source.")
        self.reload_custom_scrapers()
        source = self.sources[source.key]
        self.config.set_source_enabled(source.key, True, self.default_map())
        return source

    def remove_scraper_plugin(self, key: str) -> bool:
        source = self.sources.get(key)
        if not isinstance(source, PluginSource):
            return False
        removed = self._custom_scrapers.remove(key)
        if removed:
            self.reload_custom_scrapers()
            self.config.set_source_enabled(key, False, self.default_map())
        return removed

    def default_map(self) -> Dict[str, bool]:
        return {k: s.default_enabled and not getattr(s, "manual_only", False) for k, s in self.sources.items()}

    def enabled_keys(self) -> List[str]:
        return [
            k for k, s in self.sources.items()
            if not getattr(s, "manual_only", False) and self.config.source_enabled(k, s.default_enabled)
        ]

    def effective_query(self, query: str, category: Optional[str]) -> str:
        query = translate_query(query)                # the sources are English-only: "بحر" -> "sea"
        if query:
            return query
        return CATEGORY_QUERIES.get(category or "", "")

    def _context(self) -> Context:
        return Context(http=self.http, cfg=self.config.snapshot())

    def _acceptable(self, src: Source, wp: Wallpaper, ctx: Context) -> bool:
        if not src.host_ok(wp.url) or (wp.thumb_url and not src.host_ok(wp.thumb_url)):
            return False
        if ctx.cfg.get("verified_only") and (not (wp.width and wp.height) or wp.extra.get("size") == "assumed"):
            return False
        # Blocked domains check
        blocked = ctx.cfg.get("blocked_domains") or []
        for b in blocked:
            if b:
                b_low = b.lower()
                if (b_low in (wp.url or "").lower() or
                    b_low in (wp.thumb_url or "").lower() or
                    b_low in (wp.page_url or "").lower()):
                    return False
        # Dismissed wallpapers check
        dismissed = ctx.cfg.get("dismissed_ids") or []
        if wp.uid in dismissed:
            return False
        # Content filters (real humans & non-Islamic religious symbols)
        f_humans = bool(ctx.cfg.get("filter_real_humans", False))
        f_religions = bool(ctx.cfg.get("filter_non_islamic_religions", False))
        if f_humans or f_religions:
            hint = f"{wp.title} {' '.join(wp.tags)}"
            if matches_content_filter(hint, f_humans, f_religions):
                return False
        return ctx.meets_min(wp.width, wp.height)

    # ------------------------------------------------------------ search
    async def search(self, query: str, category: Optional[str], page: int, keys: List[str],
                     seen: Set[str], on_batch: Callable[[str, List[Wallpaper]], None]) -> Dict[str, Status]:
        """Query ``keys`` concurrently. ``on_batch(source, wallpapers)`` fires as each source answers."""
        ctx = self._context()
        text = self.effective_query(query, category)
        statuses: Dict[str, Status] = {}

        async def run(key: str) -> None:
            src = self.sources[key]
            required_keys = src.required_keys or ((src.key_name,) if src.key_required and src.key_name else ())
            if any(not ctx.key(name) for name in required_keys):
                statuses[key] = Status("skipped", message="needs an API key")
                return
            if query and not src.supports_query:
                # This source cannot filter free-text searches; category browsing can still use
                # its general feed.
                statuses[key] = Status("skipped", message="no search support")
                return
            source_query = text if src.supports_query else ""
            try:
                found = await asyncio.wait_for(src.search(ctx, source_query, page, category), SOURCE_TIMEOUT)
            except asyncio.TimeoutError:
                statuses[key] = Status("error", message="timed out")
                return
            except Exception as exc:  # noqa: BLE001 - one broken source must never break the rest
                logger.info("%s failed: %s", key, exc)
                statuses[key] = Status("error", message=_short(exc))
                return
            fresh = []
            for wp in found:
                marker = f"{wp.uid}|{wp.url}"
                if marker in seen or not self._acceptable(src, wp, ctx):
                    continue
                seen.add(marker)
                fresh.append(wp)
            # Sources answer at very different speeds, so without this the fast ones (their whole
            # batch arriving first) dominate the top of the grid every time and the slower ones
            # only ever show up at the bottom. Shuffling each source's own batch, combined with the
            # randomized starting page above, is what actually produces a mixed, varied-looking feed
            # instead of long runs of a single source.
            random.shuffle(fresh)
            statuses[key] = Status("ok", count=len(fresh))
            if fresh:
                on_batch(key, fresh)

        await asyncio.gather(*(run(k) for k in keys if k in self.sources))
        return statuses

    # ------------------------------------------------------------ downloads
    async def fetch_thumb(self, wp: Wallpaper) -> Optional[Path]:
        is_local = wp.source == "local"
        src = self.sources.get(wp.source)
        if is_local:
            original = Path(wp.thumb_url or wp.url)
            if not original.is_file():
                return None
            try:
                stat = original.stat()
            except OSError:
                return None
            identity = f"{wp.uid}|{original.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
        else:
            if src is None or not wp.thumb_url or not src.host_ok(wp.thumb_url):
                return None
            original = None
            identity = f"{wp.uid}|{wp.thumb_url}"
        THUMB_DIR.mkdir(parents=True, exist_ok=True)
        dest = THUMB_DIR / ("thumb_v2_" + hashlib.sha1(identity.encode()).hexdigest() + ".webp")
        if dest.exists() and dest.stat().st_size > 0:
            return dest
        downloaded = None
        tmp = _tmp_path(dest)
        try:
            if not is_local:
                downloaded = _tmp_path(dest)
                if src.min_interval:
                    await self.http.throttle(src.key, src.min_interval)
                await self.http.download(wp.thumb_url, downloaded, MAX_THUMB_BYTES, final_url_ok=src.host_ok)
                original = downloaded
            loop = asyncio.get_running_loop()
            if not await loop.run_in_executor(None, validate_image, original):
                return None
            await loop.run_in_executor(None, _write_thumbnail, original, tmp)
            tmp.replace(dest)
            return dest
        except (HttpError, OSError, ValueError, RuntimeError) as exc:
            logger.debug("thumb %s could not be fetched or resized: %s", wp.uid, exc)
            return None
        finally:
            tmp.unlink(missing_ok=True)
            if downloaded is not None:
                downloaded.unlink(missing_ok=True)

    async def fetch_preview(self, wp: Wallpaper) -> Optional[Path]:
        """Cache a full-resolution preview for the focused carousel image."""
        if wp.source == "local":
            path = Path(wp.url)
            return path if path.is_file() else None
        src = self.sources.get(wp.source)
        if src is None:
            return None
        THUMB_DIR.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha1(f"{wp.uid}|{wp.url}".encode()).hexdigest()
        dest = THUMB_DIR / f"preview_{key}.img"
        if dest.exists() and dest.stat().st_size > 0:
            os.utime(dest)
            return dest
        ctx = self._context()
        url = await src.resolve(ctx, wp)
        if not src.host_ok(url):
            raise ValueError("the image is hosted somewhere this source is not allowed to preview")
        tmp = _tmp_path(dest)
        if src.min_interval:
            await self.http.throttle(src.key, src.min_interval)
        await self.http.download(url, tmp, MAX_PREVIEW_BYTES, final_url_ok=src.host_ok)
        loop = asyncio.get_running_loop()
        if not await loop.run_in_executor(None, validate_image, tmp):
            tmp.unlink(missing_ok=True)
            raise ValueError("the preview is not a valid image")
        tmp.replace(dest)
        self._prune_preview_cache(dest)
        return dest

    @staticmethod
    def _prune_preview_cache(keep: Path) -> None:
        previews = []
        for path in THUMB_DIR.glob("preview_*.img"):
            try:
                stat = path.stat()
            except OSError:
                continue
            previews.append((stat.st_mtime, stat.st_size, path))
        total = sum(size for _, size, _ in previews)
        for _, size, path in sorted(previews):
            if total <= MAX_PREVIEW_CACHE_BYTES:
                break
            if path == keep:
                continue
            try:
                path.unlink()
                total -= size
            except OSError:
                pass

    async def fetch_full(self, wp: Wallpaper, progress: Optional[Callable[[float], None]] = None) -> FullImage:
        """Resolve, download and verify the full-size image. Raises HttpError/ValueError on failure."""
        if wp.source == "local" and Path(wp.url).is_file():
            p = Path(wp.url)
            loop = asyncio.get_running_loop()
            info = await loop.run_in_executor(None, validate_image, p)
            if info:
                return FullImage(p, info[1], info[2])
            raise ValueError("the local file is not a valid image")

        stem = _safe_name(f"{wp.source}_{wp.id}")
        cached = await self._cached_full(stem)             # already on disk: no network at all, not even resolve()
        if cached:
            return cached
        task = self._inflight.get(stem)
        if task is None:                                   # first caller starts it, the others just wait for it
            task = asyncio.ensure_future(self._download_full(wp, stem, progress))
            self._inflight[stem] = task
            task.add_done_callback(lambda _t, k=stem: self._inflight.pop(k, None))
        return await asyncio.shield(task)

    async def _cached_full(self, stem: str) -> Optional[FullImage]:
        """Look for an earlier download: the app cache first, then the user's Pictures/Lumi folder."""
        loop = asyncio.get_running_loop()
        for directory in (WALLPAPER_DIR, saved_dir()):
            for ext in EXT_FOR_FORMAT.values():
                path = directory / f"{stem}.{ext}"
                if not path.is_file():
                    continue
                info = await loop.run_in_executor(None, validate_image, path)
                if info:
                    try:
                        os.utime(path)                     # used just now: the 1 GB cleanup removes it last
                    except OSError:
                        pass
                    return FullImage(path, info[1], info[2])
        return None

    async def _download_full(self, wp: Wallpaper, stem: str, progress) -> FullImage:
        src = self.sources.get(wp.source) or self.sources.get("custom_url")
        ctx = self._context()
        url = await src.resolve(ctx, wp) if src else wp.url
        if src and not src.host_ok(url):
            raise ValueError("the image is hosted somewhere this source is not allowed to download from")
        WALLPAPER_DIR.mkdir(parents=True, exist_ok=True)
        loop = asyncio.get_running_loop()
        tmp = _tmp_path(WALLPAPER_DIR / stem)
        final_ok = src.host_ok if src else None
        if src and src.min_interval:
            await self.http.throttle(src.key, src.min_interval)
        await self.http.download(url, tmp, MAX_FULL_BYTES, progress, final_url_ok=final_ok)
        info = await loop.run_in_executor(None, validate_image, tmp)
        if not info:
            tmp.unlink(missing_ok=True)
            raise ValueError("the download is not a valid JPEG/PNG/WebP image")
        fmt, width, height = info
        dest = WALLPAPER_DIR / f"{stem}.{EXT_FOR_FORMAT[fmt]}"
        tmp.replace(dest)
        return FullImage(dest, width, height)

    async def download_from_url(self, url: str, dest_dir: Path,
                                progress: Optional[Callable[[float], None]] = None) -> FullImage:
        """Scrape ``url`` (a wallpaper page of any site, or a direct image link), download the highest-quality
        picture into ``dest_dir`` and verify it. Raises HttpError/ValueError on failure."""
        url = (url or "").strip()
        src = self.sources["custom_url"]
        if not src.host_ok(url):
            raise ValueError("enter a full http(s) link")
        image_url = url if ext_is_image(url) else await UniversalWebScraper.find_best_image(self.http, url)
        if not src.host_ok(image_url):
            raise ValueError("the image link found on the page is not a web address")

        # name: the page slug (e.g. "forest-mist-4k-wallpaper"), hash of the real file URL keeps names unique
        slug = Path(urlparse(url).path.rstrip("/")).stem or urlparse(url).hostname or "wallpaper"
        stem = f"{re.sub(r'[^A-Za-z0-9._-]+', '_', slug)[:50].strip('.') or 'wallpaper'}_{hashlib.sha1(image_url.encode()).hexdigest()[:8]}"
        dest_dir.mkdir(parents=True, exist_ok=True)
        loop = asyncio.get_running_loop()
        for ext in EXT_FOR_FORMAT.values():                       # already downloaded earlier: reuse it
            existing = dest_dir / f"{stem}.{ext}"
            if existing.is_file():
                info = await loop.run_in_executor(None, validate_image, existing)
                if info:
                    return FullImage(existing, info[1], info[2])

        tmp = _tmp_path(dest_dir / stem)
        if src.min_interval:
            await self.http.throttle(src.key, src.min_interval)
        await self.http.download(image_url, tmp, MAX_FULL_BYTES, progress, final_url_ok=src.host_ok,
                                 headers={"Referer": url})
        info = await loop.run_in_executor(None, validate_image, tmp)
        if not info:
            tmp.unlink(missing_ok=True)
            raise ValueError("the download is not a valid JPEG/PNG/WebP image")
        fmt, width, height = info
        dest = dest_dir / f"{stem}.{EXT_FOR_FORMAT[fmt]}"
        tmp.replace(dest)
        return FullImage(dest, width, height)

    def prune(self, keep: Optional[Path] = None, clear_all: bool = False) -> int:
        return prune_downloads(keep, clear_all=clear_all)

    async def notify_use(self, wp: Wallpaper) -> None:
        src = self.sources.get(wp.source)
        if src:
            await src.on_use(self._context(), wp)

    async def close(self) -> None:
        await self.http.close()
