"""UI sound dispatcher — clicks, modal pops, toggle chirps.

A single ``UiSoundPlayer`` instance owns a ``QSoundEffect`` per known
sound key. Call sites do ``window.ui_sounds.play("nav")`` — the dispatch
is short-circuited when the master toggle is off, when music is playing
(set via ``set_muted``), or when the key has no WAV registered.

WAVs live in ``<repo>/assets/sounds/`` and ship with the package. The
loader is lenient: any missing file silently disables that key, so the
feature degrades cleanly on a fresh checkout where the user hasn't
authored every sound yet.

Music-playing detection: ``app.py`` connects the playback router's
``state_changed`` signal to ``set_muted(state == PlayState.PLAYING)``,
so UI sounds reappear automatically the moment playback pauses / ends.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Slot
from PySide6.QtMultimedia import QSoundEffect


# All known sound keys with their on-disk filenames. Extending this is the
# only place a new event type needs to be declared — call sites just pass
# the string key.
SOUND_KEYS: dict[str, str] = {
    "nav":         "nav.wav",
    "back":        "back.wav",
    "modal_open":  "modal_open.wav",
    "modal_close": "modal_close.wav",
    "toggle_on":   "toggle_on.wav",
    "toggle_off":  "toggle_off.wav",
}

# Quieter than the music itself — the sounds are feedback, not events
# the user is listening to. 0.20 gives an audible click at normal system
# volumes without startling when speakers are loud.
DEFAULT_VOLUME = 0.20


def _default_sounds_dir() -> Path:
    """The bundled assets/sounds dir relative to this file. Walks up
    until it finds a sibling ``assets`` dir so both an installed wheel
    layout and a from-checkout layout work."""
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        candidate = parent / "assets" / "sounds"
        if candidate.is_dir():
            return candidate
    # Fallback to the conventional repo-root path even if it doesn't
    # exist — the loader will just find no files and every key no-ops.
    return here.parent.parent.parent / "assets" / "sounds"


class UiSoundPlayer(QObject):
    """Thin wrapper around a dict of ``QSoundEffect``s."""

    def __init__(self, sounds_dir: Path | None = None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._enabled = False
        self._muted = False
        self._volume = DEFAULT_VOLUME
        self._effects: dict[str, QSoundEffect] = {}
        self._sounds_dir = Path(sounds_dir) if sounds_dir else _default_sounds_dir()
        self._load()

    # ---------- loading ----------

    def _load(self) -> None:
        """Instantiate a QSoundEffect for each WAV present. Missing
        files are skipped (the key is simply absent from the dict).
        QSoundEffect parses headers lazily, so any malformed file
        surfaces as a load-failed status the first time the key fires —
        we don't try to validate up-front.
        """
        for key, filename in SOUND_KEYS.items():
            path = self._sounds_dir / filename
            if not path.is_file():
                continue
            effect = QSoundEffect(self)
            effect.setSource(QUrl.fromLocalFile(str(path)))
            effect.setVolume(self._volume)
            self._effects[key] = effect

    # ---------- knobs ----------

    @Slot(bool)
    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    @Slot(bool)
    def set_muted(self, muted: bool) -> None:
        """``True`` while music is playing so UI sounds don't layer
        over the audio the user is actually listening to."""
        self._muted = bool(muted)

    def set_volume(self, volume: float) -> None:
        clamped = max(0.0, min(1.0, float(volume)))
        self._volume = clamped
        for effect in self._effects.values():
            try:
                effect.setVolume(clamped)
            except Exception:
                pass

    # ---------- the API call sites use ----------

    @Slot(str)
    def play(self, key: str) -> None:
        if not self._enabled or self._muted:
            return
        effect = self._effects.get(key)
        if effect is None:
            return
        try:
            # ``stop`` + ``play`` together so rapid repeated nav clicks
            # don't queue and instead retrigger from the head — feels
            # better when spamming nav buttons.
            effect.stop()
            effect.play()
        except Exception:
            pass

    # ---------- introspection ----------

    def available_keys(self) -> list[str]:
        return list(self._effects.keys())

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def muted(self) -> bool:
        return self._muted


__all__ = ["UiSoundPlayer", "SOUND_KEYS", "DEFAULT_VOLUME"]
