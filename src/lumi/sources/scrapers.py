"""Experimental sources with NO public API: they read the sites' HTML.

These are OFF by default, use selectors written from the sites' public page
structure, and may break whenever a site changes its markup (or refuse
automated access). Anything unexpected results in an empty list, never a crash.
Run ``lumi --check-sources`` to see which ones work for you right now.
"""

from __future__ import annotations

import re
from html import unescape
import urllib.robotparser
from html.parser import HTMLParser
from typing import Dict, List, Optional
from urllib.parse import parse_qs, quote, quote_plus, urlencode, urljoin, urlparse

from ..http import HttpError
from ..models import Wallpaper
from .base import KIND_EXPERIMENTAL, Context, Source, clip

class _AnchorParser(HTMLParser):
    """Collect anchors and their first image without depending on attribute order."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.anchors: List[Dict[str, str]] = []
        self.current: Optional[Dict[str, str]] = None

    def handle_starttag(self, tag, raw_attrs):
        attrs = dict(raw_attrs)
        if tag == "a":
            self.current = {"href": attrs.get("href", ""), "text": ""}
        elif tag == "img" and self.current is not None and not self.current.get("image"):
            self.current["image"] = attrs.get("data-src") or attrs.get("src") or ""
            self.current["alt"] = attrs.get("alt", "")

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"] += data

    def handle_endtag(self, tag):
        if tag == "a" and self.current is not None:
            if self.current.get("href"):
                self.anchors.append(self.current)
            self.current = None


class _FourKListingParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []
        self.active = False
        self.depth = 0
        self.current = None

    def handle_starttag(self, tag, raw_attrs):
        attrs = dict(raw_attrs)
        classes = attrs.get("class", "").split()
        if tag == "div" and attrs.get("id") == "pics-list" and not self.active:
            self.active = True
            self.depth = 1
            return
        if not self.active:
            return
        if tag == "div":
            self.depth += 1
        elif tag == "p" and "wallpapers__item" in classes:
            self.current = {"tags": ()}
        elif self.current is not None and tag == "meta" and attrs.get("itemprop") == "keywords":
            self.current["tags"] = tuple(
                value.strip() for value in attrs.get("content", "").split(",") if value.strip()
            )
        elif self.current is not None and tag == "a" and (
            attrs.get("itemprop") == "url" or "wallpapers__canvas_image" in classes
        ):
            self.current["detail_url"] = attrs.get("href", "")
            self.current["title"] = attrs.get("title", "").removesuffix(" Wallpaper")
        elif self.current is not None and tag == "img":
            self.current["thumb_url"] = attrs.get("src", "")
            self.current["title"] = self.current.get("title") or attrs.get("alt", "")

    def handle_endtag(self, tag):
        if not self.active:
            return
        if tag == "p" and self.current is not None:
            if self.current.get("detail_url") and self.current.get("thumb_url"):
                self.items.append(self.current)
            self.current = None
        elif tag == "div":
            self.depth -= 1
            if self.depth == 0:
                self.active = False


class _WallhavenListingParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []
        self.current = None
        self.in_resolution = False

    def handle_starttag(self, tag, raw_attrs):
        attrs = dict(raw_attrs)
        classes = attrs.get("class", "").split()
        if tag == "figure" and "thumb" in classes:
            self.current = {
                "id": attrs.get("data-wallpaper-id", ""),
                "safe": "thumb-sfw" in classes,
            }
        elif self.current is not None and tag == "img":
            self.current["thumb_url"] = attrs.get("data-src") or attrs.get("src", "")
        elif self.current is not None and tag == "a" and "preview" in classes:
            self.current["detail_url"] = attrs.get("href", "")
        elif self.current is not None and tag == "span" and "wall-res" in classes:
            self.in_resolution = True
            self.current["resolution"] = ""

    def handle_data(self, data):
        if self.current is not None and self.in_resolution:
            self.current["resolution"] += data

    def handle_endtag(self, tag):
        if tag == "span" and self.in_resolution:
            self.in_resolution = False
        elif tag == "figure" and self.current is not None:
            if self.current.get("id") and self.current.get("detail_url"):
                self.items.append(self.current)
            self.current = None


class _WallhavenDetailParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.image_url = ""
        self.title = ""
        self.purity = ""
        self.in_title = False
        self.in_purity = False
        self.purity_pending = False

    def handle_starttag(self, tag, raw_attrs):
        attrs = dict(raw_attrs)
        if tag == "img" and attrs.get("id") == "wallpaper":
            self.image_url = attrs.get("src", "")
        elif tag == "title":
            self.in_title = True
        elif tag == "dt":
            self.purity_pending = False
            self._field = ""
            self._in_dt = True
        elif tag == "dd" and self.purity_pending:
            self.in_purity = True

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if getattr(self, "_in_dt", False):
            self._field += data
        if self.in_purity:
            self.purity += data

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        elif tag == "dt":
            self._in_dt = False
            self.purity_pending = self._field.strip().casefold() == "purity"
        elif tag == "dd" and self.in_purity:
            self.in_purity = False
            self.purity_pending = False


class _KonachanListingParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []
        self.current = None
        self.in_resolution = False

    def handle_starttag(self, tag, raw_attrs):
        attrs = dict(raw_attrs)
        classes = attrs.get("class", "").split()
        if tag == "li" and re.fullmatch(r"p\d+", attrs.get("id", "")):
            self.current = {"id": attrs["id"][1:]}
        elif self.current is not None and tag == "img" and "preview" in classes:
            self.current["thumb_url"] = attrs.get("src", "")
            self.current["alt"] = attrs.get("alt", "")
        elif self.current is not None and tag == "a" and {"directlink", "largeimg"} <= set(classes):
            self.current["full_url"] = attrs.get("href", "")
        elif self.current is not None and tag == "a" and "thumb" in classes:
            self.current["detail_url"] = attrs.get("href", "")
        elif self.current is not None and tag == "span" and "directlink-res" in classes:
            self.current["resolution"] = ""
            self.in_resolution = True

    def handle_data(self, data):
        if self.current is not None and self.in_resolution:
            self.current["resolution"] += data

    def handle_endtag(self, tag):
        if tag == "span" and self.in_resolution:
            self.in_resolution = False
        elif tag == "li" and self.current is not None:
            self.items.append(self.current)
            self.current = None


class _SafebooruListingParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []
        self.current = None

    def handle_starttag(self, tag, raw_attrs):
        attrs = dict(raw_attrs)
        if tag == "a" and attrs.get("id", "").startswith("p"):
            self.current = {
                "detail_url": attrs.get("href", ""),
                "title": "",
                "thumb_url": "",
            }
        elif self.current is not None and tag == "img" and "preview" in attrs.get("class", "").split():
            self.current["thumb_url"] = attrs.get("src", "")
            self.current["title"] = attrs.get("title") or attrs.get("alt", "")

    def handle_endtag(self, tag):
        if tag == "a" and self.current is not None:
            if self.current.get("detail_url") and self.current.get("thumb_url"):
                self.items.append(self.current)
            self.current = None


class _GelbooruListingParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []
        self.current = None

    def handle_starttag(self, tag, raw_attrs):
        attrs = dict(raw_attrs)
        if tag == "a" and re.fullmatch(r"p\d+", attrs.get("id", "")):
            self.current = {
                "detail_url": attrs.get("href", ""),
                "title": "",
                "thumb_url": "",
            }
        elif self.current is not None and tag == "img":
            self.current["thumb_url"] = attrs.get("src", "")
            self.current["title"] = attrs.get("title") or attrs.get("alt", "")

    def handle_endtag(self, tag):
        if tag == "a" and self.current is not None:
            if self.current.get("detail_url") and self.current.get("thumb_url"):
                self.items.append(self.current)
            self.current = None


class _SafebooruDetailParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = ""
        self.original_url = ""
        self.current_link = None
        self.current_link_text = ""

    def handle_starttag(self, tag, raw_attrs):
        if tag == "a":
            attrs = dict(raw_attrs)
            self.current_link = attrs.get("href", "")
            self.current_link_text = ""

    def handle_data(self, data):
        self.text += data + " "
        if self.current_link is not None:
            self.current_link_text += data

    def handle_endtag(self, tag):
        if tag == "a" and self.current_link is not None:
            if self.current_link_text.strip().casefold() == "original image":
                self.original_url = self.current_link
            self.current_link = None
            self.current_link_text = ""


class FourKWallpapers(Source):
    key, name, kind = "4kwallpapers", "4K Wallpapers", KIND_EXPERIMENTAL
    description = "Recent and search results from 4kwallpapers.com; resolves the largest listed download."
    homepage = "https://4kwallpapers.com"
    hosts = ("4kwallpapers.com",)
    min_interval = 1.0
    supports_query = True
    _full_image_re = re.compile(
        r"-(?P<width>\d{3,5})x(?P<height>\d{3,5})-\d+\.(?:jpe?g|png|webp)$", re.I
    )

    def list_url(self, query: str, page: int, category: Optional[str] = None) -> str:
        if query:
            path = "/search/?q=" + quote(query.strip().replace(" ", "-"), safe="-")
        elif category:
            slug = re.sub(r"[^a-z0-9]+", "-", category.lower()).strip("-")
            path = f"/{slug}/" if slug else "/"
        else:
            path = "/"
        if page > 1:
            path += ("&" if "?" in path else "?") + f"page={page}"
        return self.homepage + path

    async def search(self, ctx: Context, query, page, category):
        await ctx.http.throttle(self.key, self.min_interval)
        html = await ctx.http.get_text(self.list_url(query, page, category))
        parser = _FourKListingParser()
        parser.feed(html)
        out, seen = [], set()
        for item in parser.items:
            detail_url = urljoin(self.homepage + "/", item["detail_url"])
            thumb_url = urljoin(self.homepage + "/", item["thumb_url"])
            match = re.search(r"-(\d+)\.html$", detail_url)
            item_id = match.group(1) if match else detail_url
            if item_id in seen or not self.host_ok(thumb_url):
                continue
            seen.add(item_id)
            out.append(Wallpaper(
                id=item_id,
                source=self.key,
                url=detail_url,
                thumb_url=thumb_url,
                title=clip(item.get("title") or "4K Wallpapers image"),
                page_url=detail_url,
                tags=item.get("tags", ()),
                extra={"detail_url": detail_url},
            ))
        return out

    async def resolve(self, ctx, wp):
        detail_url = wp.extra.get("detail_url") or wp.page_url
        await ctx.http.throttle(self.key, self.min_interval)
        html = await ctx.http.get_text(detail_url)
        candidates = []
        for raw_url in re.findall(
            r"""href=["']([^"']*/images/wallpapers/[^"']+)["']""", html, re.I
        ):
            image_url = urljoin(detail_url, unescape(raw_url))
            match = self._full_image_re.search(image_url)
            if not match or not self.host_ok(image_url):
                continue
            width, height = int(match.group("width")), int(match.group("height"))
            candidates.append((width * height, width, height, image_url))
        if not candidates:
            raise ValueError("4K Wallpapers detail page has no full-size image links")
        _, width, height, image_url = max(candidates)
        if max(width, height) < ctx.min_long:
            raise ValueError(
                f"4K Wallpapers image maxes out at {width}x{height}, below the configured minimum"
            )
        return image_url


