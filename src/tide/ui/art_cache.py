"""Shared thumbnail cache.

Track rows and cards all want the same per-track image. Loading them
independently wastes bandwidth and triggers redundant repaints, so we
centralise here.

Pipeline per URL:
  memory (LRU)  →  disk (~/.cache/tide/art/<sha1>.bin)  →  network

Callers don't worry about lifecycle. They:
  1. call ``request(url, callback)``  where callback receives QImage|None
  2. paint a placeholder for now
  3. when the callback fires (on the GUI thread), repaint with the image

The cache emits a global ``image_loaded(url, image)`` signal too so
delegates can listen once and invalidate the right model index when it
fires, instead of binding a closure per cell.
"""
from __future__ import annotations

import hashlib
from collections import OrderedDict
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from .. import config


MEM_LRU_LIMIT = 256


def _hash(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()


def _disk_path(url: str) -> Path:
    return config.ART_CACHE_DIR / _hash(url)


class _ArtCache(QObject):
    image_loaded = Signal(str, QImage)  # url, image

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._net = QNetworkAccessManager(self)
        # url -> QImage
        self._mem: "OrderedDict[str, QImage]" = OrderedDict()
        # url -> list of one-shot callbacks queued before the image arrives
        self._waiting: dict[str, list[Callable[[QImage | None], None]]] = {}
        # currently in-flight QNetworkReplies, keyed by url (for dedup)
        self._inflight: set[str] = set()

    # ---------- public API ----------

    def get(self, url: str) -> QImage | None:
        """Return the cached image if available right now, else None."""
        if not url:
            return None
        img = self._mem.get(url)
        if img is not None:
            self._touch(url)
            return img
        return self._maybe_load_disk(url)

    def request(self, url: str, callback: Callable[[QImage | None], None] | None = None) -> QImage | None:
        """Get-or-fetch. Returns image immediately if cached, else None and
        invokes ``callback`` later (on GUI thread). Always safe to call.
        """
        if not url:
            if callback:
                callback(None)
            return None
        img = self._mem.get(url)
        if img is not None:
            self._touch(url)
            return img
        img = self._maybe_load_disk(url)
        if img is not None:
            return img
        if callback is not None:
            self._waiting.setdefault(url, []).append(callback)
        self._fetch(url)
        return None

    def warm(self, urls: list[str]) -> None:
        """Pre-fetch a batch (e.g. all visible thumbs in a shelf)."""
        for u in urls:
            self.request(u)

    # ---------- internals ----------

    def _touch(self, url: str) -> None:
        try:
            self._mem.move_to_end(url)
        except KeyError:
            pass

    def _store(self, url: str, img: QImage) -> None:
        self._mem[url] = img
        self._touch(url)
        while len(self._mem) > MEM_LRU_LIMIT:
            self._mem.popitem(last=False)

    def _maybe_load_disk(self, url: str) -> QImage | None:
        path = _disk_path(url)
        if not path.is_file():
            return None
        try:
            data = path.read_bytes()
        except OSError:
            return None
        img = QImage()
        if not img.loadFromData(data):
            return None
        self._store(url, img)
        return img

    def _save_disk(self, url: str, raw: bytes) -> None:
        path = _disk_path(url)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        except OSError:
            pass

    def _fetch(self, url: str) -> None:
        if url in self._inflight:
            return
        self._inflight.add(url)
        req = QNetworkRequest(QUrl(url))
        reply = self._net.get(req)

        def on_finished():
            try:
                err = reply.error()
            except RuntimeError:
                self._inflight.discard(url)
                return
            if err != QNetworkReply.NoError:
                reply.deleteLater()
                self._inflight.discard(url)
                self._fire_callbacks(url, None)
                return
            data = bytes(reply.readAll().data())
            reply.deleteLater()
            self._inflight.discard(url)
            img = QImage()
            if not img.loadFromData(data):
                self._fire_callbacks(url, None)
                return
            self._store(url, img)
            self._save_disk(url, data)
            self.image_loaded.emit(url, img)
            self._fire_callbacks(url, img)

        reply.finished.connect(on_finished)

    def _fire_callbacks(self, url: str, img: QImage | None) -> None:
        cbs = self._waiting.pop(url, [])
        for cb in cbs:
            try:
                cb(img)
            except Exception:
                pass


_instance: _ArtCache | None = None


def cache() -> _ArtCache:
    global _instance
    if _instance is None:
        _instance = _ArtCache()
    return _instance
