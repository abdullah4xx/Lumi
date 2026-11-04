import base64
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from lumi.classifier import classify_with_gemini, interpret_wallpaper_request


class FixtureHttp:
    def __init__(self, response):
        self.response = response
        self.call = None

    async def get_json(self, url, params=None, headers=None, method="GET", data=None):
        self.call = {
            "url": url,
            "params": params,
            "headers": headers,
            "method": method,
            "payload": json.loads(data),
        }
        return self.response


class GeminiClassifierTests(unittest.IsolatedAsyncioTestCase):
    async def test_sends_resized_image_and_normalizes_categories(self):
        http = FixtureHttp({"candidates": [{
            "content": {"parts": [{"text": json.dumps({"categories": [
                {"name": "Nature", "confidence": 0.94},
                {"name": "Space", "confidence": 0.62},
                {"name": "Unknown", "confidence": 1.0},
            ]})}]},
        }]})
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "wallpaper.png"
            Image.new("RGB", (20, 10), "blue").save(path)
            result = await classify_with_gemini(http, path, "fixture-key", "blue landscape")

        self.assertEqual(result, [("Nature", 0.94), ("Space", 0.62)])
        self.assertEqual(http.call["method"], "POST")
        self.assertEqual(http.call["params"], {"key": "fixture-key"})
        self.assertEqual(http.call["headers"]["Content-Type"], "application/json")
        self.assertTrue(http.call["url"].endswith(":generateContent"))
        image_part = http.call["payload"]["contents"][0]["parts"][1]["inline_data"]
        self.assertEqual(image_part["mime_type"], "image/jpeg")
        self.assertTrue(base64.b64decode(image_part["data"]))

    async def test_rejects_responses_without_supported_categories(self):
        http = FixtureHttp({"candidates": [{
            "content": {"parts": [{"text": '{"categories":[{"name":"not-a-category"}]}'}]},
        }]})
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "wallpaper.png"
            Image.new("RGB", (4, 4), "blue").save(path)
            with self.assertRaisesRegex(ValueError, "supported category"):
                await classify_with_gemini(http, path, "fixture-key")

    async def test_interprets_arabic_wallpaper_request_as_english_search_query(self):
        http = FixtureHttp({"candidates": [{
            "content": {"parts": [{"text": json.dumps({
                "query": "misty mountain lake at sunrise",
                "category": "Nature",
            })}]},
        }]})
        result = await interpret_wallpaper_request(http, "عاوز خلفية بحيرة بين الجبال وقت الشروق", "fixture-key")

        self.assertEqual(result, {"query": "misty mountain lake at sunrise", "category": "Nature"})
        self.assertEqual(http.call["method"], "POST")
        self.assertEqual(http.call["params"], {"key": "fixture-key"})
        self.assertIn("Understand Arabic", http.call["payload"]["contents"][0]["parts"][0]["text"])
        self.assertEqual(http.call["payload"]["generationConfig"]["maxOutputTokens"], 128)

    async def test_discards_unsupported_category_and_rejects_empty_query(self):
        http = FixtureHttp({"candidates": [{
            "content": {"parts": [{"text": '{"query":"blue ocean","category":"Unsupported"}'}]},
        }]})
        result = await interpret_wallpaper_request(http, "blue ocean", "fixture-key")
        self.assertEqual(result, {"query": "blue ocean", "category": None})

        http.response = {"candidates": [{
            "content": {"parts": [{"text": '{"query":" ","category":null}'}]},
        }]}
        with self.assertRaisesRegex(ValueError, "empty search query"):
            await interpret_wallpaper_request(http, "blue ocean", "fixture-key")