class WallhavenHtml(Source):
    """Website-only Wallhaven scraper; purity is always restricted to SFW."""

    key, name, kind = "wallhaven_web", "Wallhaven (website)", KIND_EXPERIMENTAL
    description = "Searches Wallhaven's website with SFW results only."
    homepage = "https://wallhaven.cc"
    hosts = ("wallhaven.cc",)
    min_interval = 1.0
    supports_query = True

    def __init__(self):
        self._robots = None

    async def _check_robots(self, ctx, url):
        if self._robots is None:
            robots_url = f"{self.homepage}/robots.txt"
            await ctx.http.throttle(self.key, self.min_interval)
            robots_txt = await ctx.http.get_text(robots_url)
            rules = urllib.robotparser.RobotFileParser(robots_url)
            rules.parse(robots_txt.splitlines())
            self._robots = rules
        if not self._robots.can_fetch("Lumi", url):
            raise ValueError(f"Wallhaven robots.txt disallows {url}")

    def list_url(self, query, page, category=None):
        normalized_category = (category or "").strip().casefold()
        categories = "010" if normalized_category == "anime" else "111"
        params = {
            "q": query or normalized_category or "nature",
            "categories": categories,
            "purity": "100",
            "sorting": "relevance",
        }
        if page > 1:
            params["page"] = max(1, int(page))
        return f"{self.homepage}/search?{urlencode(params)}"

    async def search(self, ctx, query, page, category):
        listing_url = self.list_url(query, page, category)
        await self._check_robots(ctx, listing_url)
        await ctx.http.throttle(self.key, self.min_interval)
        html = await ctx.http.get_text(listing_url)
        parser = _WallhavenListingParser()
        parser.feed(html)
        out, seen = [], set()
        category_name = category or ""
        for item in parser.items:
            item_id = item["id"]
            detail_url = urljoin(self.homepage + "/", item["detail_url"])
            thumb_url = item.get("thumb_url", "")
            resolution = re.search(r"(\d{3,5})\s*x\s*(\d{3,5})", item.get("resolution", ""))
            width = int(resolution.group(1)) if resolution else None
            height = int(resolution.group(2)) if resolution else None
            if (
                not item["safe"]
                or item_id in seen
                or not self.host_ok(detail_url)
                or not self.host_ok(thumb_url)
                or not width
                or not height
                or max(width, height) < 1920
                or min(width, height) < 1080
                or not ctx.meets_min(width, height)
            ):
                continue
            seen.add(item_id)
            out.append(Wallpaper(
                id=item_id,
                source=self.key,
                url=detail_url,
                thumb_url=thumb_url,
                width=width,
                height=height,
                title=f"Wallhaven {item_id}",
                page_url=detail_url,
                tags=(category_name,) if category_name else (),
                extra={"category": category_name, "rating": "safe"},
            ))
        return out

    async def resolve(self, ctx, wp):
        if not self.host_ok(wp.page_url):
            raise ValueError("Wallhaven detail URL is outside the site")
        await self._check_robots(ctx, wp.page_url)
        await ctx.http.throttle(self.key, self.min_interval)
        html = await ctx.http.get_text(wp.page_url)
        parser = _WallhavenDetailParser()
        parser.feed(html)
        if parser.purity.strip().casefold() != "sfw":
            raise ValueError("Wallhaven detail page is not marked SFW")
        if not parser.image_url or not self.host_ok(parser.image_url):
            raise ValueError("Wallhaven detail page has no trusted original image")
        return parser.image_url


