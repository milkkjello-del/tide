"""Cache for stream URLs and album art.

Stream URLs are TTL'd because YouTube's CDN URLs expire ~6h after fetch.
Album art is mtime-pruned because thumbs are small and we just don't want
the directory growing unbounded.

The stream cache is a single JSON file:
    ~/.cache/tide/streams.json   {video_id: {url, expires_at}}

It's capped on save: oldest by expires_at first, then by total entry count.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import config


STREAM_TTL_SECONDS = 4 * 3600          # YT URLs typically last ~6h
STREAM_MAX_ENTRIES = 500
STREAM_MAX_BYTES = 5 * 1024 * 1024     # 5 MB
ART_MAX_FILES = 1000


# In-memory mirror, populated lazily from disk.
_stream_mem: dict[str, tuple[str, float]] | None = None


# ---------- stream cache ----------


def _load_stream_disk() -> dict[str, tuple[str, float]]:
    path = config.STREAM_CACHE_FILE
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return {k: (v["url"], float(v["expires_at"])) for k, v in raw.items()}
    except Exception:
        return {}


def _save_stream_disk(cache: dict[str, tuple[str, float]]) -> None:
    path = config.STREAM_CACHE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = {k: {"url": u, "expires_at": exp} for k, (u, exp) in cache.items()}
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(serializable, f)
    tmp.replace(path)


def _prune_stream_cache(cache: dict[str, tuple[str, float]]) -> None:
    """Drop expired entries first, then trim to size cap by oldest expires_at."""
    now = time.time()
    expired = [k for k, (_, exp) in cache.items() if exp <= now]
    for k in expired:
        cache.pop(k, None)

    if len(cache) <= STREAM_MAX_ENTRIES:
        return

    # Sort by expires_at ascending; the smallest are closest to expiry.
    by_age = sorted(cache.items(), key=lambda kv: kv[1][1])
    keep = dict(by_age[-STREAM_MAX_ENTRIES:])
    cache.clear()
    cache.update(keep)


def _ensure_stream_loaded() -> dict[str, tuple[str, float]]:
    global _stream_mem
    if _stream_mem is None:
        _stream_mem = _load_stream_disk()
        _prune_stream_cache(_stream_mem)
    return _stream_mem


def get_stream_url(video_id: str) -> str | None:
    """Return a cached URL if still valid, else None."""
    mem = _ensure_stream_loaded()
    cached = mem.get(video_id)
    if not cached:
        return None
    url, exp = cached
    if exp <= time.time():
        return None
    return url


def put_stream_url(video_id: str, url: str, ttl_seconds: float = STREAM_TTL_SECONDS) -> None:
    mem = _ensure_stream_loaded()
    mem[video_id] = (url, time.time() + ttl_seconds)
    _prune_stream_cache(mem)
    try:
        _save_stream_disk(mem)
    except Exception:
        pass
    _enforce_byte_cap()


def _enforce_byte_cap() -> None:
    path = config.STREAM_CACHE_FILE
    try:
        size = path.stat().st_size
    except OSError:
        return
    if size <= STREAM_MAX_BYTES:
        return
    # Halve the cache by oldest expires_at and re-save.
    mem = _ensure_stream_loaded()
    by_age = sorted(mem.items(), key=lambda kv: kv[1][1])
    keep = dict(by_age[len(by_age) // 2:])
    mem.clear()
    mem.update(keep)
    try:
        _save_stream_disk(mem)
    except Exception:
        pass


# ---------- art cache prune ----------


def prune_art_cache() -> int:
    """Keep newest ART_MAX_FILES files in the art cache dir. Returns count removed."""
    art_dir: Path = config.ART_CACHE_DIR
    if not art_dir.is_dir():
        return 0
    try:
        entries = [p for p in art_dir.iterdir() if p.is_file()]
    except OSError:
        return 0
    if len(entries) <= ART_MAX_FILES:
        return 0
    entries.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    to_remove = entries[ART_MAX_FILES:]
    removed = 0
    for p in to_remove:
        try:
            p.unlink()
            removed += 1
        except OSError:
            pass
    return removed
