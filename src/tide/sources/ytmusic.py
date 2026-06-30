"""YouTube Music source.

The original v1.0/v1.1 client class lived at ``tide.api.Api``. v1.2 lifts
it into the source abstraction: it now implements ``MusicSource``, and a
``tide.api`` shim keeps existing imports working.

Stream resolution is delegated to ``yt-dlp`` and cached per source via
``tide.cache`` so URLs survive page navigations without being refetched.
"""
from __future__ import annotations

from typing import Iterable

import yt_dlp
from ytmusicapi import YTMusic

from .. import cache
from .base import (
    AlbumDetail,
    AlbumEntry,
    ArtistDetail,
    ArtistEntry,
    MusicSource,
    NotSupportedError,
    PlaylistDetail,
    PlaylistEntry,
    Shelf,
    ShelfItem,
    StreamRef,
    Track,
)


SOURCE_SLUG = "ytmusic"


def _join_artists(items: Iterable[dict] | None) -> str:
    if not items:
        return ""
    names = [a.get("name", "") for a in items if isinstance(a, dict)]
    return ", ".join(n for n in names if n)


def _thumb(items: list[dict] | None) -> str:
    if not items:
        return ""
    return items[-1].get("url", "")


def _parse_hms(s: str) -> int:
    parts = [int(p) for p in s.split(":") if p.isdigit()]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return 0


def _to_track(item: dict) -> Track | None:
    vid = item.get("videoId")
    if not vid:
        return None
    duration = item.get("duration") or item.get("length") or ""
    secs = int(item.get("duration_seconds") or 0)
    if secs == 0 and duration and ":" in duration:
        secs = _parse_hms(duration)
    album = ""
    alb = item.get("album")
    if isinstance(alb, dict):
        album = alb.get("name", "")
    elif isinstance(alb, str):
        album = alb
    thumbs = item.get("thumbnails") or item.get("thumbnail")
    return Track(
        video_id=vid,
        title=item.get("title", ""),
        artists=_join_artists(item.get("artists")),
        album=album,
        duration=duration,
        duration_seconds=secs,
        thumbnail=_thumb(thumbs),
        source=SOURCE_SLUG,
        extras=item,
    )


