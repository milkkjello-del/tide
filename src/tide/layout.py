"""Layout system — what widgets, where, what variant.

Mirrors ``theming.py`` in shape. A layout TOML declares the structural
mode + which variant to use in each slot + which top-level views are
visible. Users pick a preset from Settings → Appearance; per-slot
overrides are stored separately in ``settings.toml``.

Discovery order (later wins):
  1. bundled  — src/tide/layouts/<slug>/layout.toml
  2. system   — /usr/share/tide/layouts/<slug>/layout.toml
  3. user     — ~/.config/tide/layouts/<slug>/layout.toml
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from PySide6.QtCore import QObject, Signal

from . import config


BUNDLED_LAYOUTS_DIR = Path(__file__).parent / "layouts"
SYSTEM_LAYOUTS_DIR = Path("/usr/share/tide/layouts")
USER_LAYOUTS_DIR = config.CONFIG_DIR / "layouts"


# Default values used when a TOML doesn't specify a slot or visibility flag.
DEFAULT_SLOTS = {
    "progress":  "blocks",
    "volume":    "blocks",
    "album_art": "square",
    "controls":  "bracket",
    "now_label": "stacked",
}

DEFAULT_VISIBILITY = {
    "nav_rail":   True,
    "status_bar": True,
    "queue_view": True,
    "visualizer": True,
    "lyrics":     True,
    "history":    True,
}

DEFAULT_MODE = "classic"   # "classic" | "compact" | "stage"


@dataclass(frozen=True)
class Layout:
    slug: str
    name: str
    description: str
    mode: str
    window_default: tuple[int, int]
    slots: dict[str, str]
    visibility: dict[str, bool]
    path: Path

    @staticmethod
    def with_overrides(base: "Layout", overrides: dict[str, str]) -> "Layout":
        """Return a new Layout where ``overrides`` replace matching slots."""
        if not overrides:
            return base
        merged = dict(base.slots)
        for k, v in overrides.items():
            if k in merged and v:
                merged[k] = v
        return Layout(
            slug=base.slug,
            name=base.name,
            description=base.description,
            mode=base.mode,
            window_default=base.window_default,
            slots=merged,
            visibility=base.visibility,
            path=base.path,
        )


def _layout_dirs() -> list[Path]:
    return [BUNDLED_LAYOUTS_DIR, SYSTEM_LAYOUTS_DIR, USER_LAYOUTS_DIR]


def _read_layout(layout_dir: Path) -> Layout | None:
    toml_path = layout_dir / "layout.toml"
    if not toml_path.is_file():
        return None
    try:
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return None
    meta = data.get("meta", {}) or {}
    slug = str(meta.get("slug") or layout_dir.name)
    name = str(meta.get("name") or slug)
    description = str(meta.get("description", ""))
    mode = str(meta.get("mode", DEFAULT_MODE))
    window_default_raw = meta.get("window_default") or [1100, 720]
    try:
        window_default = (int(window_default_raw[0]), int(window_default_raw[1]))
    except Exception:
        window_default = (1100, 720)

    slots = dict(DEFAULT_SLOTS)
    for k, v in (data.get("slots", {}) or {}).items():
        if isinstance(v, str):
            slots[k] = v

    visibility = dict(DEFAULT_VISIBILITY)
    for k, v in (data.get("visibility", {}) or {}).items():
        if isinstance(v, bool):
            visibility[k] = v

    return Layout(
        slug=slug,
        name=name,
        description=description,
        mode=mode,
        window_default=window_default,
        slots=slots,
        visibility=visibility,
        path=layout_dir,
    )


def discover_layouts() -> dict[str, Layout]:
    found: dict[str, Layout] = {}
    for base in _layout_dirs():
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            if not child.is_dir():
                continue
            layout = _read_layout(child)
            if layout is not None:
                found[layout.slug] = layout
    return found


def fallback_layout() -> Layout:
    """A Layout used when nothing's been picked yet (e.g. fresh install)."""
    return Layout(
        slug="classic",
        name="classic",
        description="(fallback)",
        mode=DEFAULT_MODE,
        window_default=(1100, 720),
        slots=dict(DEFAULT_SLOTS),
        visibility=dict(DEFAULT_VISIBILITY),
        path=BUNDLED_LAYOUTS_DIR / "classic",
    )


class LayoutManager(QObject):
    layout_changed = Signal(object)   # Layout (effective, with overrides)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._layouts: dict[str, Layout] = {}
        self._active: Layout = fallback_layout()
        self._overrides: dict[str, str] = {}

    def refresh(self) -> None:
        self._layouts = discover_layouts()

    def list_layouts(self) -> list[Layout]:
        if not self._layouts:
            self.refresh()
        return list(self._layouts.values())

    def get(self, slug: str) -> Layout | None:
        if not self._layouts:
            self.refresh()
        return self._layouts.get(slug)

    def current(self) -> Layout:
        return Layout.with_overrides(self._active, self._overrides)

    def base_slug(self) -> str:
        return self._active.slug

    def apply(self, slug: str, overrides: dict[str, str] | None = None) -> Layout | None:
        if not self._layouts:
            self.refresh()
        layout = self._layouts.get(slug)
        if layout is None:
            return None
        self._active = layout
        self._overrides = dict(overrides or {})
        effective = Layout.with_overrides(layout, self._overrides)
        self.layout_changed.emit(effective)
        return effective

    def update_overrides(self, overrides: dict[str, str]) -> Layout:
        self._overrides = dict(overrides or {})
        effective = Layout.with_overrides(self._active, self._overrides)
        self.layout_changed.emit(effective)
        return effective


_manager: LayoutManager | None = None


def manager() -> LayoutManager:
    global _manager
    if _manager is None:
        _manager = LayoutManager()
    return _manager
