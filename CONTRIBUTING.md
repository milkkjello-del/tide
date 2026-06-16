# Contributing to tide

Hey — thanks for being here.

tide is a small project with a strong sense of identity. The bar for changes that ship is "does this make tide feel more like itself?" If you're not sure, open a discussion first.

## Running from source

```bash
git clone https://github.com/captiencelovesarch/tide.git
cd tide
PYTHONPATH=src python -m tide
```

Dependencies live in `pyproject.toml`. On Arch you probably already have most of them via the `tide` package — if not, `pacman -S pyside6 python-mpv mpv yt-dlp python-ytmusicapi python-cryptography python-mutagen python-requests`.

## Style

- **Don't add comments that explain WHAT the code does.** Names and structure should make that clear. Add a comment when the WHY isn't obvious — a hidden invariant, a workaround for a specific Qt quirk, a tradeoff you weighed and want the next reader to understand.
- **Lowercase, terse, blunt.** Match the brutalist aesthetic of the README and the UI. Sentences in error messages and status text don't end with periods.
- **Pure functions where you can.** UI-side state lives on the widget; settings live in `Settings`; themes/layouts/sources are plugins.
- **No bouncy easing curves.** All animation goes through `src/tide/ui/motion.py`. If you need a new curve, add it there and document why brutalist motion needs it.

## Adding a theme

1. Make a folder under `src/tide/themes/<slug>/`.
2. Drop in `theme.toml` (declares tokens + typography + layout flags) and `theme.qss` (the stylesheet, with `@token` substitutions).
3. Test with `tide --theme <slug>` or pick it from `Settings → appearance → theme`.
4. Add a screenshot at `assets/screenshots/<slug>.png` if you want it in the README gallery.

Keep the theme self-contained — don't introduce new tokens unless every other theme can fall back gracefully.

## Adding a source

A source is a Python class that implements `tide.sources.base.Source`. Look at `tide/sources/ytmusic.py` or `tide/sources/local.py` for examples. The key methods are `search`, `home`, `library`, `album`, `artist`, and `resolve_stream`.

Sources declare their capabilities via `supports("rating")`, `supports("radio")`, etc. — the UI uses these to gray out buttons your source can't satisfy. Failing gracefully is more important than supporting everything.

## Testing

There's no formal test suite yet. Before you push:

1. **Syntax check every touched Python file:**
   ```bash
   python -c "import ast; [ast.parse(open(p).read()) for p in ['src/tide/your_file.py', ...]]"
   ```
2. **Launch tide** and exercise the feature/fix manually. Try at least two themes (e.g. brutalist-mono and synthwave) since they have very different layout flags.
3. **If you added a setting**, verify it hot-swaps from the dialog without needing a restart.

CI runs the same syntax check on every PR.

## Commits

Commit messages follow this loose shape, matching the existing history:

```
type(scope): one-line title

· bullet about what changed
· bullet about why
```

`type` is one of `feat`, `fix`, `chore`, `docs`, `refactor`, `release`. `scope` is optional but useful for grouping (`v1.2`, `theming`, `playback`, etc.). The `·` bullets are the project style — feel free to use plain dashes if you prefer.

Co-authored-by trailers are welcome when you actually collaborated.

## License

By contributing, you agree your contribution is licensed under [GPL-3.0-or-later](LICENSE), the same as tide.