class KonachanHtml(Source):
    """Website-only Konachan scraper with a mandatory safe-rating filter."""

    key, name, kind = "konachan_web", "Konachan (website)", KIND_EXPERIMENTAL
    description = "Searches Konachan's website for safe-rated, high-resolution images."
    homepage = "https://konachan.net"
    hosts = ("konachan.net",)
    min_interval = 1.0
    supports_query = True

    def __init__(self):
        self._robots = None

    async def _check_robots(self, ctx, url):
        if self._robots is None:
            robots_url = f"{self.homepage}/robots.txt"
            await ctx.http.throttle(self.key, self.min_interval)
            robots_txt = await ctx.http.get_text(robots_url)
            rules = urllib.robotparser.RobotFileParser(robots_url)
            rules.parse(robots_txt.splitlines())
            self._robots = rules
        if not self._robots.can_fetch("Lumi", url):
            raise ValueError(f"{self.name} robots.txt disallows {url}")

    def list_url(self, query, page, category=None):
        term = (query or category or "wallpaper").strip()
        tags = [token for token in term.split() if not token.casefold().startswith("rating:")]
        tags.append("rating:s")
        params = {"tags": " ".join(tags)}
        if page > 1:
            params = {"page": max(1, int(page)), **params}
        return f"{self.homepage}/post?{urlencode(params)}"

    async def search(self, ctx, query, page, category):
        listing_url = self.list_url(query, page, category)
        await self._check_robots(ctx, listing_url)
        await ctx.http.throttle(self.key, self.min_interval)
        html = await ctx.http.get_text(listing_url)
        parser = _KonachanListingParser()
        parser.feed(html)
        out, seen = [], set()
        for item in parser.items:
            item_id = item.get("id", "")
            detail_url = urljoin(self.homepage + "/", item.get("detail_url", ""))
            thumb_url = urljoin(self.homepage + "/", item.get("thumb_url", ""))
            full_url = urljoin(self.homepage + "/", item.get("full_url", ""))
            resolution = re.search(r"(\d{3,5})\s*x\s*(\d{3,5})", item.get("resolution", ""))
            width = int(resolution.group(1)) if resolution else None
            height = int(resolution.group(2)) if resolution else None
            alt = item.get("alt", "")
            is_safe = bool(re.search(r"\bRating:\s*Safe\b", alt, re.I))
            if (
                not item_id
                or item_id in seen
                or not is_safe
                or not self.host_ok(detail_url)
                or not self.host_ok(thumb_url)
                or not self.host_ok(full_url)
                or not width
                or not height
                or max(width, height) < 1920
                or min(width, height) < 1080
                or not ctx.meets_min(width, height)
            ):
                continue
            seen.add(item_id)
            tag_match = re.search(r"\bTags:\s*(.*?)(?:\s+User:|$)", alt)
            title = " ".join(
                token.replace("_", " ")
                for token in (tag_match.group(1).split()[:5] if tag_match else [])
            ) or f"Konachan {item_id}"
            out.append(Wallpaper(
                id=item_id,
                source=self.key,
                url=full_url,
                thumb_url=thumb_url,
                width=width,
                height=height,
                title=clip(title),
                page_url=detail_url,
                tags=(category,) if category else (),
                extra={"category": category or "", "rating": "safe"},
            ))
        return out

    async def resolve(self, ctx, wp):
        if wp.extra.get("rating") != "safe":
            raise ValueError("Konachan result is not marked safe")
        if not self.host_ok(wp.url):
            raise ValueError("Konachan original image URL is outside the site")
        await self._check_robots(ctx, wp.url)
        await ctx.http.throttle(self.key, self.min_interval)
        return wp.url


