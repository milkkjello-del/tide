"""LRClib lyrics fallback.

YouTube Music's lyrics endpoint covers many tracks but not all. LRClib
(https://lrclib.net) is a community-curated lyrics database with both
plain and timed (LRC-format) lyrics. When YT Music returns nothing, we
ask LRClib by title + artist + (optional) album + duration.

Result shape:

  LyricsResult(plain_text="...", timed_lines=[(seconds, "line"), ...])

If neither plain nor timed is available, the result is None and callers
fall back to the "no lyrics" empty state.

Caching: ~/.cache/tide/lyrics/<sha1>.json so re-listens don't re-query.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from . import config


USER_AGENT = "tide/1.0 (https://github.com/captiencelovesarch/tide)"
LRCLIB_URL = "https://lrclib.net/api/get"
TIMEOUT_SECONDS = 5.0


@dataclass
class LyricsResult:
    plain_text: str = ""
    timed_lines: list[tuple[float, str]] = field(default_factory=list)

    @property
    def has_timed(self) -> bool:
        return bool(self.timed_lines)

    @property
    def is_empty(self) -> bool:
        return not self.plain_text and not self.timed_lines


_LRC_LINE = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\](.*)")


def parse_lrc(text: str) -> list[tuple[float, str]]:
    """Parse LRC-format lyrics into ``[(seconds, line), ...]``.

    Handles multiple timestamps per line (very common). Skips metadata
    tags like ``[ar: artist]``.
    """
    out: list[tuple[float, str]] = []
    for raw in text.splitlines():
        timestamps: list[float] = []
        rest = raw
        while True:
            m = _LRC_LINE.match(rest)
            if not m:
                break
            mm = int(m.group(1))
            ss = float(m.group(2))
            timestamps.append(mm * 60 + ss)
            rest = m.group(3)
        if not timestamps:
            continue
        line = rest.strip()
        for t in timestamps:
            out.append((t, line))
    out.sort(key=lambda x: x[0])
    return out


def _cache_path(query_key: str) -> Path:
    name = hashlib.sha1(query_key.encode("utf-8")).hexdigest() + ".json"
    return config.LYRICS_CACHE_DIR / name


def _load_cache(key: str) -> LyricsResult | None:
    path = _cache_path(key)
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    timed_raw = data.get("timed") or []
    timed = [(float(t), str(line)) for t, line in timed_raw if isinstance(line, str)]
    return LyricsResult(plain_text=data.get("plain", "") or "", timed_lines=timed)


def _save_cache(key: str, result: LyricsResult) -> None:
    path = _cache_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "plain": result.plain_text,
                "timed": [(t, line) for t, line in result.timed_lines],
            }, f)
    except OSError:
        pass


def fetch_lrclib(*, title: str, artist: str, album: str = "",
                  duration_seconds: int = 0) -> LyricsResult | None:
    """Query LRClib for the track. Returns None on miss or network error."""
    if not title or not artist:
        return None
    key = f"{title}|{artist}|{album}|{int(duration_seconds)}"
    cached = _load_cache(key)
    if cached is not None and not cached.is_empty:
        return cached

    params = {
        "track_name": title.strip(),
        "artist_name": artist.strip(),
    }
    if album:
        params["album_name"] = album.strip()
    if duration_seconds > 0:
        params["duration"] = str(int(duration_seconds))
    url = LRCLIB_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            if resp.status != 200:
                return None
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    plain = (data.get("plainLyrics") or "").strip()
    synced = (data.get("syncedLyrics") or "").strip()
    timed = parse_lrc(synced) if synced else []
    result = LyricsResult(plain_text=plain, timed_lines=timed)
    if not result.is_empty:
        _save_cache(key, result)
    return result if not result.is_empty else None
