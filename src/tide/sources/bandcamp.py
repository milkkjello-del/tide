"""Bandcamp source.

Bandcamp has no official public API and yt-dlp has no search prefix for
it, so search hits the JSON autocomplete endpoint the site itself uses
(``/api/bcsearch_public_api/1/autocomplete_elastic``). Stream resolution
stays on yt-dlp's ``Bandcamp`` extractor via the track permalink; stream
URLs are stable per upload — we cache with effectively infinite TTL.
"""
from __future__ import annotations

import json
import urllib.request

from .. import cache
from .base import MusicSource, StreamRef, Track
from ._ytdlp import resolve_audio_url


SOURCE_SLUG = "bandcamp"

_SEARCH_URL = "https://bandcamp.com/api/bcsearch_public_api/1/autocomplete_elastic"
_USER_AGENT = "tide/1.0"
_TIMEOUT_SECONDS = 10.0


def _result_to_track(r: dict) -> Track | None:
    """One ``auto.results[]`` item → Track. Non-track hits → None."""
    if r.get("type") != "t":    # "t"=track, "a"=album, "b"=band
        return None
    url = r.get("item_url_path") or ""
    if url.startswith("/"):     # defensive: join if ever relative
        url = (r.get("item_url_root") or "").rstrip("/") + url
    if not url:
        return None
    art_id = r.get("art_id")
    # _4 = ~300px square, verified served for a<art_id>; ``img`` is the
    # endpoint's own (100px) fallback.
    thumb = f"https://f4.bcbits.com/img/a{int(art_id)}_4.jpg" if art_id else (r.get("img") or "")
    return Track(
        video_id=url,
        title=r.get("name", "") or "",
        artists=r.get("band_name", "") or "",
        album=r.get("album_name") or "",
        duration="",            # endpoint doesn't expose track length
        duration_seconds=0,
        thumbnail=thumb,
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
        if not query.strip():
            return []
        body = json.dumps({
            "search_text": query,
            "search_filter": "t",   # tracks only
            "full_page": False,
            "fan_id": None,
        }).encode("utf-8")
        req = urllib.request.Request(
            _SEARCH_URL,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": _USER_AGENT,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
                data = json.loads(resp.read(16 * 1024 * 1024).decode("utf-8", errors="replace"))
        except Exception:
            return []
        results = (data.get("auto") or {}).get("results") if isinstance(data, dict) else None
        out: list[Track] = []
        for r in results or []:
            if not isinstance(r, dict):
                continue
            tr = _result_to_track(r)
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