class YandeHtml(KonachanHtml):
    """Yande.re website scraper, sharing the verified safe Booru markup."""

    key, name = "yande_web", "Yande.re (website)"
    description = "Searches Yande.re's website for safe-rated high-resolution images."
    homepage = "https://yande.re"
    hosts = ("yande.re",)


class SafebooruHtml(Source):
    """Safebooru website scraper restricted to General-rated posts."""

    key, name, kind = "safebooru_web", "Safebooru (website)", KIND_EXPERIMENTAL
    description = "Searches Safebooru's website for General-rated high-resolution images."
    homepage = "https://safebooru.org"
    hosts = ("safebooru.org",)
    min_interval = 1.0
    supports_query = True
    page_size = 42

    def __init__(self):
        self._robots = None

    async def _check_robots(self, ctx, url):
        if self._robots is None:
            robots_url = f"{self.homepage}/robots.txt"
            await ctx.http.throttle(self.key, self.min_interval)
            robots_txt = await ctx.http.get_text(robots_url)
            rules = urllib.robotparser.RobotFileParser(robots_url)
            rules.parse(robots_txt.splitlines())
            self._robots = rules
        if not self._robots.can_fetch("Lumi", url):
            raise ValueError(f"{self.name} robots.txt disallows {url}")

    def list_url(self, query, page, category=None):
        term = (query or category or "wallpaper").strip()
        tags = [
            token for token in term.split()
            if not token.casefold().startswith("rating:") and token.casefold() != "highres"
        ]
        tags.extend(("highres", "rating:general"))
        params = {"page": "post", "s": "list", "tags": " ".join(tags)}
        if page > 1:
            params["pid"] = str((max(1, int(page)) - 1) * self.page_size)
        return f"{self.homepage}/index.php?{urlencode(params)}"

    async def search(self, ctx, query, page, category):
        listing_url = self.list_url(query, page, category)
        await self._check_robots(ctx, listing_url)
        await ctx.http.throttle(self.key, self.min_interval)
        listing_html = await ctx.http.get_text(listing_url)
        parser = _SafebooruListingParser()
        parser.feed(listing_html)
        out, seen = [], set()
        category_name = category or ""
        for item in parser.items:
            title = item["title"]
            detail_url = urljoin(self.homepage + "/", item["detail_url"])
            thumb_url = urljoin(self.homepage + "/", item["thumb_url"])
            post_id = parse_qs(urlparse(detail_url).query).get("id", [""])[0]
            if (
                not post_id
                or post_id in seen
                or "rating:general" not in title.casefold()
                or not self.host_ok(detail_url)
                or not self.host_ok(thumb_url)
            ):
                continue
            seen.add(post_id)
            await self._check_robots(ctx, detail_url)
            await ctx.http.throttle(self.key, self.min_interval)
            detail_html = await ctx.http.get_text(detail_url)
            detail = _SafebooruDetailParser()
            detail.feed(detail_html)
            size = re.search(r"\bSize:\s*(\d{2,5})\s*x\s*(\d{2,5})", detail.text, re.I)
            rating = re.search(r"\bRating:\s*([a-z]+)", detail.text, re.I)
            if not size or not rating or rating.group(1).casefold() != "general":
                continue
            width, height = int(size.group(1)), int(size.group(2))
            full_url = urljoin(detail_url, detail.original_url)
            if (
                max(width, height) < 1920
                or min(width, height) < 1080
                or not ctx.meets_min(width, height)
                or not self.host_ok(full_url)
            ):
                continue
            tags = re.sub(r"\s+score:.*$", "", title, flags=re.I).strip()
            out.append(Wallpaper(
                id=post_id,
                source=self.key,
                url=full_url,
                thumb_url=thumb_url,
                width=width,
                height=height,
                title=clip(" ".join(tags.split()[:6]).replace("_", " ")),
                page_url=detail_url,
                tags=(category_name,) if category_name else (),
                extra={"category": category_name, "rating": "general"},
            ))
        return out

    async def resolve(self, ctx, wp):
        if wp.extra.get("rating") != "general":
            raise ValueError("Safebooru result is not General-rated")
        if not self.host_ok(wp.url):
            raise ValueError("Safebooru original image URL is outside the site")
        if not wp.width or not wp.height or max(wp.width, wp.height) < 1920 or min(wp.width, wp.height) < 1080:
            raise ValueError("Safebooru original image is below 1920x1080")
        await self._check_robots(ctx, wp.url)
        return wp.url


