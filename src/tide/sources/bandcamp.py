"""Bandcamp source.

yt-dlp covers Bandcamp via the ``bandcamp:`` extractor; search uses the
``bandcampsearchN:`` prefix (yt-dlp ≥ 2024.xx). Stream URLs are stable
per upload — we cache with effectively infinite TTL.
"""
from __future__ import annotations

from .. import cache
from .base import MusicSource, StreamRef, Track
from ._ytdlp import (
    best_thumbnail,
    duration_str,
    first_artist,
    resolve_audio_url,
    search_flat,
)


SOURCE_SLUG = "bandcamp"


def _entry_to_track(e: dict) -> Track | None:
    url = e.get("webpage_url") or e.get("url") or ""
    if not url:
        return None
    secs = int(e.get("duration") or 0)
    return Track(
        video_id=url,
        title=e.get("title", "") or "",
        artists=first_artist(e),
        album=e.get("album") or "",
        duration=duration_str(secs),
        duration_seconds=secs,
        thumbnail=best_thumbnail(e),
        source=SOURCE_SLUG,
        extras={"url": url},
    )


class BandcampSource(MusicSource):
    slug = SOURCE_SLUG
    name = "bandcamp"
    icon = "bandcamp"
    needs_auth = False
    backend_slug = "mpv"
    short_tag = "BC"
    capabilities = frozenset()    # search-only in v1.2.0

    # Bandcamp stream URLs don't rotate; keep them forever.
    STREAM_TTL_SECONDS = cache.NEVER_EXPIRES

    def is_authenticated(self) -> bool:
        return True

    def status_text(self) -> str:
        return "no auth required"

    def search_songs(self, query: str, limit: int = 20) -> list[Track]:
        entries = search_flat("bandcampsearch", query, limit=limit)
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
