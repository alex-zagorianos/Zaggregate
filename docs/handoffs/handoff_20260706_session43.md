# Handoff — Session 43 (2026-07-06 evening) — src/ LAYOUT RESTRUCTURE, live on the public repo

Same conversation as S39–S42. Alex approved the full restructure via
option-question; goal: repo root = README/LICENSE/docs + one source folder;
exes stay in GitHub Releases. **Committed `3abf007`, private origin pushed,
public Zaggregate fast-forwarded `22c2dc6..d56ca51`.**

## What moved

489-file commit: 480 pure `git mv` renames (100% similarity — history follows
with `git log --follow`). Into `src/`: all 24 root modules, the 11 code
packages (incl. webui/frontend), legacy/, scripts/, browser_ext/, claude-code/,
packaging/, data_static/, data_templates/, companies.json, app.spec. Root
keeps: README/LICENSE/EULA/PRIVACY/CLAUDE.md/_index.md, requirements*,
.env.example, config.example.json, the two user-facing .bats, docs/, brain/,
tests/, .claude/ + every gitignored user/build dir.

## The keystone (read this before touching config.py)

`config.py`'s two dev anchors DIVERGED on purpose:

- `_get_data_dir()` stays `Path(__file__).parent` → **src/** (bundle assets
  moved with the code).
- `_get_user_data_dir()` became `parent.parent` → **repo root** (projects/,
  output/, .env, preferences, tracker dbs did NOT move). `load_dotenv` is now
  anchored to the repo-root `.env` in dev.

Consequence: the tracked `src/companies.json` is the SEED; the app seeds a
USER copy at the repo root on first run (now gitignored as `/companies.json`).
Registry improvements that should ship must be made in `src/companies.json`.

## Everything re-pointed

- `build_package.py`: ROOT(repo)/SRC(code) split; PyInstaller runs
  `src/app.spec` with cwd=repo → dist/, build/, production/ unchanged at root;
  app.spec needed ZERO datas edits (spec-relative paths).
- **4 scheduled lanes re-registered**: `py src\daily_run.py --project <slug>`
  (verified in Task Scheduler; db-path resolution proven against the real
  applied-ai project).
- run_servers.bat (cd src first), setup_schedule.bat, in-app "daily updates"
  flow (delegates to the fixed setup_schedule.py — single command builder).
- Dev receiver runs from src/ (launch bat updated); live-verified serving
  Alex's REAL project list — the user-data anchor proof.
- claude-code channel: `.mcp.json` → `src/mcp_server.py` + packaged-install
  note (clone the repo; `JOBPROGRAM_DATA` points the server at app data).
- tests/conftest inserts src/; 6 path-reading tests re-anchored.
- Docs: README (Download link + quick start + repo layout), ARCHITECTURE
  module map, BUILD, USER-GUIDE, CLAUDE.md.

## Review fleet catches (fixed pre-push)

1. **.gitignore was silently stale** — root-anchored patterns
   (legacy PII scratch incl. dad's config, frontend node_modules, coverage
   reach, the *.pem and app.spec negation exceptions) no longer matched their
   moved targets; a `git add -A` could have staged personal files. All
   re-pointed at src/ and empirically re-verified with `git check-ignore`.
2. **Packaged claude-code channel dead-end** — the zip never shipped
   mcp_server.py source; README now tells packaged users to clone the repo.

## Verification ladder (all green)

pytest 3,248 passed / 2 skipped · vitest 237 · exe rebuilt from `src/app.spec`

- frozen-smoked via the Web launcher (sole 5002 listener) · package zip layout
  byte-identical (1,430 entries, PII re-scanned clean) · daily_run fast-fail +
  db-path checks · receiver live with real data · graphify rebuilt.

## S43b addendum — in-repo Executables/ download folder (`2bc4af4`, public `2cba1ec`)

Repo root gained `Executables/`: the single ready-to-run zip (46.5MB) +
SHA256SUMS + a 3-step plain-English README. A GitHub folder can't be
downloaded by itself, so the folder carries the one-click zip — and it works
BEFORE any GitHub Release exists (the README's Releases links 404 until Alex
runs `gh auth login` + release.ps1). Self-maintaining:
`build_package.zip_package()` now ends with `refresh_executables()`
(version-stamped README regenerated, old-version zips dropped; kit test pins
it). Root README download links point at the folder; raw download URL
live-verified (HTTP 206). Trade-off on record: ~46MB per version enters git
history — slim to a pointer README once the Releases pipeline is live (the
republish rewrite can drop the blobs).

## Notes

- The S43 plan doc (`brain/plan-2026-07-06-src-layout.md`) is purged from the
  public history by path (names the private dad files) — runbook purge list
  updated; public HEAD = private HEAD minus 5 files.
- dist/ zip + production/ reassembled post-docs; release.ps1 flow unchanged
  (v1.0.0 release creation still awaits `gh auth login`).
