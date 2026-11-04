"""Small async HTTP layer: retries, throttling, size caps, streaming download."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import socket
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib.parse import urljoin, urlsplit

from . import REPO, __version__

USER_AGENT = f"Lumi/{__version__} (GNOME wallpaper app; +https://github.com/{REPO})"
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_TEXT_BYTES = 4 * 1024 * 1024
RETRY_STATUSES = (429, 500, 502, 503, 504)


class HttpError(Exception):
    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class UnsafeUrlError(HttpError):
    """A URL or redirect was rejected before opening a network connection."""


def _aiohttp():
    import aiohttp  # imported lazily so the pure-logic modules stay importable in tests
    return aiohttp


def is_public_http_url(url: str) -> bool:
    try:
        parsed = urlsplit(url or "")
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError:
        return False
    if (
        parsed.scheme not in ("http", "https")
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or (port is not None and not 1 <= port <= 65535)
        or host == "localhost"
        or host.endswith((".localhost", ".local", ".internal", ".home.arpa"))
    ):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return "." in host


def _origin(url: str):
    parsed = urlsplit(url)
    return parsed.scheme.lower(), (parsed.hostname or "").lower(), parsed.port


def _redirect_headers(headers, old_url: str, new_url: str):
    if not headers or _origin(old_url) == _origin(new_url):
        return headers
    sensitive = {"authorization", "cookie", "proxy-authorization", "referer"}
    return {key: value for key, value in headers.items() if key.lower() not in sensitive}


class _PublicResolver:
    def __init__(self):
        self._resolver = _aiohttp().resolver.DefaultResolver()

    async def resolve(self, host, port=0, family=socket.AF_INET):
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            addresses = await self._resolver.resolve(host, port, family)
            if not addresses or any(not ipaddress.ip_address(item["host"]).is_global for item in addresses):
                raise OSError("hostname resolves to a non-public address")
            return addresses
        if not ip.is_global:
            raise OSError("non-public IP addresses are not allowed")
        return await self._resolver.resolve(host, port, family)

    async def close(self):
        await self._resolver.close()


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
                connector=aiohttp.TCPConnector(resolver=_PublicResolver()),
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

    async def _get(self, url: str, params=None, headers=None, limit=MAX_JSON_BYTES,
                   method="GET", data=None, final_url_ok: Optional[Callable[[str], bool]] = None) -> bytes:
        aiohttp = _aiohttp()
        session = await self.session()
        last_exc: Optional[Exception] = None
        for attempt in range(3):
            retry_delay = None
            current_url, current_method, current_data = url, method, data
            current_headers = dict(headers) if headers else None
            try:
                for redirect in range(6):
                    if not is_public_http_url(current_url):
                        raise UnsafeUrlError("request URL is not a public HTTP(S) address")
                    if final_url_ok and not final_url_ok(current_url):
                        raise UnsafeUrlError("request URL is outside the allowed host")
                    async with self._sem:
                        async with session.request(
                            current_method, current_url, params=params if redirect == 0 else None,
                            headers=current_headers, data=current_data, allow_redirects=False,
                        ) as resp:
                            if resp.status in (301, 302, 303, 307, 308):
                                location = resp.headers.get("Location")
                                if not location or redirect == 5:
                                    raise HttpError("too many or invalid redirects", resp.status)
                                next_url = urljoin(str(resp.url), location)
                                current_headers = _redirect_headers(current_headers, current_url, next_url)
                                current_url = next_url
                                if final_url_ok and not final_url_ok(current_url):
                                    raise UnsafeUrlError("redirected outside the allowed host", resp.status)
                                if resp.status == 303 or (
                                    resp.status in (301, 302) and current_method != "GET"
                                ):
                                    current_method, current_data = "GET", None
                                continue
                            if resp.status in RETRY_STATUSES and attempt < 2:
                                retry_after = resp.headers.get("Retry-After", "")
                                retry_delay = float(retry_after) if retry_after.isdigit() else 1.5 * (attempt + 1)
                                last_exc = HttpError(f"HTTP {resp.status}", resp.status)
                                break
                            if resp.status != 200:
                                raise HttpError(f"HTTP {resp.status}", resp.status)
                            return await self._read_limited(resp, limit)
                if retry_delay is not None:
                    await asyncio.sleep(min(retry_delay, 8))
                    continue
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_exc = HttpError(f"network error: {exc.__class__.__name__}")
                if attempt < 2:
                    await asyncio.sleep(1.0 * (attempt + 1))
        raise last_exc or HttpError("request failed")

    async def get_json(self, url: str, params=None, headers=None, method="GET", data=None,
                       final_url_ok: Optional[Callable[[str], bool]] = None) -> Any:
        raw = await self._get(url, params, headers, MAX_JSON_BYTES, method, data, final_url_ok)
        try:
            return json.loads(raw)
        except ValueError as exc:
            raise HttpError("invalid JSON") from exc

    async def get_text(self, url: str, params=None, headers=None,
                       final_url_ok: Optional[Callable[[str], bool]] = None) -> str:
        raw = await self._get(url, params, headers, MAX_TEXT_BYTES, final_url_ok=final_url_ok)
        return raw.decode("utf-8", "replace")

    async def download(self, url: str, dest: Path, max_bytes: int, progress: Optional[Callable[[float], None]] = None,
                       final_url_ok: Optional[Callable[[str], bool]] = None,
                       headers: Optional[Dict[str, str]] = None) -> None:
        """Stream ``url`` into ``dest`` (a temp path). Raises HttpError on any problem."""
        aiohttp = _aiohttp()
        session = await self.session()
        timeout = aiohttp.ClientTimeout(total=300, sock_read=30)
        last_exc: Optional[Exception] = None
        for attempt in range(3):
            retry_delay = None
            current_url = url
            current_headers = dict(headers) if headers else None
            try:
                for redirect in range(6):
                    if not is_public_http_url(current_url):
                        raise UnsafeUrlError("download URL is not a public HTTP(S) address")
                    if final_url_ok and not final_url_ok(current_url):
                        raise UnsafeUrlError("download URL is outside the allowed host")
                    async with self._sem:
                        async with session.get(
                            current_url, timeout=timeout, headers=current_headers, allow_redirects=False
                        ) as resp:
                            if resp.status in (301, 302, 303, 307, 308):
                                location = resp.headers.get("Location")
                                if not location or redirect == 5:
                                    raise HttpError("too many or invalid redirects", resp.status)
                                next_url = urljoin(str(resp.url), location)
                                current_headers = _redirect_headers(current_headers, current_url, next_url)
                                current_url = next_url
                                if final_url_ok and not final_url_ok(current_url):
                                    raise UnsafeUrlError("redirected outside the allowed host", resp.status)
                                continue
                            if resp.status in RETRY_STATUSES and attempt < 2:
                                retry_after = resp.headers.get("Retry-After", "")
                                retry_delay = float(retry_after) if retry_after.isdigit() else 1.5 * (attempt + 1)
                                last_exc = HttpError(f"HTTP {resp.status}", resp.status)
                                break
                            if resp.status != 200:
                                raise HttpError(f"HTTP {resp.status}", resp.status)
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
                                        progress(min(done / total, 1.0) if total else -1.0)
                            return
                if retry_delay is not None:
                    dest.unlink(missing_ok=True)
                    await asyncio.sleep(min(retry_delay, 8))
                    continue
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
                dest.unlink(missing_ok=True)
                last_exc = HttpError(f"download failed: {exc.__class__.__name__}")
                if attempt < 2:
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                raise last_exc from exc
            except (HttpError, asyncio.CancelledError):
                dest.unlink(missing_ok=True)
                raise
        dest.unlink(missing_ok=True)
        raise last_exc or HttpError("download failed")
