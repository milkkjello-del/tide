"""SoundCloud source.

No auth needed for public catalog. yt-dlp handles search via the
``scsearchN:`` prefix and resolves stream URLs from track permalinks.

Limitations carried over from the plan:
- No library / liked tracks (would need OAuth — punted to v1.3).
- Radio is built off the ``related`` field that yt-dlp returns for a track.
"""
from __future__ import annotations

from typing import Iterable

from .. import cache
from .base import MusicSource, StreamRef, Track, safe_int
from ._ytdlp import (
    best_thumbnail,
    duration_str,
    first_artist,
    resolve_audio_url,
    search_flat,
)


SOURCE_SLUG = "soundcloud"


def _entry_to_track(e: dict) -> Track | None:
    url = e.get("url") or e.get("webpage_url") or ""
    if not url and e.get("id"):
        url = f"https://soundcloud.com/-/tracks/{e['id']}"
    if not url:
        return None
    secs = safe_int(e.get("duration"))
    return Track(
        video_id=url,
        title=e.get("title", "") or "",
        artists=first_artist(e),
        album="",
        duration=duration_str(secs),
        duration_seconds=secs,
        thumbnail=best_thumbnail(e),
        source=SOURCE_SLUG,
        extras={"url": url},
    )


class SoundCloudSource(MusicSource):
    slug = SOURCE_SLUG
    name = "soundcloud"
    icon = "soundcloud"
    needs_auth = False
    backend_slug = "mpv"
    short_tag = "SC"
    capabilities = frozenset()    # search-only in v1.2.0

    STREAM_TTL_SECONDS = 12 * 3600

    def is_authenticated(self) -> bool:
        return True

    def status_text(self) -> str:
        return "no auth required"

    def search_songs(self, query: str, limit: int = 20) -> list[Track]:
        entries = search_flat("scsearch", query, limit=limit)
        out: list[Track] = []
        for e in entries:
            tr = _entry_to_track(e)
            if tr is not None:
                out.append(tr)
        return out

    def resolve_stream(self, track: Track) -> StreamRef:
        cached = cache.get_stream_url(SOURCE_SLUG, track.video_id)
        if cached:
            return StreamRef(backend="mpv", payload=cached)
        url = resolve_audio_url(track.video_id, format_spec="bestaudio/best")
        cache.put_stream_url(SOURCE_SLUG, track.video_id, url, ttl_seconds=self.STREAM_TTL_SECONDS)
        return StreamRef(backend="mpv", payload=url)
