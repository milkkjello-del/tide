"""Once-a-day check for a newer GitHub release.

We hit ``api.github.com/repos/.../releases/latest`` in the background,
compare the tag's version to the bundled ``__version__``, and surface a
toast with a `[view]` action if newer. Result is cached in
``~/.cache/tide/update_check.json`` so we don't spam GitHub.
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.request
from typing import Callable

from . import config


GITHUB_REPO = "captiencelovesarch/tide"
LATEST_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
CACHE_PATH = config.CACHE_DIR / "update_check.json"
CHECK_INTERVAL_SECONDS = 24 * 3600
USER_AGENT = "tide/1.0"


def _parse_semver(tag: str) -> tuple[int, int, int] | None:
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", tag)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def _load_cache() -> dict:
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(data: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass


def _fetch_latest() -> tuple[str, str] | None:
    """Return (tag_name, html_url) or None on failure."""
    req = urllib.request.Request(LATEST_URL, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status != 200:
                return None
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    tag = data.get("tag_name") or ""
    url = data.get("html_url") or ""
    if not tag:
        return None
    return tag, url


def check_in_background(current_version: str, on_newer: Callable[[str, str], None]) -> None:
    """Spawn a daemon thread. If a newer release exists, ``on_newer`` is
    called with (tag, html_url). Skips if we checked within 24h.
    """
    cache = _load_cache()
    last = float(cache.get("last_checked", 0))
    if time.time() - last < CHECK_INTERVAL_SECONDS:
        return

    cur = _parse_semver(current_version)
    if cur is None:
        return

    def run() -> None:
        result = _fetch_latest()
        now = time.time()
        _save_cache({"last_checked": now, "latest_tag": result[0] if result else ""})
        if not result:
            return
        tag, url = result
        remote = _parse_semver(tag)
        if remote is None or remote <= cur:
            return
        on_newer(tag, url)

    threading.Thread(target=run, name="tide-update-check", daemon=True).start()
