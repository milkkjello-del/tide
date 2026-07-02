"""Local files source.

Walks a user-chosen music directory, reads ID3/Vorbis/etc. tags via
``mutagen``, and indexes everything into a SQLite FTS5 database at
``~/.cache/tide/local_index.sqlite``. Search hits FTS; track resolution
hands the file path straight to mpv.

A ``watchdog`` filesystem observer keeps the index fresh while the app
runs — added/removed/renamed files are reflected without a full rescan.
``watchdog`` is an optdepend; if it's not installed the index is rebuilt
on every app launch instead.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .. import config
from .base import (
    AlbumDetail,
    AlbumEntry,
    ArtistDetail,
    ArtistEntry,
    MusicSource,
    PlaylistDetail,
    PlaylistEntry,
    Shelf,
    ShelfItem,
    StreamRef,
    Track,
)


SOURCE_SLUG = "local"

SUPPORTED_EXTS = {
    ".mp3", ".flac", ".ogg", ".oga", ".opus", ".m4a", ".aac",
    ".wav", ".aiff", ".aif", ".wv", ".ape", ".mka",
}


def _index_path() -> Path:
    return config.CACHE_DIR / "local_index.sqlite"


def default_music_dir() -> str:
    """Resolve the user's preferred music directory.

    Honors ``$XDG_MUSIC_DIR`` from the user-dirs spec, then falls back to
    ``~/Music`` (Arch/KDE/GNOME convention).
    """
    env = os.environ.get("XDG_MUSIC_DIR")
    if env and Path(env).is_dir():
        return env
    user_dirs = Path.home() / ".config" / "user-dirs.dirs"
    if user_dirs.is_file():
        try:
            for line in user_dirs.read_text().splitlines():
                if line.startswith("XDG_MUSIC_DIR="):
                    raw = line.split("=", 1)[1].strip().strip('"')
                    expanded = raw.replace("$HOME", str(Path.home()))
                    if Path(expanded).is_dir():
                        return expanded
        except OSError:
            pass
    return str(Path.home() / "Music")


# ---------- tag reading ----------

def _read_tags(path: Path) -> dict | None:
    try:
        from mutagen import File as MFile
    except Exception:
        return None
    try:
        mf = MFile(str(path), easy=True)
    except Exception:
        return None
    if mf is None:
        return None
    tags = getattr(mf, "tags", None) or {}
    def _first(key: str) -> str:
        v = tags.get(key) if hasattr(tags, "get") else None
        if isinstance(v, list) and v:
            return str(v[0])
        if isinstance(v, str):
            return v
        return ""
    duration = float(getattr(mf.info, "length", 0.0) or 0.0)
    return {
        "title": _first("title") or path.stem,
        "artist": _first("artist") or _first("albumartist"),
        "album": _first("album"),
        "albumartist": _first("albumartist"),
        "year": _first("date") or _first("year"),
        "tracknumber": _first("tracknumber"),
        "duration_seconds": int(duration),
    }


# ---------- sqlite store ----------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    path        TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    artist      TEXT NOT NULL,
    album       TEXT NOT NULL,
    albumartist TEXT NOT NULL,
    year        TEXT NOT NULL,
    tracknumber TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL,
    mtime       REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS tracks_album_idx ON tracks(album, tracknumber);
CREATE INDEX IF NOT EXISTS tracks_artist_idx ON tracks(artist);
CREATE VIRTUAL TABLE IF NOT EXISTS tracks_fts USING fts5(
    path UNINDEXED, title, artist, album,
    content='tracks', content_rowid='rowid'
);
CREATE TRIGGER IF NOT EXISTS tracks_ai AFTER INSERT ON tracks BEGIN
    INSERT INTO tracks_fts(rowid, path, title, artist, album)
    VALUES (new.rowid, new.path, new.title, new.artist, new.album);
END;
CREATE TRIGGER IF NOT EXISTS tracks_ad AFTER DELETE ON tracks BEGIN
    INSERT INTO tracks_fts(tracks_fts, rowid, path, title, artist, album)
    VALUES ('delete', old.rowid, old.path, old.title, old.artist, old.album);
END;
CREATE TRIGGER IF NOT EXISTS tracks_au AFTER UPDATE ON tracks BEGIN
    INSERT INTO tracks_fts(tracks_fts, rowid, path, title, artist, album)
    VALUES ('delete', old.rowid, old.path, old.title, old.artist, old.album);
    INSERT INTO tracks_fts(rowid, path, title, artist, album)
    VALUES (new.rowid, new.path, new.title, new.artist, new.album);
END;
"""


