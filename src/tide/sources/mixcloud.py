"""Mixcloud source.

DJ-mix oriented — tracks here are typically 1–3 hours long. Search uses
the official JSON API (``api.mixcloud.com/search/``, no auth needed);
yt-dlp resolves streams from show permalinks.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from .. import cache
from .base import MusicSource, StreamRef, Track
from ._ytdlp import duration_str, resolve_audio_url


SOURCE_SLUG = "mixcloud"

_SEARCH_URL = "https://api.mixcloud.com/search/"
_USER_AGENT = "tide/1.0"
_TIMEOUT_SECONDS = 10.0

# ``pictures`` dict keys, best-first, for list thumbnails.
_PICTURE_KEYS = ("extra_large", "large", "640wx640h", "medium", "thumbnail")


def _pick_picture(pictures) -> str:
    if not isinstance(pictures, dict):
        return ""
    for key in _PICTURE_KEYS:
        v = pictures.get(key)
        if isinstance(v, str) and v:
            return v
    return ""


def _cloudcast_to_track(c: dict) -> Track | None:
    """One ``data[]`` cloudcast from the search API → Track."""
    url = c.get("url") or ""
    if not url:
        return None
    secs = int(c.get("audio_length") or 0)
    user = c.get("user") if isinstance(c.get("user"), dict) else {}
    return Track(
        video_id=url,
        title=c.get("name", "") or "",
        artists=user.get("name") or user.get("username") or "",
        album="",
        duration=duration_str(secs),
        duration_seconds=secs,
        thumbnail=_pick_picture(c.get("pictures")),
        source=SOURCE_SLUG,
        extras={"url": url},
    )


class MixcloudSource(MusicSource):
    slug = SOURCE_SLUG
    name = "mixcloud"
    icon = "mixcloud"
    needs_auth = False
    backend_slug = "mpv"
    short_tag = "MC"
    capabilities = frozenset()    # search-only in v1.2.0

    STREAM_TTL_SECONDS = 24 * 3600

    def is_authenticated(self) -> bool:
        return True

    def status_text(self) -> str:
        return "no auth required"

    def search_songs(self, query: str, limit: int = 20) -> list[Track]:
        if not query.strip():
            return []
        params = urllib.parse.urlencode({
            "q": query,
            "type": "cloudcast",
            "limit": int(limit),
        })
        req = urllib.request.Request(
            _SEARCH_URL + "?" + params,
            headers={"User-Agent": _USER_AGENT},
        )
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
                data = json.loads(resp.read(16 * 1024 * 1024).decode("utf-8", errors="replace"))
        except Exception:
            return []
        items = data.get("data") if isinstance(data, dict) else None
        out: list[Track] = []
        for c in items or []:
            if not isinstance(c, dict):
                continue
            tr = _cloudcast_to_track(c)
            if tr is not None:
                out.append(tr)
                if len(out) >= limit:
                    break
        return out

    def resolve_stream(self, track: Track) -> StreamRef:
        cached = cache.get_stream_url(SOURCE_SLUG, track.video_id)
        if cached:
            return StreamRef(backend="mpv", payload=cached)
        url = resolve_audio_url(track.video_id, format_spec="bestaudio/best")
        cache.put_stream_url(SOURCE_SLUG, track.video_id, url, ttl_seconds=self.STREAM_TTL_SECONDS)
        return StreamRef(backend="mpv", payload=url)
