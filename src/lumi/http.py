"""Small async HTTP layer: retries, throttling, size caps, streaming download."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from . import REPO, __version__

USER_AGENT = f"Lumi/{__version__} (GNOME wallpaper app; +https://github.com/{REPO})"
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_TEXT_BYTES = 4 * 1024 * 1024
RETRY_STATUSES = (429, 500, 502, 503, 504)


class HttpError(Exception):
    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


def _aiohttp():
    import aiohttp  # imported lazily so the pure-logic modules stay importable in tests
    return aiohttp


class Http:
    def __init__(self, max_connections: int = 12):
        self._session = None
        self._sem = asyncio.Semaphore(max_connections)
        self._locks: Dict[str, asyncio.Lock] = {}
        self._last: Dict[str, float] = {}

    async def session(self):
        if self._session is None or self._session.closed:
            aiohttp = _aiohttp()
            self._session = aiohttp.ClientSession(
                headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
                timeout=aiohttp.ClientTimeout(total=30, sock_read=20),
            )
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()

    async def throttle(self, key: str, interval: float) -> None:
        """Keep at least ``interval`` seconds between requests for ``key``."""
        if interval <= 0:
            return
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            wait = self._last.get(key, 0.0) + interval - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last[key] = time.monotonic()

    async def _read_limited(self, resp, limit: int) -> bytes:
        chunks, size = [], 0
        async for chunk in resp.content.iter_chunked(64 * 1024):
            size += len(chunk)
            if size > limit:
                raise HttpError("response too large")
            chunks.append(chunk)
        return b"".join(chunks)

    async def _get(self, url: str, params=None, headers=None, limit=MAX_JSON_BYTES, method="GET", data=None) -> bytes:
        aiohttp = _aiohttp()
        session = await self.session()
        last_exc: Optional[Exception] = None
        for attempt in range(3):
            try:
                async with self._sem:
                    async with session.request(method, url, params=params, headers=headers, data=data) as resp:
                        if resp.status in RETRY_STATUSES and attempt < 2:
                            retry_after = resp.headers.get("Retry-After", "")
                            delay = float(retry_after) if retry_after.isdigit() else 1.5 * (attempt + 1)
                            last_exc = HttpError(f"HTTP {resp.status}", resp.status)
                            await asyncio.sleep(min(delay, 8))
                            continue
                        if resp.status != 200:
                            raise HttpError(f"HTTP {resp.status}", resp.status)
                        return await self._read_limited(resp, limit)
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_exc = HttpError(f"network error: {exc.__class__.__name__}")
                if attempt < 2:
                    await asyncio.sleep(1.0 * (attempt + 1))
        raise last_exc or HttpError("request failed")

    async def get_json(self, url: str, params=None, headers=None, method="GET", data=None) -> Any:
        raw = await self._get(url, params, headers, MAX_JSON_BYTES, method, data)
        try:
            return json.loads(raw)
        except ValueError as exc:
            raise HttpError("invalid JSON") from exc

    async def get_text(self, url: str, params=None, headers=None) -> str:
        raw = await self._get(url, params, headers, MAX_TEXT_BYTES)
        return raw.decode("utf-8", "replace")

    async def download(self, url: str, dest: Path, max_bytes: int, progress: Optional[Callable[[float], None]] = None,
                       final_url_ok: Optional[Callable[[str], bool]] = None,
                       headers: Optional[Dict[str, str]] = None) -> None:
        """Stream ``url`` into ``dest`` (a temp path). Raises HttpError on any problem."""
        aiohttp = _aiohttp()
        session = await self.session()
        timeout = aiohttp.ClientTimeout(total=300, sock_read=30)
        try:
            async with self._sem:
                async with session.get(url, timeout=timeout, headers=headers) as resp:
                    if resp.status != 200:
                        raise HttpError(f"HTTP {resp.status}", resp.status)
                    if final_url_ok and not final_url_ok(str(resp.url)):
                        raise HttpError("redirected to an untrusted address")
                    total = resp.content_length or 0
                    if total > max_bytes:
                        raise HttpError("file too large")
                    done = 0
                    with open(dest, "wb") as fh:
                        async for chunk in resp.content.iter_chunked(128 * 1024):
                            done += len(chunk)
                            if done > max_bytes:
                                raise HttpError("file too large")
                            fh.write(chunk)
                            if progress:
                                progress(min(done / total, 1.0) if total else -1.0)   # -1 = unknown size
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
            dest.unlink(missing_ok=True)
            raise HttpError(f"download failed: {exc.__class__.__name__}") from exc
        except (HttpError, asyncio.CancelledError):
            dest.unlink(missing_ok=True)
            raise
