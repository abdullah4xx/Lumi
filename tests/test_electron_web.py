import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from aiohttp.test_utils import TestClient, TestServer

from lumi.config import Config
from lumi.http import HttpError
from lumi.local import LocalManager
from lumi.models import Wallpaper
from lumi.sources import build_registry
from lumi.store import Store
from lumi.web import WebCompanionServer


class EmptyEngine:
    sources = {}
    http = object()

    def enabled_keys(self):
        return []

    async def search(self, query, category, page, keys, seen, on_batch):
        return {}

    async def close(self):
        return None

    async def fetch_full(self, wallpaper):
        return SimpleNamespace(path=Path(wallpaper.url))

    async def fetch_preview(self, wallpaper):
        return Path(wallpaper.url)

    def prune(self, keep=None, clear_all=False):
        return 0


class DesktopApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = Config(path=self.root / "config.json")
        self.store = Store(directory=self.root / "data")
        self.local_mgr = LocalManager(self.config)
        self.engine = EmptyEngine()
        server = WebCompanionServer(
            self.config,
            self.engine,
            self.store,
            self.local_mgr,
            ui_dir=Path(__file__).parents[1] / "ui",
        )
        self.web_server = server
        self.client = TestClient(TestServer(server.app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.temp.cleanup()

    async def test_ui_and_categories_are_served_from_the_active_ui(self):
        response = await self.client.get("/")
        self.assertEqual(response.status, 200)
        html = await response.text()
        self.assertIn("<title>lumi</title>", html)
        self.assertIn('id="wallpaper-context-menu"', html)
        self.assertIn('data-category="local"', html)
        self.assertNotIn('class="glass__actions"', html)
        self.assertIn('data-api-key="gemini"', html)

        response = await self.client.get("/api/categories")
        self.assertEqual(response.status, 200)
        self.assertIn("Games", await response.json())
        response = await self.client.get("/i18n.js")
        self.assertEqual(response.status, 200)
        self.assertIn("setLanguage", await response.text())
        response = await self.client.get("/fonts/almotlaq-regular.ttf")
        self.assertEqual(response.status, 200)

    async def test_settings_are_persisted_without_exposing_api_key_values(self):
        response = await self.client.put(
            "/api/settings",
            json={"theme": "dark", "api_keys": {"wallhaven": "private-key", "gemini": "gemini-secret"}},
        )
        self.assertEqual(response.status, 200)
        settings = await response.json()
        self.assertEqual(settings["theme"], "dark")
        self.assertEqual(settings["render_pixel_budget"], 8_000_000)
        self.assertTrue(settings["api_keys"]["wallhaven"])
        self.assertTrue(settings["api_keys"]["gemini"])
        self.assertNotIn("private-key", str(settings))
        self.assertNotIn("gemini-secret", str(settings))

        response = await self.client.put("/api/settings", json={"unknown_setting": True})
        self.assertEqual(response.status, 400)

    async def test_render_pixel_budget_can_be_selected_and_is_validated(self):
        response = await self.client.put("/api/settings", json={"render_pixel_budget": 12_000_000})
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())["render_pixel_budget"], 12_000_000)

        response = await self.client.put("/api/settings", json={"render_pixel_budget": 16_000_000})
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())["render_pixel_budget"], 8_000_000)

    async def test_source_catalog_lists_api_state_and_manual_website_links(self):
        self.engine.sources = build_registry()
        self.config.set("api_keys", {"openverse_id": "client-id"})
        response = await self.client.get("/api/sources")
        self.assertEqual(response.status, 200)
        sources = {source["key"]: source for source in await response.json()}
        self.assertTrue(sources["openverse"]["enabled"])
        self.assertEqual(sources["openverse"]["key_status"], {
            "openverse_id": True,
            "openverse_secret": False,
        })
        self.assertNotIn("client-id", str(sources["openverse"]))
        self.assertTrue(sources["rijksmuseum"]["needs_key"])
        self.assertFalse(sources["rijksmuseum"]["key_saved"])
        self.assertFalse(sources["artstation"]["manual_only"])
        self.assertEqual(sources["artstation"]["homepage"], "https://www.artstation.com")
        self.assertTrue(sources["artstation"]["experimental"])
        self.assertFalse(sources["earthview"]["manual_only"])
        self.assertTrue(sources["desktoppr"]["manual_only"])
        self.assertFalse(sources["desktoppr"]["enabled"])

    async def test_source_catalog_exposes_latest_search_failures(self):
        self.engine.sources = build_registry()
        self.web_server._source_statuses = {
            "artstation": SimpleNamespace(state="error", count=0, message="HTTP 403"),
        }
        response = await self.client.get("/api/sources")
        sources = {source["key"]: source for source in await response.json()}
        self.assertEqual(sources["artstation"]["last_status"], "error")
        self.assertEqual(sources["artstation"]["last_message"], "HTTP 403")

    async def test_gemini_backend_requires_key_before_classifying(self):
        self.config.set("ai_backend", "gemini")
        response = await self.client.post("/api/classify", json={
            "id": "test", "source": "local", "url": str(self.root / "missing.jpg"),
            "title": "test image", "tags": [],
        })
        self.assertEqual(response.status, 400)
        self.assertIn("Gemini API key", (await response.json())["error"])

    async def test_gemini_models_requires_key_and_returns_models_supported_by_key(self):
        response = await self.client.get("/api/gemini/models")
        self.assertEqual(response.status, 400)
        self.assertEqual((await response.json())["code"], "AI_NO_KEY")

        self.config.set("api_keys", {"gemini": "fixture-key"})
        self.engine.http = SimpleNamespace(get_json=AsyncMock(return_value={
            "models": [
                {
                    "name": "models/gemini-2.5-flash",
                    "displayName": "Gemini 2.5 Flash",
                    "supportedGenerationMethods": ["generateContent"],
                },
                {
                    "name": "models/gemini-embedding-001",
                    "displayName": "Gemini Embedding",
                    "supportedGenerationMethods": ["embedContent"],
                },
                {
                    "name": "models/imagen-4.0-generate-001",
                    "displayName": "Imagen 4",
                    "supportedGenerationMethods": ["generateContent"],
                },
            ],
        }))

        response = await self.client.get("/api/gemini/models")

        self.assertEqual(response.status, 200)
        self.assertEqual(await response.json(), {"models": [{
            "name": "gemini-2.5-flash",
            "display_name": "Gemini 2.5 Flash",
        }]})
        self.engine.http.get_json.assert_awaited_once_with(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": "fixture-key", "pageSize": 1000},
        )

    async def test_gemini_models_returns_safe_error_for_invalid_key(self):
        self.config.set("api_keys", {"gemini": "secret-fixture-key"})
        self.engine.http = SimpleNamespace(
            get_json=AsyncMock(side_effect=HttpError("HTTP 403", status=403)),
        )

        response = await self.client.get("/api/gemini/models")
        result = await response.json()

        self.assertEqual(response.status, 400)
        self.assertEqual(result["code"], "AI_INVALID_KEY")
        self.assertNotIn("secret-fixture-key", str(result))

    async def test_settings_accept_model_ids_discovered_from_gemini(self):
        response = await self.client.put(
            "/api/settings", json={"gemini_model": "gemini-3.1-pro-preview"},
        )

        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())["gemini_model"], "gemini-3.1-pro-preview")

    async def test_assistant_search_requires_key_and_valid_request(self):
        response = await self.client.post("/api/assistant/search", json={"prompt": "mountain at sunrise"})
        self.assertEqual(response.status, 400)
        self.assertIn("Gemini API key", (await response.json())["error"])

        self.config.set("api_keys", {"gemini": "fixture-key"})
        response = await self.client.post("/api/assistant/search", json={"prompt": "  "})
        self.assertEqual(response.status, 400)
        response = await self.client.post("/api/assistant/search", json={"prompt": ["not", "text"]})
        self.assertEqual(response.status, 400)

        response = await self.client.post("/api/assistant/search", json={"prompt": "x" * 501})
        self.assertEqual(response.status, 400)

    async def test_assistant_search_uses_gemini_intent_and_returns_carousel_wallpapers(self):
        self.config.set("api_keys", {"gemini": "fixture-key"})
        wallpaper = Wallpaper(
            id="assistant-result", source="wallhaven", url="https://example.test/image.jpg",
            thumb_url="https://example.test/thumb.jpg", width=3840, height=2160,
            title="Misty mountain lake", tags=("mountains", "lake"),
        )
        search_call = {}

        async def search(query, category, page, keys, seen, on_batch):
            search_call.update(query=query, category=category, page=page, keys=keys)
            on_batch("wallhaven", [wallpaper])
            return {}

        self.engine.search = search
        intent = {"query": "misty mountain lake at sunrise", "category": "Nature"}
        with patch("lumi.web.interpret_wallpaper_request", new=AsyncMock(return_value=intent)) as interpret:
            response = await self.client.post(
                "/api/assistant/search", json={"prompt": "عاوز خلفية بحيرة بين الجبال وقت الشروق"}
            )

        self.assertEqual(response.status, 200)
        result = await response.json()
        self.assertEqual(result["query"], intent["query"])
        self.assertEqual(result["category"], "Nature")
        self.assertEqual(result["wallpapers"][0]["id"], "assistant-result")
        self.assertEqual(search_call, {
            "query": intent["query"], "category": "Nature", "page": 1, "keys": [],
        })
        interpret.assert_awaited_once_with(
            self.engine.http, "عاوز خلفية بحيرة بين الجبال وقت الشروق",
            "fixture-key", "gemini-3.5-flash",
        )
        self.assertEqual(
            self.web_server._wallpapers[wallpaper.uid],
            wallpaper,
        )

    async def test_full_quality_thumbnail_route_uses_preview_service(self):
        wallpaper = {
            "id": "full-image",
            "source": "wallhaven",
            "url": str(self.root / "full.jpg"),
            "thumb_url": "",
            "title": "Full image",
            "tags": [],
        }
        response = await self.client.post("/api/favorite", json=wallpaper)
        self.assertEqual(response.status, 200)
        self.engine.fetch_preview = lambda wp: self._preview_path(wp)
        self.root.joinpath("full.jpg").write_bytes(b"preview")
        response = await self.client.get("/api/wallpapers?collection=favorites")
        item = (await response.json())[0]
        response = await self.client.get(f"/api/thumb?quality=full&uid={item['source']}:{item['id']}")
        self.assertEqual(response.status, 200)
        self.assertEqual(await response.read(), b"preview")

    async def _preview_path(self, wallpaper):
        return Path(wallpaper.url)

    async def test_favourites_are_shared_with_the_collection_api(self):
        wallpaper = {
            "id": "test-image",
            "source": "wallhaven",
            "url": "https://example.test/wallpaper.jpg",
            "thumb_url": "",
            "title": "Test wallpaper",
            "tags": ["nature"],
        }
        response = await self.client.post("/api/favorite", json=wallpaper)
        self.assertEqual((await response.json())["favorite"], True)

        response = await self.client.get("/api/wallpapers?collection=favorites")
        wallpapers = await response.json()
        self.assertEqual([item["title"] for item in wallpapers], ["Test wallpaper"])
        self.assertTrue(wallpapers[0]["favorite"])

    async def test_strict_category_filter_uses_saved_classifications(self):
        wallpaper = {
            "id": "classified-image",
            "source": "wallhaven",
            "url": "https://example.test/classified.jpg",
            "thumb_url": "",
            "title": "Classified wallpaper",
            "tags": [],
        }
        response = await self.client.post("/api/favorite", json=wallpaper)
        self.assertEqual(response.status, 200)
        self.store.set_classes("wallhaven:classified-image", [("Games", 0.9)])
        self.config.set("strict_ai_filter", True)

        response = await self.client.get("/api/wallpapers?collection=favorites&category=Nature")
        self.assertEqual(await response.json(), [])

        response = await self.client.get("/api/wallpapers?collection=favorites&category=Games")
        wallpapers = await response.json()
        self.assertEqual(wallpapers[0]["categories"], [["Games", 0.9]])

    async def test_local_images_are_only_returned_for_the_local_collection(self):
        wallpaper = {
            "id": "device-image",
            "source": "local",
            "url": str(self.root / "device.jpg"),
            "thumb_url": "",
            "title": "Device image",
            "tags": [],
        }
        response = await self.client.post("/api/favorite", json=wallpaper)
        self.assertEqual(response.status, 200)
        with patch.object(self.local_mgr, "scan_folders", return_value=[
            Wallpaper.from_dict(wallpaper)
        ]):
            response = await self.client.get("/api/wallpapers?category=Nature")
            self.assertEqual(await response.json(), [])

            response = await self.client.get("/api/wallpapers?collection=favorites")
            self.assertEqual(await response.json(), [])

            response = await self.client.get("/api/wallpapers?collection=local")
            local_wallpapers = await response.json()
        self.assertEqual([item["source"] for item in local_wallpapers], ["local"])

    async def test_wallpaper_search_uses_requested_page_without_exact_title_filtering(self):
        wallpaper = Wallpaper(
            id="semantic-match", source="wallhaven", url="https://example.test/image.jpg",
            thumb_url="https://example.test/thumb.jpg", width=3840, height=2160,
            title="Quiet mountain scenery", tags=("lake",),
        )
        search_call = {}

        async def search(query, category, page, keys, seen, on_batch):
            search_call.update(query=query, category=category, page=page)
            on_batch("wallhaven", [wallpaper])
            return {}

        self.engine.enabled_keys = lambda: ["wallhaven"]
        self.engine.search = search
        response = await self.client.get("/api/wallpapers?q=misty%20lake&page=2")

        self.assertEqual(response.status, 200)
        self.assertEqual(search_call, {"query": "misty lake", "category": None, "page": 2})
        self.assertEqual([item["id"] for item in await response.json()], ["semantic-match"])

    async def test_wallpaper_search_rejects_invalid_page(self):
        response = await self.client.get("/api/wallpapers?page=invalid")
        self.assertEqual(response.status, 400)
        self.assertIn("Page must be a positive integer", (await response.json())["error"])

    async def test_classify_returns_and_persists_results_for_the_wallpaper_uid(self):
        image_path = self.root / "wallpaper.jpg"
        image_path.write_bytes(b"test image")
        wallpaper = {
            "id": "classify-image",
            "source": "local",
            "url": str(image_path),
            "thumb_url": "",
            "title": "Game wallpaper",
            "tags": ["game"],
        }
        with patch("lumi.web.Classifier.classify", return_value=[("Games", 0.91)]) as classify:
            response = await self.client.post("/api/classify", json=wallpaper)

        self.assertEqual(response.status, 200)
        result = await response.json()
        self.assertEqual(result["uid"], "local:classify-image")
        self.assertEqual(result["categories"], [["Games", 0.91]])
        self.assertEqual(self.store.get_classes(result["uid"]), [("Games", 0.91)])
        classify.assert_called_once()
