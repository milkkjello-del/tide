"""Ambient-background controller.

Bridges the audio feed to the central-area background so it pulses on bass,
app-wide, whenever tide is playing.

Kept deliberately thin: it owns *when* the shared capture runs for the
pulse (a reference-counted consumer named ``"ambient"``) and forwards the
feed's ``pulse_updated`` envelope to :class:`~tide.ui.central_bg.CentralBg`.
The actual reactive rendering lives in CentralBg; the palette shift lives in
:class:`~tide.ui.adaptive.AdaptiveDriver`. This class only connects them to
the audio level.

Capture is only held while the player is PLAYING, so a paused/idle tide
doesn't keep a parec process (and a monitor stream) alive for nothing.
"""
from __future__ import annotations

from PySide6.QtCore import QObject

from .. import audio_capture, settings as settings_module


_CONSUMER = "ambient"


class AmbientController(QObject):
    def __init__(self, player, central_bg, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._player = player
        self._central_bg = central_bg
        self._feed = audio_capture.feed()
        self._enabled = False
        self._holding = False

        self._player.state_changed.connect(self._on_state)
        self._feed.pulse_updated.connect(self._on_pulse)

    # ---------- public API ----------

    def set_pulse_enabled(self, on: bool) -> None:
        on = bool(on)
        if on == self._enabled:
            return
        self._enabled = on
        if on:
            # Start capturing immediately if we're already playing.
            self._reconcile()
        else:
            self._release()
            self._central_bg.set_pulse(0.0)

    def is_enabled(self) -> bool:
        return self._enabled

    # ---------- internals ----------

    def _is_playing(self) -> bool:
        from ..player import PlayState
        try:
            return self._player.state == PlayState.PLAYING
        except Exception:
            return False

    def _on_state(self, _state) -> None:
        self._reconcile()

    def _reconcile(self) -> None:
        if self._enabled and self._is_playing():
            self._acquire()
        else:
            self._release()
            # Let the glow settle back down when playback stops.
            self._central_bg.set_pulse(0.0)

    def _acquire(self) -> None:
        if self._holding:
            return
        # Honor the user's saved monitor-source override (shared with the
        # visualizer's audio-source picker).
        source = None
        try:
            source = settings_module.load().audio_device or None
        except Exception:
            source = None
        self._feed.add_consumer(_CONSUMER, source=source)
        self._holding = True

    def _release(self) -> None:
        if not self._holding:
            return
        self._feed.remove_consumer(_CONSUMER)
        self._holding = False

    def _on_pulse(self, level: float) -> None:
        if self._enabled and self._holding:
            self._central_bg.set_pulse(level)
