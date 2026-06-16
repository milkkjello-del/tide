"""PlaybackBackend abstraction.

A backend handles audio for one or more sources. v1.2.0 ships ``MpvBackend``
only (used by all 5 zero-DRM sources). v1.2.1 adds ``LibrespotBackend`` for
Spotify; v1.2.2 adds ``MusicKitBackend`` for Apple Music.

Backends expose the same signal surface as `tide.player.Player` so the
`PlaybackRouter` can re-emit transparently and existing window wiring keeps
working.
"""
from __future__ import annotations

from abc import abstractmethod

from PySide6.QtCore import QObject, Signal


class PlaybackBackend(QObject):
    state_changed = Signal(object)        # PlayState
    position_changed = Signal(float)      # seconds
    duration_changed = Signal(float)      # seconds
    ended = Signal()
    error = Signal(str)

    slug: str = ""

    @abstractmethod
    def load(self, payload: str) -> None: ...

    @abstractmethod
    def play(self) -> None: ...

    @abstractmethod
    def pause(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def seek(self, seconds: float) -> None: ...

    @abstractmethod
    def set_volume(self, percent: int) -> None: ...

    def shutdown(self) -> None:
        return None

    @property
    @abstractmethod
    def state(self): ...

    @property
    @abstractmethod
    def duration(self) -> float: ...
