# Changelog

All notable changes to **tide** land here. Format roughly follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are [semver-ish](https://semver.org/) with a 4-segment patch when a release ships polish on top of an already-tagged feature drop.

The canonical source of truth for the diff lives in the [GitHub Releases](https://github.com/captiencelovesarch/tide/releases) — this file is for browsing history at a glance.

## [1.2.3.1] — 2026-06-30 — bug fixes

Pure bug-fix patch on top of 1.2.3 — no new surface, just things that were quietly wrong. The headline is YouTube Music personalization: the home feed served the generic logged-out shelves and the library came up empty even while signed in.

### Fixed
- **YouTube Music home is personalized again** — `browser_import` was merging `.google.com` *and* `.youtube.com` cookies into one flat header and deduping by name across domains. The auth cookies (`SID`, `__Secure-3PSID`, `SAPISID`, `__Secure-3PAPISID`) exist on **both** domains with **different** values, so wrong-domain values reached `music.youtube.com` and YouTube treated every request as logged-out (`LOGGED_IN:false`) — search still worked only because it needs no auth, which masked the bug. Now imports only `youtube.com`-scoped cookies, exactly what a browser sends to `music.youtube.com`. Personalized shelves (Quick picks, Listen again, Mixed for you, …) and library are restored.
- **YouTube Music sign-out actually signs out** — `YTMusicSource` inherited the base no-op `sign_out()`, so the Sources-tab button never cleared the saved cookie and the row kept saying "signed in". It now clears the cookie and flips the row state.
- **In-app re-sign-in** — the source gear dialog showed no button at all for a signed-out auth source, so signing out stranded YouTube Music until a restart. Added a `[sign in]` button (and `begin_auth()`) that re-runs the import wizard and refreshes the live client in place — no restart.
- **Auth no longer self-destructs on a network blip** — `ensure_signed_in()` deleted the saved cookies on *any* exception while building the client (which makes a network call), silently signing the user out. Transient failures now leave the saved session intact.
- **Album art honors rounded corners** — QSS `border-radius` never clips a `QLabel` pixmap, and `AlbumArt` read the theme's base `layout.radius_px` instead of the effective corner-style radius, so the art stayed square inside a rounded border. The pixmap is now masked to `theming.effective_radius_px()`. Sharp themes and the circle/polaroid variants are unchanged.
- **Settings stop resetting on save** — the settings dialog rebuilt its working copy field-by-field and silently dropped 16 fields (`ui_sounds_enabled`, `sources_enabled`, Spotify/Subsonic credentials, `audio_fx_state`, `first_launch_complete`, …), resetting them to defaults every time you hit save. It now deep-copies the whole settings object.

## [1.2.3] — 2026-06-16 — ui sounds + crossfading views

Tide gets a sense of touch. Short percussive sounds when switching nav views, soft pops on modal open/close, chirps on checkbox/radio toggles — all six WAVs hand-authored, all ship in `assets/sounds/`. The sounds auto-mute the second music starts playing so they never compete with the audio you're actually listening to. View switches also crossfade now using the same motion helper the onboarding wizard already used. Defaults to **off** on first launch — opt in via Settings → appearance → "ui sounds".

### Added
- **UI sound dispatcher** — `tide.ui_sounds.UiSoundPlayer`: one `QSoundEffect` per WAV key, played via `play("nav")` / `play("modal_open")` etc. Volume capped at 20 % of system so clicks never startle.
- **Six bundled sounds** — `nav` / `back` (view switch + back), `modal_open` / `modal_close` (dialogs), `toggle_on` / `toggle_off` (checkbox + radio flips).
- **Auto-mute during playback** — listens to the playback router's `state_changed`; flips muted on `PlayState.PLAYING` and back off the instant the player pauses or stops. Reseeds from the live player state on app start so resume-from-paused-session stays silent or not as appropriate.
- **Crossfading view transitions** — `_switch_view`, `_push_view`, and `_go_back` route through `tide.ui.motion.crossfade_stack` with `DUR_SHORT` (200 ms). Motion intensity `off` falls through to a direct `setCurrentIndex` automatically — same path the onboarding wizard already used between steps.
- **Settings toggle** — new "ui sounds" row under "motion:" in the appearance form. Hot-applied on save (no restart). Default `False` so a fresh install is silent.

### Technical
- `assets/sounds/` directory + `README.md` author spec — WAV format target documented for future contributors.
- Missing WAVs degrade cleanly — the loader treats every key as optional, so a fresh checkout without files just plays silence per key.
- Toggle hookups live in `_on_master_toggle` / `_on_loudness` / `_on_compressor` / `_on_mono` (audio fx view) and `_on_row_enable` / `_on_federate_toggle` (source panel). Future toggles add one `self._ui_sound(...)` line to the same handler.

## [1.2.2] — 2026-06-16 — audio fx rack

The "slowed + reverb" aesthetic finally has the reverb. v1.2.2 ships a full audio-FX rack riding on top of the existing mpv playback path — a 10-band graphic EQ, a five-preset reverb (off / room / hall / cathedral / signature **slowed**), bass + treble shelves, loudness normalization for queue sanity, stereo width, a level-boost compressor, and a mono fold. Everything composes with the existing speed + pitch-correction controls because mpv layers its scaletempo around our user filter graph. Works across every source — YT Music, SoundCloud, Bandcamp, Mixcloud, Local, Subsonic — anything that resolves to a stream mpv plays.

### Added
- **`[audio fx]` panel** — new top-level view at `Ctrl+9`. 10 vertical EQ sliders (32 Hz → 16 kHz, ±12 dB, half-octave width). EQ preset cards (flat / bass boost / treble boost / vocal boost / v-shape / soft warmth). Reverb preset picker + wet slider. Bass + treble shelves. Loudness-norm / compressor / mono toggles. Stereo-width slider. Three user-saved EQ slots (`[save] [load] [clear]`).
- **Quick `[fx]` popover** — new now-playing-strip button (next to `[speed]`). Master enable, preset chooser, reverb chooser, bass + treble shelves. Right-click the button toggles the whole rack on/off without opening the popover.
- **Signature "slowed" reverb preset** — three-tap `aecho` chain tuned for the slowed-and-reverb vibe. Pair with playback speed 0.85× + pitch-correction off for the canonical tide sound.
- **Loudness normalization** — `loudnorm=I=-14:LRA=11:tp=-1.5` (the streaming-platform target) gives consistent perceived volume across queue tracks regardless of source mastering.
- **Persisted state** — full rack (master + EQ bands + every knob + custom slots) round-trips through `~/.config/tide/settings.toml` as a single `audio_fx_state` JSON string. Debounced saves (250 ms) so EQ-slider drag doesn't write the file 60 times a second.
- **Settings dialog `audio fx` section** — short explainer + `[open audio fx panel →]` jump.

### Technical
- New `tide/audio_fx.py` module — pure-Python `AudioFxState` dataclass + `build_filter_chain(state) → str` (renders mpv `af` chain in fixed order: EQ → bass → treble → stereo → compressor → reverb → loudnorm → mono). No Qt dependency.
- New `Player.set_audio_filter_chain(chain)` writes the mpv `af` property; rejection (unparseable filter string) leaves the previous chain intact and logs to stderr instead of crashing.
- `PlaybackBackend` default no-op + `PlaybackRouter` fan-out — librespot / MusicKit ignore the chain since they own their audio rendering path.

## [1.2.1] — 2026-06-16 — spotify (shelved) + subsonic + wizard fix

The architecture for Spotify lands — six sources can register, the library and search surfaces work end-to-end, librespot runs as a Spotify Connect device, OAuth and credentials caching are wired. **But audio playback is broken upstream** and there's no client-side fix. Spotify rolled out a platform-security update on 2026-02-06 that refuses audio-decryption keys to librespot regardless of how it authenticates (`--access-token`, librespot's own `--enable-oauth`, cached credentials — all fail with `audio key error 0 1`). Tide ships the source so the code path is ready when (if) Spotify reopens or librespot upstream patches it, but enabling Spotify surfaces an explicit warning that playback won't work.

Subsonic is the silver lining of the same release. Self-hosted music — Navidrome, Airsonic, gonic, Funkwhale, the reference Subsonic server — all speak the same REST surface, and tide now streams audio straight from your server. Search + library + albums + artists + home shelves + starred-as-liked all wired through `search3` / `getAlbumList2` / `getArtist` / `getSimilarSongs2`. No platform broker, no rate limits, no shelf state — your server, your music.

### Added (functional)
- **Spotify source** — search (10-result cap, see below), library + playlists (Liked Songs first), like/save, lyrics via LRClib fallback. Registered after auth completes; appears last in the source panel.
- **Subsonic / Navidrome source** — full Subsonic API 1.16.1 client: search3 for songs/albums/artists, getPlaylists + getPlaylist for library, getAlbum / getArtist / getArtistInfo2 for detail pages, getAlbumList2 (newest / frequent / starred / random) for home shelves, getSimilarSongs2 → getRandomSongs as the radio fallback, star/unstar for likes. MD5(password + salt) auth by default (safe over HTTP); plain-password mode for HTTPS-only Navidrome installs. Audio streams via the `stream` endpoint straight into mpv — same playback path as YT Music / SoundCloud / Bandcamp.
- **Subsonic connect dialog** — onboarding wizard ships a [set up] card for Subsonic that opens a URL + user + password + auth-style form with a `[test connection]` button (ping runs on a background thread, returns "signed in as X" or "can't reach …"). Same dialog reachable from the source panel's gear icon for re-configure or sign-out.
- **Shelved-state warning** — toggling Spotify on (in the onboarding wizard or the source panel) surfaces a confirmation dialog explaining what works, what doesn't, and why. Defaults to "No".
- **OAuth-PKCE sign-in for Web API** — onboarding's source step shows Spotify; clicking it opens the browser to Spotify's auth page and tide listens on `127.0.0.1:8898` for the redirect. Refresh tokens AES-encrypted at `~/.config/tide/spotify.json`.
- **Librespot subprocess + Web API control plane** — librespot runs as a Spotify Connect device named `tide` with `--system-cache ~/.cache/tide/librespot/`. tide drives play/pause/seek/queue via Web API. The router auto-switches between MPV (everywhere else) and librespot mid-queue.

### Spotify Dev Mode caveats (all the new February 2026 walls)
Spotify rolled out a tightened "Development Mode" tier on 2026-02-06. Apps that haven't been granted Extended Quota Mode (an explicit app review at developer.spotify.com) hit four new walls:
- **Audio decryption refused** — `audio_key error 0 1` for every track, regardless of auth method. This is the blocker that shelved playback.
- **Search results capped at 10** per query — anything higher returns 400 "Invalid limit". tide caps at 10 so the UI never sees the error.
- **`/browse/*` endpoints are 403** (featured-playlists, new-releases, categories) — home shelves can't render. Spotify's source registers without the `home` capability.
- **Artist top-tracks + related-artists are 403** — artist detail and track-station radio can't fill. Spotify's source registers without the `radio` capability.

### Fixed
- **First-launch wizard segfault** — clicking the `[set up]` button on a source card or canceling a YT cookie / Local-files dialog was opening a modal QDialog directly inside the click emission. On PySide6 + Python 3.14, returning to the Python frame ref-dropped the dialog while the SignalManager frames were still live, and the `deleteChildren` walk corrupted the heap. The setup dialog is now deferred past the emission via `QTimer.singleShot(0)`, and the dialog instance is explicitly `deleteLater()`'d instead of relying on Python ref-drop. Same blockSignals guard on the cancel-path uncheck so a second toggled emission can't re-enter mid-cleanup.
- **Radio refill against unsupported sources** — `_on_radio_refill_requested` checked the active source's `radio` capability; if the source declares no radio (now true for Spotify), tide auto-disables the queue's radio flag instead of spinning a worker that 403s in a loop.
- **librespot stderr was swallowed** — subprocess used to `stderr=subprocess.DEVNULL`, which hid the `Unrecognized option` / `audio key error` / Connect-handshake details that took most of v1.2.1's debugging time to surface. Now stderr inherits tide's so librespot's logs land in the same stream.

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

[1.2.1]: https://github.com/captiencelovesarch/tide/releases/tag/v1.2.1
[1.2.0.1]: https://github.com/captiencelovesarch/tide/releases/tag/v1.2.0.1
[1.2.0]: https://github.com/captiencelovesarch/tide/releases/tag/v1.2.0
[1.1.1]: https://github.com/captiencelovesarch/tide/releases/tag/v1.1.1
[1.1.0]: https://github.com/captiencelovesarch/tide/releases/tag/v1.1.0
[1.0.0]: https://github.com/captiencelovesarch/tide/releases/tag/v1.0.0
