# Deep Testing Plan — Web-UI Migration (S36, 2026-07-04)

Purpose: prove the migration didn't break anything and that the new surface is
sound, before scenario testing. Executed by agents; every failure becomes a
finding with severity + fix disposition. Baseline entering: 2858 passed / 1
skipped Python, ~151 vitest, typecheck+build clean.

## D1 — Regression matrix (the old world still works)

- D1.1 Full Python suite, fresh run, exact counts (`py -3.12 -m pytest -q`).
- D1.2 Order-dependence: `tests/webui` alone; `tests/ui tests/webui` in one
  invocation; `tests/webui tests/ui` reversed. Counts identical.
- D1.3 tk GUI import + construction smoke: `import gui` exposes all compat
  names (29+ from the split eras + ApplyQueueTab); no webui import leaks tk
  (subprocess isolation test exists — re-run it explicitly).
- D1.4 Browser-extension receiver: full `tests/test_browser_receiver*` set +
  `/clip`, `/harvest`, `/track` behavior unchanged (no webui route shadowing);
  popup.js has no dangling :5001 references.
- D1.5 MCP server: `mcp_server.py` tool surface untouched by the migration —
  its tests green; it still pins-once at startup.

## D2 — Scoring/engine parity (the sacred constraint)

- D2.1 Daily-run parity: run the existing eng-profile parity harness (S35b's
  25-job harness — locate under tests/ or scripts/) OR construct equivalent:
  score a fixed job set through `match.scorer.score_jobs` pre/post-migration
  code paths — must be byte-identical (migration never touched match/, ranker,
  hard_gate; prove it: `git diff 6be40b9..HEAD --stat -- match/ ranker.py
preferences.py` should show ZERO scoring-logic lines; rescore levers intact).
- D2.2 `daily_run_core.run_ingest` extraction equivalence: gui.run_daily_ingest
  is a thin re-export; tk tests that patch it still intercept web-path calls.

## D3 — API contract sweep (the new world is sound)

- D3.1 Route inventory audit (meta-test, ADD to tests/webui): enumerate
  `app.url_map`; assert EVERY mutating (POST/PUT/PATCH/DELETE) /api/* route is
  origin-gated (introspectable decorator marker — add one if the decorator
  leaves none) except documented exceptions; assert every route returns the
  {ok} envelope on error (spot 404/400 responses are JSON, not HTML).
- D3.2 Security regression: header-less mutating → 403 (sample across every
  api module); foreign-Origin → 403; traversal attempts on ALL download routes
  (export, queue, resume, backup, /app static); test hooks unreachable without
  TESTING+pytest; no raw secret in any keys/test/probe response (grep response
  bodies in tests for seeded key material).
- D3.3 SSE: line/done/error framing; late subscriber replay; cancel semantics;
  exclusive-mutex 409s (daily vs search vs build-list vs seed-metro vs restore).
- D3.4 Serializer robustness: malformed extras, bytes, huge descriptions.

## D4 — Frontend verification

- D4.1 `tsc --noEmit`, `vite build`, `vitest run` — clean/counts recorded.
- D4.2 Token drift: `py -3.12 scripts/gen_web_tokens.py --check` (or the drift
  test); committed static freshness: index.html's hashed assets exist and match
  the latest build of src (rebuild → git diff webui/static must be empty).
- D4.3 Bundle hygiene: no external URLs (offline guarantee), no sourcemaps, no
  absolute local paths; size recorded.

## D5 — Frozen exe functional pass

- D5.1 Rebuild: `py -3.12 -m PyInstaller app.spec --noconfirm` clean.
- D5.2 Web smoke hook (ZAGGREGATE_WEB_SMOKE=1, port 5003): /app 200 + status ok.
- D5.3 Extended frozen probes vs the running frozen exe: /api/toppicks,
  /api/guide, /api/settings/keys (masked), /api/onboarding, /app/assets/* one
  hashed asset — all 200/shape-correct (catches frozen-only import/data gaps
  in the NEW Phase 3-5 modules; collect_submodules should cover, prove it).
- D5.4 `--web` flag: frozen exe with --web + monkeypatched-equivalent (env var
  to suppress browser-open if needed) starts and serves; document behavior.
- D5.5 tk GUI still launches from the frozen exe (spawn, wait for window class
  or a --daily no-op path as proxy if headless; document what was possible).

## D6 — Performance sanity

- D6.1 Seed 2,000 synthetic inbox rows in a tmp project; GET /api/inbox
  (unfiltered + filtered + q=) server timing < 1.5s each; response size sane;
  windowed UI target noted (client-side already windows at 100).
- D6.2 SSE under a chatty job (2,000 lines): memory bounded (deque cap),
  stream completes.

## D7 — Data-safety spot checks

- D7.1 Backup zip: contains expected trees, downloads, restore round-trips a
  tmp data dir byte-faithfully; zip-slip refused; restore 409 during a run
  (already tested — re-run).
- D7.2 Demo rows: never mutate real DB (track 404s, dismiss no-ops server-side).
- D7.3 Project switch mid-idle: POST /api/project flips registry active; no
  pin leaks (workspace.pinned() None after every job — assert in tests).

Execution: parallel agents per section, findings consolidated, fix pass for
anything actionable, re-verify. Deliverable: results appended to this doc +
fixes committed.