class GelbooruHtml(Source):
    """Gelbooru website scraper restricted to General-rated images."""

    key, name, kind = "gelbooru_web", "Gelbooru (website)", KIND_EXPERIMENTAL
    description = "Searches Gelbooru for General-rated high-resolution images."
    homepage = "https://gelbooru.com"
    hosts = ("gelbooru.com",)
    min_interval = 1.0
    supports_query = True
    page_size = 42

    def __init__(self):
        self._robots = {}

    async def _check_robots(self, ctx, url):
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots:
            robots_url = f"{origin}/robots.txt"
            await ctx.http.throttle(self.key, self.min_interval)
            try:
                robots_txt = await ctx.http.get_text(robots_url)
            except HttpError as exc:
                if exc.status != 404:
                    raise
                robots_txt = ""
            rules = urllib.robotparser.RobotFileParser(robots_url)
            rules.parse(robots_txt.splitlines())
            self._robots[origin] = rules
        if not self._robots[origin].can_fetch("Lumi", url):
            raise ValueError(f"{self.name} robots.txt disallows {url}")

    def list_url(self, query, page, category=None):
        term = (query or category or "wallpaper").strip()
        tags = [
            token for token in term.split()
            if not token.casefold().startswith("rating:") and token.casefold() != "highres"
        ]
        tags.extend(("highres", "rating:general"))
        params = {"page": "post", "s": "list", "tags": " ".join(tags)}
        if page > 1:
            params["pid"] = str((max(1, int(page)) - 1) * self.page_size)
        return f"{self.homepage}/index.php?{urlencode(params)}"

    async def search(self, ctx, query, page, category):
        listing_url = self.list_url(query, page, category)
        await self._check_robots(ctx, listing_url)
        await ctx.http.throttle(self.key, self.min_interval)
        parser = _GelbooruListingParser()
        parser.feed(await ctx.http.get_text(listing_url))
        out, seen = [], set()
        category_name = category or ""
        for item in parser.items:
            title = item["title"]
            detail_url = urljoin(self.homepage + "/", item["detail_url"])
            thumb_url = urljoin(self.homepage + "/", item["thumb_url"])
            post_id = parse_qs(urlparse(detail_url).query).get("id", [""])[0]
            if (
                not post_id
                or post_id in seen
                or "rating:general" not in title.casefold()
                or not self.host_ok(detail_url)
                or not self.host_ok(thumb_url)
            ):
                continue
            seen.add(post_id)
            await self._check_robots(ctx, detail_url)
            await ctx.http.throttle(self.key, self.min_interval)
            detail = _SafebooruDetailParser()
            detail.feed(await ctx.http.get_text(detail_url))
            size = re.search(r"\bSize:\s*(\d{2,5})\s*x\s*(\d{2,5})", detail.text, re.I)
            rating = re.search(r"\bRating:\s*([a-z]+)", detail.text, re.I)
            if not size or not rating or rating.group(1).casefold() != "general":
                continue
            width, height = int(size.group(1)), int(size.group(2))
            full_url = urljoin(detail_url, detail.original_url)
            if (
                max(width, height) < 1920
                or min(width, height) < 1080
                or not ctx.meets_min(width, height)
                or not self.host_ok(full_url)
            ):
                continue
            tags = re.sub(r"\s+score:.*$", "", title, flags=re.I).strip()
            out.append(Wallpaper(
                id=post_id,
                source=self.key,
                url=full_url,
                thumb_url=thumb_url,
                width=width,
                height=height,
                title=clip(" ".join(tags.split()[:6]).replace("_", " ")),
                page_url=detail_url,
                tags=(category_name,) if category_name else (),
                extra={"category": category_name, "rating": "general"},
            ))
        return out

    async def resolve(self, ctx, wp):
        if wp.extra.get("rating") != "general":
            raise ValueError("Gelbooru result is not General-rated")
        if not self.host_ok(wp.url):
            raise ValueError("Gelbooru original image URL is outside the site")
        if (
            not wp.width or not wp.height
            or max(wp.width, wp.height) < 1920
            or min(wp.width, wp.height) < 1080
            or not ctx.meets_min(wp.width, wp.height)
        ):
            raise ValueError("Gelbooru original image is below the configured minimum")
        await self._check_robots(ctx, wp.url)
        return wp.url