class YTMusicSource(MusicSource):
    slug = SOURCE_SLUG
    name = "youtube music"
    icon = "ytmusic"
    needs_auth = True
    supports_in_app_auth = True
    backend_slug = "mpv"
    short_tag = "YT"
    capabilities = frozenset({
        "library", "albums", "artists", "videos",
        "home", "radio", "lyrics", "rating",
    })

    STREAM_TTL_SECONDS = 4 * 3600          # YT CDN URLs last ~6h

    def __init__(self, yt: YTMusic) -> None:
        self.yt = yt
        self._signed_out = False

    # ---------- auth surface ----------

    def is_authenticated(self) -> bool:
        return self.yt is not None and not self._signed_out

    def sign_out(self) -> None:
        """Delete the saved cookie auth and mark this live source signed-out.

        Without this override the Sources-tab sign-out button hit the base
        no-op, so the cookie file was never removed and the row kept saying
        "signed in". We delete ``browser.json`` (and the legacy oauth file)
        so the next launch re-runs the import wizard, and flip a flag so the
        row reflects the change immediately. The in-memory ``yt`` client is
        left intact — every browse/search method dereferences it, and the
        established re-auth UX is "restart to sign back in" — so nulling it
        would only invite AttributeErrors before the restart. The embedded
        webview profile is left untouched too, so re-signing-in can harvest
        fresh cookies from the still-live Google session in one click.
        """
        from .. import auth
        auth.clear_saved_auth()
        self._signed_out = True

    def begin_auth(self, parent_widget) -> bool:
        """Run the import wizard and refresh this live source's client so the
        user can sign back in *without restarting tide* — the recovery path
        for ``sign_out()``. Returns True iff auth now exists.

        The wizard writes ``browser.json`` itself on success; we just rebuild
        the YTMusic client from it and clear the signed-out flag so the row
        flips back to authenticated immediately.
        """
        from ..ui.wizard import SignInDialog
        from .. import auth
        dlg = SignInDialog(parent_widget)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return False
        try:
            self.yt = auth.yt_client()
        except Exception:
            return False
        self._signed_out = False
        return True

    def status_text(self) -> str:
        return "signed in (cookie import)" if self.is_authenticated() else "sign in via [import]"

    # ---------- required ----------

    def search_songs(self, query: str, limit: int = 20) -> list[Track]:
        if not query.strip():
            return []
        results = self.yt.search(query, filter="songs", limit=limit) or []
        out: list[Track] = []
        for item in results:
            tr = _to_track(item)
            if tr:
                out.append(tr)
        return out

    def resolve_stream(self, track: Track) -> StreamRef:
        url = resolve_stream_url(track.video_id)
        return StreamRef(backend="mpv", payload=url)

    # ---------- search filter dispatch ----------

    def search_albums(self, query: str, limit: int = 20) -> list[AlbumEntry]:
        if not query.strip():
            return []
        results = self.yt.search(query, filter="albums", limit=limit) or []
        out: list[AlbumEntry] = []
        for item in results:
            bid = item.get("browseId") or ""
            if not bid:
                continue
            out.append(AlbumEntry(
                browse_id=bid,
                title=item.get("title", "") or "",
                artists=_join_artists(item.get("artists")),
                year=str(item.get("year") or ""),
                thumbnail=_thumb(item.get("thumbnails")),
                playlist_id=item.get("playlistId", "") or "",
            ))
        return out

    def search_artists(self, query: str, limit: int = 20) -> list[ArtistEntry]:
        if not query.strip():
            return []
        results = self.yt.search(query, filter="artists", limit=limit) or []
        out: list[ArtistEntry] = []
        for item in results:
            cid = item.get("browseId") or ""
            if not cid:
                continue
            out.append(ArtistEntry(
                channel_id=cid,
                name=item.get("artist", "") or "",
                thumbnail=_thumb(item.get("thumbnails")),
                subscribers=str(item.get("subscribers") or ""),
            ))
        return out

    def search_videos(self, query: str, limit: int = 20) -> list[Track]:
        if not query.strip():
            return []
        results = self.yt.search(query, filter="videos", limit=limit) or []
        out: list[Track] = []
        for item in results:
            tr = _to_track(item)
            if tr:
                out.append(tr)
        return out

    # ---------- library + discovery ----------

    def get_library_playlists(self, limit: int = 100) -> list[PlaylistEntry]:
        items = self.yt.get_library_playlists(limit=limit) or []
        return [
            PlaylistEntry(
                playlist_id=p.get("playlistId", ""),
                title=p.get("title", ""),
                description=p.get("description", "") or "",
                thumbnail=_thumb(p.get("thumbnails")),
            )
            for p in items
            if p.get("playlistId")
        ]

    def get_playlist(self, playlist_id: str, limit: int = 500) -> PlaylistDetail:
        if playlist_id == "LM":
            raw = self.yt.get_liked_songs(limit=limit) or {}
        else:
            raw = self.yt.get_playlist(playlistId=playlist_id, limit=limit) or {}
        tracks: list[Track] = []
        for item in raw.get("tracks", []) or []:
            tr = _to_track(item)
            if tr:
                tracks.append(tr)
        return PlaylistDetail(
            playlist_id=playlist_id,
            title=raw.get("title", "") or "",
            description=raw.get("description", "") or "",
            track_count=int(raw.get("trackCount") or len(tracks)),
            thumbnail=_thumb(raw.get("thumbnails")),
            tracks=tracks,
        )

    def get_home(self, limit: int = 5) -> list[Shelf]:
        try:
            raw = self.yt.get_home(limit=limit) or []
        except Exception:
            return []
        out: list[Shelf] = []
        for shelf in raw:
            items: list[ShelfItem] = []
            for c in shelf.get("contents", []) or []:
                item = self._shelf_item_from_raw(c)
                if item:
                    items.append(item)
            if items:
                out.append(Shelf(title=shelf.get("title", "") or "", items=items))
        return out

    def _shelf_item_from_raw(self, c: dict) -> ShelfItem | None:
        thumb = _thumb(c.get("thumbnails"))
        title = c.get("title", "") or ""
        if c.get("videoId"):
            tr = _to_track(c)
            if tr is None:
                return None
            return ShelfItem(
                kind="video" if c.get("videoType") == "MUSIC_VIDEO_TYPE_OMV" else "song",
                title=title, subtitle=tr.artists, thumbnail=thumb, track=tr,
            )
        if c.get("browseId", "").startswith("MPREb") or c.get("type") == "Album":
            return ShelfItem(
                kind="album", title=title,
                subtitle=_join_artists(c.get("artists")),
                thumbnail=thumb,
                album=AlbumEntry(
                    browse_id=c.get("browseId", ""),
                    title=title,
                    artists=_join_artists(c.get("artists")),
                    year=str(c.get("year") or ""),
                    thumbnail=thumb,
                    playlist_id=c.get("playlistId", "") or "",
                ),
            )
        if c.get("browseId", "").startswith("UC") and c.get("type") != "playlist":
            return ShelfItem(
                kind="artist", title=title, subtitle="artist", thumbnail=thumb,
                artist=ArtistEntry(
                    channel_id=c.get("browseId", ""),
                    name=title, thumbnail=thumb,
                ),
            )
        if c.get("playlistId"):
            return ShelfItem(
                kind="playlist", title=title,
                subtitle=c.get("description", "") or "",
                thumbnail=thumb,
                playlist=PlaylistEntry(
                    playlist_id=c.get("playlistId", ""),
                    title=title,
                    description=c.get("description", "") or "",
                    thumbnail=thumb,
                ),
            )
        return None

    def get_artist(self, channel_id: str) -> ArtistDetail | None:
        if not channel_id:
            return None
        try:
            raw = self.yt.get_artist(channel_id)
        except Exception:
            return None
        songs: list[Track] = []
        for s in (raw.get("songs", {}) or {}).get("results", []) or []:
            tr = _to_track(s)
            if tr:
                songs.append(tr)
        def _entries(key: str) -> list[AlbumEntry]:
            out: list[AlbumEntry] = []
            for a in (raw.get(key, {}) or {}).get("results", []) or []:
                bid = a.get("browseId") or ""
                if not bid:
                    continue
                out.append(AlbumEntry(
                    browse_id=bid,
                    title=a.get("title", "") or "",
                    artists=_join_artists(a.get("artists")),
                    year=str(a.get("year") or ""),
                    thumbnail=_thumb(a.get("thumbnails")),
                    playlist_id=a.get("playlistId", "") or "",
                ))
            return out
        related: list[ArtistEntry] = []
        for r in (raw.get("related", {}) or {}).get("results", []) or []:
            cid = r.get("browseId") or ""
            if not cid:
                continue
            related.append(ArtistEntry(
                channel_id=cid,
                name=r.get("title", "") or "",
                thumbnail=_thumb(r.get("thumbnails")),
                subscribers=str(r.get("subscribers") or ""),
            ))
        return ArtistDetail(
            channel_id=channel_id,
            name=raw.get("name", "") or "",
            description=raw.get("description", "") or "",
            subscribers=str(raw.get("subscribers") or ""),
            monthly_listeners=str(raw.get("monthlyListeners") or ""),
            thumbnail=_thumb(raw.get("thumbnails")),
            top_songs=songs,
            albums=_entries("albums"),
            singles=_entries("singles"),
            related=related,
        )

    def get_album(self, browse_id: str) -> AlbumDetail | None:
        if not browse_id:
            return None
        try:
            raw = self.yt.get_album(browse_id)
        except Exception:
            return None
        tracks: list[Track] = []
        album_thumb = _thumb(raw.get("thumbnails"))
        album_artists = _join_artists(raw.get("artists"))
        for item in raw.get("tracks", []) or []:
            tr = _to_track(item)
            if tr is None:
                continue
            if not tr.album:
                tr.album = raw.get("title", "") or ""
            if not tr.thumbnail:
                tr.thumbnail = album_thumb
            if not tr.artists:
                tr.artists = album_artists
            tracks.append(tr)
        track_count = int(raw.get("trackCount") or len(tracks))
        return AlbumDetail(
            browse_id=browse_id,
            title=raw.get("title", "") or "",
            artists=album_artists,
            year=str(raw.get("year") or ""),
            duration=str(raw.get("duration") or ""),
            track_count=track_count,
            thumbnail=album_thumb,
            description=raw.get("description", "") or "",
            tracks=tracks,
        )

    # ---------- like / radio / lyrics ----------

    def rate_song(self, video_id: str, liked: bool) -> None:
        if not video_id:
            return
        rating = "LIKE" if liked else "INDIFFERENT"
        self.yt.rate_song(video_id, rating)

    def is_liked(self, video_id: str) -> bool | None:
        if not video_id:
            return None
        try:
            wp = self.yt.get_watch_playlist(videoId=video_id, limit=1)
        except Exception:
            return None
        tracks = wp.get("tracks", []) if isinstance(wp, dict) else []
        if not tracks:
            return None
        status = tracks[0].get("likeStatus")
        if status == "LIKE":
            return True
        if status in ("INDIFFERENT", "DISLIKE"):
            return False
        return None

    def get_lyrics_for(self, video_id: str) -> str | None:
        if not video_id:
            return None
        try:
            wp = self.yt.get_watch_playlist(videoId=video_id)
        except Exception:
            return None
        browse_id = wp.get("lyrics") if isinstance(wp, dict) else None
        if not browse_id:
            return None
        try:
            lyr = self.yt.get_lyrics(browse_id)
        except Exception:
            return None
        if not lyr:
            return None
        text = lyr.get("lyrics") if isinstance(lyr, dict) else getattr(lyr, "lyrics", None)
        if not text or not isinstance(text, str):
            return None
        return text

    def get_lyrics_for_track(self, track: Track):
        from ..lyrics_provider import LyricsResult, fetch_lrclib
        plain = self.get_lyrics_for(track.video_id)
        if plain:
            timed = fetch_lrclib(
                title=track.title or "",
                artist=track.artists or "",
                album=track.album or "",
                duration_seconds=int(track.duration_seconds or 0),
            )
            if timed is not None and timed.has_timed:
                return LyricsResult(plain_text=plain, timed_lines=timed.timed_lines)
            return LyricsResult(plain_text=plain)
        return fetch_lrclib(
            title=track.title or "",
            artist=track.artists or "",
            album=track.album or "",
            duration_seconds=int(track.duration_seconds or 0),
        )

    def get_radio(self, video_id: str, exclude: set[str] | None = None) -> list[Track]:
        if not video_id:
            return []
        excluded = set(exclude or ())
        excluded.add(video_id)
        res = self.yt.get_watch_playlist(videoId=video_id, radio=True)
        out: list[Track] = []
        for item in res.get("tracks", []) or []:
            tr = _to_track(item)
            if not tr or tr.video_id in excluded:
                continue
            excluded.add(tr.video_id)
            out.append(tr)
        return out


# ---------- yt-dlp stream URL resolution ----------


def resolve_stream_url(video_id: str) -> str:
    """Return a playable audio URL for the given YT Music video id.

    Uses tide.cache for the per-source TTL cache.
    """
    cached_url = cache.get_stream_url(SOURCE_SLUG, video_id)
    if cached_url:
        return cached_url

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "format": "bestaudio[acodec=opus]/bestaudio/best",
        "noplaylist": True,
    }
    url = f"https://music.youtube.com/watch?v={video_id}"
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    stream_url = info.get("url")
    if not stream_url and "requested_formats" in info:
        stream_url = info["requested_formats"][0].get("url")
    if not stream_url:
        raise RuntimeError(f"no playable audio stream for {video_id}")

    cache.put_stream_url(SOURCE_SLUG, video_id, stream_url, ttl_seconds=YTMusicSource.STREAM_TTL_SECONDS)
    return stream_url
