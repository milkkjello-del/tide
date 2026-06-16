<div align="center">

<img src="assets/icon-256.png" alt="tide" width="160" height="160" />

# tide

**a brutalist multi-source music client**

native Qt6 · 5 sources · 11 themes · 9 visualizers · MPRIS2 · adaptive accent · pitch-shifting speed · zero config-file editing

[![release](https://img.shields.io/github/v/release/captiencelovesarch/tide?style=flat-square&color=d4b95e&labelColor=0b0b0b)](https://github.com/captiencelovesarch/tide/releases/latest)
[![license](https://img.shields.io/badge/license-GPL--3.0-d4b95e?style=flat-square&labelColor=0b0b0b)](LICENSE)
[![arch](https://img.shields.io/badge/distro-arch_linux-d4b95e?style=flat-square&labelColor=0b0b0b)](https://archlinux.org)
[![qt6](https://img.shields.io/badge/qt-6-d4b95e?style=flat-square&labelColor=0b0b0b)](https://www.qt.io)

</div>

---

<div align="center">

<img src="assets/screenshots/now-playing-adaptive.png" alt="tide — now playing, adaptive theme with album-tinted gradient" width="780" />

<sub>adaptive theme · album-tinted central gradient · soft corners · v1.2.1</sub>

</div>

```
yay -S tide        # release (when AUR registrations reopen)
# or right now:
git clone https://github.com/captiencelovesarch/tide.git && cd tide && makepkg -si
```

then launch `tide`, click **`[import]`**, you're listening. that's the whole setup.

> **note on spotify** · the integration is shipped but shelved — spotify's 2026-02-06 platform-security update started refusing audio-decryption keys to librespot regardless of how it authenticates, so audio plays as silence on every account we've tested. tide can still search the catalog, browse your library, and appear as a Connect device, but enabling spotify pops a confirmation explaining that playback is broken. when (if) spotify reopens or librespot upstream patches it, the integration will start working with no code change.

---

## what it is

tide is a **standalone desktop client for music — from anywhere you can stream it**. native Qt6 — not an Electron skin. it sits on top of `mpv`, talks to YouTube Music via `ytmusicapi`, resolves streams via `yt-dlp`, reads your local files via `mutagen`, and renders everything in IBM Plex with monochrome + an accent color you can let the album cover dictate.

it was designed for one thing: to be **the music app that has a sense of itself**. no shipped defaults are middle-of-the-road. brutalist-mono ships as the default; if you don't like brutalism, swap themes from a dropdown — same app, completely different personality.

## sources (v1.2)

press `Ctrl+8` for the `[source]` panel — every source is one toggle away.

| | tag | search | library | requires |
|---|---|---|---|---|
| **youtube music** | `[YT]` | ✓ | ✓ | cookie import |
| **soundcloud** | `[SC]` | ✓ | — | nothing |
| **bandcamp** | `[BC]` | ✓ | — | nothing |
| **mixcloud** | `[MC]` | ✓ | — | nothing |
| **local files** | `[LO]` | ✓ | ✓ (by album) | a music directory |
| **subsonic / navidrome** | `[SS]` | ✓ | ✓ (playlists + albums + artists) | your server's url + login |
| spotify | `[SP]` | shelved | shelved | broken upstream — see note below |
| apple music | `[AM]` | v1.2.2 | v1.2.2 | apple id |

queue is source-agnostic. mix a YT Music search, a Bandcamp deep cut, and a local FLAC in the same queue — tide dispatches each to the right backend. **federated search** mode (toggle in the source panel) runs every enabled source in parallel and tags each result row so you can see where the hit came from.

<div align="center">

<img src="assets/screenshots/source-panel.png" alt="tide — source panel" width="780" />

<sub>`Ctrl+8` — each source one toggle away</sub>

</div>

## features

### playback

- search the YouTube Music catalog (your account or anonymous)
- your **library + playlists** (liked songs first)
- **queue + radio autoplay** — when the queue ends, tide pulls a continuous radio seeded from the last track
- **lyrics** — plain from YT Music, **synced** via LRClib fallback (active line bolds + auto-scrolls)
- **drag-to-reorder queue**, sleep timer (Ctrl+I), like button (Ctrl+H), history view, mini-mode (Ctrl+M)
- **resume on launch** — quit mid-song, relaunch, picks up paused at the same position

<div align="center">

<img src="assets/screenshots/lyrics-synced.png" alt="tide — synced lyrics view" width="780" />

<sub>synced lyrics via LRClib fallback — active line bolds + auto-scrolls</sub>

</div>

### discovery (Ctrl+6)

- YT Music's home shelves rendered as horizontal card rows
- artist detail (top songs + albums + singles + related)
- album detail (cover + tracklist + play all / shuffle)
- search filter tabs: `[songs] [videos] [albums] [artists]`

<div align="center">

<img src="assets/screenshots/explore.png" alt="explore — home shelves" width="780" />

</div>

### look & feel

- **11 themes**, each with its own personality:

  | | font | case | controls | accent |
  |---|---|---|---|---|
  | **brutalist-mono** (default) | IBM Plex Mono | lowercase | `[play]` | amber `#d4b95e` |
  | gruvbox | IBM Plex Mono | lowercase | `[play]` | mustard |
  | terminal-green | IBM Plex Mono | UPPERCASE | `[play]` | CRT green |
  | solarized-light | IBM Plex Mono | normal | text | blue |
  | paper | IBM Plex Sans | normal | text | crimson |
  | nord | IBM Plex Sans | normal | ▶ | frost |
  | catppuccin | IBM Plex Sans | normal | ▶ | pink |
  | rose-pine | IBM Plex Sans | normal | ▶ | rose |
  | ambient | IBM Plex Sans | normal | ▶ | lavender |
  | synthwave | IBM Plex Sans | **`L33T`** | ▶ | neon magenta + cyan |
  | adaptive | IBM Plex Sans | normal | ▶ | follows current album art |

<div align="center">

<table>
<tr>
<td><img src="assets/screenshots/theme1.png" alt="theme variant 1" width="300" /></td>
<td><img src="assets/screenshots/theme2.png" alt="theme variant 2" width="300" /></td>
<td><img src="assets/screenshots/theme3.png" alt="theme variant 3" width="300" /></td>
</tr>
</table>

<sub>same app, three themes</sub>

</div>

- **4 layout presets**: `classic`, `focused`, `dj-deck`, `walkman` (portrait phone-shape) — each swaps widget variants (progress style, volume style, album-art shape, controls size, label arrangement)
- **adaptive accent** — opt-in toggle that animates the theme accent toward the current cover's dominant color
- **adaptive central-area gradient** — optional companion to adaptive accent; tints the main content area with a soft vertical gradient pulled from the album palette, retinting per track
- **per-theme text case** — synthwave renders `H3110 W0R1D`, terminal-green renders `ALL CAPS`, brutalist stays lowercase
- **3 bundled fonts** — IBM Plex Mono, JetBrains Mono, Inter — plus a font picker that overrides any theme's typography (accepts arbitrary system family names)
- **themed nav icons** — bundled brutalist SVG line-art (recolored to the active theme's `fg`), classic mono glyphs, or emoji

### motion & feel  *(new in v1.2.0.1)*

- **motion intensity** — `off` / `lite` (default — signature + everyday animations) / `full` (everything including atmospheric). respects `QT_REDUCED_MOTION` and clamps `full` to `lite` when set.
- **track-change signature** — title decodes left-to-right from random block glyphs while the album art crossfades; layered on top of the existing 1.5s adaptive accent fade for a triple-timeline reveal.
- **playback speed** — popover with `−0.05` / `+0.05` nudges, preset buttons (`0.5× 0.75× 1.0× 1.25× 1.5× 2.0×`), and a reset. Pitch-shifted by default for the slowed-and-reverb / nightcore vibe; toggle "preserve pitch" in settings for audiobook use. Shortcuts: `[` slow · `]` fast · `\` reset.
- **audio fx rack** *(new in v1.2.2)* — `Ctrl+9` for the full panel: 10-band graphic EQ (32 Hz → 16 kHz, ±12 dB) with preset cards (`flat / bass boost / treble boost / vocal boost / v-shape / soft warmth`) and 3 user-saved slots, reverb preset bank (`off / room / hall / cathedral / `**`slowed`**) with wet slider, bass + treble shelves, loudness normalization (-14 LUFS), stereo width, compressor, mono fold. Quick `[fx]` popover next to `[speed]` for one-click preset + reverb + bass/treble. Right-click `[fx]` to toggle the whole rack on/off. Pair the **slowed** reverb with playback speed 0.85× + pitch-correction off for the canonical tide signature.
- **UI sounds + crossfading views** *(new in v1.2.3)* — short percussive sounds on nav clicks, soft pops on modal open/close, chirps on toggle flips. Auto-muted the second music starts playing so they never compete with the player. View switches crossfade instead of snapping. Six bundled WAVs (hand-authored), defaults **off** — opt in via Settings → appearance → "ui sounds".
- **UI scale** — `compact (0.85×) / normal / large (1.15×) / huge (1.30×)`. cascades through every fixed-size widget (track row, album art, cards, album/artist pages, view margins).
- **soft corners** — `sharp` / `soft (6px)` / `rounded (12px)` applies a sticky `@radius` override on inputs, scrollbars, and the central-area clip.
- **customizable loading bar** — five styles in the status bar tracking the resolve → buffer → playing window: `off`, `numbers`, `blocks`, `dots`, `ascii`.
- **stream-URL prefetch** — once a track has ≤15s remaining, tide pre-resolves the next one. auto-advance is ~instant on cache hit; silent fallback to normal resolve on miss.

<div align="center">

<table>
<tr>
<td><img src="assets/screenshots/speed-popover.png" alt="speed popover" width="380" /></td>
<td><img src="assets/screenshots/settings-appearance.png" alt="settings appearance section" width="380" /></td>
</tr>
</table>

<sub>speed popover (left) · appearance settings showing motion / ui scale / corners / nav icons / font (right)</sub>

</div>

### audio visualizer (Ctrl+7, F11 for fullscreen)

9 theme-aware renderers driven by a PipeWire monitor capture + numpy FFT pipeline:

- `bars-mono` `▁▂▃▅▆▇█` — for mono themes
- `bars-filled` — gradient rectangles, sans themes
- `oscilloscope` — waveform line + halo (ambient)
- `neon-grid` — synthwave perspective grid + spectrum bars
- `circle-burst` — radial 360° spectrum
- `mirror-bars` — symmetric VU-style EQ
- `dot-matrix` — pixelated reactive grid (brutalist)
- `starfield` — particles flying toward camera, bass-driven speed
- `matrix-rain` — cascading characters

in-canvas `⚙` cog overrides renderer + audio source on the fly.

<div align="center">

<img src="assets/screenshots/visualizer-synthwave.png" alt="tide — visualizer, synthwave theme + neon-grid renderer" width="780" />

<sub>synthwave theme + `neon-grid` renderer</sub>

</div>

### system integration

- **MPRIS2** over QtDBus — media keys, KDE Plasma & GNOME panel controls, lockscreen art
- **Discord rich presence** — opt-in, shows `0:34 / 3:42` progress with current track + album cover (you bring your own Discord app ID)
- **ListenBrainz scrobbling** — opt-in, paste your user token
- **system tray** (KDE/GNOME) — hide-to-tray on close, full controls in the tray menu
- **daily update check** — toast when a newer release lands on GitHub

## install

### arch linux (everything is in `extra`)

```sh
git clone https://github.com/captiencelovesarch/tide.git
cd tide
makepkg -si
```

tide ends up at `/usr/bin/tide`. desktop launcher + icon get installed for KDE/GNOME menus. when AUR registrations reopen, `yay -S tide` will work too.

### sign in

on first launch, tide opens a small dialog: open YT Music in your browser, sign in normally, click **`[import]`** in tide. tide reads the cookies straight out of your chromium-family browser (decrypting via your kwallet/libsecret key) and you're in.

supported browsers: Chromium, Chrome, Brave, Vivaldi, Microsoft Edge. **OAuth doesn't work** for YT Music as of 2024 — Google blocks WEB_REMIX endpoints for OAuth-bearer tokens — so cookie import is the only working path.

### other linux distros

not officially supported, but doable:

```sh
sudo apt install python3 mpv libmpv-dev fonts-ibm-plex   # debian/ubuntu equivalent
pip install --user pyside6 ytmusicapi yt-dlp python-mpv cryptography pypresence numpy sounddevice secretstorage
git clone https://github.com/captiencelovesarch/tide.git
cd tide && PYTHONPATH=src python -m tide
```

no desktop launcher, no auto-icons. tested only on arch.

### macOS / Windows

probably possible, untested, doesn't make sense without MPRIS / kwallet / parec. you'd be in port-the-app territory.

## keyboard shortcuts

| key | action |
|---|---|
| `Ctrl+1` | search |
| `Ctrl+2` | library |
| `Ctrl+3` | queue |
| `Ctrl+4` | lyrics |
| `Ctrl+5` | history |
| `Ctrl+6` | explore |
| `Ctrl+7` | visualizer |
| `Ctrl+8` | source panel |
| `Ctrl+,` | settings |
| `Ctrl+F` / `Ctrl+L` | focus search bar |
| `Space` | play / pause |
| `Ctrl+→` / `Ctrl+←` | next / previous track |
| `Ctrl+↑` / `Ctrl+↓` | volume +/− 5 |
| `[` / `]` | playback speed −/+ 0.05 |
| `\` | reset playback speed to 1.0× |
| `Ctrl+9` | open `[audio fx]` panel — eq + reverb + the rest |
| `Ctrl+H` | like / unlike current track |
| `Ctrl+I` | sleep timer dialog |
| `Ctrl+M` | toggle mini-mode |
| `F11` | visualizer fullscreen |

right-click any track row for: play now / play next / add to queue / start radio from here / view artist.

## file locations

| path | what |
|---|---|
| `~/.config/tide/settings.toml` | theme, layout, discord, scrobbling, volume, etc. |
| `~/.config/tide/browser.json` | imported YT cookies (chmod 0600) |
| `~/.config/tide/themes/` | drop your own themes here |
| `~/.config/tide/layouts/` | drop your own layouts here |
| `~/.cache/tide/streams/<source>.json` | stream URL cache, one file per source (Bandcamp never expires; others TTL'd) |
| `~/.cache/tide/local_index.sqlite` | local-files tag index (FTS5) |
| `~/.cache/tide/art/` | thumbnail cache (auto-pruned to 1000 newest) |
| `~/.cache/tide/lyrics/` | LRClib lyric cache |
| `~/.cache/tide/session.json` | resume-on-launch state |
| `~/.cache/tide/history.jsonl` | play history |
| `~/.local/share/tide/webview/` | leftover from old webview wizard (safe to delete) |

every settable knob is reachable from the **Settings** dialog. no config-file editing is required for anything tide ships. ever.

## tech

```
python 3.12+
PySide6 (Qt6, LGPL)
mpv + python-mpv
ytmusicapi + yt-dlp        (YT Music + SoundCloud + Bandcamp + Mixcloud)
python-mutagen             (local files tag reader)
python-cryptography        (chromium cookie decryption)
python-numpy               (visualizer FFT)
python-sounddevice         (audio capture)
parec                      (PipeWire monitor capture)
ttf-ibm-plex               (bundled font)

optional:
python-pypresence          (Discord rich presence)
python-secretstorage       (GNOME/libsecret cookie key)
kwallet                    (KDE wallet cookie key)
python-watchdog            (live re-index of local files)
```

all deps live in Arch's `extra` repo. zero AUR-only python packages. the PKGBUILD is the entire dependency manifest.

## roadmap

- [x] **v1.0** — initial release (search, library, playlists, queue, lyrics, MPRIS, 10 themes)
- [x] **v1.1** — QOL kitchen sink (visualizer, scrobbling, layouts, adaptive accent, tray, history, sleep timer, mini-mode, 11 themes)
- [x] **v1.2.0** — multi-source: + SoundCloud + Bandcamp + Mixcloud + Local files, source panel, federated search
- [x] **v1.2.0.1** — pre-spotify glow-up: animations, pitch-shifting speed, UI scale, adaptive central gradient + soft corners, themed nav icons + SVG set, 3 bundled fonts + picker, customizable loading bar, Discord-timer + adaptive-picker fixes, stream-URL prefetch
- [x] **v1.2.1** — Spotify (shelved upstream) + Subsonic / Navidrome (self-hosted music)
- [x] **v1.2.2** — audio fx rack (10-band eq + reverb + loudness norm + extras), `Ctrl+9`
- [x] **v1.2.3** — UI sounds (nav clicks + modal pops + toggle chirps, auto-muted during playback) + crossfading view transitions
- [ ] **v1.2.4** — Apple Music (MusicKit JS via embedded webview)

## license

[GPL-3.0-or-later](LICENSE).

## not affiliated

not affiliated with YouTube or Google. tide uses public YT Music endpoints via [`ytmusicapi`](https://github.com/sigma67/ytmusicapi) and resolves audio streams via [`yt-dlp`](https://github.com/yt-dlp/yt-dlp). YouTube cookies you import are stored only locally.

---

<div align="center">

made with care, claude, and a lot of "lol let's just add that too"

</div>