class ScrapeSource(Source):
    kind = KIND_EXPERIMENTAL
    default_enabled = False
    supports_query = False
    min_interval = 1.5
    item_re: "re.Pattern[str]"

    def list_url(self, query: str, page: int) -> str:
        raise NotImplementedError

    def make(self, m: "re.Match[str]", ctx: Context) -> Optional[Wallpaper]:
        raise NotImplementedError

    async def search(self, ctx: Context, query, page, category) -> List[Wallpaper]:
        await ctx.http.throttle(self.key, self.min_interval)
        html = await ctx.http.get_text(self.list_url(query, page))
        out, seen = [], set()
        for m in self.item_re.finditer(html):
            wp = self.make(m, ctx)
            if wp and wp.id not in seen and self.host_ok(wp.thumb_url):
                seen.add(wp.id)
                out.append(wp)
        return out


def _anchor_items(html: str) -> List[Dict[str, str]]:
    parser = _AnchorParser()
    parser.feed(html)
    return parser.anchors


def _largest_link(html: str, base_url: str, pattern: "re.Pattern[str]", host_ok) -> Optional[tuple]:
    candidates = []
    for anchor in _anchor_items(html):
        href = unescape(anchor["href"])
        match = pattern.search(urlparse(href).path)
        if not match:
            continue
        image_url = urljoin(base_url, href)
        if not host_ok(image_url):
            continue
        width, height = int(match.group("width")), int(match.group("height"))
        candidates.append((width * height, width, height, image_url))
    return max(candidates) if candidates else None


# 12 ---------------------------------------------------------------- HDWallpapers
class HDWallpapers(ScrapeSource):
    key, name = "hdwallpapers", "HDWallpapers"
    description = "Scrapes hdwallpapers.in listings; available originals vary by wallpaper."
    homepage = "https://www.hdwallpapers.in"
    hosts = ("hdwallpapers.in",)
    def list_url(self, query, page):
        return f"https://www.hdwallpapers.in/latest_wallpapers/page/{max(page, 1)}/"

    async def search(self, ctx, query, page, category):
        await ctx.http.throttle(self.key, self.min_interval)
        html = await ctx.http.get_text(self.list_url(query, page))
        out, seen = [], set()
        for item in _anchor_items(html):
            href = urljoin(self.homepage + "/", unescape(item["href"]))
            path = urlparse(href).path
            image = urljoin(self.homepage + "/", unescape(item.get("image", "")))
            if not path.endswith("-wallpapers.html") or "/thumbs/" not in urlparse(image).path:
                continue
            slug = path.rsplit("/", 1)[-1].removesuffix("-wallpapers.html")
            if slug in seen or not self.host_ok(image):
                continue
            seen.add(slug)
            out.append(Wallpaper(
                id=slug, source=self.key, url=href, thumb_url=image,
                title=clip(item.get("alt") or item.get("text") or slug.replace("_", " ")),
                page_url=href, extra={"detail_url": href},
            ))
        return out

    async def resolve(self, ctx, wp):
        detail_url = wp.extra.get("detail_url") or wp.page_url
        await ctx.http.throttle(self.key, self.min_interval)
        html = await ctx.http.get_text(detail_url)
        explicit = _largest_link(
            html, detail_url,
            re.compile(r"-(?P<width>\d{3,5})x(?P<height>\d{3,5})\.(?:jpe?g|png|webp)$", re.I),
            self.host_ok,
        )
        original = next(
            (
                urljoin(detail_url, unescape(item["href"]))
                for item in _anchor_items(html)
                if re.search(r"-HD\.(?:jpe?g|png|webp)$", urlparse(item["href"]).path, re.I)
                and self.host_ok(urljoin(detail_url, unescape(item["href"])))
            ),
            None,
        )
        if explicit and max(explicit[1], explicit[2]) >= ctx.min_long:
            return explicit[3]
        if original:
            return original
        if explicit:
            raise ValueError(
                f"HDWallpapers image maxes out at {explicit[1]}x{explicit[2]}, below the configured minimum"
            )
        raise ValueError("HDWallpapers detail page has no full-size image links")


