import unittest

from lumi.sources import FourKWallpapers
from lumi.sources.base import Context


LISTING = """
<div id="pics-list">
  <p class="wallpapers__item">
    <meta itemprop="keywords" content="City, Night, Neon">
    <a itemprop="url" class="wallpapers__canvas_image" href="/games/city-night-123.html"
       title="City Night Wallpaper">
      <img itemprop="thumbnail" src="/images/walls/thumbs/123.jpg" alt="City Night">
    </a>
  </p>
</div>
<p class="pages"><a href="?page=2">2</a></p>
<div id="packs-list"><p class="wallpapers__item"><a href="/related-999.html">
  <img src="/images/walls/thumbs/999.jpg"></a></p></div>
"""

DETAIL = """
<a href="/images/wallpapers/city-night-1920x1080-123.jpg">Full HD</a>
<a href="/images/wallpapers/city-night-3840x2160-123.jpg">4K UHD</a>
<a href="/images/wallpapers/city-night-5120x2880-123.jpg">Original</a>
"""


class FixtureHttp:
    def __init__(self):
        self.urls = []
        self.detail = DETAIL

    async def throttle(self, *_):
        pass

    async def get_text(self, url):
        self.urls.append(url)
        return self.detail if url.endswith(".html") and "city-night" in url else LISTING


class FourKWallpapersTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.source = FourKWallpapers()
        self.http = FixtureHttp()
        self.ctx = Context(self.http, {"min_long_side": 3840})

    def test_listing_urls_support_search_and_pagination(self):
        self.assertEqual(
            self.source.list_url("desktop wallpaper", 2),
            "https://4kwallpapers.com/search/?q=desktop-wallpaper&page=2",
        )
        self.assertEqual(
            self.source.list_url("", 2),
            "https://4kwallpapers.com/?page=2",
        )

    async def test_listing_extracts_only_main_gallery_and_resolves_largest_image(self):
        items = await self.source.search(self.ctx, "", 1, None)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].id, "123")
        self.assertEqual(items[0].title, "City Night")
        self.assertEqual(items[0].tags, ("City", "Night", "Neon"))
        self.assertEqual(items[0].thumb_url, "https://4kwallpapers.com/images/walls/thumbs/123.jpg")

        url = await self.source.resolve(self.ctx, items[0])

        self.assertEqual(
            url,
            "https://4kwallpapers.com/images/wallpapers/city-night-5120x2880-123.jpg",
        )

    async def test_resolution_rejects_images_below_configured_minimum(self):
        self.http.detail = '<a href="/images/wallpapers/city-night-1920x1080-123.jpg">Full HD</a>'
        ctx = Context(self.http, {"min_long_side": 3840})
        items = await self.source.search(ctx, "", 1, None)

        with self.assertRaisesRegex(ValueError, "below the configured minimum"):
            await self.source.resolve(ctx, items[0])
