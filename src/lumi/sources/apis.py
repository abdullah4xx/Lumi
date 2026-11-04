"""Sources backed by documented public APIs (some need the user's own key)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Optional
from urllib.parse import quote

from ..models import Wallpaper
from .base import (KIND_API, KIND_EXPERIMENTAL, KIND_KEY, Context, Source, clip, ext_is_image,
                   strip_html, to_int)


# 1 ------------------------------------------------------------------ Wallhaven
class Wallhaven(Source):
    key, name, kind = "wallhaven", "Wallhaven", KIND_API
    description = "Community wallpapers, filtered to 4K server-side. An API key is optional."
    homepage = "https://wallhaven.cc"
    key_name = "wallhaven"
    hosts = ("wallhaven.cc",)
    min_interval = 1.4                                # API limit: 45 requests/minute

    async def search(self, ctx: Context, query, page, category):
        params = {
            "q": query, "categories": "010" if category == "Anime" else "111", "purity": "100",
            "atleast": f"{ctx.min_long}x1080", "page": str(page),
            "sorting": "relevance" if query else "toplist", "order": "desc",
        }
        if not query:
            params["topRange"] = "1M"
        if ctx.key("wallhaven"):
            params["apikey"] = ctx.key("wallhaven")
        await ctx.http.throttle(self.key, self.min_interval)
        data = await ctx.http.get_json("https://wallhaven.cc/api/v1/search", params=params)
        out = []
        for d in data.get("data", []):
            thumbs = d.get("thumbs") or {}
            if not d.get("path") or not (thumbs.get("large") or thumbs.get("small")):
                continue
            out.append(Wallpaper(
                id=str(d["id"]), source=self.key, url=d["path"],
                thumb_url=thumbs.get("large") or thumbs["small"],
                width=to_int(d.get("dimension_x")), height=to_int(d.get("dimension_y")),
                title=f"Wallhaven {d['id']}", page_url=d.get("url", ""),
                tags=tuple(t for t in (d.get("category"),) if t),
            ))
        return out


# 2 ------------------------------------------------------------------ Unsplash
class Unsplash(Source):
    key, name, kind = "unsplash", "Unsplash", KIND_KEY
    description = "High-quality photography. Needs a free Access Key (unsplash.com/developers)."
    homepage = "https://unsplash.com"
    key_name, key_required = "unsplash", True
    hosts = ("unsplash.com",)
    min_interval = 0.5

    def _headers(self, ctx):
        return {"Authorization": f"Client-ID {ctx.key('unsplash')}", "Accept-Version": "v1"}

    async def search(self, ctx: Context, query, page, category):
        await ctx.http.throttle(self.key, self.min_interval)
        if query:
            data = await ctx.http.get_json(
                "https://api.unsplash.com/search/photos", headers=self._headers(ctx),
                params={"query": query, "page": str(page), "per_page": "30", "orientation": "landscape"})
            photos = data.get("results", [])
        else:
            photos = await ctx.http.get_json(
                "https://api.unsplash.com/photos", headers=self._headers(ctx),
                params={"page": str(page), "per_page": "30", "order_by": "popular"})
        out = []
        for p in photos if isinstance(photos, list) else []:
            urls, w, h = p.get("urls") or {}, to_int(p.get("width")), to_int(p.get("height"))
            if not urls.get("raw") or not w or not h or max(w, h) < ctx.min_long:
                continue
            out.append(Wallpaper(
                id=p["id"], source=self.key, url=urls["raw"],
                thumb_url=urls.get("small") or urls.get("thumb", ""), width=w, height=h,
                title=clip(p.get("description") or p.get("alt_description") or "Unsplash photo"),
                author=(p.get("user") or {}).get("name", ""), page_url=(p.get("links") or {}).get("html", ""),
                tags=tuple(t.get("title", "") for t in (p.get("tags") or [])[:5] if t.get("title")),
                extra={"download_location": (p.get("links") or {}).get("download_location", "")},
            ))
        return out

    async def on_use(self, ctx, wp):
        loc = wp.extra.get("download_location", "")
        if loc.startswith("https://api.unsplash.com/"):      # required by Unsplash API guidelines
            try:
                await ctx.http.get_json(loc, headers=self._headers(ctx))
            except Exception:  # noqa: BLE001 - tracking is best effort
                pass


# 3 ------------------------------------------------------------------ Pexels
class Pexels(Source):
    key, name, kind = "pexels", "Pexels", KIND_KEY
    description = "Free stock photos. Needs a free API key (pexels.com/api)."
    homepage = "https://www.pexels.com"
    key_name, key_required = "pexels", True
    hosts = ("pexels.com",)
    min_interval = 0.5

    async def search(self, ctx: Context, query, page, category):
        await ctx.http.throttle(self.key, self.min_interval)
        headers = {"Authorization": ctx.key("pexels")}
        if query:
            data = await ctx.http.get_json("https://api.pexels.com/v1/search", headers=headers, params={
                "query": query, "orientation": "landscape", "size": "large", "per_page": "40", "page": str(page)})
        else:
            data = await ctx.http.get_json("https://api.pexels.com/v1/curated", headers=headers,
                                           params={"per_page": "40", "page": str(page)})
        out = []
        for p in data.get("photos", []):
            src = p.get("src") or {}
            if not src.get("original"):
                continue
            out.append(Wallpaper(
                id=str(p["id"]), source=self.key, url=src["original"],
                thumb_url=src.get("medium") or src.get("small", ""),
                width=to_int(p.get("width")), height=to_int(p.get("height")),
                title=clip(p.get("alt") or "Pexels photo"), author=p.get("photographer", ""),
                page_url=p.get("url", "")))
        return out


# 4 ------------------------------------------------------------------ Pixabay
class Pixabay(Source):
    key, name, kind = "pixabay", "Pixabay", KIND_KEY
    description = ("Free images. Needs an API key; full-size (4K) files are only returned to keys "
                   "with Pixabay's 'full API access' approval, otherwise this source yields nothing.")
    homepage = "https://pixabay.com"
    key_name, key_required = "pixabay", True
    hosts = ("pixabay.com",)
    min_interval = 0.7

    async def search(self, ctx: Context, query, page, category):
        await ctx.http.throttle(self.key, self.min_interval)
        data = await ctx.http.get_json("https://pixabay.com/api/", params={
            "key": ctx.key("pixabay"), "q": query, "image_type": "photo", "orientation": "horizontal",
            "min_width": str(ctx.min_long), "per_page": "50", "page": str(page),
            "safesearch": "true", "order": "popular"})
        out = []
        for h in data.get("hits", []):
            full = h.get("imageURL")              # only present with full API access
            if not full:
                continue
            out.append(Wallpaper(
                id=str(h["id"]), source=self.key, url=full,
                thumb_url=h.get("webformatURL") or h.get("previewURL", ""),
                width=to_int(h.get("imageWidth")), height=to_int(h.get("imageHeight")),
                title=clip(h.get("tags", "Pixabay image")), author=h.get("user", ""),
                page_url=h.get("pageURL", ""),
                tags=tuple(t.strip() for t in str(h.get("tags", "")).split(",")[:5] if t.strip())))
        return out


# 5 ------------------------------------------------------------------ Reddit
class Reddit(Source):
    key, name, kind = "reddit", "Reddit", KIND_API
    description = "Top wallpaper posts from r/wallpapers, r/EarthPorn and friends (configurable list)."
    homepage = "https://www.reddit.com"
    hosts = ("redd.it",)
    min_interval = 1.2

    def __init__(self):
        self._after = {}

    async def search(self, ctx: Context, query, page, category):
        subs = ctx.cfg.get("reddit_subs") or ["wallpapers"]
        if page <= 1:
            self._after.clear()
        sub = subs[(max(page, 1) - 1) % len(subs)]          # rotate, so each sub's cursor advances
        ck = (sub, query)
        params = {"limit": "50", "raw_json": "1", "t": "month", "sort": "top"}
        if query:
            url, params["q"], params["restrict_sr"] = f"https://www.reddit.com/r/{sub}/search.json", query, "1"
        else:
            url = f"https://www.reddit.com/r/{sub}/top.json"
        if page > 1 and ck in self._after:
            params["after"] = self._after[ck]
        await ctx.http.throttle(self.key, self.min_interval)
        data = (await ctx.http.get_json(url, params=params)).get("data", {})
        if data.get("after"):
            self._after[ck] = data["after"]
        else:
            self._after.pop(ck, None)
        out = []
        for child in data.get("children", []):
            d = child.get("data", {})
            if ctx.cfg.get("safe_search", True) and d.get("over_18"):
                continue
            img = d.get("url_overridden_by_dest") or d.get("url") or ""
            if not ext_is_image(img) or not self.host_ok(img):
                continue
            first = ((d.get("preview") or {}).get("images") or [{}])[0]
            src, thumbs = first.get("source") or {}, first.get("resolutions") or []
            thumb = next((t["url"] for t in thumbs if t.get("width", 0) >= 480), None) or (thumbs[-1]["url"] if thumbs else img)
            out.append(Wallpaper(
                id=d.get("id", img), source=self.key, url=img, thumb_url=thumb,
                width=to_int(src.get("width")), height=to_int(src.get("height")),
                title=clip(d.get("title", "")), author=f"u/{d.get('author', '?')}",
                page_url="https://www.reddit.com" + d.get("permalink", ""), tags=(f"r/{sub}",)))
        return out


# 6 ------------------------------------------------------------------ Wikimedia Commons
class Wikimedia(Source):
    key, name, kind = "wikimedia", "Wikimedia Commons", KIND_API
    description = "Freely licensed images; featured pictures by default, size-filtered with CirrusSearch."
    homepage = "https://commons.wikimedia.org"
    hosts = ("wikimedia.org",)
    min_interval = 0.6

    async def search(self, ctx: Context, query, page, category):
        size = f"filew:>{ctx.min_long - 1}"
        if query:
            term = f"{query} filetype:bitmap {size}"
        else:
            term = f'filetype:bitmap {size} incategory:"Featured pictures on Wikimedia Commons"'
        await ctx.http.throttle(self.key, self.min_interval)
        data = await ctx.http.get_json("https://commons.wikimedia.org/w/api.php", params={
            "action": "query", "format": "json", "formatversion": "2", "generator": "search",
            "gsrsearch": term, "gsrnamespace": "6", "gsrlimit": "30", "gsroffset": str((page - 1) * 30),
            "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata", "iiurlwidth": "640",
            "iiextmetadatafilter": "Artist|ObjectName"})
        pages = sorted((data.get("query") or {}).get("pages", []), key=lambda p: p.get("index", 0))
        out = []
        for p in pages:
            ii = (p.get("imageinfo") or [{}])[0]
            if ii.get("mime") not in ("image/jpeg", "image/png") or not ii.get("url"):
                continue
            meta = ii.get("extmetadata") or {}
            title = strip_html((meta.get("ObjectName") or {}).get("value", "")) or p.get("title", "").replace("File:", "")
            out.append(Wallpaper(
                id=str(p.get("pageid", p.get("title"))), source=self.key, url=ii["url"],
                thumb_url=ii.get("thumburl") or ii["url"], width=to_int(ii.get("width")), height=to_int(ii.get("height")),
                title=clip(title), author=clip(strip_html((meta.get("Artist") or {}).get("value", "")), 60),
                page_url=ii.get("descriptionurl", "")))
        return out


# 7 ------------------------------------------------------------------ Bing
class Bing(Source):
    key, name, kind = "bing", "Bing Image of the Day", KIND_API
    description = "Daily Bing photos in UHD; pages rotate through regional markets for variety."
    homepage = "https://www.bing.com"
    hosts = ("bing.com",)
    supports_query = False
    MARKETS = ["en-US", "en-GB", "de-DE", "fr-FR", "ja-JP", "es-ES", "it-IT", "pt-BR", "en-CA", "en-AU", "en-IN", "zh-CN"]

    async def search(self, ctx: Context, query, page, category):
        page = max(page, 1)
        mkt = self.MARKETS[(page - 1) % len(self.MARKETS)]
        idx = ((page - 1) // len(self.MARKETS)) * 8
        data = await ctx.http.get_json("https://www.bing.com/HPImageArchive.aspx",
                                       params={"format": "js", "idx": str(idx), "n": "8", "mkt": mkt})
        out = []
        for img in data.get("images", []):
            base = img.get("urlbase")
            if not base:
                continue
            title = img.get("title") or img.get("copyright", "Bing image")
            out.append(Wallpaper(
                id=img.get("hsh") or base, source=self.key, url=f"https://www.bing.com{base}_UHD.jpg",
                thumb_url=f"https://www.bing.com{base}_320x180.jpg", width=3840, height=2160, extra={"size": "assumed"},
                title=clip(title), author=clip(img.get("copyright", ""), 80),
                page_url=img.get("copyrightlink", "")))
        return out


# 8 ------------------------------------------------------------------ NASA APOD
class NasaApod(Source):
    key, name, kind = "nasa_apod", "NASA APOD", KIND_API
    description = "Astronomy Picture of the Day (random picks). Uses DEMO_KEY unless you add a NASA key."
    homepage = "https://apod.nasa.gov"
    key_name = "nasa"
    hosts = ("nasa.gov",)
    supports_query = False

    async def search(self, ctx: Context, query, page, category):
        if page > 1 and not ctx.key("nasa"):
            return []          # DEMO_KEY allows only ~30 requests/hour: one random batch per refresh
        data = await ctx.http.get_json("https://api.nasa.gov/planetary/apod", params={
            "api_key": ctx.key("nasa") or "DEMO_KEY", "count": "24", "thumbs": "true"})
        out = []
        for d in data if isinstance(data, list) else []:
            if d.get("media_type") != "image":
                continue
            full = d.get("hdurl") or d.get("url")
            if not full or not ext_is_image(full):
                continue
            date = d.get("date", "")
            out.append(Wallpaper(
                id=date or full, source=self.key, url=full, thumb_url=d.get("url") or full,
                title=clip(d.get("title", "APOD")), author=clip(d.get("copyright", "NASA").replace("\n", " "), 60),
                page_url=f"https://apod.nasa.gov/apod/ap{date[2:4]}{date[5:7]}{date[8:10]}.html" if len(date) == 10 else ""))
        return out


# 9 ------------------------------------------------------------------ ArtStation
class ArtStation(Source):
    key, name, kind = "artstation", "ArtStation (trending)", KIND_EXPERIMENTAL
    description = "Unofficial trending feed; ArtStation has no public API and often blocks scripts."
    homepage = "https://www.artstation.com"
    hosts = ("artstation.com",)
    default_enabled = False
    supports_query = False

    async def search(self, ctx: Context, query, page, category):
        data = await ctx.http.get_json("https://www.artstation.com/api/v2/community/explore/projects/trending.json",
                                       params={"page": str(page), "dimension": "all", "per_page": "30"})
        out = []
        for d in data.get("data", []):
            hash_id = d.get("hash_id")
            thumb = d.get("smaller_square_cover_url") or d.get("small_square_cover_url") or ""
            if not hash_id or not thumb:
                continue
            out.append(Wallpaper(
                id=hash_id, source=self.key, url=d.get("url", ""), thumb_url=thumb,
                title=clip(d.get("title", "")), author=(d.get("user") or {}).get("full_name", ""),
                page_url=d.get("url", ""), extra={"hash_id": hash_id}))
        return out

    async def resolve(self, ctx, wp):
        data = await ctx.http.get_json(f"https://www.artstation.com/projects/{quote(wp.extra.get('hash_id', wp.id))}.json")
        assets = [a for a in data.get("assets", []) if a.get("has_image") and a.get("image_url")]
        if not assets:
            raise ValueError("no image assets")
        best = max(assets, key=lambda a: to_int(a.get("width")) or 0)
        return best["image_url"]


# 10 ----------------------------------------------------------------- DeviantArt
class DeviantArt(Source):
    key, name, kind = "deviantart", "DeviantArt (RSS)", KIND_EXPERIMENTAL
    description = "Public RSS search feed; result sizes vary, so 4K filtering happens after download."
    homepage = "https://www.deviantart.com"
    hosts = ("deviantart.com", "deviantart.net", "wixmp.com")
    default_enabled = False
    min_interval = 1.0

    async def search(self, ctx: Context, query, page, category):
        await ctx.http.throttle(self.key, self.min_interval)
        text = await ctx.http.get_text("https://backend.deviantart.com/rss.xml", params={
            "type": "deviation", "q": f"{query or 'wallpaper 4k'} sort:popular", "offset": str((page - 1) * 60)})
        if "<!DOCTYPE" in text or "<!ENTITY" in text:          # refuse DTD tricks (entity expansion)
            raise ValueError("unexpected DTD in feed")
        ns = {"media": "http://search.yahoo.com/mrss/"}
        out = []
        for item in ET.fromstring(text).iter("item"):
            mc = item.find("media:content", ns)
            if mc is None or mc.get("medium") != "image" or not mc.get("url"):
                continue
            thumbs = item.findall("media:thumbnail", ns)
            thumb = (max(thumbs, key=lambda t: to_int(t.get("width")) or 0).get("url") if thumbs else mc.get("url"))
            link = (item.findtext("link") or "").strip()
            out.append(Wallpaper(
                id=link or mc.get("url"), source=self.key, url=mc.get("url"), thumb_url=thumb,
                width=to_int(mc.get("width")), height=to_int(mc.get("height")),
                title=clip(item.findtext("title") or ""), author=clip((item.findtext("media:credit", namespaces=ns) or ""), 60),
                page_url=link))
        return out


# 11 ----------------------------------------------------------------- Alpha Coders
class AlphaCoders(Source):
    key, name, kind = "alphacoders", "Alpha Coders", KIND_KEY
    description = "Wallpaper Abyss. Needs an API key from alphacoders.com (their API is key-only)."
    homepage = "https://wall.alphacoders.com"
    key_name, key_required = "alphacoders", True
    hosts = ("alphacoders.com",)
    min_interval = 1.0

    async def search(self, ctx: Context, query, page, category):
        await ctx.http.throttle(self.key, self.min_interval)
        data = await ctx.http.get_json("https://wall.alphacoders.com/api2.0/get.php", params={
            "auth": ctx.key("alphacoders"), "method": "search" if query else "popular", "term": query,
            "page": str(page), "info_level": "2", "width": str(ctx.min_long), "height": "2160", "operator": "min"})
        out = []
        for w in data.get("wallpapers", []):
            if not w.get("url_image"):
                continue
            out.append(Wallpaper(
                id=str(w["id"]), source=self.key, url=w["url_image"], thumb_url=w.get("url_thumb") or w["url_image"],
                width=to_int(w.get("width")), height=to_int(w.get("height")),
                title=clip(w.get("sub_category") or w.get("category") or "Alpha Coders"), page_url=w.get("url_page", ""),
                tags=tuple(t for t in (w.get("category"), w.get("sub_category")) if t)))
        return out


# 16 ----------------------------------------------------------------- Desktoppr
class Desktoppr(Source):
    key, name, kind = "desktoppr", "Desktoppr", KIND_API
    description = "The public API is no longer available; open the Desktoppr website."
    homepage = "https://www.desktoppr.co"
    hosts = ("desktoppr.co", "amazonaws.com", "cloudfront.net")
    supports_query = False
    default_enabled = False
    manual_only = True
    min_interval = 0.8

    async def search(self, ctx: Context, query, page, category):
        await ctx.http.throttle(self.key, self.min_interval)
        data = await ctx.http.get_json("https://api.desktoppr.co/1/wallpapers", params={"page": str(page)})
        out = []
        for w in data.get("response", []):
            image = w.get("image") or {}
            url = image.get("url")
            thumb = (image.get("preview") or {}).get("url") or (image.get("thumb") or {}).get("url") or url
            if not url:
                continue
            uploader = w.get("uploader")
            out.append(Wallpaper(
                id=str(w["id"]), source=self.key, url=url, thumb_url=thumb,
                width=to_int(w.get("width")), height=to_int(w.get("height")),
                title=f"Desktoppr {w['id']}", author=uploader if isinstance(uploader, str) else "",
                page_url=w.get("url", "")))
        return out


# 19 ----------------------------------------------------------------- Flickr
class Flickr(Source):
    key, name, kind = "flickr", "Flickr (CC / Commons)", KIND_KEY
    description = "Openly licensed and Commons photos in original size. Needs a Flickr API key."
    homepage = "https://www.flickr.com"
    key_name, key_required = "flickr", True
    hosts = ("staticflickr.com", "flickr.com")
    min_interval = 0.6

    async def search(self, ctx: Context, query, page, category):
        await ctx.http.throttle(self.key, self.min_interval)
        data = await ctx.http.get_json("https://www.flickr.com/services/rest/", params={
            "method": "flickr.photos.search", "api_key": ctx.key("flickr"), "text": query or "landscape wallpaper",
            "license": "1,2,3,4,5,6,9,10", "media": "photos", "sort": "interestingness-desc", "safe_search": "1",
            "content_types": "0", "extras": "url_o,o_dims,owner_name", "per_page": "50", "page": str(page),
            "format": "json", "nojsoncallback": "1"})
        out = []
        for p in (data.get("photos") or {}).get("photo", []):
            w, h = to_int(p.get("width_o")), to_int(p.get("height_o"))
            if not p.get("url_o") or not w or not h:
                continue                           # original size not available for this photo
            out.append(Wallpaper(
                id=str(p["id"]), source=self.key, url=p["url_o"],
                thumb_url=f"https://live.staticflickr.com/{p['server']}/{p['id']}_{p['secret']}_z.jpg",
                width=w, height=h, title=clip(p.get("title", "Flickr photo")), author=p.get("ownername", ""),
                page_url=f"https://www.flickr.com/photos/{p.get('owner')}/{p['id']}"))
        return out


# ------------------------------------------------------------------ Danbooru
class Danbooru(Source):
    key, name, kind = "danbooru", "Danbooru", KIND_API
    description = "Anime artwork limited to General-rated images."
    homepage = "https://danbooru.donmai.us"
    hosts = ("donmai.us",)
    min_interval = 1.0

    async def search(self, ctx: Context, query, page, category):
        term = (query or category or "landscape").strip().lower()
        tag = re.sub(r"[^a-z0-9_]+", "_", term).strip("_")[:60] or "landscape"
        await ctx.http.throttle(self.key, self.min_interval)
        data = await ctx.http.get_json("https://danbooru.donmai.us/posts.json", params={
            "tags": f"{tag} rating:g", "limit": "40", "page": str(max(1, page)),
        })
        out = []
        for post in data if isinstance(data, list) else []:
            full_url = post.get("file_url")
            thumb_url = post.get("preview_file_url") or post.get("large_file_url") or full_url
            width, height = to_int(post.get("image_width")), to_int(post.get("image_height"))
            if (
                post.get("rating") != "g"
                or not ext_is_image(full_url or "")
                or not width or not height
                or max(width, height) < 1920
                or min(width, height) < 1080
                or not ctx.meets_min(width, height)
                or not self.host_ok(full_url)
                or not self.host_ok(thumb_url)
            ):
                continue
            tags = (post.get("tag_string") or "").split()
            characters = (post.get("tag_string_character") or "").split()
            artists = (post.get("tag_string_artist") or "").split()
            out.append(Wallpaper(
                id=str(post["id"]),
                source=self.key,
                url=full_url,
                thumb_url=thumb_url,
                width=width,
                height=height,
                title=clip((characters or tags or ["Danbooru image"])[0].replace("_", " ")),
                author=clip(artists[0].replace("_", " ")) if artists else "",
                page_url=f"{self.homepage}/posts/{post['id']}",
                tags=tuple(tag.replace("_", " ") for tag in tags[:10]),
                extra={"rating": "general"},
            ))
        return out


# -------------------------------------------------------------------- Picsum
class Picsum(Source):
    key, name, kind = "picsum", "Picsum (random photos)", KIND_EXPERIMENTAL
    description = "Random landscape photos without text search; enable explicitly to use this feed."
    homepage = "https://picsum.photos"
    hosts = ("picsum.photos",)
    supports_query = False
    default_enabled = False
    min_interval = 0.5

    async def search(self, ctx: Context, query, page, category):
        if query:
            return []
        await ctx.http.throttle(self.key, self.min_interval)
        data = await ctx.http.get_json("https://picsum.photos/v2/list", params={
            "page": str(max(1, page)), "limit": "30",
        })
        out = []
        for photo in data if isinstance(data, list) else []:
            photo_id = str(photo.get("id") or "")
            full_url = photo.get("download_url") or ""
            width, height = to_int(photo.get("width")), to_int(photo.get("height"))
            thumb_url = f"{self.homepage}/id/{photo_id}/640/360"
            if (
                not photo_id
                or not width or not height
                or max(width, height) < 1920
                or min(width, height) < 1080
                or not ctx.meets_min(width, height)
                or not self.host_ok(full_url)
                or not self.host_ok(thumb_url)
            ):
                continue
            out.append(Wallpaper(
                id=photo_id,
                source=self.key,
                url=full_url,
                thumb_url=thumb_url,
                width=width,
                height=height,
                title=clip(f"Photo by {photo.get('author') or 'Unknown'}"),
                author=clip(photo.get("author") or ""),
                page_url=photo.get("url") or "",
            ))
        return out


# 20 ----------------------------------------------------------------- Google Earth View
class EarthView(Source):
    key, name, kind = "earthview", "Google Earth View", KIND_EXPERIMENTAL
    description = "Community-maintained list of Earth View images (typically ~2K, below true 4K)."
    homepage = "https://earthview.withgoogle.com"
    hosts = ("gstatic.com", "jsdelivr.net", "githubusercontent.com", "withgoogle.com")
    default_enabled = False
    supports_query = False
    LIST_URL = "https://cdn.jsdelivr.net/gh/limhenry/earthview@master/earthview.json"

    def __init__(self):
        self._items: Optional[list] = None

    async def search(self, ctx: Context, query, page, category):
        if self._items is None:
            data = await ctx.http.get_json(self.LIST_URL)
            self._items = [d for d in data if isinstance(d, dict) and d.get("image")] if isinstance(data, list) else []
        chunk = self._items[(page - 1) * 30: page * 30]
        out = []
        for d in chunk:
            img = d["image"]
            slug = str(d.get("slug") or d.get("id") or img.rsplit("/", 1)[-1])
            title = ", ".join(x for x in (d.get("region"), d.get("country")) if x) or "Earth View"
            out.append(Wallpaper(id=slug, source=self.key, url=img, thumb_url=img, title=clip(title),
                                 author="Google Earth View", page_url=d.get("map", "")))
        return out


# 21 ----------------------------------------------------------------- NASA Image and Video Library
class NasaLibrary(Source):
    key, name, kind = "nasa_library", "NASA Image Library", KIND_API
    description = "NASA's public image archive (no key). Full-size files are resolved when you open an image."
    homepage = "https://images.nasa.gov"
    hosts = ("nasa.gov",)
    min_interval = 0.5

    async def search(self, ctx: Context, query, page, category):
        await ctx.http.throttle(self.key, self.min_interval)
        data = await ctx.http.get_json("https://images-api.nasa.gov/search", params={
            "q": query or "galaxy nebula earth", "media_type": "image", "page": str(page), "page_size": "40"})
        out = []
        for it in (data.get("collection") or {}).get("items", []):
            meta = (it.get("data") or [{}])[0]
            thumb = next((l["href"] for l in it.get("links", []) if l.get("render") == "image"), "")
            nid = meta.get("nasa_id")
            if not nid or not thumb:
                continue
            out.append(Wallpaper(
                id=nid, source=self.key, url=thumb, thumb_url=thumb, title=clip(meta.get("title", nid)),
                author=clip(meta.get("photographer") or meta.get("center") or "NASA", 60),
                page_url=f"https://images.nasa.gov/details/{quote(nid)}",
                tags=tuple(str(k) for k in (meta.get("keywords") or [])[:5]),
                extra={"asset": f"https://images-api.nasa.gov/asset/{quote(nid)}"}))
        return out

    async def resolve(self, ctx, wp):
        data = await ctx.http.get_json(wp.extra.get("asset") or f"https://images-api.nasa.gov/asset/{quote(wp.id)}")
        hrefs = [i.get("href", "") for i in (data.get("collection") or {}).get("items", [])]
        for marker in ("~orig", "~large"):
            for h in hrefs:
                if marker in h and ext_is_image(h):
                    return h.replace("http://", "https://")
        raise ValueError("no downloadable image in asset manifest")