# 13 ---------------------------------------------------------------- WallpapersCraft
class WallpapersCraft(ScrapeSource):
    key, name = "wallpaperscraft", "WallpapersCraft"
    description = "Scrapes the 4K catalogue and resolves each wallpaper's largest original."
    homepage = "https://wallpaperscraft.com"
    hosts = ("wallpaperscraft.com",)
    supports_query = False
    item_re = re.compile(r'src="(?P<prefix>https://images\.wallpaperscraft\.com/image/single/(?P<slug>[^"/]+?))_\d+x\d+\.jpg"', re.I)
    _download_re = re.compile(r"/download/[^/]+/(?P<width>\d{3,5})x(?P<height>\d{3,5})/?$", re.I)
    _full_image_re = re.compile(
        r"_(?P<width>\d{3,5})x(?P<height>\d{3,5})\.(?:jpe?g|png|webp)$", re.I
    )
    _catalogs = {
        "3d", "abstract", "animals", "anime", "art", "black", "black_and_white", "cars",
        "city", "dark", "fantasy", "flowers", "food", "holidays", "love", "macro",
        "minimalism", "motorcycles", "music", "nature", "other", "space", "sport",
        "technologies", "textures", "vector", "words",
    }
    _category_aliases = {
        "dark_amoled": "dark",
        "digital_art": "art",
        "minimalist": "minimalism",
        "sci_fi": "space",
    }

    def list_url(self, query, page, category=None):
        slug = re.sub(r"[^a-z0-9]+", "_", (category or "").strip().lower()).strip("_")
        slug = self._category_aliases.get(slug, slug)
        if slug in self._catalogs:
            base = f"https://wallpaperscraft.com/catalog/{slug}"
            return base if page <= 1 else f"{base}/page{page}"
        base = "https://wallpaperscraft.com/all/3840x2160"
        return base if page <= 1 else f"{base}/page{page}"

    async def search(self, ctx, query, page, category):
        await ctx.http.throttle(self.key, self.min_interval)
        html = await ctx.http.get_text(self.list_url(query, page, category))
        out, seen = [], set()
        for match in self.item_re.finditer(html):
            wallpaper = self.make(match, ctx)
            if wallpaper and wallpaper.id not in seen and self.host_ok(wallpaper.thumb_url):
                seen.add(wallpaper.id)
                out.append(wallpaper)
        return out

    def make(self, m, ctx):
        prefix, slug = m.group("prefix"), m.group("slug")
        return Wallpaper(
            id=slug, source=self.key, url=f"{prefix}_3840x2160.jpg", thumb_url=f"{prefix}_300x168.jpg",
            width=3840, height=2160, extra={"size": "assumed"}, title=clip(re.sub(r"_\d+$", "", slug).replace("_", " ").title()),
            page_url=f"https://wallpaperscraft.com/wallpaper/{slug}",
        )

    async def resolve(self, ctx, wp):
        detail_url = wp.page_url
        await ctx.http.throttle(self.key, self.min_interval)
        html = await ctx.http.get_text(detail_url)
        sizes = []
        for item in _anchor_items(html):
            href = unescape(item["href"])
            match = self._download_re.search(urlparse(href).path)
            if not match:
                continue
            width, height = int(match.group("width")), int(match.group("height"))
            download_page = urljoin(detail_url, href)
            if self.host_ok(download_page):
                sizes.append((width * height, width, height, download_page))
        if not sizes:
            raise ValueError("WallpapersCraft detail page has no resolution download links")
        _, _, _, download_page = max(sizes)
        await ctx.http.throttle(self.key, self.min_interval)
        download_html = await ctx.http.get_text(download_page)
        original = _largest_link(download_html, download_page, self._full_image_re, self.host_ok)
        if not original:
            raise ValueError("WallpapersCraft download page has no original image link")
        _, width, height, image_url = original
        if not ctx.meets_min(width, height):
            raise ValueError(
                f"WallpapersCraft original is {width}x{height}, below the configured minimum"
            )
        return image_url


