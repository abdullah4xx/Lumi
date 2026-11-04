import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from lumi.http import Http, HttpError, _PublicResolver, is_public_http_url


class Response:
    def __init__(self, status, body=b"", headers=None, url="https://example.test/image.png"):
        self.status = status
        self.headers = headers or {}
        self.url = url
        self.content_length = len(body)
        self.content = self
        self.body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def iter_chunked(self, _size):
        yield self.body


class Session:
    closed = False

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def get(self, *_args, **_kwargs):
        self.calls += 1
        return self.responses.pop(0)


class RequestSession(Session):
    def __init__(self, responses):
        super().__init__(responses)
        self.request_calls = []

    def request(self, method, url, **kwargs):
        self.request_calls.append((method, url, kwargs))
        return self.responses.pop(0)


class HttpDownloadTests(unittest.IsolatedAsyncioTestCase):
    def test_public_url_validation_rejects_local_and_non_http_addresses(self):
        for url in (
            "http://127.0.0.1/image.png",
            "http://10.0.0.4/image.png",
            "http://[::1]/image.png",
            "http://localhost/image.png",
            "file:///etc/passwd",
            "https://user:pass@example.com/image.png",
        ):
            with self.subTest(url=url):
                self.assertFalse(is_public_http_url(url))

        self.assertTrue(is_public_http_url("https://images.example.com/wallpaper.jpg"))
        self.assertTrue(is_public_http_url("https://[2606:4700:4700::1111]/image.jpg"))
        self.assertFalse(is_public_http_url("http://router.home.arpa/image.jpg"))

    async def test_resolver_rejects_hostnames_with_private_addresses(self):
        class Resolver:
            async def resolve(self, *_args, **_kwargs):
                return [{"host": "93.184.216.34"}, {"host": "10.0.0.7"}]

            async def close(self):
                return None

        fake_aiohttp = SimpleNamespace(
            resolver=SimpleNamespace(DefaultResolver=lambda: Resolver())
        )
        with patch("lumi.http._aiohttp", return_value=fake_aiohttp):
            resolver = _PublicResolver()
            with self.assertRaisesRegex(OSError, "non-public"):
                await resolver.resolve("example.test", 443)
            await resolver.close()

    async def test_get_rejects_private_redirect_before_following_it(self):
        session = RequestSession([
            Response(302, headers={"Location": "http://127.0.0.1/admin"}),
        ])
        http = Http()
        http._session = session

        with self.assertRaisesRegex(HttpError, "redirected outside|not a public"):
            await http.get_text("https://example.test/page")

        self.assertEqual(len(session.request_calls), 1)

    async def test_download_rejects_private_redirect_before_following_it(self):
        session = Session([
            Response(302, headers={"Location": "http://192.168.1.1/private"}),
        ])
        http = Http()
        http._session = session

        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "image.part"
            with self.assertRaisesRegex(HttpError, "redirected outside|not a public"):
                await http.download("https://example.test/image.png", destination, 100)
            self.assertFalse(destination.exists())

        self.assertEqual(session.calls, 1)

    async def test_cross_origin_redirect_drops_credentials_and_referrer(self):
        session = RequestSession([
            Response(302, headers={"Location": "https://cdn.example.test/image.png"}),
            Response(200, b"ok", url="https://cdn.example.test/image.png"),
        ])
        http = Http()
        http._session = session

        self.assertEqual(
            await http.get_text(
                "https://example.test/page",
                headers={"Authorization": "secret", "Referer": "https://example.test/page"},
            ),
            "ok",
        )
        self.assertEqual(
            session.request_calls[1][2]["headers"],
            {},
        )

    async def test_retries_temporary_server_failure(self):
        session = Session([
            Response(503, headers={"Retry-After": "0"}),
            Response(200, b"image-bytes"),
        ])
        http = Http()
        http._session = session

        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "image.part"
            await http.download("https://example.test/image.png", destination, 100)

            self.assertEqual(destination.read_bytes(), b"image-bytes")
        self.assertEqual(session.calls, 2)

    async def test_releases_connection_slot_before_retry_wait(self):
        session = Session([
            Response(503, headers={"Retry-After": "1"}),
            Response(200, b"image-bytes"),
        ])
        http = Http(max_connections=1)
        http._session = session
        sleeps = []

        async def verify_released_slot(delay):
            sleeps.append(delay)
            self.assertEqual(http._sem._value, 1)

        with tempfile.TemporaryDirectory() as temp, patch(
            "lumi.http.asyncio.sleep", new=AsyncMock(side_effect=verify_released_slot)
        ):
            await http.download(
                "https://example.test/image.png", Path(temp) / "image.part", 100
            )

        self.assertEqual(sleeps, [1.0])

    async def test_does_not_retry_permanent_http_error(self):
        session = Session([Response(404)])
        http = Http()
        http._session = session

        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(HttpError, "HTTP 404"):
                await http.download(
                    "https://example.test/missing.png", Path(temp) / "image.part", 100
                )
        self.assertEqual(session.calls, 1)
