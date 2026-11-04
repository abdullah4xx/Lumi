"""Small JSON stores: favourites and cached AI classifications."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Dict, List, Tuple

from .config import DATA_DIR
from .models import Wallpaper

logger = logging.getLogger("lumi.store")


def _atomic_write(path: Path, data) -> None:
    tmp = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        with os.fdopen(fd, "w") as fh:
            json.dump(data, fh)
        os.replace(tmp, path)
        tmp = None
    except (OSError, TypeError, ValueError) as exc:
        logger.warning("Could not write %s: %s", path, exc)
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _read(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


class Store:
    def __init__(self, directory: Path = DATA_DIR):
        self.dir = directory
        self._lock = threading.RLock()
        raw = _read(directory / "favorites.json", [])
        self._favs: Dict[str, Wallpaper] = {}
        for d in raw if isinstance(raw, list) else []:
            try:
                w = Wallpaper.from_dict(d)
                self._favs[w.uid] = w
            except (KeyError, TypeError, ValueError, AttributeError):
                continue
        cls = _read(directory / "classes.json", {})
        self._classes: Dict[str, List[Tuple[str, float]]] = {}
        for k, v in (cls.items() if isinstance(cls, dict) else []):
            try:
                self._classes[str(k)] = [(str(c), float(s)) for c, s in v]
            except (TypeError, ValueError):
                continue                                  # skip a damaged entry instead of refusing to start

    # favourites -------------------------------------------------------
    def is_favorite(self, wp: Wallpaper) -> bool:
        with self._lock:
            return wp.uid in self._favs

    def toggle_favorite(self, wp: Wallpaper) -> bool:
        with self._lock:
            if wp.uid in self._favs:
                del self._favs[wp.uid]
                on = False
            else:
                self._favs[wp.uid] = wp
                on = True
            _atomic_write(self.dir / "favorites.json", [w.to_dict() for w in self._favs.values()])
            return on

    def favorites(self) -> List[Wallpaper]:
        with self._lock:
            return list(self._favs.values())

    # classifications --------------------------------------------------
    def get_classes(self, uid: str):
        with self._lock:
            return self._classes.get(uid)

    def set_classes(self, uid: str, classes: List[Tuple[str, float]]) -> None:
        with self._lock:
            self._classes[uid] = classes
            if len(self._classes) > 5000:               # keep the file bounded
                for k in list(self._classes)[:1000]:
                    del self._classes[k]
            _atomic_write(self.dir / "classes.json", self._classes)
