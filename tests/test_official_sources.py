import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image

from lumi.config import Config
from lumi.engine import Engine
from lumi.models import Wallpaper
from lumi.sources.official import (
    AniList,
    ArtInstitute,
    FanartTV,
    Kitsu,
    MetMuseum,
    Openverse,
    Rijksmuseum,
    Tmdb,
)
from lumi.sources.base import Context, Source


class FixtureHttp:
    def __init__(self):
        self.calls = []

    async def throttle(self, key, interval):
        return None

    async def get_json(self, url, params=None, headers=None, method="GET", data=None):
        self.calls.append({"url": url, "headers": headers or {}, "method": method})
        if "collectionapi.metmuseum.org/public/collection/v1.1/search" in url:
            return {"objectIDs": [1]}
        if "collectionapi.metmuseum.org/public/collection/v1/objects/" in url:
            return {
                "objectID": 1, "title": "Landscape", "isPublicDomain": True,
                "primaryImage": "https://images.metmuseum.org/artwork.jpg",
                "primaryImageSmall": "https://images.metmuseum.org/small.jpg",
            }
        if url.endswith("/api/v1/artworks/search"):
            return {"data": [{
                "id": 2, "title": "Public art", "image_id": "abc", "is_public_domain": True,
            }]}
        if url.endswith("/api/en/collection"):
            return {"artObjects": [{
                "objectNumber": "A1", "title": "Rijks art",
                "webImage": {"url": "https://www.rijksmuseum.nl/art.jpg", "width": 4000, "height": 2000},
            }]}
        if url.endswith("/v1/images/"):
            return {"results": [{
                "id": "cc-1", "url": "https://upload.wikimedia.org/image.jpg",
                "thumbnail": "https://upload.wikimedia.org/thumb.jpg", "license": "cc-by",
                "creator": "Artist", "foreign_landing_url": "https://example.org/work",
            }]}
        if url.endswith("/v1/auth_tokens/token/"):
            return {"access_token": "fixture-token", "expires_in": 3600}
        if "api.themoviedb.org/3/search/multi" in url:
            return {"results": [{
                "id": 3, "media_type": "movie", "title": "Film",
                "backdrop_path": "/backdrop.jpg",
            }]}
        if "webservice.fanart.tv/v3/movies/" in url:
            return {"moviebackground": [{"url": "https://assets.fanart.tv/background.jpg"}]}
        if url == "https://graphql.anilist.co":
            return {"data": {"Page": {"media": [{
                "id": 4, "title": {"english": "Anime"}, "bannerImage": "https://s4.anilist.co/banner.jpg",
                "siteUrl": "https://anilist.co/anime/4",
            }]}}}
        if url.endswith("/api/edge/anime"):
            return {"data": [{
                "id": "5", "attributes": {"canonicalTitle": "Kitsu", "coverImage": {
                    "original": "https://media.kitsu.io/cover.jpg",
                }},
            }]}
        raise AssertionError(f"Unexpected URL: {url}")


class PreviewHttp:
    def __init__(self):
        self.calls = 0
        image = Image.new("RGB", (8, 8), "blue")
        self.buffer = BytesIO()
        image.save(self.buffer, format="PNG")

    async def download(self, url, dest, max_bytes, progress=None, final_url_ok=None):
        self.calls += 1
        if final_url_ok and not final_url_ok(url):
            raise AssertionError("preview URL was not validated")
        dest.write_bytes(self.buffer.getvalue())


class PreviewSource(Source):
    key, name, hosts = "preview-test", "Preview test", ("images.test",)

    async def search(self, ctx, query, page, category):
        return []


class OfficialSourceTests(unittest.IsolatedAsyncioTestCase):
    def test_existing_explicit_source_lists_enable_new_official_apis_once(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"
            path.write_text('{"enabled_sources": ["wallhaven"]}')
            config = Config(path=path)
            enabled = config.get("enabled_sources")
            for key in ("met", "artic", "rijksmuseum", "openverse", "tmdb", "anilist", "kitsu", "fanart"):
                self.assertIn(key, enabled)
            for key in ("wallhaven_web", "konachan_web", "yande_web", "safebooru_web", "gelbooru_web"):
                self.assertIn(key, enabled)
            self.assertIn("danbooru", enabled)
            defaults = {"wallhaven": True, "met": True}
            config.set_source_enabled("met", False, defaults)
            reloaded = Config(path=path)
            self.assertFalse(reloaded.source_enabled("met", True))

    def test_verified_website_scrapers_are_enabled_by_default_only(self):
        from lumi.sources import build_registry

        registry = build_registry()
        for key in ("wallhaven_web", "konachan_web", "yande_web", "safebooru_web", "gelbooru_web"):
            self.assertTrue(registry[key].default_enabled)
        self.assertTrue(registry["danbooru"].default_enabled)
        self.assertFalse(registry["picsum"].default_enabled)
        self.assertFalse(registry["4kwallpapers"].default_enabled)

    async def test_official_api_adapters_normalize_results(self):
        http = FixtureHttp()
        context = Context(http=http, cfg={"api_keys": {
            "rijksmuseum": "rijks-key", "tmdb": "tmdb-key", "fanart": "fanart-key",
            "openverse_id": "client-id", "openverse_secret": "client-secret",
        }})
        cases = [
            (MetMuseum(), "met"),
            (ArtInstitute(), "artic"),
            (Rijksmuseum(), "rijksmuseum"),
            (Openverse(), "openverse"),
            (Tmdb(), "tmdb"),
            (AniList(), "anilist"),
            (Kitsu(), "kitsu"),
            (FanartTV(), "fanart"),
        ]
        for source, expected_key in cases:
            with self.subTest(source=expected_key):
                wallpapers = await source.search(context, "landscape", 1, None)
                self.assertEqual(len(wallpapers), 1)
                self.assertEqual(wallpapers[0].source, expected_key)
                self.assertTrue(wallpapers[0].url.startswith("https://"))
        openverse_call = next(call for call in http.calls if call["url"].endswith("/v1/images/"))
        self.assertEqual(openverse_call["headers"]["Authorization"], "Bearer fixture-token")

    def test_openverse_image_hosts_must_be_https_public_names(self):
        source = Openverse()
        self.assertTrue(source.host_ok("https://upload.wikimedia.org/image.jpg"))
        self.assertFalse(source.host_ok("http://upload.wikimedia.org/image.jpg"))
        self.assertFalse(source.host_ok("https://127.0.0.1/image.jpg"))
        self.assertFalse(source.host_ok("https://local.internal/image.jpg"))

    async def test_full_resolution_preview_is_cached_for_reuse(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            http = PreviewHttp()
            engine = Engine(Config(path=root / "config.json"), http=http)
            engine.sources["preview-test"] = PreviewSource()
            wallpaper = Wallpaper(
                id="original", source="preview-test",
                url="https://images.test/original.png", thumb_url="https://images.test/thumb.jpg",
            )
            with patch("lumi.engine.THUMB_DIR", root / "cache"):
                first = await engine.fetch_preview(wallpaper)
                second = await engine.fetch_preview(wallpaper)
            self.assertEqual(first, second)
            self.assertTrue(first.name.startswith("preview_"))
            self.assertEqual(http.calls, 1)
