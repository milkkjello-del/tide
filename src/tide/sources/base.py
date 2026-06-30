"""Source abstraction layer.

A `MusicSource` produces `Track` records and resolves them to a `StreamRef`
that its declared playback backend understands. The queue is source-agnostic
— each Track carries the slug of the source that produced it, and the
playback router uses that to dispatch.

For v1.1 there was only one implicit source (YouTube Music) and tracks
flowed straight to mpv. v1.2 introduces the abstraction; existing tracks
default to ``source="ytmusic"`` so sessions written under v1.1 keep playing.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterable, Optional


class NotSupportedError(Exception):
    """A source declined a capability call. Caller should treat as graceful."""


# ---------- shared dataclasses ----------

@dataclass
class Track:
    # `video_id` is the primary key per source. For YT Music it's the actual
    # videoId; for SoundCloud/Bandcamp/Mixcloud it's the canonical permalink
    # URL; for local files it's the absolute path.
    video_id: str
    title: str
    artists: str
    album: str = ""
    duration: str = ""
    duration_seconds: int = 0
    thumbnail: str = ""
    source: str = "ytmusic"
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
    top_songs: list = field(default_factory=list)
    albums: list = field(default_factory=list)
    singles: list = field(default_factory=list)
    related: list = field(default_factory=list)


@dataclass
class ShelfItem:
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
    items: list = field(default_factory=list)


# ---------- StreamRef: how a source hands a Track off to a backend ----------

@dataclass
class StreamRef:
    """What `resolve_stream` returns. ``backend`` tells the router which
    playback backend handles ``payload``.

    - mpv backend: payload is a URL or absolute file path.
    - librespot backend (v1.2.1): payload is a ``spotify:track:<id>`` URI.
    - musickit backend (v1.2.2): payload is an Apple Music catalog id.
    """
    backend: str
    payload: str
    headers: dict | None = None


# ---------- MusicSource ABC ----------

class MusicSource(ABC):
    """Minimum surface every source must implement, plus optional capability
    methods that default to ``NotSupportedError`` so callers can probe.

    ``capabilities`` declares which optional methods are wired. Views check
    ``source.supports("library")`` (etc.) and render a clean empty state
    when the active source doesn't expose the feature, instead of catching
    NotSupportedError after a wasted thread spin.
    """

    slug: str = ""
    name: str = ""
    icon: str = ""
    needs_auth: bool = False
    backend_slug: str = "mpv"
    short_tag: str = ""        # 2-char badge for federated search rows
    # True when ``begin_auth()`` is implemented, i.e. the source can sign in
    # from inside the generic source dialog. Sources with bespoke setup flows
    # (Spotify OAuth, Subsonic server form) leave this False — they handle
    # sign-in via their own gear dialogs, not the generic [sign in] button.
    supports_in_app_auth: bool = False

    # Known capability keys: "library", "albums", "artists", "videos",
    # "home", "radio", "lyrics", "rating". Required surface (search_songs +
    # resolve_stream) is implicit.
    capabilities: frozenset = frozenset()

    def supports(self, cap: str) -> bool:
        return cap in self.capabilities

    # ---------- auth ----------

    def is_authenticated(self) -> bool:
        return not self.needs_auth

    def begin_auth(self, parent_widget) -> bool:
        raise NotSupportedError(f"{self.slug} has no in-app auth")

    def sign_out(self) -> None:
        return None

    def status_text(self) -> str:
        """One-line human label for the Source panel."""
        return "ok" if self.is_authenticated() else "not signed in"

    # ---------- required capabilities ----------

    @abstractmethod
    def search_songs(self, query: str, limit: int = 20) -> list[Track]: ...

    @abstractmethod
    def resolve_stream(self, track: Track) -> StreamRef: ...

    # ---------- optional capabilities ----------

    def search_albums(self, query: str, limit: int = 20) -> list[AlbumEntry]:
        raise NotSupportedError(f"{self.slug}: search_albums")

    def search_artists(self, query: str, limit: int = 20) -> list[ArtistEntry]:
        raise NotSupportedError(f"{self.slug}: search_artists")

    def search_videos(self, query: str, limit: int = 20) -> list[Track]:
        raise NotSupportedError(f"{self.slug}: search_videos")

    def get_library_playlists(self, limit: int = 100) -> list[PlaylistEntry]:
        raise NotSupportedError(f"{self.slug}: get_library_playlists")

    def get_playlist(self, playlist_id: str, limit: int = 500) -> PlaylistDetail:
        raise NotSupportedError(f"{self.slug}: get_playlist")

    def get_album(self, browse_id: str) -> AlbumDetail | None:
        raise NotSupportedError(f"{self.slug}: get_album")

    def get_artist(self, channel_id: str) -> ArtistDetail | None:
        raise NotSupportedError(f"{self.slug}: get_artist")

    def get_home(self, limit: int = 5) -> list[Shelf]:
        raise NotSupportedError(f"{self.slug}: get_home")

    def get_radio(self, video_id: str, exclude: set[str] | None = None) -> list[Track]:
        raise NotSupportedError(f"{self.slug}: get_radio")

    def get_lyrics_for(self, video_id: str) -> str | None:
        return None

    def get_lyrics_for_track(self, track: Track):
        return None

    def rate_song(self, video_id: str, liked: bool) -> None:
        raise NotSupportedError(f"{self.slug}: rate_song")

    def is_liked(self, video_id: str) -> bool | None:
        return None
