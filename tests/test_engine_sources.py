import asyncio
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from lumi.config import Config
from lumi.engine import Engine
from lumi.http import UnsafeUrlError
from lumi.models import Wallpaper
from lumi.sources.base import KIND_EXPERIMENTAL, Source
from lumi.sources.universal import Candidate, UniversalWebScraper


class NoQuerySource(Source):
    key, name, kind = "no-query-test", "No-query test", KIND_EXPERIMENTAL
    hosts = ("example.test",)
    supports_query = False

    def __init__(self):
        self.queries = []

    async def search(self, ctx, query, page, category):
        self.queries.append((query, category))
        return [Wallpaper(
            id="result", source=self.key, url="https://images.example.test/result.jpg",
            thumb_url="https://images.example.test/result.jpg", width=4000, height=2000,
        )]


class SlowSource(Source):
    key, name, kind = "slow-test", "Slow test", KIND_EXPERIMENTAL
    hosts = ("example.test",)

    async def search(self, ctx, query, page, category):
        await asyncio.sleep(1)
        return []


class ThumbnailHttp:
    def __init__(self, source_path):
        self.source_path = source_path

    async def download(self, url, destination, max_bytes, progress=None, final_url_ok=None, headers=None):
        if final_url_ok and not final_url_ok(url):
            raise ValueError("unexpected thumbnail host")
        shutil.copyfile(self.source_path, destination)

    async def throttle(self, *_):
        return None


class EngineSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_universal_scraper_does_not_ignore_unsafe_follow_up_url(self):
        class ScraperHttp:
            calls = 0

            async def get_text(self, *_args, **_kwargs):
                self.calls += 1
                if self.calls == 1:
                    return "<html>gallery</html>"
                raise UnsafeUrlError("redirected outside the allowed host")

        candidates = [
            Candidate("https://example.test/download/4000x2000", 100, kind="page"),
            Candidate("https://images.example.test/wallpaper.jpg", 50),
        ]
        http = ScraperHttp()
        with patch.object(UniversalWebScraper, "rank_candidates", return_value=candidates):
            with self.assertRaisesRegex(UnsafeUrlError, "outside the allowed host"):
                await UniversalWebScraper.find_best_image(
                    http, "https://example.test/gallery",
                    final_url_ok=lambda url: "example.test" in url,
                )

        self.assertEqual(http.calls, 2)

    async def test_enabled_experimental_feed_is_used_for_category_browsing(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Config(path=Path(temp) / "config.json")
            source = NoQuerySource()
            engine = Engine(config)
            engine.sources = {source.key: source}
            config.set("enabled_sources", [source.key])
            batches = []

            statuses = await engine.search(
                "", "Nature", 1, engine.enabled_keys(), set(),
                lambda key, wallpapers: batches.append((key, wallpapers)),
            )

        self.assertEqual(source.queries, [("", "Nature")])
        self.assertEqual(statuses[source.key].state, "ok")
        self.assertEqual(len(batches), 1)

    async def test_no_query_feed_is_skipped_for_free_text_search(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Config(path=Path(temp) / "config.json")
            source = NoQuerySource()
            engine = Engine(config)
            engine.sources = {source.key: source}
            config.set("enabled_sources", [source.key])

            statuses = await engine.search("sunset", None, 1, engine.enabled_keys(), set(), lambda *_: None)

        self.assertEqual(source.queries, [])
        self.assertEqual(statuses[source.key].state, "skipped")
        self.assertEqual(statuses[source.key].message, "no search support")

    async def test_slow_source_times_out_without_discarding_fast_results(self):
        with tempfile.TemporaryDirectory() as temp:
            config = Config(path=Path(temp) / "config.json")
            fast = NoQuerySource()
            slow = SlowSource()
            engine = Engine(config)
            engine.sources = {fast.key: fast, slow.key: slow}
            config.set("enabled_sources", [fast.key, slow.key])
            batches = []

            with patch("lumi.engine.SOURCE_TIMEOUT", 0.01):
                statuses = await engine.search(
                    "", "Nature", 1, engine.enabled_keys(), set(),
                    lambda key, wallpapers: batches.append((key, wallpapers)),
                )

        self.assertEqual(statuses[fast.key].state, "ok")
        self.assertEqual(statuses[slow.key].state, "error")
        self.assertEqual(statuses[slow.key].message, "timed out")
        self.assertEqual([key for key, _ in batches], [fast.key])

    async def test_local_thumbnail_is_resized_and_cached_as_webp(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "wallpaper.png"
            Image.new("RGB", (1800, 1200), "blue").save(source)
            engine = Engine(Config(path=root / "config.json"))
            wallpaper = Wallpaper(id="local-image", source="local", url=str(source), thumb_url="")

            with patch("lumi.engine.THUMB_DIR", root / "thumbs"):
                result = await engine.fetch_thumb(wallpaper)

            self.assertIsNotNone(result)
            with Image.open(result) as image:
                self.assertEqual(image.format, "WEBP")
                self.assertEqual(image.size, (900, 600))
            self.assertEqual(len(list((root / "thumbs").iterdir())), 1)

    async def test_remote_thumbnail_is_resized_after_download(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source_path = root / "source.png"
            Image.new("RGB", (1800, 1200), "green").save(source_path)
            engine = Engine(Config(path=root / "config.json"), http=ThumbnailHttp(source_path))
            source = Source()
            source.hosts = ("example.test",)
            engine.sources = {"test": source}
            url = "https://images.example.test/thumb.png"
            wallpaper = Wallpaper(id="remote-image", source="test", url=url, thumb_url=url)

            with patch("lumi.engine.THUMB_DIR", root / "thumbs"):
                result = await engine.fetch_thumb(wallpaper)

            self.assertIsNotNone(result)
            with Image.open(result) as image:
                self.assertEqual(image.format, "WEBP")
                self.assertEqual(image.size, (900, 600))
            self.assertEqual(len(list((root / "thumbs").iterdir())), 1)

    async def test_legacy_web_url_wallpaper_can_load_its_thumbnail(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source_path = root / "source.png"
            Image.new("RGB", (1800, 1200), "purple").save(source_path)
            engine = Engine(Config(path=root / "config.json"), http=ThumbnailHttp(source_path))
            wallpaper = Wallpaper(
                id="legacy-web-image", source="web_url",
                url="https://images.example.test/original.png",
                thumb_url="https://images.example.test/thumb.png",
            )

            with patch("lumi.engine.THUMB_DIR", root / "thumbs"):
                result = await engine.fetch_thumb(wallpaper)

            self.assertIsNotNone(result)
            with Image.open(result) as image:
                self.assertEqual(image.format, "WEBP")

    async def test_download_rejects_an_unknown_image_below_configured_minimum(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source_path = root / "small.png"
            Image.new("RGB", (1920, 1080), "orange").save(source_path)
            config = Config(path=root / "config.json")
            config.set("min_long_side", 3840)
            engine = Engine(config, http=ThumbnailHttp(source_path))
            source = Source()
            source.hosts = ("example.test",)
            engine.sources = {"test": source}
            wallpaper = Wallpaper(
                id="unknown-size", source="test",
                url="https://images.example.test/wallpaper.png",
                thumb_url="https://images.example.test/thumb.png",
            )

            with (
                patch("lumi.engine.WALLPAPER_DIR", root / "cache"),
                patch("lumi.engine.saved_dir", return_value=root / "saved"),
            ):
                with self.assertRaisesRegex(ValueError, "below the configured minimum"):
                    await engine.fetch_full(wallpaper)
