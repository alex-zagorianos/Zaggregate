# Building Zaggregate

Two artifacts come out of one script, `build_package.py`, driven by `app.spec`
(the PyInstaller onedir spec — the reproducibility anchor, committed to the repo):

| Artifact              | Command                                  | What it is                                                                              |
| --------------------- | ---------------------------------------- | --------------------------------------------------------------------------------------- |
| **Shippable zip**     | `py -3.12 build_package.py`              | `dist/Zaggregate-v{ver}.zip` — a friend downloads, unzips, runs.                        |
| **Production folder** | `py -3.12 build_package.py --production` | `production/` at the repo root — the same app, already unzipped and ready to hand over. |

Both are **build artifacts** and are gitignored (`dist/`, `build/`, `production/`,
throwaway `*.spec`). The deliverables under version control are `build_package.py`
and `app.spec`; you regenerate the folders with one command.

Requires PyInstaller (pinned in `requirements.txt`): `py -3.12 -m pip install pyinstaller`.

> Internal names stay `JobProgram` (the exe, the data folder, the version resource)
> on purpose — renaming them orphans existing users' data under
> `%LOCALAPPDATA%\JobProgram`. The **product** name is Zaggregate; the **internal**
> name is JobProgram. Do not "fix" this.

## The production folder — one command

```
py -3.12 build_package.py --production
```

This runs PyInstaller (`app.spec` → `dist/JobProgram/`), then assembles
`production/`. To skip the ~2-minute PyInstaller pass and just re-assemble from an
existing `dist/JobProgram/`, add `--no-build`:

```
py -3.12 build_package.py --production --no-build
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
    launch.bat            friendly one-line launcher for the exe
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
`build_package.py`'s CI story just confirms the frozen exe stays alive (a missing
hidden import kills a windowed exe within ~1-2 s) — liveness alone proves the
wizard/window came up clean.

## Cutting a release / bumping the version

The version is a **single source of truth**: `config.APP_VERSION`. Bump that one
line (semantic versioning, `MAJOR.MINOR.PATCH`) and everything follows:

- the zip name (`Zaggregate-v{ver}.zip`),
- the exe's Windows version resource (`app.spec` reads `config.APP_VERSION`),
- `QUICKSTART.md`, `README.txt`, `CHANGES.txt`,
- the in-app About dialog / `last_run.json` / problem-report bundle.

After bumping, edit the `CHANGES` stub in `build_package.py` (replace the
placeholder date with the ship date, add user-facing bullets) and rebuild.

## Code signing (optional, not enabled)

The exe is unsigned, so Windows shows an "unknown publisher" warning the first
time (handled by `FIRST-RUN.txt`). To remove it, get an OV/EV code-signing cert
and wire up `_sign_exe()` in `build_package.py` — see its docstring for the
`signtool` invocation. Left off by default.
