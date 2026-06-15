"""Thin wrapper over ytmusicapi + yt-dlp.

Search returns normalized Track records. Stream URL resolution delegates to
the shared cache helper in `cache.py` (size-capped, TTL'd).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import yt_dlp
from ytmusicapi import YTMusic

from . import cache


@dataclass
class Track:
    video_id: str
    title: str
    artists: str
    album: str = ""
    duration: str = ""           # "3:42"
    duration_seconds: int = 0
    thumbnail: str = ""
    extras: dict = field(default_factory=dict)


@dataclass
class PlaylistEntry:
    playlist_id: str
    title: str
    description: str = ""
    thumbnail: str = ""


@dataclass
class PlaylistDetail:
    playlist_id: str
    title: str
    description: str = ""
    track_count: int = 0
    thumbnail: str = ""
    tracks: list = field(default_factory=list)


@dataclass
class AlbumEntry:
    browse_id: str
    title: str
    artists: str = ""
    year: str = ""
    thumbnail: str = ""
    playlist_id: str = ""


@dataclass
class ArtistEntry:
    channel_id: str
    name: str
    thumbnail: str = ""
    subscribers: str = ""


@dataclass
class AlbumDetail:
    browse_id: str
    title: str
    artists: str = ""
    year: str = ""
    duration: str = ""
    track_count: int = 0
    thumbnail: str = ""
    description: str = ""
    tracks: list = field(default_factory=list)


@dataclass
class ArtistDetail:
    channel_id: str
    name: str
    description: str = ""
    subscribers: str = ""
    monthly_listeners: str = ""
    thumbnail: str = ""
    top_songs: list = field(default_factory=list)        # list[Track]
    albums: list = field(default_factory=list)           # list[AlbumEntry]
    singles: list = field(default_factory=list)          # list[AlbumEntry]
    related: list = field(default_factory=list)          # list[ArtistEntry]


@dataclass
class ShelfItem:
    """One card on an Explore shelf. Polymorphic — only one of the *_entry
    fields is populated per item; the UI dispatches on ``kind``."""
    kind: str   # "song" | "video" | "album" | "playlist" | "artist"
    title: str
    subtitle: str = ""
    thumbnail: str = ""
    track: Track | None = None
    album: AlbumEntry | None = None
    artist: ArtistEntry | None = None
    playlist: PlaylistEntry | None = None


@dataclass
class Shelf:
    title: str
    items: list = field(default_factory=list)        # list[ShelfItem]


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
    # watch_playlist uses "thumbnail" key (singular), search uses "thumbnails"
    thumbs = item.get("thumbnails") or item.get("thumbnail")
    return Track(
        video_id=vid,
        title=item.get("title", ""),
        artists=_join_artists(item.get("artists")),
        album=album,
        duration=duration,
        duration_seconds=secs,
        thumbnail=_thumb(thumbs),
        extras=item,
    )


class Api:
    """Wraps a YTMusic client. All ytmusicapi-facing code lives here."""

    def __init__(self, yt: YTMusic) -> None:
        self.yt = yt

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

    def get_library_playlists(self, limit: int = 100) -> list["PlaylistEntry"]:
        """Return the user's playlists (including 'Liked Music' as 'LM')."""
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

    def get_playlist(self, playlist_id: str, limit: int = 500) -> "PlaylistDetail":
        """Fetch playlist metadata + tracks. Works for user playlists and 'LM'."""
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

    # ---------- discovery surfaces ----------

    def get_home(self, limit: int = 5) -> list[Shelf]:
        """YT Music's Home: shelves like 'Listen again', 'Quick picks', etc."""
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

    def _shelf_item_from_raw(self, c: dict) -> "ShelfItem | None":
        thumb = _thumb(c.get("thumbnails"))
        title = c.get("title", "") or ""
        # song / video
        if c.get("videoId"):
            tr = _to_track(c)
            if tr is None:
                return None
            return ShelfItem(
                kind="video" if c.get("videoType") == "MUSIC_VIDEO_TYPE_OMV" else "song",
                title=title, subtitle=tr.artists, thumbnail=thumb, track=tr,
            )
        # album
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
        # artist
        if c.get("browseId", "").startswith("UC") and c.get("type") != "playlist":
            return ShelfItem(
                kind="artist", title=title, subtitle="artist", thumbnail=thumb,
                artist=ArtistEntry(
                    channel_id=c.get("browseId", ""),
                    name=title, thumbnail=thumb,
                ),
            )
        # playlist
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
        # Top songs
        songs: list[Track] = []
        for s in (raw.get("songs", {}) or {}).get("results", []) or []:
            tr = _to_track(s)
            if tr:
                songs.append(tr)
        # Albums / singles
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
        # Related artists
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
            # Album tracks often lack their own album/thumbnail/artist string —
            # fill those from the album metadata so cards have everything.
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

    # ---------- like / radio / lyrics (existing) ----------

    def rate_song(self, video_id: str, liked: bool) -> None:
        """Like or unlike a song. ytmusicapi's LikeStatus uses LIKE / INDIFFERENT."""
        if not video_id:
            return
        rating = "LIKE" if liked else "INDIFFERENT"
        # ytmusicapi accepts the bare string per the LikeStatus enum value.
        self.yt.rate_song(video_id, rating)

    def is_liked(self, video_id: str) -> bool | None:
        """Best-effort check. Returns None if we can't tell quickly."""
        # YT Music doesn't have a single-call endpoint for like state, so we
        # peek at the watch playlist (which carries likeStatus on the seed
        # track). Cached at most once per video_id per session.
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
        """Return plain lyrics text for `video_id`, or None if unavailable.

        Skips timestamped fetch (which needs the mobile client context that
        cookie-auth can't use). For tide's purposes static text is fine.
        """
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

    def get_lyrics_for_track(self, track: "Track"):
        """Return a ``LyricsResult`` (plain + timed) or None.

        Tries YT Music first (plain only); falls back to LRClib for timed.
        """
        from .lyrics_provider import LyricsResult, fetch_lrclib
        plain = self.get_lyrics_for(track.video_id)
        if plain:
            # YT Music has it — check LRClib in case it has TIMED for the same
            # so we can offer karaoke mode alongside.
            timed = fetch_lrclib(
                title=track.title or "",
                artist=track.artists or "",
                album=track.album or "",
                duration_seconds=int(track.duration_seconds or 0),
            )
            if timed is not None and timed.has_timed:
                return LyricsResult(plain_text=plain, timed_lines=timed.timed_lines)
            return LyricsResult(plain_text=plain)
        # No YT lyrics — try LRClib entirely.
        return fetch_lrclib(
            title=track.title or "",
            artist=track.artists or "",
            album=track.album or "",
            duration_seconds=int(track.duration_seconds or 0),
        )

    def get_radio(self, video_id: str, exclude: set[str] | None = None) -> list[Track]:
        """Return the YT Music auto-generated radio for a track.

        Drops the seed track itself plus anything in `exclude` (typically the
        current queue's video_ids), so callers can splice the result without
        introducing dupes.
        """
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


# ---------- stream URL resolution (yt-dlp) ----------


def resolve_stream_url(video_id: str) -> str:
    """Return a playable audio URL for the given YT Music video id.

    Uses tide.cache for the in-memory + on-disk TTL cache.
    """
    cached_url = cache.get_stream_url(video_id)
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

    cache.put_stream_url(video_id, stream_url)
    return stream_url
