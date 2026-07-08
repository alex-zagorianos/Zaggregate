# Plan — Beta distribution + auto-update (Velopack phase 2)

**Date:** 2026-07-08 · **Status:** approved, implementing
**Supersedes:** the "2 open design calls" in `docs/handoffs/handoff_20260707_session44.md:101`

## The two open design calls, now closed

1. **Where does user data live?** → `%LOCALAPPDATA%\JobProgram`, unconditionally, for every
   frozen build. (Was: `<exe>/data` if writable — which sits _inside_ Velopack's swap zone.)
2. **How do beta testers get separate builds?** → a dedicated Velopack `beta` channel, fed by
   the existing hyphenated-tag pre-release convention.

Alex's calls (2026-07-08): **Setup.exe only** (drop the portable zip) · **click-to-check,
click-to-apply** (PRIVACY.md promise preserved) · **dedicated `beta` channel** ·
**ship unsigned to the closed cohort**, signing hook stubbed for later.

## Verified ground truth (measured, not assumed)

Probed against the real `velopack` 1.2.0 wheel in a throwaway venv:

| Claim                                                                                     | Result                                                                                                                                   |
| ----------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `velopack` on PyPI, official                                                              | ✅ 1.2.0, 2026-06-03, abi3 wheels incl. `win_amd64`                                                                                      |
| `App().run()` outside a Velopack install                                                  | ✅ **safe no-op** (logs `NotInstalled`, does not exit)                                                                                   |
| `UpdateManager(...)` outside a Velopack install                                           | ✅ raises `RuntimeError: This application is not properly installed` → **free, reliable managed-install detector**                       |
| `apply_updates_and_restart_with_args(update, args)`                                       | ✅ exists → `--web`/`--classic` survive an update                                                                                        |
| `wait_exit_then_apply_updates(update, silent, restart, restart_args)`                     | ✅ exists → we can answer HTTP 200 _then_ exit                                                                                           |
| `download_updates(info, progress_callback=None)`                                          | ✅ exists → progress bar                                                                                                                 |
| `GithubSource(repo_url, access_token=None, prerelease=False)`                             | ✅ prerelease flag is first-class                                                                                                        |
| `UpdateOptions(AllowVersionDowngrade, MaximumDeltasBeforeFallback, ExplicitChannel=None)` | ⚠️ **2 required positional args** — not kwargs-only                                                                                      |
| `vpk` CLI                                                                                 | ships as a dotnet tool (`vpk.1.2.0.nupkg`, 124 MB). CI `windows-latest` has the .NET SDK; **this desktop has runtime 5.0.15 and no SDK** |

Consequences baked into the plan below: the `RuntimeError` _is_ the detector (no marker file);
`UpdateOptions` takes positionals; the `vpk` leg can only be exercised in CI from this machine.

## Install layout after this change

```
%LOCALAPPDATA%\Zaggregate\          <- Velopack RootAppDir
    Update.exe
    current\                        <- SWAPPED WHOLESALE on every update
        JobProgram.exe
        _internal\...
    packages\
%LOCALAPPDATA%\JobProgram\          <- user data. OUTSIDE the swap zone.
    tracker.db  secrets/  projects/  preferences.json  cache/  logs/  output/
```

`%LOCALAPPDATA%\JobProgram` is _already_ the existing fallback path in `config.py:78`, so this
is not a new location — it becomes the only location.

## Hard constraints this design must not violate

- **A folder swap must never touch user data.** Enforced by moving the anchor before any
  updater code lands. This is the ordering constraint of the whole plan.
- **Windows locks a running exe.** Never overwrite in place. Velopack's `Update.exe` waits for
  our PID to exit, then swaps, then relaunches. We use `wait_exit_then_apply_updates` so the
  HTTP response flushes before we exit.
- **`PRIVACY.md:41-45` promises no unprompted outbound update call.** Every step stays
  user-clicked. No `set_auto_apply_on_startup`.
- **Classic Tk mode has zero update surface** today. It gets one, or Tk testers are stranded.
- **`--daily` runs as a separate scheduled process** from the same install. Apply must refuse
  while one is live.
- **The exe is unsigned.** Every update is a fresh zero-reputation binary. Accepted for the
  closed cohort; `_sign_exe` stays a stub behind a CI secret.

## Migration for existing zip testers — no new code

The app already ships backup/restore (`src/ui/help_core.py` `make_backup()` / restore, exposed
in the web Settings menu). The documented path is therefore:

> Old zip app → Settings → **Download backup** → install `Setup.exe` → Settings → **Restore
> from backup**.

No import wizard, no path guessing, no data-loss window. Zero engineering.

## Work items

### A. Data anchor (must land first, alone, tested)

1. `src/config.py::_get_user_data_dir` — frozen → `%LOCALAPPDATA%\JobProgram` unconditionally.
   Drop the `<exe>/data` branch. `JOBPROGRAM_DATA` override and the dev path are unchanged.
2. `_dir_writable` becomes unused → delete it (only caller was the dropped branch).
3. `src/build_package.py` — stop seeding `data/` next to the exe. Runtime `userdata.bootstrap()`
   already scaffolds on first launch from **all four** entry points (`gui.py:147`,
   `webui/__main__.py:179`, `daily_run.py:275`, `mcp_server.py:442`), so nothing regresses.
4. Tests: frozen-simulation asserts the anchor ignores a writable `<exe>/data`.

### B. Updater core

5. `src/updater.py` (new) — the only module that imports `velopack`. Public surface:
   `is_supported()`, `is_managed()`, `status()`, `check()`, `download_async()`, `progress()`,
   `apply_and_restart(restart_args)`. Every velopack call wrapped: `ImportError` and
   `RuntimeError("not properly installed")` both degrade to "not managed", never a 500.
6. Apply guard: refuse when a `--daily` run holds the lock (new `daily.lock` PID file written by
   the headless daily path, checked here).
7. `src/gui.py::main` — `velopack.App().run()` as the first statement _after_ the
   `ZAGGREGATE_WEB_SMOKE` early-return (before it would corrupt the smoke's stdout JSON), guarded
   by `sys.frozen`, wrapped in `try/except Exception: pass`.

### C. Surfaces

8. `src/webui/api/meta.py` — extend `update-check` with `managed`; add `update/download`,
   `update/progress`, `update/apply`. All `@require_local_origin`. When not managed, behaviour is
   byte-identical to today (existing `tests/webui/test_meta.py` must stay green untouched).
9. `src/webui/frontend/` — `endpoints.ts` + `settings-menu.tsx`: progress bar, then an explicit
   **"Restart to finish updating"** confirm. Link-out remains the fallback when unmanaged.
10. `src/ui/help.py` — a "Check for Updates…" item in the classic Tk Help menu.

### D. Packaging + CI

11. `requirements.txt` — add `velopack==1.2.0`. (Runtime-required, build-required → **pin it**,
    per the v1.0.0 pywebview CI trap in `docs/handoffs/handoff_20260707_session44.md`.)
12. `src/build_package.py --velopack` — emit `dist/JobProgram/` as the vpk staging dir and print
    the exact `vpk pack` argv (single source of truth for the version/packId).
13. `.github/workflows/release.yml` — after the existing build+verify:
    `dotnet tool install -g vpk` → `vpk pack --packId Zaggregate --packVersion <APP_VERSION>
--packDir dist/JobProgram --mainExe JobProgram.exe --channel <win|beta>` → upload
    `Releases/*` (Setup.exe, `.nupkg`, `RELEASES-<channel>`) as Release assets alongside the
    existing zip + SHA256SUMS.
    - Stable tag `v1.0.3` → pack **both** `win` and `beta` channels (same bits), publish `--latest`.
      Packing beta too keeps the beta feed monotonic so a beta tester never sees an empty channel
      when stable overtakes beta.
    - Pre-release tag `v1.0.3-beta1` → pack `beta` only, publish `--prerelease`.
14. `_sign_exe` stays `NotImplementedError`; CI gains a no-op signing step gated on a
    `SIGNING_CERT` secret that does not exist yet. Turning signing on later = populate the secret.

### E. Docs

15. `PRIVACY.md` — the update section now covers "download + apply", still user-clicked.
16. `docs/BETA-WALKTHROUGH.md` — new install/update flow + the backup→restore migration.
17. `brain/project-status.md`, `_index.md`, `docs/handoffs/` — per the S34 brain-update rule.

## What is NOT verifiable on this machine

`vpk pack` needs the .NET SDK; this desktop has runtime 5.0.15 only. The Python side (A, B, C)
is fully unit-testable and will be tested. The **D leg proves itself on the first pushed tag**,
and the first real apply must be smoke-tested on a VM or the spare laptop before any tester sees
it. That is a stated gap, not a silent one.

## Rollback

`UpdateOptions.AllowVersionDowngrade=True` + delete the bad release's assets from GitHub → the
next check offers the previous version and Velopack applies it as a full (non-delta) update.
Unlike TUF, Velopack has no anti-rollback state to fight. This is why the tufup design was killed.
