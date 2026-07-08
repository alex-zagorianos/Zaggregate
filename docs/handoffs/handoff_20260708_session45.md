# Handoff — Session 45 (2026-07-08) — Auto-update phase 2 (Velopack) BUILT

Alex: "Plan what is needed to get it to the point I can hand this off to beta
testers and when I push updates theirs updates as well" → "Once the plan is in
implement" → mid-build: "consider --classic legacy and stop updating it and
remove it from shipments."

**Status: implemented, full suite green, NOT pushed (push held per repo rule).**
This is the first release that self-updates. Plan: [[plan-2026-07-08-velopack-auto-update]].

## What shipped

Velopack (official PyPI `velopack` 1.2.0 SDK, verified real + API-probed) wired in
as the update engine. Every velopack fact below was checked against the actual wheel
in a throwaway venv, not taken from docs — three design assumptions were wrong and
got corrected:

- `App().run()` outside a Velopack install is a **safe no-op** (logs NotInstalled).
- `UpdateManager(...)` **raises `RuntimeError("...not properly installed")`** outside
  an install → that IS the "am I managed?" detector; no marker file.
- `UpdateOptions(bool, int, chan=None)` takes **2 required positional args** (the
  design agents assumed kwargs — would have been a build break).

### Files

- **`src/config.py`** — frozen `USER_DATA_DIR` is now **always `%LOCALAPPDATA%\JobProgram`**
  (dropped the `<exe>/data` branch + `_dir_writable`). This is THE load-bearing change:
  Velopack swaps the exe's folder wholesale on every update, so data beside the exe would
  be destroyed. **APP_VERSION 1.0.2 → 1.0.3.**
- **`src/updater.py`** (new, the only velopack importer) — `is_managed/status/check/
download_async/progress/apply_and_restart/restart_args_for_current_process`. Degradation
  contract: dev checkout / plain zip / missing wheel → every call benign, never raises into
  Flask. Downgrade enabled (rollback), `prerelease=True` (beta feed), daily-run interlock.
- **`src/webui/api/meta.py`** — `update-check` gains `managed` (SDK is source of truth when
  managed, else v1.0.2 GitHub-tag behaviour verbatim); new `update/download`, `update/progress`,
  `update/apply` (apply returns 200 then `os._exit` on a 0.5s daemon timer so Velopack's
  Update.exe swaps AFTER the response flushes).
- **`src/gui.py`** — `velopack.App().run()` first thing after the web-smoke early-return
  (frozen-only, swallowed); `--daily` now holds `daily.lock` for the run; **`--classic`
  retired from the frozen exe** (accepted-and-ignored → opens desktop, scrubbed from argv).
- **`src/build_package.py`** — no more seeded `data/` beside the exe (runtime
  `userdata.bootstrap()` covers all 4 entry points); `vpk_pack_argv()` + `--velopack [--run]
--channel {win,beta} --pack-version`; CHANGES/README/launcher text de-classic'd.
- **`src/app.spec`** — bundles `velopack` + its native `.pyd` (`collect_dynamic_libs`);
  `ZAGGREGATE_REQUIRE_VELOPACK=1` makes a release build fail loudly if the wheel is absent.
- **`requirements.txt`** — `velopack==1.2.0` pinned (build-required; keep in lockstep with the
  `vpk` version in CI).
- **`.github/workflows/release.yml`** — installs `vpk` 1.2.0, packs the channel(s)
  (stable tag → win+beta same bits; `-betaN` tag → beta only at the prerelease version),
  publishes **Setup.exe + feed** (no more zip on releases).
- **Frontend** — `client.ts` types + endpoints, `lib/update-flow.ts` (pure, tested) +
  `settings-menu.tsx` (check → Download w/ progress bar → "Restart to finish").
- **Docs** — PRIVACY.md (download+apply, still click-only), BETA-WALKTHROUGH.md (Setup.exe
  - backup→restore migration), USER-GUIDE.md.

### Decisions locked (Alex, this session)

Setup.exe only (drop portable zip) · click-check→click-apply (no PRIVACY rewrite of the
promise) · dedicated **beta channel** · ship **unsigned** to the closed cohort (CI signing
step stubbed behind a not-yet-existing `SIGNING_CERT` secret) · **--classic retired** from
shipments (Tk code stays for dev `py src\gui.py`).

## Verification

- **Python 3302 passed / 1 skipped.** New: `tests/test_updater.py` (30), `tests/webui/
test_meta_update.py`, `tests/test_velopack_packaging.py`; `test_userdata.py` +
  `test_launcher.py` updated for the new anchor + retired flag.
- **Frontend: tsc clean (tsconfig.app.json), vitest 257 passed** (incl. 20 update-flow).
- **Real-wheel smoke:** installed `velopack==1.2.0` into the 3.12 env and drove `updater.py`
  through it from a non-install → `supported:True, managed:False`, real `RuntimeError` →
  `NotManaged`. Contract holds against the real SDK, not just fakes.
- **NOT verified (can't on this box — no .NET SDK):** the actual `vpk pack`, the real
  Setup.exe install, and the running-exe self-swap. **These prove themselves on the first
  pushed tag and MUST be smoke-tested on a VM / the spare laptop before any tester sees a
  real update.** Stated gap, not silent.

## To ship (Alex)

1. Decide the version is right (currently 1.0.3) — CI tag guard requires `tag == v$APP_VERSION`.
2. Push, tag `v1.0.3` (or `v1.0.3-beta1` first for a beta-only dry run).
3. On the spare laptop / a clean VM: install Setup.exe, then push a `v1.0.4-beta1`, and
   confirm Settings → Check for updates → Download → Restart lands on the new build with
   data intact. THIS is the gate before wider beta.
4. Existing v1.0.2 zip testers: backup → Setup.exe → restore (documented in BETA-WALKTHROUGH).

## Open / deferred

- Code signing (SmartScreen/Smart App Control) — deferred to before a wider/public cohort;
  CI hook stubbed. SignPath free OSS tier is the likely path (repo is AGPL-3.0 + public).
- `assets.<channel>.json` vs `RELEASES-<channel>` feed-manifest name — CI verify accepts
  either; confirm which vpk 1.2.0 actually emits on the first run.
- The zip pipeline (`zip_package`) is still built locally but no longer published — could be
  removed later once Setup.exe is proven.
