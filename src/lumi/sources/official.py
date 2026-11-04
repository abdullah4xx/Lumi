"""Documented API integrations for museums, open images, film and anime."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import time
from urllib.parse import quote, urlencode, urlparse

from ..models import Wallpaper
from .base import KIND_API, KIND_KEY, Context, Source, clip, to_int

logger = logging.getLogger("lumi.sources.official")


class MetMuseum(Source):
    key, name, kind = "met", "The Metropolitan Museum of Art", KIND_API
    description = "The Met Collection API; records include rights and public-domain status."
    homepage = "https://www.metmuseum.org"
    hosts = ("metmuseum.org",)
    min_interval = 0.1

    async def search(self, ctx, query, page, category):
        data = await ctx.http.get_json("https://collectionapi.metmuseum.org/public/collection/v1.1/search",
                                       params={"q": query or "landscape", "hasImages": "true",
                                               "limit": "12", "offset": str((max(1, page) - 1) * 12)})
        ids = data.get("objectIDs") or []
        await ctx.http.throttle(self.key, self.min_interval)
        objects = await asyncio.gather(*(
            ctx.http.get_json(f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{int(oid)}")
            for oid in ids if str(oid).isdigit()
        ), return_exceptions=True)
        out = []
        for item in objects:
            if isinstance(item, Exception):
                logger.info("Met Museum object lookup failed: %s", item)
                continue
            image = item.get("primaryImage") or item.get("primaryImageSmall")
            if not image or not item.get("isPublicDomain"):
                continue
            width, height = to_int(item.get("dimensionsWidth")), to_int(item.get("dimensionsHeight"))
            out.append(Wallpaper(
                id=str(item.get("objectID")), source=self.key, url=image,
                thumb_url=item.get("primaryImageSmall") or image, width=width, height=height,
                title=clip(item.get("title") or "Untitled artwork"),
                author=clip(item.get("artistDisplayName") or "Unknown artist", 60),
                page_url=item.get("objectURL") or "",
                extra={"license": "Public Domain", "credit": "The Metropolitan Museum of Art"},
            ))
        return out


class ArtInstitute(Source):
    key, name, kind = "artic", "Art Institute of Chicago", KIND_API
    description = "Official public API; only public-domain artworks with images are returned."
    homepage = "https://www.artic.edu"
    hosts = ("artic.edu",)

    async def search(self, ctx, query, page, category):
        data = await ctx.http.get_json("https://api.artic.edu/api/v1/artworks/search", params={
            "q": query or "landscape",
            "query[term][is_public_domain]": "true",
            "fields": "id,title,image_id,is_public_domain,artist_title,date_display,thumbnail,width,height",
            "limit": "30", "page": str(max(1, page)),
        })
        out = []
        for item in data.get("data") or []:
            image_id = item.get("image_id")
            if not image_id or not item.get("is_public_domain"):
                continue
            image = f"https://www.artic.edu/iiif/2/{quote(str(image_id), safe='')}/full/1686,/0/default.jpg"
            thumb = f"https://www.artic.edu/iiif/2/{quote(str(image_id), safe='')}/full/843,/0/default.jpg"
            out.append(Wallpaper(
                id=str(item.get("id")), source=self.key, url=image, thumb_url=thumb,
                width=to_int(item.get("width")), height=to_int(item.get("height")),
                title=clip(item.get("title") or "Untitled artwork"),
                author=clip(item.get("artist_title") or "Unknown artist", 60),
                page_url=f"https://www.artic.edu/artworks/{item.get('id')}",
                extra={"license": "Public Domain", "credit": "Art Institute of Chicago"},
            ))
        return out


class Rijksmuseum(Source):
    key, name, kind = "rijksmuseum", "Rijksmuseum", KIND_KEY
    description = "Official collection API; requires a free Rijksmuseum API key."
    homepage = "https://www.rijksmuseum.nl/en/api"
    key_name, key_required = "rijksmuseum", True
    hosts = ("rijksmuseum.nl",)

    async def search(self, ctx, query, page, category):
        data = await ctx.http.get_json("https://www.rijksmuseum.nl/api/en/collection", params={
            "key": ctx.key("rijksmuseum"), "q": query or "landscape", "imgonly": "true",
            "ps": "30", "p": str(max(1, page)),
        })
        out = []
        for item in data.get("artObjects") or []:
            image = item.get("webImage") or {}
            if not image.get("url") or item.get("copyrightHolder"):
                continue
            out.append(Wallpaper(
                id=str(item.get("objectNumber") or item.get("id")), source=self.key,
                url=image["url"], thumb_url=image["url"],
                width=to_int(image.get("width")), height=to_int(image.get("height")),
                title=clip(item.get("title") or "Untitled artwork"),
                author=clip(item.get("principalOrFirstMaker") or "Unknown artist", 60),
                page_url=item.get("links", {}).get("web") or "",
                extra={"credit": "Rijksmuseum", "license": "Check the individual artwork page"},
            ))
        return out


class Openverse(Source):
    key, name, kind = "openverse", "Openverse", KIND_KEY
    description = "Openly licensed image search; requires Openverse OAuth client ID and secret."
    homepage = "https://openverse.org"
    # Openverse returns originals hosted by many independent sites. Refuse non-HTTPS,
    # IP-literal and local hostnames before allowing image downloads.
    hosts = ()
    required_keys = ("openverse_id", "openverse_secret")

    def __init__(self):
        self._token = ""
        self._token_expires = 0.0

    def host_ok(self, url):
        parsed = urlparse(url or "")
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme != "https" or not host or "." not in host:
            return False
        try:
            ipaddress.ip_address(host)
            return False
        except ValueError:
            return not (host == "localhost" or host.endswith((".localhost", ".local", ".internal")))

    async def _access_token(self, ctx):
        if self._token and time.monotonic() < self._token_expires:
            return self._token
        data = await ctx.http.get_json(
            "https://api.openverse.org/v1/auth_tokens/token/",
            method="POST",
            data=urlencode({
                "grant_type": "client_credentials",
                "client_id": ctx.key("openverse_id"),
                "client_secret": ctx.key("openverse_secret"),
            }),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        self._token = str(data.get("access_token") or "")
        self._token_expires = time.monotonic() + max(60, int(data.get("expires_in", 3600)) - 60)
        if not self._token:
            raise ValueError("Openverse did not return an access token")
        return self._token

    async def search(self, ctx, query, page, category):
        token = await self._access_token(ctx)
        data = await ctx.http.get_json("https://api.openverse.org/v1/images/", params={
            "q": query or "landscape", "page": str(max(1, page)), "page_size": "30",
            "aspect_ratio": "wide", "license_type": "commercial",
        }, headers={"Authorization": f"Bearer {token}"})
        out = []
        for item in data.get("results") or []:
            image, thumb = item.get("url"), item.get("thumbnail")
            if not image or not thumb or not self.host_ok(image) or not self.host_ok(thumb):
                continue
            license_name = item.get("license") or "Unknown"
            version = item.get("license_version") or ""
            out.append(Wallpaper(
                id=str(item.get("id") or image), source=self.key, url=image, thumb_url=thumb,
                width=to_int(item.get("width")), height=to_int(item.get("height")),
                title=clip(item.get("title") or "Openly licensed image"),
                author=clip(item.get("creator") or "Unknown creator", 60),
                page_url=item.get("foreign_landing_url") or "",
                extra={
                    "license": f"{license_name} {version}".strip(),
                    "credit": str(item.get("source") or ""),
                },
            ))
        return out


class Tmdb(Source):
    key, name, kind = "tmdb", "TMDB", KIND_KEY
    description = "Movie and TV backdrops through TMDB's official API; requires a TMDB API key."
    homepage = "https://www.themoviedb.org/settings/api"
    key_name, key_required = "tmdb", True
    hosts = ("themoviedb.org", "tmdb.org")

    async def search(self, ctx, query, page, category):
        data = await ctx.http.get_json("https://api.themoviedb.org/3/search/multi", params={
            "api_key": ctx.key("tmdb"), "query": query or "landscape",
            "include_adult": "false", "page": str(max(1, page)),
        })
        out = []
        for item in data.get("results") or []:
            backdrop = item.get("backdrop_path")
            if not backdrop:
                continue
            image = f"https://image.tmdb.org/t/p/original{backdrop}"
            thumb = f"https://image.tmdb.org/t/p/w1280{backdrop}"
            title = item.get("title") or item.get("name") or "Film backdrop"
            out.append(Wallpaper(
                id=f"{item.get('media_type', 'movie')}-{item.get('id')}", source=self.key,
                url=image, thumb_url=thumb, width=None, height=None,
                title=clip(title), author="TMDB",
                page_url=f"https://www.themoviedb.org/{item.get('media_type', 'movie')}/{item.get('id')}",
                extra={"credit": "TMDB", "license": "TMDB API terms; attribution required"},
            ))
        return out


class AniList(Source):
    key, name, kind = "anilist", "AniList", KIND_API
    description = "Anime banners from the official AniList GraphQL API."
    homepage = "https://anilist.co"
    hosts = ("anilist.co",)

    async def search(self, ctx, query, page, category):
        variables = {"search": query or "anime", "page": max(1, page)}
        payload = json.dumps({
            "query": "query ($search: String, $page: Int) { Page(page: $page, perPage: 30) { media(search: $search, type: ANIME, isAdult: false) { id title { english romaji } bannerImage siteUrl } } }",
            "variables": variables,
        })
        data = await ctx.http.get_json(
            "https://graphql.anilist.co", method="POST", data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        out = []
        for item in (data.get("data") or {}).get("Page", {}).get("media", []):
            image = item.get("bannerImage")
            if not image:
                continue
            title = (item.get("title") or {}).get("english") or (item.get("title") or {}).get("romaji")
            out.append(Wallpaper(
                id=str(item.get("id")), source=self.key, url=image, thumb_url=image,
                title=clip(title or "Anime banner"), author="AniList", page_url=item.get("siteUrl") or "",
                extra={"credit": "AniList", "license": "See the linked title page"},
            ))
        return out


class Kitsu(Source):
    key, name, kind = "kitsu", "Kitsu", KIND_API
    description = "Anime artwork through the public Kitsu JSON:API."
    homepage = "https://kitsu.io"
    hosts = ("kitsu.io", "kitsu.app")

    async def search(self, ctx, query, page, category):
        data = await ctx.http.get_json("https://kitsu.io/api/edge/anime", params={
            "filter[text]": query or "anime", "page[limit]": "20",
            "page[offset]": str((max(1, page) - 1) * 20),
        })
        out = []
        for item in data.get("data") or []:
            attributes = item.get("attributes") or {}
            cover = attributes.get("coverImage") or {}
            poster = attributes.get("posterImage") or {}
            image = cover.get("original") or poster.get("original")
            if not image:
                continue
            out.append(Wallpaper(
                id=str(item.get("id")), source=self.key, url=image,
                thumb_url=cover.get("large") or poster.get("large") or image,
                width=to_int(cover.get("width")), height=to_int(cover.get("height")),
                title=clip((attributes.get("titles") or {}).get("en") or attributes.get("canonicalTitle") or "Anime artwork"),
                author="Kitsu", page_url=f"https://kitsu.io/anime/{item.get('id')}",
                extra={"credit": "Kitsu", "license": "See the linked title page"},
            ))
        return out


class FanartTV(Source):
    key, name, kind = "fanart", "fanart.tv", KIND_KEY
    description = "Movie/TV backgrounds via fanart.tv; requires both Fanart.tv and TMDB API keys."
    homepage = "https://fanart.tv/get-an-api-key/"
    key_name, key_required = "fanart", True
    required_keys = ("fanart", "tmdb")
    hosts = ("fanart.tv",)

    async def search(self, ctx, query, page, category):
        tmdb = await ctx.http.get_json("https://api.themoviedb.org/3/search/multi", params={
            "api_key": ctx.key("tmdb"), "query": query or "landscape",
            "include_adult": "false", "page": str(max(1, page)),
        })
        candidates = [
            item for item in tmdb.get("results") or []
            if item.get("id") and item.get("media_type") in {"movie", "tv"}
        ][:8]
        async def artwork(item):
            endpoint = "movies" if item["media_type"] == "movie" else "tv"
            return item, await ctx.http.get_json(
                f"https://webservice.fanart.tv/v3/{endpoint}/{item['id']}",
                params={"api_key": ctx.key("fanart")},
            )
        responses = await asyncio.gather(*(artwork(item) for item in candidates), return_exceptions=True)
        out = []
        for result in responses:
            if isinstance(result, Exception):
                logger.info("Fanart.tv artwork lookup failed: %s", result)
                continue
            item, data = result
            images = data.get("moviebackground" if item["media_type"] == "movie" else "showbackground") or []
            for index, art in enumerate(images[:3]):
                image = art.get("url")
                if not image:
                    continue
                title = item.get("title") or item.get("name") or "Fanart background"
                out.append(Wallpaper(
                    id=f"{item['media_type']}-{item['id']}-{index}", source=self.key,
                    url=image, thumb_url=image, title=clip(title),
                    author=clip(art.get("lang") or "fanart.tv", 60),
                    page_url=f"https://www.themoviedb.org/{item['media_type']}/{item['id']}",
                    extra={"credit": "fanart.tv", "license": "Fanart.tv API terms; attribution required"},
                ))
        return out