# 14 ---------------------------------------------------------------- WallpaperFlare
class WallpaperFlare(ScrapeSource):
    key, name = "wallpaperflare", "WallpaperFlare"
    description = "Lists WallpaperFlare search results; original downloads require interactive verification."
    homepage = "https://www.wallpaperflare.com"
    hosts = ("wallpaperflare.com",)
    supports_query = True
    def list_url(self, query, page):
        return f"https://www.wallpaperflare.com/search?wallpaper={quote_plus(query or '4k')}&width=3840&height=2160&page={max(page, 1)}"

    async def search(self, ctx, query, page, category):
        await ctx.http.throttle(self.key, self.min_interval)
        html = await ctx.http.get_text(self.list_url(query, page))
        out, seen = [], set()
        for item in _anchor_items(html):
            detail_url = urljoin(self.homepage + "/", unescape(item["href"]))
            path = urlparse(detail_url).path
            thumb_url = urljoin(self.homepage + "/", unescape(item.get("image", "")))
            item_id = path.rsplit("/", 1)[-1]
            if "wallpaper-" not in item_id or not item.get("image") or item_id in seen:
                continue
            if not self.host_ok(detail_url) or not self.host_ok(thumb_url):
                continue
            seen.add(item_id)
            title = item.get("alt") or item.get("text") or item_id.replace("-", " ")
            out.append(Wallpaper(
                id=item_id, source=self.key, url=detail_url, thumb_url=thumb_url,
                title=clip(re.sub(r"\s+HD wallpaper$", "", title, flags=re.I)),
                page_url=detail_url, extra={"detail_url": detail_url},
            ))
        return out

    async def resolve(self, ctx, wp):
        raise ValueError(
            "WallpaperFlare requires interactive download verification to access original images"
        )


# 15 ---------------------------------------------------------------- Simple Desktops
class SimpleDesktops(ScrapeSource):
    key, name = "simpledesktops", "Simple Desktops"
    description = "Minimalist desktops from simpledesktops.com; serves the original file."
    homepage = "https://simpledesktops.com"
    hosts = ("simpledesktops.com",)
    item_re = re.compile(r'src="(?P<thumb>(?P<full>https?://static\.simpledesktops\.com/uploads/desktops/[^"]+?\.(?:png|jpg))\.\d+x\d+_q\d+\.(?:png|jpg))"', re.I)

    def list_url(self, query, page):
        return f"https://simpledesktops.com/browse/{max(page, 1)}/"

    def make(self, m, ctx):
        full = m.group("full").replace("http://", "https://")
        return Wallpaper(id=full.rsplit("/", 1)[-1], source=self.key, url=full, thumb_url=m.group("thumb").replace("http://", "https://"),
                         title=clip(full.rsplit("/", 1)[-1].rsplit(".", 1)[0].replace("_", " ").replace("-", " ").title()),
                         page_url="https://simpledesktops.com/")


# 18 ---------------------------------------------------------------- WallpapersWide
class WallpapersWide(ScrapeSource):
    key, name = "wallpaperswide", "WallpapersWide"
    description = "Scrapes category listings and resolves the largest direct download."
    homepage = "https://wallpaperswide.com"
    hosts = ("wallpaperswide.com",)
    supports_query = False

    def list_url(self, query, page):
        topic = re.sub(r"[^a-z0-9]+", "-", (query or "landscape").strip().lower()).strip("-")
        topic = quote(topic or "landscape")
        base = f"https://wallpaperswide.com/{topic}-desktop-wallpapers.html"
        return base if page <= 1 else f"https://wallpaperswide.com/{topic}-desktop-wallpapers/page/{page}"

    async def search(self, ctx, query, page, category):
        await ctx.http.throttle(self.key, self.min_interval)
        html = await ctx.http.get_text(self.list_url(category or query, page))
        out, seen = [], set()
        for item in _anchor_items(html):
            detail_url = urljoin(self.homepage + "/", unescape(item["href"]))
            path = urlparse(detail_url).path
            thumb_url = urljoin(self.homepage + "/", unescape(item.get("image", "")))
            if not path.endswith("-wallpapers.html") or not item.get("image"):
                continue
            slug = path.rsplit("/", 1)[-1].removesuffix("-wallpapers.html")
            if slug in seen or not self.host_ok(detail_url) or not self.host_ok(thumb_url):
                continue
            seen.add(slug)
            out.append(Wallpaper(
                id=slug, source=self.key, url=detail_url, thumb_url=thumb_url,
                title=clip(item.get("alt") or item.get("text") or slug.replace("_", " ")),
                page_url=detail_url, extra={"detail_url": detail_url},
            ))
        return out

    async def resolve(self, ctx, wp):
        detail_url = wp.extra.get("detail_url") or wp.page_url
        await ctx.http.throttle(self.key, self.min_interval)
        html = await ctx.http.get_text(detail_url)
        candidate = _largest_link(
            html, detail_url,
            re.compile(r"-(?P<width>\d{3,5})x(?P<height>\d{3,5})\.(?:jpe?g|png|webp)$", re.I),
            self.host_ok,
        )
        if not candidate:
            raise ValueError("WallpapersWide detail page has no full-size image links")
        _, width, height, image_url = candidate
        if max(width, height) < ctx.min_long:
            raise ValueError(
                f"WallpapersWide image maxes out at {width}x{height}, below the configured minimum"
            )
        return image_url
