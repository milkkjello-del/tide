# Changelog

All notable changes to **tide** land here. Format roughly follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are [semver-ish](https://semver.org/) with a 4-segment patch when a release ships polish on top of an already-tagged feature drop.

The canonical source of truth for the diff lives in the [GitHub Releases](https://github.com/captiencelovesarch/tide/releases) — this file is for browsing history at a glance.

## [1.2.0.1] — 2026-06-16 — pre-spotify glow-up

### Added
- **Animations** — a motion system (`off` / `lite` / `full`) gating the new track-change signature: title scramble-decodes left-to-right while the album art crossfades between covers, layered on top of the existing adaptive accent fade. Reduced-motion env hint clamps `full` to `lite`.
- **Playback speed** — pitch-shifting speed control from 0.5× to 2.0× with a popover (`−0.05` / `+0.05` / presets / reset) and keyboard shortcuts (`[`, `]`, `\`). Pitch-shifted by default for the slowed-and-reverb / nightcore vibe; settings has a "preserve pitch" toggle for audiobook use.
- **Stream-URL prefetch** — when the current track has ≤15s remaining, tide pre-resolves the next track's stream URL. Auto-advance is now ~instant on cache hit; falls back silently on miss.
- **UI scale** — `compact` / `normal` / `large` / `huge` presets cascade through every fixed-size widget (track row, album art, cards, album/artist covers, view margins).
- **Adaptive central-area gradient** — opt-in subtle vertical gradient on the main content area (theme `bg` → album-derived `bg_alt`) that retints per track.
- **Soft corners** — `sharp` / `soft` / `rounded` picker applies a sticky `@radius` override across inputs, scrollbars, and the central-area clip.
- **Loading indicator** — customizable status-bar progress for the resolve → buffer → playing window. Five styles: `off`, `numbers`, `blocks`, `dots`, `ascii`.
- **Themed nav icons** — three sets: bundled brutalist SVG line-art (recolored to the active theme's `fg`), classic mono glyphs, and emoji.
- **Bundled fonts** — IBM Plex Mono, JetBrains Mono, and Inter ship in the package. New font picker in Settings overrides any theme's typography (editable to accept arbitrary system family names).

### Fixed
- **Adaptive theme color picker** — was sorting palette candidates purely by HLS saturation, so a single bright pixel could steal the accent. Now weighted by `vibrancy × √frequency` and normalized into a readable lightness band against the theme background.
- **Skip button** — now stops audio the instant you press it instead of letting the previous track play for the 1–3s the resolve worker takes.
- **Discord RP elapsed timer** — used to anchor to "queue selected" instead of "audio actually started," inflating the displayed elapsed time by the entire resolve+buffer window. Now anchors to `PlayState.PLAYING` via `now − player.position`; self-corrects for first-play, resume-from-pause, and reconnect-mid-song. Source label ("YouTube Music" etc.) now runs through `styled_case` so it tracks the active theme's typography.
- **Prefetch crash** — initial implementation held Python dict refs to the QThread that raced with Qt's `deleteLater` and segfaulted under PySide6. Now Qt-owned via `QThread(self)` with a clean `findChildren(QThread)`-based shutdown.

## [1.2.0] — 2026-06-16 — multi-source

tide is now a multi-source music client. A `MusicSource` ABC sits in front of every catalog; a `PlaybackRouter` dispatches audio to the producing source's declared backend.

- **5 sources at launch**: YouTube Music, SoundCloud, Bandcamp, Mixcloud, Local Files (mutagen + SQLite FTS5)
- **`[source]` panel** (Ctrl+8) — per-source enable + active-source + status dot + sub-dialog gear
- **Federated search** — runs every enabled source in parallel and tags each row with its source badge
- **Capability-aware UI** — library / explore / like / radio buttons adapt to what the active source supports
- **Per-source stream cache** — each source picks its own TTL
- **Source-aware Discord RP** — per-source asset keys for `large_image` / `small_image`
- v1.2.1 → Spotify (Librespot backend), v1.2.2 → Apple Music (MusicKit backend)

## [1.1.1] — 2026-06-16

Three lag/glitch fixes from end-of-v1.1 testing.

- **Adaptive theme override leak** — switching themes while adaptive was on left the previous theme's accent + bg_alt stuck in place. Now clears on every explicit theme apply.
- **Adaptive feedback loop** — in-flight accent animation re-triggering itself when token overrides emitted `theme_changed` mid-frame. Now gates on base-slug change.
- **Settings dialog lag** — opening Settings with adaptive on fired apply_layout + apply_theme + palette extraction for every dropdown's initial `setCurrentIndex`. Now `blockSignals` on all pickers during populate.

## [1.1.0] — 2026-06-15 — QOL kitchen sink

Five milestones of polish, discovery, integration, marquee features, and customization landed in this drop.

- **P1 polish + persistence** — resume on launch, sleep timer (Ctrl+I), mini-mode (Ctrl+M / double-click art), drag-to-reorder queue, history view (Ctrl+5), like/unlike (Ctrl+H), up-next preview, cache cap + auto-prune
- **P2 discovery** — explore page (Ctrl+6), artist + album detail, search filter tabs, thumbnails everywhere, per-theme text case (lowercase, UPPERCASE, l33t)
- **P3 visualizer** (Ctrl+7) — 9 theme-aware renderers (bars-mono, bars-filled, oscilloscope, neon-grid, circle-burst, mirror-bars, dot-matrix, starfield, matrix-rain), PipeWire monitor capture
- **P4 integration** — system tray, ListenBrainz scrobbling, LRClib timed lyrics fallback, toast notifications, daily update check, About section in Settings
- **P5 customization** — widget variants (5 slots × multiple variants), 4 layout presets (classic, focused, dj-deck, walkman)

## [1.0.0] — 2026-06-15 — initial release

A brutalist YouTube Music desktop client. Native Qt6, no Electron.

- Search, library, playlists, queue + radio autoplay, lyrics
- 10 swappable themes (brutalist-mono default, gruvbox, terminal-green, solarized-light, paper, nord, catppuccin, rose-pine, ambient, synthwave)
- MPRIS2 over QtDBus — media keys + KDE Plasma / GNOME panel controls
- Discord rich presence (opt-in, bring your own application id)
- GUI-first sign-in by importing cookies from your real browser

[1.2.0.1]: https://github.com/captiencelovesarch/tide/releases/tag/v1.2.0.1
[1.2.0]: https://github.com/captiencelovesarch/tide/releases/tag/v1.2.0
[1.1.1]: https://github.com/captiencelovesarch/tide/releases/tag/v1.1.1
[1.1.0]: https://github.com/captiencelovesarch/tide/releases/tag/v1.1.0
[1.0.0]: https://github.com/captiencelovesarch/tide/releases/tag/v1.0.0
