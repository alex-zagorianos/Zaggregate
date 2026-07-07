# Building Zaggregate

Two artifacts come out of one script, `src/build_package.py`, driven by
`src/app.spec` (the PyInstaller onedir spec — the reproducibility anchor,
committed to the repo). Both commands are run from the repo root and their
outputs land at the **repo root** (not under `src/`):

| Artifact              | Command                                      | What it is                                                                              |
| --------------------- | -------------------------------------------- | --------------------------------------------------------------------------------------- |
| **Shippable zip**     | `py -3.12 src\build_package.py`              | `dist/Zaggregate-v{ver}.zip` (repo root) — a friend downloads, unzips, runs.            |
| **Production folder** | `py -3.12 src\build_package.py --production` | `production/` at the repo root — the same app, already unzipped and ready to hand over. |

Both are **build artifacts** and are gitignored (`dist/`, `build/`, `production/`,
throwaway `*.spec`). The deliverables under version control are `src/build_package.py`
and `src/app.spec`; you regenerate the folders with one command.

Requires PyInstaller (pinned in `requirements.txt`): `py -3.12 -m pip install pyinstaller`.

> Internal names stay `JobProgram` (the exe, the data folder, the version resource)
> on purpose — renaming them orphans existing users' data under
> `%LOCALAPPDATA%\JobProgram`. The **product** name is Zaggregate; the **internal**
> name is JobProgram. Do not "fix" this.

## The production folder — one command

```
py -3.12 src\build_package.py --production
```

This runs PyInstaller (`src/app.spec` → `dist/JobProgram/` at the repo root),
then assembles `production/` at the repo root. To skip the ~2-minute PyInstaller
pass and just re-assemble from an existing `dist/JobProgram/`, add `--no-build`:

```
py -3.12 src\build_package.py --production --no-build
```

### What's inside `production/`

```
production/
  JobProgram/
    JobProgram.exe        the runnable Windows app (onedir, windowed/noconsole)
    _internal/            PyInstaller runtime: Python, tkinter/ttkbootstrap, and the
                          read-only bundle (data_static/, data_templates/,
                          companies.json, search/templates, resume/templates)
    data/                 seeded writable data: companies.json + experience.md +
                          preferences.md/json  (the app resolves <exe>/data here;
                          falls back to %LOCALAPPDATA%\JobProgram if <exe>/data is
                          read-only, e.g. Program Files)
    FIRST-RUN.txt         plain-English steps past the SmartScreen "unknown publisher"
    Zaggregate-Desktop.bat / Zaggregate-Web.bat
                          one-click launchers (desktop window / browser); the
                          bare exe opens the desktop app too, --classic = legacy Tk
    browser_ext/          the extension, next to the exe (the in-app Guide points here)
    claude-code/          the MCP / Claude Code channel (BYO-AI, ships as source)
    requirements-mcp.txt  pip deps for the MCP channel
  browser_ext/            the extension again, lifted to the top level so the user's
                          chrome://extensions "Load unpacked" target is obvious
  QUICKSTART.md           run the exe -> the wizard opens -> load the extension
  README.txt              full readme, including the upgrade (data-preserving) path
  CHANGES.txt             per-release changelog
  .env.example            optional API keys (none required to start)
```

Size: ~115 MB total; the exe alone is ~18 MB, `_internal/` ~95 MB.

No personal data ships: `data/` carries only the neutral templates from
`data_templates/` and the public starter `companies.json`. Secrets never bundle.

### First-run behavior (verified)

Launching `JobProgram.exe` with no `.onboarded` marker opens the **Setup wizard**
~120 ms after the window appears, then bootstraps the data folder (seeds
preferences/experience, initializes `tracker.db`). The smoke test in
`src/build_package.py`'s CI story just confirms the frozen exe stays alive (a missing
hidden import kills a windowed exe within ~1-2 s) — liveness alone proves the
wizard/window came up clean.

## Cutting a release / bumping the version

The version is a **single source of truth**: `config.APP_VERSION` (in
`src/config.py`). Bump that one line (semantic versioning, `MAJOR.MINOR.PATCH`)
and everything follows:

- the zip name (`Zaggregate-v{ver}.zip`),
- the exe's Windows version resource (`src/app.spec` reads `config.APP_VERSION`),
- `QUICKSTART.md`, `README.txt`, `CHANGES.txt`,
- the in-app About dialog / `last_run.json` / problem-report bundle.

After bumping, edit the `CHANGES` stub in `src/build_package.py` (replace the
placeholder date with the ship date, add user-facing bullets) and rebuild.

### Publishing a release (GitHub Actions)

Releases are built and published by CI — nothing is built or uploaded from a
dev machine. Pushing a version tag to this repository triggers
[`.github/workflows/release.yml`](../.github/workflows/release.yml), which:

1. checks the tag against `config.APP_VERSION` (they must agree),
2. runs the packaging tests,
3. builds `dist/Zaggregate-v{ver}.zip` + `SHA256SUMS.txt` from that exact tree,
4. verifies the checksum, and
5. publishes a GitHub Release with both files under Assets.

```
git tag v1.2.3 && git push origin v1.2.3     # full release (marked "latest")
git tag v1.2.4-beta1 && ...                  # hyphenated tag -> pre-release
```

The in-app update check (`src/webui/api/meta.py`) reads `releases/latest`
from this repository, so publishing a full release is what makes existing
installs offer the new version. The built app is **not** committed to the
repo — `Executables/` is a pointer README; the Release asset is the download.

## Code signing (optional, not enabled)

The exe is unsigned, so Windows shows an "unknown publisher" warning the first
time (handled by `FIRST-RUN.txt`). To remove it, get an OV/EV code-signing cert
and wire up `_sign_exe()` in `src/build_package.py` — see its docstring for the
`signtool` invocation. Left off by default.
