"""User-installed Python scraper plugins."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import inspect
import json
import logging
import re
import time
from pathlib import Path
from types import ModuleType
from typing import Dict, List, Optional
from urllib.parse import urlparse

from ..config import CACHE_DIR, DATA_DIR
from ..models import Wallpaper
from .base import KIND_EXPERIMENTAL, Context, Source, clip, to_int

logger = logging.getLogger("lumi.sources.plugins")

MAX_PLUGIN_BYTES = 1024 * 1024
RESULT_CACHE_TTL = 30 * 60
_PLUGIN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
_SAFE_RATINGS = {"safe", "general", "s"}


class PluginError(ValueError):
    """A user scraper could not be installed or returned invalid data."""


def _plugin_metadata(path: Path, fallback_id: Optional[str] = None) -> tuple[ModuleType, str, str, tuple[str, ...], bool]:
    if path.suffix.lower() != ".py" or not path.is_file():
        raise PluginError("Choose a Python .py scraper file.")
    if path.stat().st_size > MAX_PLUGIN_BYTES:
        raise PluginError("Scraper files must be 1 MiB or smaller.")

    module_name = "_lumi_user_scraper_" + hashlib.sha256(
        str(path.resolve()).encode("utf-8")
    ).hexdigest()[:20]
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise PluginError("Could not load the scraper file.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not callable(getattr(module, "search", None)):
        raise PluginError("The scraper must define search(query, category, page).")
    source_id = getattr(module, "SOURCE_ID", fallback_id or path.stem)
    if not isinstance(source_id, str):
        raise PluginError("SOURCE_ID must be a string.")
    source_id = source_id.strip().lower()
    if not _PLUGIN_ID_RE.fullmatch(source_id):
        raise PluginError("SOURCE_ID must contain only lowercase letters, numbers, '-' or '_'.")
    name = getattr(module, "SOURCE_NAME", path.stem)
    homepage = getattr(module, "SOURCE_URL", "")
    if not isinstance(name, str) or not name.strip():
        raise PluginError("SOURCE_NAME must be a non-empty string.")
    parsed = urlparse(homepage if isinstance(homepage, str) else "")
    if parsed.scheme != "https" or not parsed.hostname:
        raise PluginError("SOURCE_URL must be an HTTPS website URL.")

    hosts = {parsed.hostname.lower()}
    declared_hosts = getattr(module, "SOURCE_HOSTS", ())
    if not isinstance(declared_hosts, (list, tuple)):
        raise PluginError("SOURCE_HOSTS must be a list of image-host names.")
    for host in declared_hosts:
        if not isinstance(host, str) or not host.strip() or "/" in host or ":" in host:
            raise PluginError("SOURCE_HOSTS entries must be plain host names.")
        hosts.add(host.strip().lower().lstrip("."))
    anime = str(getattr(module, "SOURCE_CATEGORY", "")).casefold() == "anime"
    safe_rating = getattr(module, "SAFE_RATING", False) is True
    if anime and not safe_rating:
        raise PluginError("Anime scrapers must declare SAFE_RATING = True.")
    return module, source_id, name.strip(), tuple(sorted(hosts)), anime


class PluginSource(Source):
    kind = KIND_EXPERIMENTAL
    default_enabled = False
    min_interval = 1.0
    supports_query = True

    def __init__(self, path: Path, cache_dir: Path, metadata=None):
        self.plugin_path = path
        self.cache_dir = cache_dir
        self.module, source_id, self.name, self.hosts, self.is_anime = metadata or _plugin_metadata(path)
        self.key = "custom_scraper_" + source_id
        self.homepage = self.module.SOURCE_URL
        self.description = getattr(
            self.module, "SOURCE_DESCRIPTION", f"User-installed scraper for {self.homepage}"
        )
        self._code_hash = hashlib.sha256(path.read_bytes()).hexdigest()

    async def search(self, ctx: Context, query, page, category):
        cache_key = hashlib.sha256(
            json.dumps(
                [self._code_hash, query, category, int(page)],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        cached = self._read_cache(cache_key)
        if cached is not None:
            raw_items = cached
        else:
            await ctx.http.throttle(self.key, self.min_interval)
            if inspect.iscoroutinefunction(self.module.search):
                result = await asyncio.wait_for(
                    self.module.search(query, category, page), timeout=30
                )
            else:
                result = await asyncio.wait_for(
                    asyncio.to_thread(self.module.search, query, category, page), timeout=30
                )
            if inspect.isawaitable(result):
                result = await asyncio.wait_for(result, timeout=30)
            if not isinstance(result, list):
                raise PluginError("search() must return a list of wallpaper dictionaries.")
            raw_items = result
            self._write_cache(cache_key, raw_items)

        out, seen = [], set()
        for item in raw_items:
            wallpaper = self._wallpaper(item, ctx)
            if wallpaper and wallpaper.id not in seen:
                seen.add(wallpaper.id)
                out.append(wallpaper)
        return out

    def _wallpaper(self, item, ctx):
        if not isinstance(item, dict):
            raise PluginError("Every search result must be a dictionary.")
        required = (
            "title", "thumb_url", "full_url", "width", "height",
            "source", "category", "page_url",
        )
        if any(key not in item for key in required):
            raise PluginError("Each result needs title, thumb_url, full_url, width, height, and page_url.")
        full_url = item["full_url"]
        thumb_url = item["thumb_url"]
        page_url = item["page_url"]
        if not isinstance(full_url, str) or not isinstance(thumb_url, str):
            raise PluginError("Image URLs must be strings.")
        if not isinstance(item["source"], str):
            raise PluginError("The source field must be a string.")
        if item["category"] is not None and not isinstance(item["category"], str):
            raise PluginError("The category field must be a string or null.")
        if not isinstance(page_url, str) or not self.host_ok(page_url):
            raise PluginError("The page_url must be HTTPS and use a host declared by the scraper.")
        if not self.host_ok(full_url) or not self.host_ok(thumb_url):
            raise PluginError("Image URLs must use HTTPS and a host declared by the scraper.")
        width, height = to_int(item["width"]), to_int(item["height"])
        if not width or not height or max(width, height) < 1920 or min(width, height) < 1080:
            return None
        if not ctx.meets_min(width, height):
            return None
        category = item["category"] or ""
        if self.is_anime:
            rating = str(item.get("rating") or "").casefold()
            if rating not in _SAFE_RATINGS:
                return None
        item_id = hashlib.sha256(full_url.encode("utf-8")).hexdigest()[:24]
        tags = tuple(x for x in (category,) if x)
        return Wallpaper(
            id=item_id,
            source=self.key,
            url=full_url,
            thumb_url=thumb_url,
            width=width,
            height=height,
            title=clip(item["title"]),
            page_url=page_url,
            tags=tags,
            extra={"category": category},
        )

    async def resolve(self, ctx, wp):
        if not self.host_ok(wp.url):
            raise PluginError("The scraper's image URL is outside its declared hosts.")
        return wp.url

    def _cache_path(self, cache_key: str) -> Path:
        return self.cache_dir / (cache_key + ".json")

    def _read_cache(self, cache_key: str):
        path = self._cache_path(cache_key)
        try:
            if time.time() - path.stat().st_mtime > RESULT_CACHE_TTL:
                path.unlink(missing_ok=True)
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else None
        except (OSError, json.JSONDecodeError):
            return None

    def _write_cache(self, cache_key: str, items: List[dict]) -> None:
        if len(items) > 500:
            raise PluginError("A scraper may return at most 500 results per page.")
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path = self._cache_path(cache_key)
            temp = path.with_suffix(".tmp")
            temp.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
            temp.replace(path)
        except (OSError, TypeError, ValueError) as exc:
            logger.warning("Could not cache scraper results for %s: %s", self.key, exc)


class CustomScraperRegistry:
    def __init__(self, plugin_dir: Optional[Path] = None, cache_dir: Optional[Path] = None):
        self.plugin_dir = Path(plugin_dir or DATA_DIR / "scrapers")
        self.cache_dir = Path(cache_dir or CACHE_DIR / "scraper-results")

    def load_all(self) -> Dict[str, PluginSource]:
        self.plugin_dir.mkdir(parents=True, exist_ok=True)
        sources = {}
        for path in sorted(self.plugin_dir.glob("*.py")):
            if path.name.startswith("."):
                continue
            try:
                source = PluginSource(path, self.cache_dir)
            except Exception as exc:
                logger.warning("Could not load scraper plugin %s: %s", path.name, exc)
                continue
            if source.key in sources:
                logger.warning("Ignoring duplicate scraper plugin id in %s", path.name)
                continue
            sources[source.key] = source
        return sources

    def install(self, filename: str, content: bytes) -> PluginSource:
        if not isinstance(filename, str) or Path(filename).suffix.lower() != ".py":
            raise PluginError("Choose a Python .py scraper file.")
        if not isinstance(content, bytes) or not content or len(content) > MAX_PLUGIN_BYTES:
            raise PluginError("Scraper files must be between 1 byte and 1 MiB.")
        self.plugin_dir.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(filename).stem).strip("_")
        if not safe_name:
            raise PluginError("The scraper filename must include letters or numbers.")
        path = self.plugin_dir / (safe_name + ".py")
        temp = self.plugin_dir / ("." + safe_name + ".stage.py")
        try:
            temp.write_bytes(content)
            temp.chmod(0o600)
            metadata = _plugin_metadata(temp, safe_name)
            source_key = "custom_scraper_" + metadata[1]
            for existing in self.load_all().values():
                if existing.key == source_key and existing.plugin_path != path:
                    raise PluginError("A scraper with this SOURCE_ID is already installed.")
            temp.replace(path)
            return PluginSource(path, self.cache_dir, metadata)
        except Exception:
            temp.unlink(missing_ok=True)
            raise

    def remove(self, key: str) -> bool:
        removed = False
        for path in self.plugin_dir.glob("*.py"):
            try:
                if PluginSource(path, self.cache_dir).key == key:
                    path.unlink()
                    removed = True
            except Exception as exc:
                logger.warning("Could not inspect scraper plugin %s: %s", path.name, exc)
        return removed

    def list(self) -> List[dict]:
        return [
            {
                "key": source.key,
                "name": source.name,
                "homepage": source.homepage,
                "filename": source.plugin_path.name,
            }
            for source in self.load_all().values()
        ]