class _LocalIndex:
    """SQLite index over the music library. Thread-safe via a single lock —
    the index is small and writes are infrequent, so coarse locking is fine."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None

    def _ensure(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        path = _index_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.executescript(_SCHEMA)
        conn.commit()
        self._conn = conn
        return conn

    def upsert(self, path: str, tags: dict, mtime: float) -> None:
        with self._lock:
            conn = self._ensure()
            conn.execute("DELETE FROM tracks WHERE path = ?", (path,))
            conn.execute(
                "INSERT INTO tracks (path, title, artist, album, albumartist, year, "
                "tracknumber, duration_seconds, mtime) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    path,
                    tags.get("title") or Path(path).stem,
                    tags.get("artist") or "",
                    tags.get("album") or "",
                    tags.get("albumartist") or tags.get("artist") or "",
                    tags.get("year") or "",
                    tags.get("tracknumber") or "",
                    int(tags.get("duration_seconds") or 0),
                    float(mtime),
                ),
            )
            conn.commit()

    def remove(self, path: str) -> None:
        with self._lock:
            conn = self._ensure()
            conn.execute("DELETE FROM tracks WHERE path = ?", (path,))
            conn.commit()

    def known_paths(self) -> set[str]:
        with self._lock:
            conn = self._ensure()
            cur = conn.execute("SELECT path FROM tracks")
            return {row[0] for row in cur.fetchall()}

    def count(self) -> int:
        with self._lock:
            conn = self._ensure()
            cur = conn.execute("SELECT COUNT(*) FROM tracks")
            return int(cur.fetchone()[0])

    def search(self, query: str, limit: int = 50) -> list[dict]:
        if not query.strip():
            return []
        # FTS5 MATCH: quote each token to dodge punctuation pitfalls, and
        # double any embedded quote (FTS5's escape) — a query like
        # `12" remix` would otherwise terminate the string early and make
        # the whole MATCH a syntax error.
        terms = " ".join(
            '"{}"*'.format(t.replace('"', '""')) for t in query.split() if t
        )
        if not terms:
            return []
        with self._lock:
            conn = self._ensure()
            cur = conn.execute(
                "SELECT t.path, t.title, t.artist, t.album, t.duration_seconds "
                "FROM tracks t JOIN tracks_fts f ON f.rowid = t.rowid "
                "WHERE tracks_fts MATCH ? ORDER BY rank LIMIT ?",
                (terms, limit),
            )
            rows = cur.fetchall()
        return [
            {"path": r[0], "title": r[1], "artist": r[2], "album": r[3], "duration_seconds": r[4]}
            for r in rows
        ]

    def recent(self, limit: int = 30) -> list[dict]:
        with self._lock:
            conn = self._ensure()
            cur = conn.execute(
                "SELECT path, title, artist, album, duration_seconds, mtime FROM tracks "
                "ORDER BY mtime DESC LIMIT ?", (limit,))
            rows = cur.fetchall()
        return [
            {"path": r[0], "title": r[1], "artist": r[2], "album": r[3], "duration_seconds": r[4]}
            for r in rows
        ]

    def all_tracks(self, limit: int = 5000) -> list[dict]:
        with self._lock:
            conn = self._ensure()
            cur = conn.execute(
                "SELECT path, title, artist, album, duration_seconds FROM tracks "
                "ORDER BY albumartist, album, tracknumber, title LIMIT ?", (limit,))
            rows = cur.fetchall()
        return [
            {"path": r[0], "title": r[1], "artist": r[2], "album": r[3], "duration_seconds": r[4]}
            for r in rows
        ]

    def albums(self) -> list[dict]:
        """List unique (albumartist, album) pairs with track counts."""
        with self._lock:
            conn = self._ensure()
            cur = conn.execute(
                "SELECT COALESCE(NULLIF(albumartist, ''), artist) AS aa, album, "
                "COUNT(*) AS n, MAX(year) AS year "
                "FROM tracks WHERE album != '' "
                "GROUP BY aa, album ORDER BY aa, album"
            )
            rows = cur.fetchall()
        return [{"albumartist": r[0], "album": r[1], "count": r[2], "year": r[3] or ""} for r in rows]

    def album_tracks(self, albumartist: str, album: str) -> list[dict]:
        with self._lock:
            conn = self._ensure()
            cur = conn.execute(
                "SELECT path, title, artist, album, duration_seconds, tracknumber "
                "FROM tracks WHERE album = ? AND "
                "COALESCE(NULLIF(albumartist, ''), artist) = ? "
                "ORDER BY tracknumber, title",
                (album, albumartist),
            )
            rows = cur.fetchall()
        out = []
        for r in rows:
            out.append({
                "path": r[0], "title": r[1], "artist": r[2], "album": r[3],
                "duration_seconds": r[4], "tracknumber": r[5] or "",
            })
        return out


# ---------- scanning ----------

def _scan_dir(root: Path, index: _LocalIndex, on_progress=None) -> int:
    """Walk ``root``, upsert any new or mtime-changed files, drop missing ones.
    Returns total tracks indexed afterwards."""
    if not root.is_dir():
        return 0
    seen: set[str] = set()
    n = 0
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            ext = os.path.splitext(name)[1].lower()
            if ext not in SUPPORTED_EXTS:
                continue
            p = Path(dirpath) / name
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            seen.add(str(p))
            tags = _read_tags(p)
            if not tags:
                continue
            index.upsert(str(p), tags, mtime)
            n += 1
            if on_progress and (n % 50 == 0):
                on_progress(n)
    # Drop stale entries (files outside ``root`` or no longer present).
    known = index.known_paths()
    for stale in known - seen:
        if stale.startswith(str(root)):
            try:
                if not Path(stale).is_file():
                    index.remove(stale)
            except OSError:
                index.remove(stale)
        else:
            index.remove(stale)
    return index.count()


# ---------- watchdog (optional) ----------

class _Watcher:
    """Wraps a watchdog observer. Silent no-op if watchdog isn't installed."""

    def __init__(self, root: str, index: _LocalIndex) -> None:
        self.root = root
        self.index = index
        self.observer = None

    def start(self) -> None:
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except Exception:
            return  # graceful fallback

        idx = self.index

        class _Handler(FileSystemEventHandler):
            def on_created(self, event):
                if event.is_directory:
                    return
                self._touch(event.src_path)
            def on_modified(self, event):
                if event.is_directory:
                    return
                self._touch(event.src_path)
            def on_deleted(self, event):
                if event.is_directory:
                    return
                idx.remove(event.src_path)
            def on_moved(self, event):
                if event.is_directory:
                    return
                idx.remove(event.src_path)
                self._touch(event.dest_path)
            def _touch(self, path: str) -> None:
                ext = os.path.splitext(path)[1].lower()
                if ext not in SUPPORTED_EXTS:
                    return
                p = Path(path)
                try:
                    mtime = p.stat().st_mtime
                except OSError:
                    return
                tags = _read_tags(p)
                if tags:
                    idx.upsert(path, tags, mtime)

        observer = Observer()
        observer.schedule(_Handler(), self.root, recursive=True)
        observer.daemon = True
        try:
            observer.start()
        except Exception:
            return
        self.observer = observer

    def stop(self) -> None:
        if self.observer is None:
            return
        try:
            self.observer.stop()
            self.observer.join(timeout=2)
        except Exception:
            pass
        self.observer = None


