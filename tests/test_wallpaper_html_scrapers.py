import unittest

from lumi.sources import GelbooruHtml, HDWallpapers, KonachanHtml, SafebooruHtml, WallhavenHtml, WallpaperFlare, WallpapersCraft, WallpapersWide, YandeHtml
from lumi.sources.base import Context
from lumi.models import Wallpaper

WALLHAVEN_ROBOTS_URL = "https://wallhaven.cc/robots.txt"
KONACHAN_ROBOTS_URL = "https://konachan.net/robots.txt"
YANDE_ROBOTS_URL = "https://yande.re/robots.txt"
SAFEBOORU_ROBOTS_URL = "https://safebooru.org/robots.txt"
GELBOORU_ROBOTS_URL = "https://gelbooru.com/robots.txt"
ALLOW_ALL_ROBOTS = "User-agent: *\nAllow: /\n"


class FixtureHttp:
    def __init__(self, pages):
        self.pages = pages
        self.urls = []

    async def throttle(self, *_):
        pass

    async def get_text(self, url):
        self.urls.append(url)
        return self.pages[url]


class WallpaperHtmlScraperTests(unittest.IsolatedAsyncioTestCase):
    async def test_wallhaven_website_search_is_sfw_and_uses_html_results(self):
        source = WallhavenHtml()
        listing_url = source.list_url("nature", 1, None)
        listing = """
        <ul id="thumbs">
          <li><figure class="thumb thumb-a1b2c3 thumb-sfw thumb-general" data-wallpaper-id="a1b2c3">
            <img data-src="https://th.wallhaven.cc/small/a1/a1b2c3.jpg" src="">
            <a class="preview" href="https://wallhaven.cc/w/a1b2c3"></a>
            <span class="wall-res">3840 x 2160</span>
          </figure></li>
          <li><figure class="thumb thumb-d4e5f6 thumb-sketchy thumb-anime" data-wallpaper-id="d4e5f6">
            <img data-src="https://th.wallhaven.cc/small/d4/d4e5f6.jpg" src="">
            <a class="preview" href="https://wallhaven.cc/w/d4e5f6"></a>
            <span class="wall-res">7680 x 4320</span>
          </figure></li>
          <li><figure class="thumb thumb-a1b2c3 thumb-sfw thumb-general" data-wallpaper-id="a1b2c3">
            <img data-src="https://th.wallhaven.cc/small/a1/a1b2c3.jpg" src="">
            <a class="preview" href="https://wallhaven.cc/w/a1b2c3"></a>
            <span class="wall-res">3840 x 2160</span>
          </figure></li>
        </ul>
        """
        http = FixtureHttp({WALLHAVEN_ROBOTS_URL: ALLOW_ALL_ROBOTS, listing_url: listing})
        ctx = Context(http, {"min_long_side": 1920, "landscape_only": True})

        items = await source.search(ctx, "nature", 1, None)

        self.assertIn("purity=100", listing_url)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].id, "a1b2c3")
        self.assertEqual(items[0].width, 3840)
        self.assertEqual(items[0].extra["rating"], "safe")

    async def test_wallhaven_detail_resolves_original_and_rejects_non_sfw(self):
        source = WallhavenHtml()
        detail_url = "https://wallhaven.cc/w/a1b2c3"
        detail = """
        <title>Forest - 3840x2160 Wallpaper - wallhaven.cc</title>
        <dl><dt>Purity</dt><dd><span class="purity sfw">SFW</span></dd></dl>
        <main><img id="wallpaper" src="https://w.wallhaven.cc/full/a1/wallhaven-a1b2c3.jpg"></main>
        """
        http = FixtureHttp({WALLHAVEN_ROBOTS_URL: ALLOW_ALL_ROBOTS, detail_url: detail})
        ctx = Context(http, {"min_long_side": 1920})
        listing_ctx = Context(FixtureHttp({
            WALLHAVEN_ROBOTS_URL: ALLOW_ALL_ROBOTS,
            source.list_url("forest", 1, None): """
            <figure class="thumb thumb-a1b2c3 thumb-sfw" data-wallpaper-id="a1b2c3">
              <img src="https://th.wallhaven.cc/small/a1/a1b2c3.jpg">
              <a class="preview" href="https://wallhaven.cc/w/a1b2c3"></a>
              <span class="wall-res">3840 x 2160</span>
            </figure>
            """
        }), {"min_long_side": 1920})
        wallpaper = (await source.search(listing_ctx, "forest", 1, None))[0]

        self.assertEqual(await source.resolve(ctx, wallpaper), "https://w.wallhaven.cc/full/a1/wallhaven-a1b2c3.jpg")

        http.pages[detail_url] = detail.replace("SFW", "NSFW")
        with self.assertRaisesRegex(ValueError, "not marked SFW"):
            await source.resolve(ctx, wallpaper)

    def test_wallhaven_website_uses_safe_category_and_query_pagination(self):
        source = WallhavenHtml()
        anime = source.list_url("cat", 2, "Anime")
        nature = source.list_url("forest", 2, "Nature")
        self.assertIn("categories=010", anime)
        self.assertIn("purity=100", anime)
        self.assertIn("page=2", anime)
        self.assertIn("categories=111", nature)

    async def test_wallhaven_website_honors_robots_txt(self):
        source = WallhavenHtml()
        listing_url = source.list_url("nature", 1, None)
        http = FixtureHttp({
            WALLHAVEN_ROBOTS_URL: "User-agent: *\nDisallow: /search\n",
            listing_url: "<html></html>",
        })
        ctx = Context(http, {"min_long_side": 1920})

        with self.assertRaisesRegex(ValueError, "robots.txt disallows"):
            await source.search(ctx, "nature", 1, None)

    async def test_konachan_search_uses_safe_rating_full_image_and_unique_ids(self):
        source = KonachanHtml()
        listing_url = source.list_url("landscape rating:e", 1, None)
        listing = """
        <ul id="post-list-posts">
          <li id="p1001">
            <a class="thumb" href="/post/show/1001">
              <img class="preview" src="/data/preview/thumb-1001.jpg"
                alt="Rating: Safe Score: 5 Tags: mountain sunrise landscape User: user">
            </a>
            <a class="directlink largeimg" href="/image/full-1001.jpg">
              <span class="directlink-res">3840 x 2160</span>
            </a>
          </li>
          <li id="p1002">
            <a class="thumb" href="/post/show/1002">
              <img class="preview" src="/data/preview/thumb-1002.jpg"
                alt="Rating: Explicit Score: 2 Tags: landscape User: user">
            </a>
            <a class="directlink largeimg" href="/image/full-1002.jpg">
              <span class="directlink-res">7680 x 4320</span>
            </a>
          </li>
          <li id="p1003">
            <a class="thumb" href="/post/show/1003">
              <img class="preview" src="/data/preview/thumb-1003.jpg"
                alt="Rating: Safe Score: 2 Tags: landscape User: user">
            </a>
            <a class="directlink largeimg" href="/image/full-1003.jpg">
              <span class="directlink-res">1280 x 720</span>
            </a>
          </li>
          <li id="p1001">
            <a class="thumb" href="/post/show/1001">
              <img class="preview" src="/data/preview/thumb-1001.jpg"
                alt="Rating: Safe Score: 5 Tags: mountain sunrise landscape User: user">
            </a>
            <a class="directlink largeimg" href="/image/full-1001.jpg">
              <span class="directlink-res">3840 x 2160</span>
            </a>
          </li>
        </ul>
        """
        http = FixtureHttp({KONACHAN_ROBOTS_URL: ALLOW_ALL_ROBOTS, listing_url: listing})
        ctx = Context(http, {"min_long_side": 1920, "landscape_only": True})

        items = await source.search(ctx, "landscape rating:e", 1, None)

        self.assertIn("rating%3As", listing_url)
        self.assertNotIn("rating%3Ae", listing_url)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].id, "1001")
        self.assertEqual(items[0].url, "https://konachan.net/image/full-1001.jpg")
        self.assertEqual(items[0].thumb_url, "https://konachan.net/data/preview/thumb-1001.jpg")
        self.assertEqual(items[0].width, 3840)
        self.assertEqual(items[0].extra["rating"], "safe")
        self.assertEqual(await source.resolve(ctx, items[0]), items[0].url)

    def test_konachan_uses_observed_page_parameter_and_forces_safe_rating(self):
        source = KonachanHtml()
        page_url = source.list_url("anime", 2, "Anime")
        self.assertIn("page=2&tags=anime+rating%3As", page_url)

    async def test_konachan_honors_robots_txt(self):
        source = KonachanHtml()
        listing_url = source.list_url("landscape", 1)
        http = FixtureHttp({
            KONACHAN_ROBOTS_URL: "User-agent: *\nDisallow: /post\n",
            listing_url: "<html></html>",
        })
        ctx = Context(http, {"min_long_side": 1920})

        with self.assertRaisesRegex(ValueError, "robots.txt disallows"):
            await source.search(ctx, "landscape", 1, None)

    async def test_yande_search_forces_safe_rating_and_uses_original_link(self):
        source = YandeHtml()
        listing_url = source.list_url("landscape rating:e", 1, None)
        listing = """
        <li id="p2001">
          <a class="thumb" href="/post/show/2001">
            <img class="preview" src="https://assets.yande.re/data/preview/thumb-2001.jpg"
              alt="Rating: Safe Score: 7 Tags: mountain sunrise landscape User: user">
          </a>
          <a class="directlink largeimg" href="https://files.yande.re/image/full-2001.jpg">
            <span class="directlink-res">5120 x 2880</span>
          </a>
        </li>
        <li id="p2002">
          <a class="thumb" href="/post/show/2002">
            <img class="preview" src="https://assets.yande.re/data/preview/thumb-2002.jpg"
              alt="Rating: Questionable Score: 4 Tags: landscape User: user">
          </a>
          <a class="directlink largeimg" href="https://files.yande.re/image/full-2002.jpg">
            <span class="directlink-res">7680 x 4320</span>
          </a>
        </li>
        """
        http = FixtureHttp({YANDE_ROBOTS_URL: "Sitemap: https://yande.re/sitemap.xml.gz\n", listing_url: listing})
        ctx = Context(http, {"min_long_side": 3840, "landscape_only": True})

        items = await source.search(ctx, "landscape rating:e", 1, None)

        self.assertIn("rating%3As", listing_url)
        self.assertNotIn("rating%3Ae", listing_url)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].id, "2001")
        self.assertEqual(items[0].url, "https://files.yande.re/image/full-2001.jpg")
        self.assertEqual(items[0].thumb_url, "https://assets.yande.re/data/preview/thumb-2001.jpg")
        self.assertEqual(items[0].resolution, "5120×2880")
        self.assertEqual(items[0].extra["rating"], "safe")

    async def test_yande_honors_robots_txt(self):
        source = YandeHtml()
        listing_url = source.list_url("landscape", 1)
        http = FixtureHttp({
            YANDE_ROBOTS_URL: "User-agent: *\nDisallow: /post\n",
            listing_url: "<html></html>",
        })
        ctx = Context(http, {"min_long_side": 1920})

        with self.assertRaisesRegex(ValueError, "Yande.re.*robots.txt disallows"):
            await source.search(ctx, "landscape", 1, None)

    async def test_safebooru_search_checks_general_rating_and_original_dimensions(self):
        source = SafebooruHtml()
        listing_url = source.list_url("landscape rating:explicit", 1, None)
        listing = """
        <a id="p3001" href="/index.php?page=post&amp;s=view&amp;id=3001">
          <img class="preview" title="landscape highres score:1 rating:general"
            src="/thumbnails/1/thumb-3001.jpg">
        </a>
        <a id="p3002" href="/index.php?page=post&amp;s=view&amp;id=3002">
          <img class="preview" title="landscape highres score:1 rating:questionable"
            src="/thumbnails/1/thumb-3002.jpg">
        </a>
        <a id="p3003" href="/index.php?page=post&amp;s=view&amp;id=3003">
          <img class="preview" title="landscape highres score:1 rating:general"
            src="/thumbnails/1/thumb-3003.jpg">
        </a>
        """
        detail_3001 = """
        <div>Size: 3840x2160 Rating: General</div>
        <a href="https://safebooru.org//images/1/original-3001.jpg">Original image</a>
        """
        detail_3002 = """
        <div>Size: 7680x4320 Rating: Questionable</div>
        <a href="https://safebooru.org//images/1/original-3002.jpg">Original image</a>
        """
        detail_3003 = """
        <div>Size: 1280x720 Rating: General</div>
        <a href="https://safebooru.org//images/1/original-3003.jpg">Original image</a>
        """
        http = FixtureHttp({
            SAFEBOORU_ROBOTS_URL: "User-agent: *\nDisallow: /admin/\nDisallow: /img/\n",
            listing_url: listing,
            "https://safebooru.org/index.php?page=post&s=view&id=3001": detail_3001,
            "https://safebooru.org/index.php?page=post&s=view&id=3003": detail_3003,
        })
        ctx = Context(http, {"min_long_side": 1920, "landscape_only": True})

        items = await source.search(ctx, "landscape rating:explicit", 1, None)

        self.assertIn("highres", listing_url)
        self.assertIn("rating%3Ageneral", listing_url)
        self.assertNotIn("rating%3Aexplicit", listing_url)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].id, "3001")
        self.assertEqual(items[0].url, "https://safebooru.org//images/1/original-3001.jpg")
        self.assertEqual(items[0].resolution, "3840×2160")
        self.assertEqual(items[0].extra["rating"], "general")
        self.assertEqual(await source.resolve(ctx, items[0]), items[0].url)

    def test_safebooru_uses_observed_pid_pagination(self):
        source = SafebooruHtml()
        page_url = source.list_url("wallpaper", 2, None)
        self.assertIn("pid=42", page_url)

    async def test_safebooru_honors_robots_txt(self):
        source = SafebooruHtml()
        listing_url = source.list_url("landscape", 1)
        http = FixtureHttp({
            SAFEBOORU_ROBOTS_URL: "User-agent: *\nDisallow: /index.php\n",
            listing_url: "<html></html>",
        })
        ctx = Context(http, {"min_long_side": 1920})

        with self.assertRaisesRegex(ValueError, "robots.txt disallows"):
            await source.search(ctx, "landscape", 1, None)

    async def test_gelbooru_search_checks_general_rating_and_original_dimensions(self):
        source = GelbooruHtml()
        listing_url = source.list_url("landscape rating:explicit", 1, None)
        listing = """
        <a id="p4001" href="/index.php?page=post&amp;s=view&amp;id=4001">
          <img title="landscape highres score:1 rating:general"
            src="/thumbnails/1/thumbnail-4001.jpg">
        </a>
        <a id="p4002" href="/index.php?page=post&amp;s=view&amp;id=4002">
          <img title="landscape highres score:1 rating:general"
            src="/thumbnails/1/thumbnail-4002.jpg">
        </a>
        <a id="p4003" href="/index.php?page=post&amp;s=view&amp;id=4003">
          <img title="landscape highres score:1 rating:general"
            src="/thumbnails/1/thumbnail-4003.jpg">
        </a>
        """
        detail_4001 = """
        <div>Size: 4327x2064 Rating: General</div>
        <a href="https://img4.gelbooru.com/images/1/original-4001.jpg">Original image</a>
        """
        detail_4002 = """
        <div>Size: 2048x711 Rating: General</div>
        <a href="https://img4.gelbooru.com/images/1/original-4002.jpg">Original image</a>
        """
        detail_4003 = """
        <div>Size: 7680x4320 Rating: Questionable</div>
        <a href="https://img4.gelbooru.com/images/1/original-4003.jpg">Original image</a>
        """
        http = FixtureHttp({
            GELBOORU_ROBOTS_URL: "User-agent: *\nDisallow: /public\n",
            "https://img4.gelbooru.com/robots.txt": ALLOW_ALL_ROBOTS,
            listing_url: listing,
            "https://gelbooru.com/index.php?page=post&s=view&id=4001": detail_4001,
            "https://gelbooru.com/index.php?page=post&s=view&id=4002": detail_4002,
            "https://gelbooru.com/index.php?page=post&s=view&id=4003": detail_4003,
        })
        ctx = Context(http, {"min_long_side": 1920, "landscape_only": True})

        items = await source.search(ctx, "landscape rating:explicit", 1, None)

        self.assertIn("highres", listing_url)
        self.assertIn("rating%3Ageneral", listing_url)
        self.assertNotIn("rating%3Aexplicit", listing_url)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].id, "4001")
        self.assertEqual(items[0].url, "https://img4.gelbooru.com/images/1/original-4001.jpg")
        self.assertEqual(items[0].resolution, "4327×2064")
        self.assertEqual(items[0].extra["rating"], "general")
        self.assertEqual(await source.resolve(ctx, items[0]), items[0].url)

    def test_gelbooru_uses_observed_pid_pagination(self):
        source = GelbooruHtml()
        page_url = source.list_url("wallpaper", 2, None)
        self.assertIn("pid=42", page_url)

    async def test_gelbooru_honors_robots_txt(self):
        source = GelbooruHtml()
        listing_url = source.list_url("landscape", 1)
        http = FixtureHttp({
            GELBOORU_ROBOTS_URL: "User-agent: *\nDisallow: /index.php\n",
            listing_url: "<html></html>",
        })
        ctx = Context(http, {"min_long_side": 1920})

        with self.assertRaisesRegex(ValueError, "Gelbooru.*robots.txt disallows"):
            await source.search(ctx, "landscape", 1, None)

    async def test_gelbooru_resolve_rejects_unrated_or_small_images(self):
        source = GelbooruHtml()
        ctx = Context(FixtureHttp({}), {"min_long_side": 1920})
        item = Wallpaper(
            id="4001",
            source=source.key,
            url="https://img4.gelbooru.com/images/1/original-4001.jpg",
            thumb_url="https://img4.gelbooru.com/thumbnails/1/thumbnail-4001.jpg",
            width=4327,
            height=2064,
            extra={"rating": "questionable"},
        )

        with self.assertRaisesRegex(ValueError, "not General-rated"):
            await source.resolve(ctx, item)
    async def test_wallpaperscraft_category_uses_observed_catalog_pagination(self):
        listing_url = "https://wallpaperscraft.com/catalog/nature/page2"
        listing = """
        <img src="https://images.wallpaperscraft.com/image/single/mountain_lake_1749831_300x168.jpg">
        """
        http = FixtureHttp({listing_url: listing})
        source = WallpapersCraft()
        ctx = Context(http, {"min_long_side": 3840})

        items = await source.search(ctx, "", 2, "Nature")

        self.assertEqual(http.urls, [listing_url])
        self.assertEqual([item.id for item in items], ["mountain_lake_1749831"])
        self.assertFalse(source.supports_query)

    async def test_wallpaperscraft_resolves_highest_original_from_detail_page(self):
        listing_url = "https://wallpaperscraft.com/all/3840x2160"
        detail_url = "https://wallpaperscraft.com/wallpaper/mountain_lake_1749831"
        listing = """
        <img src="https://images.wallpaperscraft.com/image/single/mountain_lake_1749831_1280x720.jpg">
        """
        detail = """
        <a href="/download/mountain_lake_1749831/3840x2160">4K</a>
        <a href="/download/mountain_lake_1749831/7680x4320">8K</a>
        """
        download_url = "https://wallpaperscraft.com/download/mountain_lake_1749831/7680x4320"
        download_page = """
        <a href="https://images.wallpaperscraft.com/image/single/mountain_lake_1749831_7680x4320.jpg">Download</a>
        """
        http = FixtureHttp({listing_url: listing, detail_url: detail, download_url: download_page})
        source = WallpapersCraft()
        ctx = Context(http, {"min_long_side": 3840})

        items = await source.search(ctx, "", 1, None)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].page_url, detail_url)
        self.assertEqual(
            await source.resolve(ctx, items[0]),
            "https://images.wallpaperscraft.com/image/single/mountain_lake_1749831_7680x4320.jpg",
        )

    async def test_wallpaperflare_finds_listings_but_does_not_treat_download_page_as_image(self):
        listing_url = "https://www.wallpaperflare.com/search?wallpaper=forest&width=3840&height=2160&page=1"
        detail_url = "https://www.wallpaperflare.com/forest-wallpaper-abc"
        listing = f"""
        <a itemprop="url" href="{detail_url}">
          <img alt="Forest HD wallpaper" src="https://c4.wallpaperflare.com/thumb-preview.jpg">
        </a>
        """
        detail = """
        <a href="/forest-wallpaper-abc/download/3840x2160">4K</a>
        <a href="/forest-wallpaper-abc/download/5120x2880">5K</a>
        """
        http = FixtureHttp({listing_url: listing, detail_url: detail})
        source = WallpaperFlare()
        ctx = Context(http, {"min_long_side": 3840})

        items = await source.search(ctx, "forest", 1, None)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Forest")
        with self.assertRaisesRegex(ValueError, "interactive download verification"):
            await source.resolve(ctx, items[0])

    async def test_wallpaperswide_uses_detail_page_download_not_thumbnail(self):
        listing_url = "https://wallpaperswide.com/landscape-desktop-wallpapers.html"
        detail_url = "https://wallpaperswide.com/mountain_lake-wallpapers.html"
        listing = f"""
        <div class="thumb">
          <a href="{detail_url}">
            <img class="thumb_img" src="https://hd.wallpaperswide.com/thumbs/mountain_lake-t1.jpg"
                 alt="Mountain Lake">
          </a>
        </div>
        """
        detail = """
        <a href="/download/mountain_lake-wallpaper-3840x2160.jpg">4K</a>
        <a href="/download/mountain_lake-wallpaper-5120x2880.jpg">5K</a>
        """
        http = FixtureHttp({listing_url: listing, detail_url: detail})
        source = WallpapersWide()
        ctx = Context(http, {"min_long_side": 3840})

        items = await source.search(ctx, "landscape", 1, None)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].thumb_url, "https://hd.wallpaperswide.com/thumbs/mountain_lake-t1.jpg")
        self.assertEqual(
            await source.resolve(ctx, items[0]),
            "https://wallpaperswide.com/download/mountain_lake-wallpaper-5120x2880.jpg",
        )

    async def test_hdwallpapers_uses_original_link_when_listed_resolutions_are_smaller(self):
        listing_url = "https://www.hdwallpapers.in/latest_wallpapers/page/1/"
        detail_url = "https://www.hdwallpapers.in/mountain_lake-wallpapers.html"
        listing = f"""
        <a href="{detail_url}">
          <img class="thumb_img" src="/thumbs/2026/mountain_lake-t1.jpg" alt="Mountain Lake">
        </a>
        """
        detail = """
        <a href="/download/mountain_lake-1920x1080.jpg">1920 x 1080</a>
        <a href="/download/mountain_lake-2560x1440.jpg">2560 x 1440</a>
        <a href="/download/mountain_lake-HD.jpg">Original</a>
        """
        http = FixtureHttp({listing_url: listing, detail_url: detail})
        source = HDWallpapers()
        ctx = Context(http, {"min_long_side": 3840})

        items = await source.search(ctx, "", 1, None)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Mountain Lake")
        self.assertEqual(
            await source.resolve(ctx, items[0]),
            "https://www.hdwallpapers.in/download/mountain_lake-HD.jpg",
        )

    def test_listing_pagination_urls_match_live_sites(self):
        self.assertTrue(HDWallpapers().list_url("", 2).endswith("/latest_wallpapers/page/2/"))
        self.assertTrue(WallpapersWide().list_url("landscape", 2).endswith("/page/2"))
        self.assertEqual(
            WallpapersCraft().list_url("", 2, "Nature"),
            "https://wallpaperscraft.com/catalog/nature/page2",
        )
        self.assertEqual(
            WallpapersCraft().list_url("", 1, "Minimalist"),
            "https://wallpaperscraft.com/catalog/minimalism",
        )
