import tempfile
import unittest
from pathlib import Path

from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer

from lumi.config import Config
from lumi.local import LocalManager
from lumi.store import Store
from lumi.sources.base import Context
from lumi.sources.plugins import CustomScraperRegistry, PluginError
from lumi.web import WebCompanionServer


class FixtureHttp:
    def __init__(self):
        self.throttles = 0

    async def throttle(self, *_):
        self.throttles += 1


class PluginWebEngine:
    def __init__(self, config, plugin_dir, cache_dir):
        self.config = config
        self.registry = CustomScraperRegistry(plugin_dir, cache_dir)
        self.sources = {}

    def install_scraper_plugin(self, filename, content):
        source = self.registry.install(filename, content)
        self.sources[source.key] = source
        self.config.set_source_enabled(source.key, True, {key: False for key in self.sources})
        return source

    def remove_scraper_plugin(self, key):
        if not self.registry.remove(key):
            return False
        self.sources.pop(key, None)
        return True


class CustomScraperPluginTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.registry = CustomScraperRegistry(root / "scrapers", root / "cache")
        self.ctx = Context(FixtureHttp(), {"min_long_side": 1920, "landscape_only": True})

    def tearDown(self):
        self.temp.cleanup()

    def install(self, name, source):
        return self.registry.install(name, source.encode("utf-8"))

    async def test_plugin_search_uses_common_shape_cache_and_url_hash_ids(self):
        source = self.install(
            "forest.py",
            """
SOURCE_ID = "forest"
SOURCE_NAME = "Forest images"
SOURCE_URL = "https://example.test"
SOURCE_HOSTS = ["images.example.test"]
calls = 0
def search(query, category, page):
    global calls
    calls += 1
    return [{
        "title": f"{query} forest",
        "thumb_url": "https://images.example.test/thumb.jpg",
        "full_url": "https://images.example.test/full.jpg",
        "width": 5120, "height": 2880, "source": "ignored",
        "category": category, "page_url": "https://example.test/wallpaper/1"
    }]
""",
        )

        first = await source.search(self.ctx, "forest", 1, "Nature")
        second = await source.search(self.ctx, "forest", 1, "Nature")

        self.assertEqual(len(first), 1)
        self.assertEqual(first[0].source, "custom_scraper_forest")
        self.assertEqual(first[0].width, 5120)
        self.assertEqual(first[0].tags, ("Nature",))
        self.assertEqual(first[0].id, second[0].id)
        self.assertEqual(source.module.calls, 1)
        self.assertEqual(self.ctx.http.throttles, 1)

    async def test_low_resolution_results_are_filtered(self):
        source = self.install(
            "small.py",
            """
SOURCE_URL = "https://example.test"
def search(query, category, page):
    return [{
        "title": "Small", "thumb_url": "https://example.test/thumb.jpg",
        "full_url": "https://example.test/full.jpg",
        "width": 1600, "height": 900, "source": "small",
        "category": None, "page_url": "https://example.test/item"
    }]
""",
        )
        self.assertEqual(await source.search(self.ctx, "", 1, None), [])

    async def test_anime_plugin_must_declare_filter_and_return_safe_rating(self):
        with self.assertRaisesRegex(PluginError, "SAFE_RATING"):
            self.install(
                "unsafe.py",
                """
SOURCE_CATEGORY = "Anime"
SOURCE_URL = "https://anime.example.test"
def search(query, category, page): return []
""",
            )

        safe = self.install(
            "safe.py",
            """
SOURCE_ID = "anime"
SOURCE_NAME = "Safe anime"
SOURCE_URL = "https://anime.example.test"
SOURCE_CATEGORY = "Anime"
SAFE_RATING = True
def search(query, category, page):
    base = {"title":"Anime", "thumb_url":"https://anime.example.test/thumb.jpg",
            "full_url":"https://anime.example.test/full.jpg", "width":3840,
            "height":2160, "source":"anime", "category":"Anime",
            "page_url":"https://anime.example.test/item"}
    return [{**base, "rating":"safe"}, {**base, "full_url":"https://anime.example.test/other.jpg",
            "rating":"explicit"}]
""",
        )

        results = await safe.search(self.ctx, "anime", 1, "Anime")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].url, "https://anime.example.test/full.jpg")

    async def test_install_rejects_bad_extension_and_untrusted_image_hosts(self):
        with self.assertRaisesRegex(PluginError, r"\.py"):
            self.registry.install("scraper.txt", b"")
        source = self.install(
            "bad_host.py",
            """
SOURCE_URL = "https://example.test"
def search(query, category, page):
    return [{"title":"Bad", "thumb_url":"https://elsewhere.test/thumb.jpg",
             "full_url":"https://elsewhere.test/full.jpg", "width":3840,
             "height":2160, "source":"bad", "category":None,
             "page_url":"https://example.test/item"}]
""",
        )
        with self.assertRaisesRegex(PluginError, "declared by the scraper"):
            await source.search(self.ctx, "", 1, None)

    async def test_plugin_file_loads_after_restart_and_can_be_removed(self):
        self.install(
            "delete_me.py",
            """
SOURCE_URL = "https://example.test"
def search(query, category, page): return []
""",
        )
        self.assertEqual(len(self.registry.load_all()), 1)
        self.assertTrue(self.registry.remove("custom_scraper_delete_me"))
        self.assertEqual(self.registry.load_all(), {})

    async def test_local_settings_api_installs_lists_and_removes_scrapers(self):
        root = Path(self.temp.name)
        config = Config(root / "config.json")
        engine = PluginWebEngine(config, root / "web-scrapers", root / "web-cache")
        server = WebCompanionServer(
            config,
            engine,
            Store(directory=root / "store"),
            LocalManager(config),
            ui_dir=root / "empty-ui",
        )
        client = TestClient(TestServer(server.app))
        await client.start_server()
        try:
            form = FormData()
            form.add_field(
                "file",
                b'SOURCE_URL="https://example.test"\n'
                b'def search(query, category, page): return []\n',
                filename="example.py",
                content_type="text/x-python",
            )
            response = await client.post("/api/scrapers", data=form)
            self.assertEqual(response.status, 200, await response.text())
            result = await response.json()
            self.assertEqual(result["scraper"]["key"], "custom_scraper_example")
            self.assertTrue(result["scraper"]["enabled"])

            response = await client.get("/api/scrapers")
            self.assertEqual((await response.json())[0]["filename"], "example.py")

            response = await client.delete("/api/scrapers/custom_scraper_example")
            self.assertEqual(response.status, 200)
            self.assertEqual(await response.json(), {"ok": True})

            response = await client.get("/api/scrapers")
            self.assertEqual(await response.json(), [])

            response = await client.post(
                "/api/scrapers",
                data=b"",
                headers={"Origin": "https://attacker.example"},
            )
            self.assertEqual(response.status, 403)
        finally:
            await client.close()