# ---------- source ----------

class LocalSource(MusicSource):
    slug = SOURCE_SLUG
    name = "local files"
    icon = "local"
    needs_auth = False
    backend_slug = "mpv"
    short_tag = "LO"
    capabilities = frozenset({"home", "library", "albums", "artists"})

    def __init__(self, music_dir: str | None = None) -> None:
        self._music_dir = music_dir or default_music_dir()
        self._index = _LocalIndex()
        self._watcher: _Watcher | None = None
        self._scan_in_progress = False

    # ---------- config ----------

    @property
    def music_dir(self) -> str:
        return self._music_dir

    def set_music_dir(self, path: str) -> None:
        """Switch the indexed directory. Caller should follow up with rescan()."""
        self._music_dir = path
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = None

    def track_count(self) -> int:
        return self._index.count()

    def is_authenticated(self) -> bool:
        return True

    def status_text(self) -> str:
        return f"{self._music_dir} · {self.track_count():,} tracks"

    # ---------- scanning ----------

    def rescan(self, on_progress=None) -> int:
        """Walk the music_dir, sync the index. Returns total track count."""
        if self._scan_in_progress:
            return self._index.count()
        self._scan_in_progress = True
        try:
            return _scan_dir(Path(self._music_dir), self._index, on_progress=on_progress)
        finally:
            self._scan_in_progress = False

    def start_watcher(self) -> None:
        if self._watcher is not None:
            return
        self._watcher = _Watcher(self._music_dir, self._index)
        self._watcher.start()

    def shutdown(self) -> None:
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = None

    # ---------- required surface ----------

    def search_songs(self, query: str, limit: int = 50) -> list[Track]:
        rows = self._index.search(query, limit=limit)
        return [self._row_to_track(r) for r in rows]

    def resolve_stream(self, track: Track) -> StreamRef:
        # video_id is the absolute path for local tracks.
        return StreamRef(backend="mpv", payload=track.video_id)

    # ---------- discovery surfaces ----------

    def get_home(self, limit: int = 5) -> list[Shelf]:
        recent = self._index.recent(limit=24)
        if not recent:
            return []
        items: list[ShelfItem] = []
        for r in recent:
            tr = self._row_to_track(r)
            items.append(ShelfItem(
                kind="song",
                title=tr.title,
                subtitle=tr.artists,
                thumbnail="",
                track=tr,
            ))
        return [Shelf(title="recently added", items=items)]

    # ---------- library (synthetic) ----------

    def get_library_playlists(self, limit: int = 100) -> list[PlaylistEntry]:
        """Synthesize one entry per (albumartist, album) pair, plus a global
        'all tracks' entry pinned to the top.

        ``playlist_id`` is encoded so ``get_playlist`` can decode the album
        without an extra round-trip.
        """
        entries: list[PlaylistEntry] = [
            PlaylistEntry(
                playlist_id="local::all",
                title="all tracks",
                description=f"{self._index.count():,} files",
                thumbnail="",
            ),
        ]
        for alb in self._index.albums():
            aa = alb.get("albumartist") or ""
            title = alb.get("album") or ""
            desc = f"{aa} · {alb.get('count', 0)} tracks"
            if alb.get("year"):
                desc += f" · {alb['year']}"
            entries.append(PlaylistEntry(
                playlist_id=f"local::alb::{aa}::{title}",
                title=title,
                description=desc,
                thumbnail="",
            ))
        return entries

    def get_playlist(self, playlist_id: str, limit: int = 1000) -> PlaylistDetail:
        if playlist_id == "local::all":
            rows = self._index.all_tracks(limit=limit)
            return PlaylistDetail(
                playlist_id=playlist_id,
                title="all tracks",
                description=f"{len(rows)} files",
                track_count=len(rows),
                tracks=[self._row_to_track(r) for r in rows],
            )
        if playlist_id.startswith("local::alb::"):
            rest = playlist_id[len("local::alb::"):]
            try:
                aa, album = rest.split("::", 1)
            except ValueError:
                return PlaylistDetail(playlist_id=playlist_id, title="(invalid)")
            rows = self._index.album_tracks(aa, album)
            return PlaylistDetail(
                playlist_id=playlist_id,
                title=album,
                description=aa,
                track_count=len(rows),
                tracks=[self._row_to_track(r) for r in rows],
            )
        return PlaylistDetail(playlist_id=playlist_id, title="(unknown)")

    # ---------- helpers ----------

    def _row_to_track(self, row: dict) -> Track:
        secs = int(row.get("duration_seconds") or 0)
        dur = ""
        if secs >= 3600:
            dur = f"{secs // 3600}:{(secs % 3600) // 60:02d}:{secs % 60:02d}"
        elif secs > 0:
            dur = f"{secs // 60}:{secs % 60:02d}"
        return Track(
            video_id=row["path"],
            title=row.get("title", "") or Path(row["path"]).stem,
            artists=row.get("artist", "") or "",
            album=row.get("album", "") or "",
            duration=dur,
            duration_seconds=secs,
            thumbnail="",
            source=SOURCE_SLUG,
            extras={"path": row["path"]},
        )
