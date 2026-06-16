"""Discord Rich Presence integration.

Off by default — to enable, the user provides a Discord Application Client ID
in Settings → Discord (or via the DISCORD_APP_ID env var). They get one in
~30 seconds at https://discord.com/developers/applications: New Application →
copy "Application ID" from General Information.

Why not bundle a default ID? Discord apps are namespaced by their owner. The
app's name + uploaded image assets are what Discord shows. Anyone using a
"tide-default" ID would see whatever assets that account uploaded, which
isn't a great trust story. Owning your own ID is also why the icon you see
in Discord can be your own album-art artwork instead of a stock glyph.

Failures are non-fatal. If Discord isn't running, we wait and try again. If
pypresence raises, we log and move on — the app keeps working.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer, Qt, Signal

try:
    from pypresence import ActivityType, Presence  # type: ignore
    from pypresence.exceptions import (            # type: ignore
        DiscordError,
        DiscordNotFound,
        InvalidID,
        InvalidPipe,
        PipeClosed,
    )
    PYPRESENCE_AVAILABLE = True
except Exception:
    ActivityType = None  # type: ignore
    PYPRESENCE_AVAILABLE = False

if TYPE_CHECKING:
    from .api import Track
    from .player import Player
    from .queue import Queue


RECONNECT_INTERVAL_MS = 30_000


@dataclass
class _Activity:
    title: str
    artists: str
    album: str
    duration_seconds: int
    started_at: float
    paused: bool
    art_url: str = ""
    source: str = ""


class DiscordPresence(QObject):
    """Presence client. Holds a pypresence connection if up; auto-reconnects."""

    connection_changed = Signal(bool)   # True when connected

    def __init__(self, player: "Player", queue: "Queue", parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._player = player
        self._queue = queue

        self._client: "Presence | None" = None
        self._app_id: str = ""
        self._enabled: bool = False
        self._connected: bool = False
        self._last_activity: _Activity | None = None
        self._track_started_at: float | None = None

        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setInterval(RECONNECT_INTERVAL_MS)
        self._reconnect_timer.timeout.connect(self._try_connect)

    # ---------- lifecycle ----------

    def configure(self, app_id: str | None, enabled: bool) -> None:
        """Set credentials + on/off. Reconnect/disconnect accordingly."""
        app_id = (app_id or "").strip()
        env_override = os.environ.get("DISCORD_APP_ID", "").strip()
        if env_override:
            app_id = env_override

        wants_on = enabled and bool(app_id) and PYPRESENCE_AVAILABLE
        creds_changed = app_id != self._app_id
        was_enabled = self._enabled

        self._app_id = app_id
        self._enabled = wants_on

        if was_enabled and (not wants_on or creds_changed):
            self._disconnect()
        if wants_on:
            self._try_connect()

    def start_wire(self) -> None:
        """Subscribe to track + state changes so presence stays current."""
        self._queue.current_changed.connect(self._on_current_changed)
        self._player.state_changed.connect(self._on_state_changed)
        self._player.duration_changed.connect(self._on_duration_changed)
        self._player.position_changed.connect(self._on_position_changed)

    def shutdown(self) -> None:
        self._reconnect_timer.stop()
        self._disconnect()

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ---------- connection ----------

    def _try_connect(self) -> None:
        if not self._enabled or self._connected or not PYPRESENCE_AVAILABLE:
            return
        if not self._app_id:
            return
        try:
            client = Presence(self._app_id)
            client.connect()
        except (DiscordNotFound, InvalidPipe, ConnectionRefusedError, FileNotFoundError):
            # Discord isn't running — try again later.
            self._reconnect_timer.start()
            return
        except (InvalidID, DiscordError) as exc:
            # The app ID is wrong or banned — stop trying.
            print(f"tide: discord rpc disabled — {exc}")
            self._enabled = False
            return
        except Exception as exc:
            print(f"tide: discord rpc connect failed — {exc!r}")
            self._reconnect_timer.start()
            return

        self._client = client
        self._connected = True
        self._reconnect_timer.stop()
        self.connection_changed.emit(True)
        if self._last_activity is not None:
            self._push_current()

    def _disconnect(self) -> None:
        if self._client is not None:
            try:
                self._client.clear()
            except Exception:
                pass
            try:
                self._client.close()
            except Exception:
                pass
        self._client = None
        if self._connected:
            self._connected = False
            self.connection_changed.emit(False)

    # ---------- track signal handlers ----------

    def _on_current_changed(self, track) -> None:
        if track is None:
            self._last_activity = None
            self._track_started_at = None
            self._clear()
            return
        self._track_started_at = time.time()
        from .player import PlayState
        self._last_activity = _Activity(
            title=track.title or "",
            artists=track.artists or "",
            album=track.album or "",
            duration_seconds=int(track.duration_seconds or 0),
            started_at=self._track_started_at,
            paused=self._player.state == PlayState.PAUSED,
            art_url=track.thumbnail or "",
            source=getattr(track, "source", "") or "",
        )
        self._push_current()

    def _on_state_changed(self, state) -> None:
        if self._last_activity is None:
            return
        from .player import PlayState
        was_paused = self._last_activity.paused
        is_paused = state == PlayState.PAUSED
        if was_paused == is_paused:
            return
        self._last_activity.paused = is_paused
        self._push_current()

    def _on_duration_changed(self, secs: float) -> None:
        if self._last_activity is None:
            return
        self._last_activity.duration_seconds = int(secs)
        # Don't bother re-pushing for duration alone — next track flip or
        # state flip will pick this up.

    def _on_position_changed(self, secs: float) -> None:
        # Discord rate-limits presence updates to ~5/min. We don't push on
        # every position tick — the timer in Discord renders smoothly from
        # the `start` field once it's set.
        return

    # ---------- presence push ----------

    def _push_current(self) -> None:
        if not self._connected or self._client is None or self._last_activity is None:
            return
        a = self._last_activity

        # When paused, hide the presence entirely — most users don't want
        # "paused tide" sitting on their profile while they walked away.
        if a.paused:
            self._clear()
            return

        # Honor the active theme's typography.case so brutalist users get
        # lowercase presence, synthwave gets l33t, etc.
        from . import theming
        details = theming.styled_case((a.title or "tide").strip())
        state_parts: list[str] = []
        if a.artists:
            state_parts.append(theming.styled_case(a.artists))
        if a.album:
            state_parts.append(theming.styled_case(a.album))
        state_text = " · ".join(state_parts) or "—"

        # Use start + end (unix-second timestamps) so Discord renders the
        # "0:34 / 3:42" progress bar based on actual song position.
        now_s = int(time.time())
        played_secs = int(max(0.0, time.time() - a.started_at))
        duration_secs = max(0, a.duration_seconds)
        if duration_secs > 0:
            played_secs = min(played_secs, duration_secs)
        start_s = now_s - played_secs
        end_s = start_s + duration_secs if duration_secs > 0 else 0

        # Per-source label for large_text / small_text. Some Discord apps
        # have per-source asset keys uploaded (ytmusic, soundcloud, etc.);
        # if so we use them, otherwise fall back to "tide". Bare slug as
        # asset key — Discord ignores unknown keys silently.
        source_label = {
            "ytmusic": "youtube music",
            "soundcloud": "soundcloud",
            "bandcamp": "bandcamp",
            "mixcloud": "mixcloud",
            "local": "local files",
            "spotify": "spotify",
            "apple": "apple music",
        }.get(a.source, "tide")

        kwargs: dict = {
            "activity_type": ActivityType.LISTENING,
            "details": details[:128],
            "state": state_text[:128],
            "large_text": source_label,
            "start": start_s,
            "small_text": "tide",
        }
        if end_s > 0:
            kwargs["end"] = end_s
        if a.art_url:
            kwargs["large_image"] = a.art_url
        else:
            # No per-track art (local files; thumbnails not surfaced). Try
            # the source-named asset; Discord will silently fall back if
            # the user's app hasn't uploaded that key.
            kwargs["large_image"] = a.source or "tide"
        # Tag the small-image badge with the source slug so Discord apps
        # that have per-source icons uploaded get them; falls back silently
        # if absent.
        if a.source:
            kwargs["small_image"] = a.source

        try:
            self._client.update(**kwargs)
        except (PipeClosed, BrokenPipeError):
            self._disconnect()
            self._reconnect_timer.start()
        except Exception as exc:
            print(f"tide: discord rpc update failed — {exc!r}")

    def _clear(self) -> None:
        if not self._connected or self._client is None:
            return
        try:
            self._client.clear()
        except Exception:
            pass
