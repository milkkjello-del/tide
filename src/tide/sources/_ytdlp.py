"""Shared yt-dlp helpers for SoundCloud / Bandcamp / Mixcloud sources.

yt-dlp's ``extract_info`` is the universal hammer: ``ytsearchN:query``,
``scsearchN:query``, direct permalink URLs, etc. all funnel through it.

This module isolates the search-prefix dispatch and the playable-URL
resolution so each source stays a thin shim implementing the
``MusicSource`` surface.
"""
from __future__ import annotations

from typing import Any

import yt_dlp


# Quiet defaults — yt-dlp prints to stdout by default, which trashes the
# Qt-console UX. ``no_warnings`` suppresses non-fatal extractor noise.
_BASE_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "noplaylist": True,
    "extract_flat": False,
}


def search_flat(search_prefix: str, query: str, limit: int = 20) -> list[dict]:
    """Run a yt-dlp search query (``scsearchN:foo`` etc.) returning the raw
    metadata entries. Failure → empty list."""
    if not query.strip():
        return []
    opts = dict(_BASE_OPTS)
    opts["extract_flat"] = "in_playlist"
    spec = f"{search_prefix}{int(limit)}:{query}"
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(spec, download=False)
    except Exception:
        return []
    if not isinstance(info, dict):
        return []
    entries = info.get("entries") or []
    out = []
    for e in entries:
        if isinstance(e, dict):
            out.append(e)
    return out


def resolve_audio_url(url: str, *, format_spec: str = "bestaudio/best") -> str:
    """Fully resolve a single page URL to a playable audio URL."""
    opts = dict(_BASE_OPTS)
    opts["format"] = format_spec
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not isinstance(info, dict):
        raise RuntimeError(f"no info for {url}")
    stream_url = info.get("url")
    if not stream_url and "requested_formats" in info:
        formats = info["requested_formats"]
        if formats:
            stream_url = formats[0].get("url")
    if not stream_url:
        # Some extractors return per-format lists only; pick the best audio.
        formats = info.get("formats") or []
        audio_only = [f for f in formats if f.get("acodec") and f.get("acodec") != "none"
                      and (f.get("vcodec") in (None, "none"))]
        if audio_only:
            audio_only.sort(key=lambda f: f.get("abr") or 0, reverse=True)
            stream_url = audio_only[0].get("url")
    if not stream_url:
        raise RuntimeError(f"no playable audio stream for {url}")
    return stream_url


def best_thumbnail(entry: dict) -> str:
    """yt-dlp ``thumbnails`` list → URL of the highest-res entry."""
    thumbs = entry.get("thumbnails")
    if isinstance(thumbs, list) and thumbs:
        with_res = [t for t in thumbs if isinstance(t, dict)]
        with_res.sort(key=lambda t: (t.get("width") or 0) * (t.get("height") or 0))
        return with_res[-1].get("url", "") if with_res else ""
    t = entry.get("thumbnail")
    return t if isinstance(t, str) else ""


def duration_str(seconds: float | int | None) -> str:
    if not seconds:
        return ""
    s = int(seconds)
    if s >= 3600:
        return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"
    return f"{s // 60}:{s % 60:02d}"


def first_artist(entry: dict) -> str:
    for key in ("uploader", "creator", "artist", "channel"):
        v = entry.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""
