import unittest

from lumi.sources.apis import AlphaCoders, Danbooru, Pexels, Picsum, Unsplash
from lumi.sources.base import Context


class FixtureHttp:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def throttle(self, *_):
        pass

    async def get_json(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


class WallpaperSiteApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_danbooru_forces_general_rating_and_filters_dimensions(self):
        http = FixtureHttp([
            {
                "id": 1, "rating": "g", "file_ext": "jpg",
                "file_url": "https://cdn.donmai.us/original/a.jpg",
                "preview_file_url": "https://cdn.donmai.us/preview/a.jpg",
                "image_width": 4327, "image_height": 2064,
                "tag_string": "landscape sky cloud", "tag_string_character": "miku_(vocaloid)",
                "tag_string_artist": "some_artist",
            },
            {
                "id": 2, "rating": "e", "file_ext": "jpg",
                "file_url": "https://cdn.donmai.us/original/b.jpg",
                "image_width": 7680, "image_height": 4320,
            },
            {
                "id": 3, "rating": "g", "file_ext": "jpg",
                "file_url": "https://cdn.donmai.us/original/c.jpg",
                "image_width": 2048, "image_height": 711,
            },
        ])
        items = await Danbooru().search(
            Context(http, {"min_long_side": 3840, "landscape_only": True}),
            "Hatsune Miku!",
            2,
            None,
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].id, "1")
        self.assertEqual(items[0].title, "miku (vocaloid)")
        self.assertEqual(items[0].author, "some artist")
        self.assertEqual(items[0].extra["rating"], "general")
        self.assertEqual(http.calls[0][0], "https://danbooru.donmai.us/posts.json")
        self.assertEqual(http.calls[0][1]["params"], {
            "tags": "hatsune_miku rating:g", "limit": "40", "page": "2",
        })

    async def test_picsum_only_returns_landscape_4k_for_browse_requests(self):
        http = FixtureHttp([
            {
                "id": "0", "author": "Alejandro Escamilla",
                "width": 5000, "height": 3333,
                "url": "https://unsplash.com/photos/0",
                "download_url": "https://picsum.photos/id/0/5000/3333",
            },
            {
                "id": "1", "author": "Small photo",
                "width": 1600, "height": 1000,
                "url": "https://unsplash.com/photos/1",
                "download_url": "https://picsum.photos/id/1/1600/1000",
            },
        ])
        source = Picsum()
        ctx = Context(http, {"min_long_side": 3840, "landscape_only": True})

        items = await source.search(ctx, "", 1, None)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].url, "https://picsum.photos/id/0/5000/3333")
        self.assertEqual(items[0].thumb_url, "https://picsum.photos/id/0/640/360")
        self.assertEqual(items[0].resolution, "5000×3333")
        self.assertFalse(source.supports_query)

    async def test_unsplash_uses_the_original_image_url_and_dimensions(self):
        raw_url = "https://images.unsplash.com/photo-original?ixlib=test"
        http = FixtureHttp({"results": [{
            "id": "photo-1",
            "urls": {"raw": raw_url, "small": "https://images.unsplash.com/photo-small"},
            "width": 6000,
            "height": 4000,
            "links": {"html": "https://unsplash.com/photos/photo-1"},
            "user": {"name": "Photographer"},
        }]})
        source = Unsplash()

        items = await source.search(
            Context(http, {"min_long_side": 3840, "api_keys": {"unsplash": "test-key"}}),
            "mountains",
            1,
            None,
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].url, raw_url)
        self.assertEqual((items[0].width, items[0].height), (6000, 4000))
        self.assertEqual(items[0].thumb_url, "https://images.unsplash.com/photo-small")

    async def test_pexels_uses_original_url(self):
        original = "https://images.pexels.com/photos/1/original.jpeg"
        http = FixtureHttp({"photos": [{
            "id": 1,
            "src": {"original": original, "medium": "https://images.pexels.com/photos/1/medium.jpeg"},
            "width": 5000,
            "height": 3000,
            "url": "https://www.pexels.com/photo/1",
        }]})
        items = await Pexels().search(
            Context(http, {"min_long_side": 3840, "api_keys": {"pexels": "test-key"}}),
            "landscape",
            1,
            None,
        )

        self.assertEqual(items[0].url, original)
        self.assertEqual((items[0].width, items[0].height), (5000, 3000))

    async def test_alpha_coders_uses_the_api_image_url(self):
        full = "https://images.alphacoders.com/1/full.jpg"
        http = FixtureHttp({"wallpapers": [{
            "id": 1,
            "url_image": full,
            "url_thumb": "https://images.alphacoders.com/1/thumb.jpg",
            "width": 5120,
            "height": 2880,
            "url_page": "https://wall.alphacoders.com/big.php?i=1",
        }]})
        items = await AlphaCoders().search(
            Context(http, {"min_long_side": 3840, "api_keys": {"alphacoders": "test-key"}}),
            "landscape",
            1,
            None,
        )

        self.assertEqual(items[0].url, full)
        self.assertEqual((items[0].width, items[0].height), (5120, 2880))
