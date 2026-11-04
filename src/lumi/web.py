"""Lumi Local Web Companion Server: Remote Dashboard & Device-Aware Theme Sync."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from aiohttp import web

from . import __version__, gnome, palette
from .classifier import Classifier, classify_with_gemini, interpret_wallpaper_request
from .config import CONFIG_DIR, DATA_DIR, THUMB_DIR, Config, DEFAULTS, saved_dir
from .engine import Engine
from .http import HttpError
from .local import LocalManager
from .models import CATEGORIES, Wallpaper
from .sources.plugins import MAX_PLUGIN_BYTES, PluginError, PluginSource
from .sources.universal import UniversalWebScraper
from .store import Store

logger = logging.getLogger("lumi.web")

class WebCompanionServer:
    """Local Aiohttp Web Server for remote wallpaper control & companion UI."""

    def __init__(
        self,
        config: Config,
        engine: Engine,
        store: Store,
        local_mgr: Optional[LocalManager] = None,
        ui_dir: Optional[Path] = None,
    ):
        self.config = config
        self.engine = engine
        self.store = store
        self.local_mgr = local_mgr or LocalManager(config)
        self.app = web.Application()
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self._wallpapers: Dict[str, Wallpaper] = {}
        self._source_statuses = {}
        self.ui_dir = Path(ui_dir or os.environ.get("LUMI_UI_DIR", Path(__file__).parents[2] / "ui"))
        self._setup_routes()

    def _setup_routes(self):
        self.app.router.add_get("/", self.handle_index)
        self.app.router.add_get("/api/status", self.handle_status)
        self.app.router.add_get("/api/categories", self.handle_categories)
        self.app.router.add_get("/api/sources", self.handle_sources)
        self.app.router.add_get("/api/wallpapers", self.handle_wallpapers)
        self.app.router.add_get("/api/thumb", self.handle_thumb)
        self.app.router.add_get("/api/settings", self.handle_settings)
        self.app.router.add_put("/api/settings", self.handle_settings)
        self.app.router.add_get("/api/scrapers", self.handle_scrapers)
        self.app.router.add_post("/api/scrapers", self.handle_scrapers)
        self.app.router.add_delete("/api/scrapers/{key}", self.handle_scrapers)
        self.app.router.add_get("/api/gemini/models", self.handle_gemini_models)
        self.app.router.add_post("/api/favorite", self.handle_favorite)
        self.app.router.add_post("/api/apply", self.handle_apply)
        self.app.router.add_post("/api/save", self.handle_save)
        self.app.router.add_post("/api/test-gemini", self.handle_test_gemini)
        self.app.router.add_post("/api/gemini/test", self.handle_test_gemini)
        self.app.router.add_post("/api/classify", self.handle_classify)
        self.app.router.add_post("/api/assistant/search", self.handle_assistant_search)
        self.app.router.add_post("/api/import", self.handle_import)
        self.app.router.add_post("/api/folders", self.handle_folders)
        self.app.router.add_delete("/api/folders", self.handle_folders)
        self.app.router.add_post("/api/storage/clear-cache", self.handle_clear_cache)
        self.app.router.add_post("/api/storage/clear-downloads", self.handle_clear_downloads)
        self.app.router.add_get("/api/backup", self.handle_backup)
        self.app.router.add_post("/api/backup", self.handle_backup)
        self.app.router.add_post("/api/shuffle", self.handle_shuffle)
        self.app.router.add_post("/api/scrape", self.handle_scrape)
        if self.ui_dir.is_dir():
            self.app.router.add_static("/img", self.ui_dir / "img", show_index=False)
            if (self.ui_dir / "vendor").is_dir():
                self.app.router.add_static("/vendor", self.ui_dir / "vendor", show_index=False)
            if (self.ui_dir / "fonts").is_dir():
                self.app.router.add_static("/fonts", self.ui_dir / "fonts", show_index=False)
            if (self.ui_dir / "i18n.js").is_file():
                self.app.router.add_get("/i18n.js", self.handle_i18n)

    async def handle_index(self, request: web.Request) -> web.Response:
        page = self.ui_dir / "index.html"
        if not page.is_file():
            page = Path(__file__).parent / "static" / "index.html"
        return web.FileResponse(page)

    async def handle_i18n(self, request: web.Request) -> web.Response:
        return web.FileResponse(self.ui_dir / "i18n.js")

    async def handle_status(self, request: web.Request) -> web.Response:
        cur_wp = gnome.current_wallpaper()
        pal = []
        if cur_wp and cur_wp.exists():
            pal = palette.extract_palette(cur_wp)

        return web.json_response({
            "version": __version__,
            "current_wallpaper": str(cur_wp) if cur_wp else None,
            "palette": pal,
            "accent_color": palette.palette_gnome_accent(pal) if pal else None,
            "paths": {
                "config": str(CONFIG_DIR),
                "data": str(DATA_DIR),
                "cache": str(THUMB_DIR.parent),
                "downloads": str(saved_dir()),
            },
        })

    async def handle_categories(self, request: web.Request) -> web.Response:
        return web.json_response(CATEGORIES)

    async def handle_sources(self, request: web.Request) -> web.Response:
        settings = self.config.snapshot()
        keys = settings.get("api_keys") or {}
        sources = []
        for key, source in self.engine.sources.items():
            required_keys = source.required_keys or ((source.key_name,) if source.key_required and source.key_name else ())
            manual_only = bool(getattr(source, "manual_only", False))
            last_status = self._source_statuses.get(key)
            sources.append({
                "key": key,
                "name": source.name,
                "homepage": source.homepage,
                "description": source.description,
                "kind": source.kind,
                "experimental": source.kind == "experimental",
                "manual_only": manual_only,
                "enabled": not manual_only and self.config.source_enabled(key, source.default_enabled),
                "needs_key": bool(required_keys),
                "key_saved": bool(required_keys) and all(bool(keys.get(name)) for name in required_keys),
                "key_status": {name: bool(keys.get(name)) for name in required_keys},
                "required_keys": list(required_keys),
                "last_status": last_status.state if last_status else None,
                "last_count": last_status.count if last_status else 0,
                "last_message": last_status.message if last_status else "",
            })
        return web.json_response(sources)

    async def handle_wallpapers(self, request: web.Request) -> web.Response:
        query = request.query.get("q", "")
        category = request.query.get("category") or None
        collection = request.query.get("collection", "")
        try:
            page = max(1, min(100, int(request.query.get("page", "1"))))
        except ValueError:
            return web.json_response({"error": "Page must be a positive integer"}, status=400)
        if category and category not in CATEGORIES:
            return web.json_response({"error": "Unknown category"}, status=400)

        source_search = not collection
        if collection == "favorites":
            results = [wp for wp in self.store.favorites() if wp.source != "local"]
        elif collection == "history":
            results = []
            for item in self.config.get("history"):
                try:
                    wallpaper = Wallpaper.from_dict(item)
                    if wallpaper.source != "local":
                        results.append(wallpaper)
                except (KeyError, TypeError, ValueError):
                    continue
        elif collection == "local":
            results = self.local_mgr.scan_folders()
        else:
            collected: List[Wallpaper] = []
            keys = self.engine.enabled_keys()
            try:
                self._source_statuses = await self.engine.search(
                    query, category, page, keys, set(), lambda _key, wps: collected.extend(wps)
                )
                results = collected
            except Exception as exc:
                logger.warning("Error searching web wallpapers: %s", exc)
                self._source_statuses = {}
                results = []

        unique: Dict[str, Wallpaper] = {}
        if query and not source_search:
            needle = query.casefold()
            results = [
                wp for wp in results
                if needle in wp.title.casefold() or needle in " ".join(wp.tags).casefold()
            ]
        if category and self.config.get("strict_ai_filter"):
            results = [
                wp for wp in results
                if category in {name for name, _score in (self.store.get_classes(wp.uid) or [])}
            ]
        for wp in results:
            unique.setdefault(wp.uid, wp)
        results = list(unique.values())[:60]
        self._wallpapers.update({wp.uid: wp for wp in results})
        if len(self._wallpapers) > 1000:
            self._wallpapers = {wp.uid: wp for wp in results}
        return web.json_response([
            {
                **wp.to_dict(),
                "favorite": self.store.is_favorite(wp),
                "categories": self.store.get_classes(wp.uid) or [],
            }
            for wp in results
        ])

    async def handle_thumb(self, request: web.Request) -> web.Response:
        uid = request.query.get("uid", "")
        wp = self._wallpapers.get(uid)
        if wp is None:
            return web.json_response({"error": "Wallpaper not found; refresh the gallery"}, status=404)
        try:
            path = (
                await self.engine.fetch_preview(wp)
                if request.query.get("quality") == "full"
                else await self.engine.fetch_thumb(wp)
            )
        except Exception as exc:
            logger.warning("Preview fetch failed for %s: %s", uid, exc)
            return web.json_response({"error": "Image preview unavailable"}, status=502)
        if path is None:
            return web.json_response({"error": "Image preview unavailable"}, status=404)
        return web.FileResponse(path)

    async def handle_settings(self, request: web.Request) -> web.Response:
        if request.method == "GET":
            return self._settings_response()

        try:
            data = await request.json()
        except (json.JSONDecodeError, web.HTTPBadRequest):
            return web.json_response({"error": "Expected a JSON object"}, status=400)
        if not isinstance(data, dict):
            return web.json_response({"error": "Expected a JSON object"}, status=400)
        allowed = set(DEFAULTS) - {"api_keys", "history", "dismissed_ids", "local_imported_wallpapers"}
        invalid = set(data) - allowed - {"api_keys"}
        if invalid:
            return web.json_response({"error": f"Unsupported setting: {sorted(invalid)[0]}"}, status=400)
        try:
            for key, value in data.items():
                if key == "api_keys":
                    if not isinstance(value, dict):
                        raise ValueError("api_keys must be an object")
                    for name, api_key in value.items():
                        if name not in self.config.get("api_keys") or not isinstance(api_key, str):
                            raise ValueError(f"Invalid API key: {name}")
                        self.config.set_api_key(name, api_key)
                else:
                    self.config.set(key, value)
        except (KeyError, TypeError, ValueError) as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return self._settings_response()

    def _settings_response(self) -> web.Response:
        settings = self.config.snapshot()
        keys = settings.pop("api_keys", {})
        settings["api_keys"] = {name: bool(value) for name, value in keys.items()}
        return web.json_response(settings)

    @staticmethod
    def _is_local_scraper_request(request: web.Request) -> bool:
        try:
            if not ipaddress.ip_address(request.remote or "").is_loopback:
                return False
        except ValueError:
            return False
        origin = request.headers.get("Origin")
        if origin:
            from urllib.parse import urlparse

            parsed = urlparse(origin)
            if parsed.netloc != request.host:
                return False
        return True

    async def handle_scrapers(self, request: web.Request) -> web.Response:
        if not self._is_local_scraper_request(request):
            return web.json_response({"error": "Scraper management is available only from this device."}, status=403)
        if request.method == "GET":
            plugins = [
                {
                    "key": source.key,
                    "name": source.name,
                    "homepage": source.homepage,
                    "filename": source.plugin_path.name,
                    "enabled": self.config.source_enabled(source.key, source.default_enabled),
                }
                for source in self.engine.sources.values()
                if isinstance(source, PluginSource)
            ]
            return web.json_response(plugins)
        if request.method == "DELETE":
            key = request.match_info.get("key", "")
            if not self.engine.remove_scraper_plugin(key):
                return web.json_response({"error": "Scraper not found."}, status=404)
            return web.json_response({"ok": True})
        if not hasattr(self.engine, "install_scraper_plugin"):
            return web.json_response({"error": "Custom scraper installation is unavailable."}, status=501)
        if request.content_length is not None and request.content_length > MAX_PLUGIN_BYTES + 65536:
            return web.json_response({"error": "Scraper files must be 1 MiB or smaller."}, status=413)
        try:
            reader = await request.multipart()
            field = await reader.next()
            if field is None or field.name != "file" or not field.filename:
                return web.json_response({"error": "Choose a Python .py scraper file."}, status=400)
            chunks, size = [], 0
            while True:
                chunk = await field.read_chunk(size=65536)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_PLUGIN_BYTES:
                    return web.json_response({"error": "Scraper files must be 1 MiB or smaller."}, status=413)
                chunks.append(chunk)
            source = self.engine.install_scraper_plugin(field.filename, b"".join(chunks))
        except (web.HTTPBadRequest, PluginError, UnicodeError, OSError, SyntaxError) as exc:
            logger.info("Scraper plugin could not be installed: %s", exc)
            return web.json_response({"error": str(exc)}, status=400)
        except Exception as exc:
            logger.exception("Scraper plugin failed during import")
            return web.json_response({"error": f"Scraper could not be loaded: {type(exc).__name__}"}, status=400)
        return web.json_response({
            "ok": True,
            "scraper": {
                "key": source.key,
                "name": source.name,
                "homepage": source.homepage,
                "filename": source.plugin_path.name,
                "enabled": True,
            },
        })

    async def handle_gemini_models(self, request: web.Request) -> web.Response:
        api_key = self.config.api_key("gemini")
        if not api_key:
            return web.json_response({
                "ok": False,
                "code": "AI_NO_KEY",
                "error": "Add a Gemini API key in Settings before loading models.",
            }, status=400)
        try:
            response = await self.engine.http.get_json(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": api_key, "pageSize": 1000},
            )
        except Exception as exc:
            code, message, status = self._gemini_error(exc)
            return web.json_response({"ok": False, "code": code, "error": message}, status=status)

        if not isinstance(response, dict) or not isinstance(response.get("models"), list):
            return web.json_response({
                "ok": False,
                "code": "AI_SERVICE_ERROR",
                "error": "Gemini returned an invalid model list.",
            }, status=502)
        models = []
        for item in response["models"]:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            methods = item.get("supportedGenerationMethods", [])
            if (
                not isinstance(name, str)
                or not name.startswith("models/gemini-")
                or not isinstance(methods, list)
                or "generateContent" not in methods
            ):
                continue
            models.append({
                "name": name.removeprefix("models/"),
                "display_name": item.get("displayName")
                if isinstance(item.get("displayName"), str) else name.removeprefix("models/"),
            })
        models.sort(key=lambda model: (model["display_name"].casefold(), model["name"]))
        return web.json_response({"models": models})

    @staticmethod
    def _gemini_error(exc: Exception) -> tuple[str, str, int]:
        """Return a stable public error without exposing provider or request details."""
        status = getattr(exc, "status", None)
        message = str(exc).lower()
        if (
            isinstance(exc, (asyncio.TimeoutError, TimeoutError))
            or "timeout" in type(exc).__name__.lower()
            or "timeout" in message
        ):
            return "AI_TIMEOUT", "Gemini took too long to respond. Please try again.", 504
        if status == 429:
            return "AI_RATE_LIMIT", "Gemini is rate limited right now. Please try again later.", 429
        if status == 404:
            return "AI_MODEL_UNAVAILABLE", "The selected Gemini model is unavailable.", 400
        if status in (400, 401, 403):
            return "AI_INVALID_KEY", "Gemini rejected the saved API key. Check it in Settings.", 400
        if isinstance(exc, HttpError) and "network error" in message:
            return "AI_NETWORK_ERROR", "Could not reach Gemini. Check your internet connection.", 502
        if isinstance(exc, (ConnectionError, OSError)):
            return "AI_NETWORK_ERROR", "Could not reach Gemini. Check your internet connection.", 502
        return "AI_SERVICE_ERROR", "Gemini could not complete the request. Please try again.", 502

    async def handle_test_gemini(self, request: web.Request) -> web.Response:
        if request.can_read_body and request.content_length != 0:
            try:
                body = await request.json()
            except (json.JSONDecodeError, web.HTTPBadRequest):
                return web.json_response({"ok": False, "code": "AI_SERVICE_ERROR",
                                          "error": "Expected an empty JSON object."}, status=400)
            if not isinstance(body, dict) or body:
                return web.json_response({"ok": False, "code": "AI_SERVICE_ERROR",
                                          "error": "This endpoint does not accept credentials or settings."},
                                         status=400)

        api_key = self.config.api_key("gemini")
        if not api_key:
            return web.json_response({
                "ok": False, "code": "AI_NO_KEY",
                "error": "Add a Gemini API key in Settings before testing the connection.",
            }, status=400)

        model = self.config.get("gemini_model")
        payload = {
            "contents": [{"parts": [{"text": "Reply with OK."}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 8},
        }
        try:
            await self.engine.http.get_json(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                params={"key": api_key},
                headers={"Content-Type": "application/json"},
                method="POST",
                data=json.dumps(payload),
            )
        except Exception as exc:  # provider exceptions may contain request URLs or credentials
            code, message, status = self._gemini_error(exc)
            return web.json_response({"ok": False, "code": code, "error": message}, status=status)
        return web.json_response({
            "ok": True, "code": "AI_OK", "model": model,
            "message": "Gemini connection successful.",
        })

    async def handle_favorite(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            wp = self._wallpaper_from_request(data)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, web.HTTPBadRequest) as exc:
            return web.json_response({"error": str(exc) or "Invalid wallpaper"}, status=400)
        favorite = self.store.toggle_favorite(wp)
        return web.json_response({"ok": True, "favorite": favorite})

    def _wallpaper_from_request(self, data: Any) -> Wallpaper:
        if not isinstance(data, dict):
            raise ValueError("Expected a wallpaper object")
        wp = Wallpaper.from_dict(data)
        if not wp.id or not wp.source or not wp.url:
            raise ValueError("Wallpaper is missing required fields")
        self._wallpapers[wp.uid] = wp
        return wp

    async def handle_apply(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            wp = self._wallpaper_from_request(data)

            # If local path
            if wp.source == "local" and Path(wp.url).is_file():
                file_path = Path(wp.url)
            else:
                full = await self.engine.fetch_full(wp)
                file_path = full.path

            target = self.config.get("apply_target") or "both"
            try:
                gnome.apply_wallpaper(file_path, self.config.get("picture_options"), target=target)
            except TypeError:
                gnome.apply_wallpaper(file_path, self.config.get("picture_options"))

            # Sync GNOME accent if enabled
            if self.config.get("sync_gnome_accent"):
                pal = palette.extract_palette(file_path)
                if pal:
                    gnome.set_gnome_accent_color(palette.palette_gnome_accent(pal))

            self.config.add_history_entry(wp.to_dict())
            return web.json_response({"ok": True, "path": str(file_path)})
        except Exception as exc:
            logger.error("Failed to apply wallpaper from web: %s", exc)
            return web.json_response({"ok": False, "message": str(exc)}, status=500)

    async def handle_save(self, request: web.Request) -> web.Response:
        try:
            wp = self._wallpaper_from_request(await request.json())
            full = await self.engine.fetch_full(wp)
            directory = saved_dir()
            directory.mkdir(parents=True, exist_ok=True)
            destination = directory / full.path.name
            if full.path.resolve() != destination.resolve():
                shutil.copy2(full.path, destination)
            return web.json_response({"ok": True, "path": str(destination)})
        except Exception as exc:
            logger.error("Failed to save wallpaper: %s", exc)
            return web.json_response({"ok": False, "message": str(exc)}, status=500)

    async def handle_classify(self, request: web.Request) -> web.Response:
        backend = None
        try:
            backend = self.config.get("ai_backend")
            if backend == "gemini" and not self.config.api_key("gemini"):
                return web.json_response({"error": "Add a Gemini API key in Settings before using Gemini."}, status=400)
            wp = self._wallpaper_from_request(await request.json())
            full = await self.engine.fetch_full(wp)
            hint = f"{wp.title} {' '.join(wp.tags)}"
            if backend == "gemini":
                classes = await classify_with_gemini(
                    self.engine.http, full.path, self.config.api_key("gemini"), hint,
                    self.config.get("gemini_model"),
                )
            else:
                classes = await asyncio.to_thread(Classifier(backend).classify, full.path, hint)
            self.store.set_classes(wp.uid, classes)
            return web.json_response({
                "uid": wp.uid,
                "categories": self.store.get_classes(wp.uid) or [],
            })
        except Exception as exc:
            if backend == "gemini":
                code, message, status = self._gemini_error(exc)
                return web.json_response({"code": code, "error": message}, status=status)
            logger.error("Failed to classify wallpaper: %s", exc)
            return web.json_response({"error": str(exc)}, status=500)

    async def handle_assistant_search(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except (json.JSONDecodeError, web.HTTPBadRequest):
            return web.json_response({"error": "Expected a JSON object"}, status=400)
        raw_prompt = data.get("prompt") if isinstance(data, dict) else None
        prompt = raw_prompt.strip() if isinstance(raw_prompt, str) else ""
        if not prompt or len(prompt) > 500:
            return web.json_response({"error": "Enter a wallpaper request under 500 characters."}, status=400)
        api_key = self.config.api_key("gemini")
        if not api_key:
            return web.json_response({"error": "Add a Gemini API key in Settings before searching."}, status=400)

        try:
            intent = await interpret_wallpaper_request(
                self.engine.http, prompt, api_key, self.config.get("gemini_model")
            )
            collected: List[Wallpaper] = []
            self._source_statuses = await self.engine.search(
                intent["query"], intent["category"], 1, self.engine.enabled_keys(), set(),
                lambda _key, wallpapers: collected.extend(wallpapers),
            )
        except Exception as exc:
            code, message, status = self._gemini_error(exc)
            return web.json_response({"code": code, "error": message}, status=status)

        unique: Dict[str, Wallpaper] = {}
        for wallpaper in collected:
            unique.setdefault(wallpaper.uid, wallpaper)
        results = list(unique.values())[:60]
        self._wallpapers.update({wallpaper.uid: wallpaper for wallpaper in results})
        return web.json_response({
            **intent,
            "wallpapers": [
                {
                    **wallpaper.to_dict(),
                    "favorite": self.store.is_favorite(wallpaper),
                    "categories": self.store.get_classes(wallpaper.uid) or [],
                }
                for wallpaper in results
            ],
        })

    async def handle_folders(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            folder = data.get("path", "").strip() if isinstance(data, dict) else ""
            if not folder:
                return web.json_response({"error": "A folder path is required"}, status=400)
            if request.method == "POST":
                if not self.local_mgr.add_folder(folder):
                    return web.json_response({"error": "Folder does not exist or is already added"}, status=400)
            else:
                self.local_mgr.remove_folder(folder)
            return web.json_response({"folders": self.config.get("local_folders")})
        except (json.JSONDecodeError, web.HTTPBadRequest) as exc:
            return web.json_response({"error": str(exc)}, status=400)

    async def handle_import(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            paths = data.get("paths") if isinstance(data, dict) else None
            if not isinstance(paths, list) or not all(isinstance(item, str) for item in paths):
                return web.json_response({"error": "Expected a list of image paths"}, status=400)
            wallpapers = self.local_mgr.import_files([Path(item) for item in paths])
            self._wallpapers.update({wp.uid: wp for wp in wallpapers})
            return web.json_response({"imported": [wp.to_dict() for wp in wallpapers]})
        except (json.JSONDecodeError, web.HTTPBadRequest) as exc:
            return web.json_response({"error": str(exc)}, status=400)

    async def handle_clear_cache(self, request: web.Request) -> web.Response:
        freed = 0
        if THUMB_DIR.is_dir():
            for item in THUMB_DIR.iterdir():
                if item.is_file():
                    try:
                        freed += item.stat().st_size
                        item.unlink()
                    except OSError as exc:
                        logger.warning("Could not remove cached thumbnail %s: %s", item, exc)
        return web.json_response({"ok": True, "bytes_freed": freed})

    async def handle_clear_downloads(self, request: web.Request) -> web.Response:
        return web.json_response({
            "ok": True,
            "bytes_freed": self.engine.prune(keep=gnome.current_wallpaper(), clear_all=True),
        })

    async def handle_backup(self, request: web.Request) -> web.Response:
        if request.method == "GET":
            return web.json_response({
                "version": __version__,
                "settings": self.config.snapshot(),
                "favorites": [wp.to_dict() for wp in self.store.favorites()],
            })
        try:
            data = await request.json()
            if not isinstance(data, dict) or not isinstance(data.get("settings"), dict):
                raise ValueError("Backup file is invalid")
            settings = data["settings"]
            allowed = set(DEFAULTS) - {"api_keys"}
            for key, value in settings.items():
                if key in allowed:
                    self.config.set(key, value)
            if isinstance(settings.get("api_keys"), dict):
                for name, value in settings["api_keys"].items():
                    if name in self.config.get("api_keys") and isinstance(value, str):
                        self.config.set_api_key(name, value)
            favorites = data.get("favorites", [])
            if not isinstance(favorites, list):
                raise ValueError("Backup favourites are invalid")
            for entry in favorites:
                wp = self._wallpaper_from_request(entry)
                if not self.store.is_favorite(wp):
                    self.store.toggle_favorite(wp)
            return web.json_response({"ok": True})
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, web.HTTPBadRequest) as exc:
            return web.json_response({"error": str(exc) or "Invalid backup"}, status=400)

    async def handle_shuffle(self, request: web.Request) -> web.Response:
        candidates = [wp for wp in self.store.favorites() if wp.source != "local"]
        if not candidates:
            # query general sources
            collected = []
            await self.engine.search("", None, 1, list(self.engine.sources.keys())[:4], set(), lambda k, wps: collected.extend(wps))
            candidates = collected

        if not candidates:
            return web.json_response({"ok": False, "message": "No wallpapers found to shuffle"}, status=404)

        import random
        wp = random.choice(candidates)
        if wp.source == "local" and Path(wp.url).is_file():
            file_path = Path(wp.url)
        else:
            full = await self.engine.fetch_full(wp)
            file_path = full.path

        try:
            gnome.apply_wallpaper(file_path, self.config.get("picture_options"))
        except TypeError:
            gnome.apply_wallpaper(file_path)

        if self.config.get("sync_gnome_accent"):
            pal = palette.extract_palette(file_path)
            if pal:
                gnome.set_gnome_accent_color(palette.palette_gnome_accent(pal))

        return web.json_response({"ok": True, "title": wp.title, "path": str(file_path)})

    async def handle_scrape(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            url = data.get("url", "").strip()
            if not url or not url.startswith(("http://", "https://")):
                return web.json_response({"error": "Invalid URL"}, status=400)

            html = await self.engine.http.get_text(url)
            wallpapers = UniversalWebScraper.extract_wallpapers(html, url)
            return web.json_response([w.to_dict() for w in wallpapers])
        except Exception as exc:
            logger.error("Scrape error: %s", exc)
            return web.json_response({"error": str(exc)}, status=500)

    async def start(self, host: str = "127.0.0.1", port: int = 5910) -> str:
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, host, port)
        await self.site.start()
        if port == 0 and self.site._server and self.site._server.sockets:
            port = self.site._server.sockets[0].getsockname()[1]
        url = f"http://{host}:{port}"
        logger.info("Lumi Web Companion started at %s", url)
        return url

    async def stop(self) -> None:
        if self.runner:
            await self.runner.cleanup()
            self.runner = None
            self.site = None
