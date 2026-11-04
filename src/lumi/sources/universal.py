"""Universal Web Scraper: extracts high-resolution images & wallpapers from any URL."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from html import unescape
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

from ..http import UnsafeUrlError, is_public_http_url
from ..models import Wallpaper
from .base import KIND_EXPERIMENTAL, Context, Source, clip, to_int

logger = logging.getLogger("lumi.sources.universal")

_IMG_TAG_RE = re.compile(r"<img\b([^>]+)>", re.I)
_A_TAG_RE = re.compile(r"<a\b([^>]+)>", re.I)
_ATTR_RE = re.compile(r'([a-zA-Z0-9_\-:]+)\s*=\s*["\']([^"\']+)["\']')
_META_RE = re.compile(r'<meta\b([^>]+)>', re.I)
_LINK_TAG_RE = re.compile(r"<link\b([^>]+)>", re.I)

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".avif", ".jxl")
JUNK_PATTERNS = re.compile(
    r"(avatar|badge|icon|logo|favicon|emoji|button|spinner|spacer|pixel|tracking|banner[_\-]?ad|"
    r"gravatar|user[_\-]thumb|advertisement|\.svg)",
    re.I,
)


def _parse_attributes(tag_inner: str) -> dict:
    return {k.lower(): unescape(v) for k, v in _ATTR_RE.findall(tag_inner)}


def _extract_best_from_srcset(srcset: str, base_url: str) -> Optional[str]:
    """Parse srcset and return the highest resolution image candidate."""
    if not srcset:
        return None
    candidates: List[Tuple[int, str]] = []
    for part in srcset.split(","):
        part = part.strip()
        if not part:
            continue
        tokens = part.split()
        if not tokens:
            continue
        candidate_url = tokens[0]
        score = 0
        if len(tokens) > 1:
            descriptor = tokens[1].lower()
            if descriptor.endswith("w"):
                try:
                    score = int(descriptor[:-1])
                except ValueError:
                    score = 0
            elif descriptor.endswith("x"):
                try:
                    score = int(float(descriptor[:-1]) * 1000)
                except ValueError:
                    score = 0
        full_candidate = urljoin(base_url, candidate_url)
        candidates.append((score, full_candidate))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    return None


_DIM_RE = re.compile(r"(?<!\d)(\d{3,5})\s*[x\u00d7]\s*(\d{3,5})(?!\d)", re.I)
_THUMB_HINT = re.compile(r"(thumb|small|preview|_sm\b|[-_]\d{2,3}x\d{2,3}\.)", re.I)
_DOWNLOAD_PAGE_RE = re.compile(r"/download/(\d{3,5})x(\d{3,5})/?$", re.I)
_JSONLD_URL_RE = re.compile(r'"contentUrl"\s*:\s*"([^"]+)"')
_SRCSET_W_RE = re.compile(r"\s(\d+)w\b")

# Score bonuses: markup that names the full-size picture beats generic hints.
BONUS_MAIN_IMAGE = 20000        # id="show_img" / itemprop="contentUrl" (the page's own "this is the picture")
BONUS_DOWNLOAD_PAGE = 10000     # /download/3840x2160 links: the page that holds the real file
BONUS_JSONLD = 4000
BONUS_OG = 3000
BONUS_TWITTER = 2000
BONUS_FULL_ATTR = 1500          # data-original / data-full-url / data-zoom-image
BONUS_DIRECT_LINK = 1000        # <a href="....jpg">
THUMB_PENALTY = 5000


@dataclass(frozen=True)
class Candidate:
    url: str
    score: int
    kind: str = "image"         # "image" = a picture URL, "page" = a page that leads to the full-size picture


def _dims_from_url(url: str) -> Optional[Tuple[int, int]]:
    m = _DIM_RE.search(urlparse(url).path)
    return (int(m.group(1)), int(m.group(2))) if m else None


def _srcset_max_width(srcset: str) -> int:
    return max((int(w) for w in _SRCSET_W_RE.findall(" " + (srcset or ""))), default=0)


def _score(url: str, width_hint: int = 0, bonus: int = 0) -> int:
    """Higher = more likely to be the biggest picture. Pixel area (in thousands) plus markup bonuses."""
    dims = _dims_from_url(url)
    if dims:
        area = dims[0] * dims[1]
    elif width_hint:
        area = width_hint * width_hint * 9 // 16          # assume 16:9 when only a width is known
    else:
        area = 0
    penalty = THUMB_PENALTY if _THUMB_HINT.search(urlparse(url).path) else 0
    return area // 1000 + bonus - penalty


class UniversalWebScraper:
    """Extracts images and wallpapers from raw HTML of any webpage."""

    @staticmethod
    def extract_wallpapers(html: str, page_url: str, custom_title: str = "") -> List[Wallpaper]:
        seen_urls: Set[str] = set()
        wallpapers: List[Wallpaper] = []
        page_domain = urlparse(page_url).netloc

        def add_candidate(img_url: str, thumb_url: Optional[str] = None, title: str = ""):
            img_url = urljoin(page_url, img_url.strip())
            parsed = urlparse(img_url)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                return
            if JUNK_PATTERNS.search(img_url) or JUNK_PATTERNS.search(parsed.path):
                return
            if img_url in seen_urls:
                return
            seen_urls.add(img_url)

            thumb = urljoin(page_url, thumb_url.strip()) if thumb_url else img_url
            img_id = hashlib.sha1(img_url.encode("utf-8")).hexdigest()[:12]
            clean_title = title.strip() or custom_title or f"Wallpaper from {page_domain}"

            wallpapers.append(
                Wallpaper(
                    id=img_id,
                    source="custom_url",
                    url=img_url,
                    thumb_url=thumb,
                    width=None,
                    height=None,
                    title=clip(clean_title, 80),
                    author=page_domain,
                    page_url=page_url,
                    tags=("custom_url", "web_extracted"),
                    extra={"origin_url": page_url},
                )
            )

        # 1. Meta OpenGraph & Twitter image headers
        for match in _META_RE.finditer(html):
            attrs = _parse_attributes(match.group(1))
            prop = attrs.get("property", "") or attrs.get("name", "")
            content = attrs.get("content", "")
            if prop.lower() in ("og:image", "og:image:secure_url", "twitter:image", "twitter:image:src") and content:
                add_candidate(content, title=attrs.get("title", ""))

        # 2. Image tags <img> with src, data-src, srcset
        for match in _IMG_TAG_RE.finditer(html):
            attrs = _parse_attributes(match.group(1))
            src = attrs.get("src", "")
            data_src = attrs.get("data-src") or attrs.get("data-original") or attrs.get("data-full-url") or attrs.get("data-zoom-image")
            srcset = attrs.get("srcset") or attrs.get("data-srcset")
            alt = attrs.get("alt", "") or attrs.get("title", "")

            best_srcset = _extract_best_from_srcset(srcset, page_url) if srcset else None
            high_res = best_srcset or data_src or src

            if high_res:
                thumb = src if (data_src or best_srcset) and src != high_res else None
                add_candidate(high_res, thumb_url=thumb, title=alt)

        # 3. Anchor tags <a> linking directly to images
        for match in _A_TAG_RE.finditer(html):
            attrs = _parse_attributes(match.group(1))
            href = attrs.get("href", "")
            if href:
                parsed_href = urlparse(href)
                if any(parsed_href.path.lower().endswith(ext) for ext in IMAGE_EXTENSIONS):
                    add_candidate(href, title=attrs.get("title", ""))

        return wallpapers

    @staticmethod
    def rank_candidates(html: str, page_url: str) -> List[Candidate]:
        """Every picture (or download page) found in ``html``, best first. Pure parsing, no network."""
        found: Dict[str, Candidate] = {}

        def add(raw: str, bonus: int = 0, width_hint: int = 0, kind: str = "image") -> None:
            url = urljoin(page_url, unescape((raw or "").strip().replace("\\/", "/")))
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                return
            if kind == "image" and (JUNK_PATTERNS.search(url) or JUNK_PATTERNS.search(parsed.path)):
                return
            cand = Candidate(url, _score(url, width_hint, bonus), kind)
            if url not in found or cand.score > found[url].score:
                found[url] = cand

        # 1. Meta tags. og:image:width/height (when the site gives them) make the score exact.
        meta = [_parse_attributes(m.group(1)) for m in _META_RE.finditer(html)]
        named = {(a.get("property") or a.get("name") or "").lower(): a.get("content", "") for a in meta}
        og_w = to_int(named.get("og:image:width")) or 0
        for prop, bonus in (("og:image", BONUS_OG), ("og:image:secure_url", BONUS_OG),
                            ("twitter:image", BONUS_TWITTER), ("twitter:image:src", BONUS_TWITTER)):
            if named.get(prop):
                add(named[prop], bonus, width_hint=og_w if prop.startswith("og:") else 0)
        for m in _LINK_TAG_RE.finditer(html):                                # <link rel="image_src" href=...>
            attrs = _parse_attributes(m.group(1))
            if attrs.get("rel", "").lower() == "image_src" and attrs.get("href"):
                add(attrs["href"], BONUS_TWITTER)

        # 2. JSON-LD "contentUrl"
        for raw in _JSONLD_URL_RE.findall(html):
            add(raw, BONUS_JSONLD)

        # 3. <img>: the page's declared main picture, lazy-load / full-size attributes, srcset, plain src
        for m in _IMG_TAG_RE.finditer(html):
            attrs = _parse_attributes(m.group(1))
            main = attrs.get("id") == "show_img" or attrs.get("itemprop", "").lower() == "contenturl"
            for key in ("data-original", "data-full-url", "data-zoom-image", "data-large-file"):
                if attrs.get(key):
                    add(attrs[key], BONUS_FULL_ATTR)
            srcset = attrs.get("srcset") or attrs.get("data-srcset") or ""
            best = _extract_best_from_srcset(srcset, page_url) if srcset else None
            if best:
                add(best, BONUS_MAIN_IMAGE if main else 0, width_hint=_srcset_max_width(srcset))
            src = attrs.get("src") or attrs.get("data-src") or ""
            if src:
                add(src, BONUS_MAIN_IMAGE if main else 0)

        # 4. <a>: direct image files, and "/download/WxH" pages on the same site
        page_host = urlparse(page_url).netloc
        for m in _A_TAG_RE.finditer(html):
            attrs = _parse_attributes(m.group(1))
            href = attrs.get("href", "")
            if not href:
                continue
            full = urljoin(page_url, href)
            path = urlparse(full).path.lower()
            if path.endswith(IMAGE_EXTENSIONS):
                add(full, BONUS_DIRECT_LINK)
            elif urlparse(full).netloc == page_host and _DOWNLOAD_PAGE_RE.search(path):
                add(full, BONUS_DOWNLOAD_PAGE, kind="page")

        return sorted(found.values(), key=lambda c: c.score, reverse=True)

    @staticmethod
    async def find_best_image(
        http: Any, page_url: str, max_hops: int = 2,
        final_url_ok: Optional[Any] = None,
    ) -> str:
        """Open ``page_url`` (and, if it links to a bigger "/download/WxH" page, that page too) and return
        the URL of the highest-quality picture. Raises ValueError when nothing usable is found."""
        current, visited = page_url, {page_url}
        images: List[Candidate] = []
        for hop in range(max_hops):
            try:
                html = await http.get_text(
                    current, headers={"Referer": page_url} if hop else None,
                    final_url_ok=final_url_ok,
                )
            except UnsafeUrlError:
                raise
            except Exception:                    # noqa: BLE001 - a dead follow-up page must not lose what hop 0 found
                if hop == 0:
                    raise
                break
            ranked = UniversalWebScraper.rank_candidates(html, current)
            images = sorted(images + [c for c in ranked if c.kind == "image"], key=lambda c: c.score, reverse=True)
            pages = [c for c in ranked if c.kind == "page" and c.url not in visited]
            if not pages:
                break
            current = pages[0].url
            visited.add(current)
        if not images:
            raise ValueError("no image found on this page")
        return images[0].url


class CustomUrlSource(Source):
    """Source that queries user-defined Custom URLs and Web Feeds."""

    key = "custom_url"
    name = "Custom Web URLs"
    kind = KIND_EXPERIMENTAL
    description = "Extracts 4K wallpapers from user-provided website links and albums."
    homepage = "https://github.com/abdullah4xx/Lumi"
    default_enabled = False
    supports_query = False
    min_interval = 0.5
    hosts = ("*",)

    def host_ok(self, url: str) -> bool:
        return is_public_http_url(url)

    async def search(self, ctx: Context, query: str, page: int, category: Optional[str]) -> List[Wallpaper]:
        custom_urls: List[str] = ctx.cfg.get("custom_urls") or []
        if not custom_urls:
            return []

        out: List[Wallpaper] = []
        for url in custom_urls:
            if not self.host_ok(url):
                continue
            try:
                await ctx.http.throttle("custom_url", self.min_interval)
                html = await ctx.http.get_text(url, final_url_ok=self.host_ok)
                extracted = UniversalWebScraper.extract_wallpapers(html, url)
                out.extend(extracted)
            except Exception as exc:
                logger.warning("Failed scraping custom URL %s: %s", url, exc)

        return out
