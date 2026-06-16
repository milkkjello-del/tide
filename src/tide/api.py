"""Back-compat shim for v1.1 imports.

The YT Music client used to live here. v1.2 moved it into the source
abstraction (``tide.sources.ytmusic``). To avoid touching every importer in
the codebase, this module re-exports the same names — ``Api``, ``Track``,
the entry dataclasses, and ``resolve_stream_url``.

New code should import from ``tide.sources`` directly. This shim will be
removed in v1.3.
"""
from __future__ import annotations

from .sources.base import (
    AlbumDetail,
    AlbumEntry,
    ArtistDetail,
    ArtistEntry,
    NotSupportedError,
    PlaylistDetail,
    PlaylistEntry,
    Shelf,
    ShelfItem,
    Track,
)
from .sources.ytmusic import YTMusicSource as Api
from .sources.ytmusic import resolve_stream_url


__all__ = [
    "AlbumDetail",
    "AlbumEntry",
    "Api",
    "ArtistDetail",
    "ArtistEntry",
    "NotSupportedError",
    "PlaylistDetail",
    "PlaylistEntry",
    "Shelf",
    "ShelfItem",
    "Track",
    "resolve_stream_url",
]
