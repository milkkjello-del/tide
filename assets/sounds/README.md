# tide/assets/sounds

UI-feedback sound files. Loaded at startup by `tide.ui_sounds.UiSoundPlayer`,
played via `QSoundEffect`. The user master toggle lives in Settings →
appearance (`ui sounds`). Sounds are automatically suppressed while
music is playing, so they only fire when the player is paused / idle.

## Catalog

| File | Triggered by |
|---|---|
| `nav.wav` | nav-rail click / view switch |
| `back.wav` | `[back]` button on detail views |
| `modal_open.wav` | any dialog opening (settings, sleep timer, sign-in flows) |
| `modal_close.wav` | any dialog closing (accepted *or* rejected) |
| `toggle_on.wav` | checkbox / radio flipping on |
| `toggle_off.wav` | flipping off |

Missing files don't crash — they just no-op for that key. Drop new keys in
via `UiSoundPlayer.SOUND_KEYS` if you add events.

## Format target

- PCM `.wav` (uncompressed)
- 22050 or 44100 Hz
- 16-bit
- mono preferred (stereo accepted)
- 30–150 ms is the sweet spot; longer feels laggy on rapid nav
- aim for peak around -6 dBFS so the 0.20 default playback gain has headroom
