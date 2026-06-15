"""ListenBrainz scrobbling.

We submit two kinds of events:

  - ``playing_now``: fire when a track starts. No persistence.
  - ``single``: fire after the user has actually listened — either the
    track has been playing for ≥30s, or playback reached 50% / 4 min,
    whichever comes first. Per the ListenBrainz "listen" definition.

Network calls happen on a background thread. Failures degrade silently —
the token might be invalid, the user might be offline. Nothing in the
GUI breaks.
"""
from __future__ import annotations

import json
import threading
import time
from typing import TYPE_CHECKING

import urllib.request
import urllib.error

from PySide6.QtCore import QObject, QTimer, Signal

if TYPE_CHECKING:
    from .api import Track
    from .player import Player
    from .queue import Queue


SUBMIT_URL = "https://api.listenbrainz.org/1/submit-listens"
USER_AGENT = "tide/1.0"


def _post(token: str, payload: dict, timeout: float = 6.0) -> tuple[int, str]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        SUBMIT_URL,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Token {token}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore") if exc.fp else ""
        return exc.code, body
    except Exception as exc:
        return 0, str(exc)


def _payload_for(track, *, listen_type: str, listened_at: int | None = None) -> dict:
    md: dict = {
        "track_name": (track.title or "").strip(),
        "artist_name": (track.artists or "").strip(),
    }
    if track.album:
        md["release_name"] = track.album
    info = {
        "submission_client": "tide",
        "submission_client_version": "1.0.0",
        "music_service": "music.youtube.com",
        "music_service_name": "YouTube Music",
        "origin_url": f"https://music.youtube.com/watch?v={track.video_id}",
    }
    md["additional_info"] = info
    body: dict = {"listen_type": listen_type, "payload": [{"track_metadata": md}]}
    if listened_at is not None:
        body["payload"][0]["listened_at"] = listened_at
    return body


class ListenBrainzScrobbler(QObject):
    """Per-app singleton handling playing_now + listen submissions."""

    status = Signal(str)

    def __init__(self, player: "Player", queue: "Queue", parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._player = player
        self._queue = queue
        self._token: str = ""
        self._enabled: bool = False

        self._current_track = None
        self._current_started_at: float | None = None
        self._current_duration: float = 0.0
        self._current_listened_secs: float = 0.0
        self._listen_submitted: bool = False
        self._last_position: float = 0.0

        queue.current_changed.connect(self._on_current_changed)
        player.state_changed.connect(self._on_state_changed)
        player.position_changed.connect(self._on_position_changed)
        player.duration_changed.connect(self._on_duration_changed)

    def configure(self, token: str, enabled: bool) -> None:
        token = (token or "").strip()
        was_enabled = self._enabled and bool(self._token)
        self._token = token
        self._enabled = enabled and bool(token)
        if self._enabled and not was_enabled and self._current_track is not None:
            self._submit_playing_now(self._current_track)

    # ---------- signal handlers ----------

    def _on_current_changed(self, track) -> None:
        # If the previous track was eligible for a listen submission but
        # we hadn't sent it yet, send now before flipping.
        self._maybe_submit_listen()

        self._current_track = track
        self._current_started_at = time.time() if track else None
        self._current_duration = float(getattr(track, "duration_seconds", 0) or 0)
        self._current_listened_secs = 0.0
        self._listen_submitted = False
        self._last_position = 0.0

        if track is not None:
            self._submit_playing_now(track)

    def _on_state_changed(self, state) -> None:
        from .player import PlayState
        # When stopped/idle, flush a listen if eligible.
        if state in (PlayState.IDLE, PlayState.PAUSED):
            self._maybe_submit_listen()

    def _on_position_changed(self, secs: float) -> None:
        # Accumulate listened-seconds based on monotonic forward motion only
        # (scrubbing back doesn't add time).
        if self._current_track is None or self._listen_submitted:
            self._last_position = secs
            return
        if secs >= self._last_position:
            self._current_listened_secs += (secs - self._last_position)
        self._last_position = secs
        self._maybe_submit_listen()

    def _on_duration_changed(self, secs: float) -> None:
        if secs > 0:
            self._current_duration = float(secs)

    # ---------- submission ----------

    def _submit_playing_now(self, track) -> None:
        if not self._enabled or not self._token or track is None:
            return
        body = _payload_for(track, listen_type="playing_now")
        self._fire_post(body, label="playing_now")

    def _maybe_submit_listen(self) -> None:
        if (not self._enabled or not self._token or self._current_track is None
                or self._listen_submitted):
            return
        eligible = False
        if self._current_listened_secs >= 30:
            eligible = True
        if (self._current_duration > 0
                and self._current_listened_secs >= 0.5 * self._current_duration):
            eligible = True
        if self._current_listened_secs >= 4 * 60:
            eligible = True
        if not eligible:
            return
        listened_at = int(self._current_started_at or time.time())
        body = _payload_for(self._current_track, listen_type="single", listened_at=listened_at)
        self._listen_submitted = True
        self._fire_post(body, label="listen")

    def _fire_post(self, body: dict, *, label: str) -> None:
        token = self._token
        def run():
            code, msg = _post(token, body)
            if 200 <= code < 300:
                self.status.emit(f"listenbrainz · {label} ok")
            elif code == 0:
                self.status.emit(f"listenbrainz · {label} network error")
            else:
                self.status.emit(f"listenbrainz · {label} http {code}")
        threading.Thread(target=run, name="tide-lb", daemon=True).start()
