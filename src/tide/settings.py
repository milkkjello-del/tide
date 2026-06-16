"""Persistent app settings (theme, Discord, etc.).

Lives at ~/.config/tide/settings.toml. The settings dialog is the user-
facing surface; this module just handles read/write. We never require
the user to hand-edit this file.
"""
from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from . import config


@dataclass
class Settings:
    theme: str = "brutalist-mono"
    discord_enabled: bool = False
    discord_app_id: str = ""
    volume: int = 80
    sleep_preset_minutes: int = 30
    mini_mode_default: bool = False
    # "theme" = use theme default, "on" = always show, "off" = never show
    show_thumbnails: str = "theme"
    # Empty = auto-detect default sink monitor; otherwise PulseAudio source name.
    audio_device: str = ""
    listenbrainz_enabled: bool = False
    listenbrainz_token: str = ""
    layout: str = "classic"
    layout_overrides: dict = field(default_factory=dict)
    adaptive_accent: bool = False
    # v1.2 multi-source
    active_source: str = "ytmusic"
    federated_search: bool = False
    # Per-source on/off. Keys are source slugs; values are bools.
    sources_enabled: dict = field(default_factory=lambda: {
        "ytmusic": True,
        "soundcloud": True,
        "bandcamp": True,
        "mixcloud": False,
        "local": True,
    })
    local_music_dir: str = ""
    local_auto_index: bool = True


def _to_toml(s: Settings) -> str:
    out: list[str] = []
    tables: list[str] = []
    for f in fields(s):
        val = getattr(s, f.name)
        if isinstance(val, bool):
            out.append(f"{f.name} = {'true' if val else 'false'}")
        elif isinstance(val, (int, float)):
            out.append(f"{f.name} = {val}")
        elif isinstance(val, dict):
            # Serialize as a [table] at the bottom.
            tables.append(f"\n[{f.name}]")
            for k, v in val.items():
                if isinstance(v, bool):
                    tables.append(f"{k} = {'true' if v else 'false'}")
                elif isinstance(v, (int, float)):
                    tables.append(f"{k} = {v}")
                else:
                    sv = str(v).replace("\\", "\\\\").replace('"', '\\"')
                    tables.append(f'{k} = "{sv}"')
        else:
            # naive string quoting — values are alphanumeric/punctuation only here
            escaped = str(val).replace("\\", "\\\\").replace('"', '\\"')
            out.append(f'{f.name} = "{escaped}"')
    return "\n".join(out) + "\n" + "\n".join(tables) + ("\n" if tables else "")


def load() -> Settings:
    path = config.SETTINGS_FILE
    if not path.is_file():
        return Settings()
    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    except Exception:
        return Settings()
    known = {f.name for f in fields(Settings)}
    filtered = {k: v for k, v in raw.items() if k in known}
    return Settings(**filtered)


def save(s: Settings) -> None:
    path = config.SETTINGS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(_to_toml(s))
    tmp.replace(path)
