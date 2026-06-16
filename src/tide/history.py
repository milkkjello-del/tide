"""Append-only play history.

One JSON object per line at `~/.cache/tide/history.jsonl`. Newest entries
are written at the bottom; the view reads the tail and reverses it.

We don't dedupe: replaying the same song five times in a row produces five
history lines. That's the honest signal — collapsing them would lie about
the listening pattern.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from . import config
from .api import Track


MAX_LINES_RETAINED = 5000   # rotate when the file grows past this
DEFAULT_TAIL = 200


@dataclass
class HistoryEntry:
    video_id: str
    title: str
    artists: str
    album: str = ""
    duration: str = ""
    duration_seconds: int = 0
    thumbnail: str = ""
    played_at: float = 0.0
    source: str = "ytmusic"

    def to_track(self) -> Track:
        return Track(
            video_id=self.video_id,
            title=self.title,
            artists=self.artists,
            album=self.album,
            duration=self.duration,
            duration_seconds=self.duration_seconds,
            thumbnail=self.thumbnail,
            source=self.source or "ytmusic",
        )


def append(track: Track) -> None:
    if not track or not track.video_id:
        return
    path = config.HISTORY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "video_id": track.video_id,
        "title": track.title,
        "artists": track.artists,
        "album": track.album,
        "duration": track.duration,
        "duration_seconds": int(track.duration_seconds or 0),
        "thumbnail": track.thumbnail,
        "source": getattr(track, "source", "") or "ytmusic",
        "played_at": time.time(),
    }
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        return
    _maybe_rotate(path)


def _maybe_rotate(path: Path) -> None:
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return
    if len(lines) <= MAX_LINES_RETAINED:
        return
    keep = lines[-MAX_LINES_RETAINED:]
    tmp = path.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.writelines(keep)
        tmp.replace(path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def read_recent(limit: int = DEFAULT_TAIL) -> list[HistoryEntry]:
    """Return the most recent entries, newest first."""
    path = config.HISTORY_FILE
    if not path.is_file():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return []
    out: list[HistoryEntry] = []
    for line in reversed(lines[-limit:]):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        out.append(HistoryEntry(
            video_id=d.get("video_id", ""),
            title=d.get("title", ""),
            artists=d.get("artists", ""),
            album=d.get("album", ""),
            duration=d.get("duration", ""),
            duration_seconds=int(d.get("duration_seconds") or 0),
            thumbnail=d.get("thumbnail", ""),
            source=d.get("source") or "ytmusic",
            played_at=float(d.get("played_at") or 0.0),
        ))
    return out


def clear() -> None:
    try:
        config.HISTORY_FILE.unlink(missing_ok=True)
    except OSError:
        pass
