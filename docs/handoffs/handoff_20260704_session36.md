# Handoff — Session 36 (2026-07-04 overnight, Fable 5 + agent fleet) — WEB-UI MIGRATION: ALL PHASES + BOTH TESTING PROGRAMS ✅

Alex approved the tkinter→web migration and went to bed: "structured in-depth
plan → agents implement → review/verify each step → deep testing plan + run →
scenario testing plan + run, hunt errors/inefficiencies/improvements." All of
it landed overnight. **Suite 2478 → 2903 passed / 0 failed** (+425), vitest
151/151, tsc + vite build clean, frozen exe proven. **PUSH HELD** (~40 commits
over `b0cff80`). Master contract: `brain/plan-2026-07-04-webui-migration.md`.

## What shipped (every phase: builder → parallel reviewers → fix → verify)

- **Stack**: Vite + React 19 + TS + Tailwind 4 + shadcn (new-york), served by
  the Flask receiver at `127.0.0.1:5002/app`; JSON API `/api/*` mirrors the
  MCP tool seam; SSE job console; Aegean Paper tokens generated from
  `ui/theme.py` by `scripts/gen_web_tokens.py` (drift-tested, both themes).
- **Phase 0** `c999dec..ff4ea68`: ApplyQueueTab→ui/tab_queue.py (last split);
  `webui/` package (blueprint, strict origin gate — header-less mutating=403,
  JobRunner w/ single-flight + exclusive engine mutex + SSE, _MEIPASS static);
  frontend scaffold + shell (wordmark topbar, tab nav, Ctrl+K palette, offline
  bundle, self-hosted Fraunces/Inter/JBMono); PyInstaller bundling + frozen
  smoke hook (`ZAGGREGATE_WEB_SMOKE`).
- **Phase 1** `d1f28db..95997b0`: Top Picks + Connect Job Sources (masked
  keys, live Test, Adzuna clipboard split). ★Review catch: key-test probe
  leaked raw secrets via HTTPError str() over HTTP → routed through
  `applog.redact()` + regression tests.
- **Phase 2** `c91865e..156929a`: applications/board/rounds/ics API;
  Tracker (chip bar, sortable, quick-status), Board (dnd-kit drag-drop w/
  forward-target enforcement + Move▸ a11y path), JobDialog sheet (offer
  section, rounds+ics, timeline, notes). `ui/kanban_core.py` extraction.
- **Phase 3** `fe3b2f4..9cc1e76` (flagship): Inbox — server-side filter
  parity (`webui/inbox_filters.py`, inclusion-over-precision enforced), tk
  filter semantics ported, detail pane (ghost/ATS/score breakdown), triage
  (t/d/o, bulk+undo), AI export/import/paste/undo-rerank, daily run over the
  JobRunner (pin/unpin discipline, `daily_run_core.py` extraction) + SSE
  console, badges (last-run/reach/keyless/demo). ★Fixes: demo-inbox parity
  (+signed-int route converter), keyboard focus re-homing.
- **Phase 4** `269abb4..4876a7b`: Search (streaming per-source progress,
  cancel, health strip, results triage, add-all), Apply Queue (prompt/paste→
  DOCX, batch-of-5, generate-via-API, mark-applied auto-advance, AI rank),
  Resume (two-step → DOCX downloads). ★Fix: SearchRunConsole fork →
  `useJobConsole` + `JobStatusPill` shared composition; real-parser 400 tests.
- **Phase 5** `cdd653b..56b03f1`: 7-step wizard (on-disk parity w/ tk wizard,
  ★industry auto-derivation restored), AI express lane, Add Companies /
  Build My List / Seed My Area (job console), Guide (editorial serif), backup
  download/restore (zip-slip defended), launcher (`py -m webui` / `--web`),
  :5001 legacy tracker retired (popup.js → :5002 only; tracker/app.py marked
  deprecated, file kept for Alex's delete call). ★Fix: restore 409s during
  exclusive engine jobs.

## Deep testing (`brain/test-plan-2026-07-04-webui-deep.md` + RESULTS inside)

D1–D7 executed by fleet: regression matrix clean, **scoring parity PROVEN**
(`git diff d25247d..HEAD -- match/ ranker.py preferences.py` = zero; lever
harness + 25-job three-revision worktree comparison), route-audit meta-test
landed (every mutating route provably origin-gated), frontend/bundle hygiene +
2k-row perf within budget, frozen-exe functional pass. ★Found+fixed
(`d999e3d`): fresh-install `/api/toppicks`+`/api/inbox` 500 (no inbox table)
→ inbox read paths return empty (touches tracker/db.py READ path — flagged).

## Scenario testing (`brain/test-plan-2026-07-04-webui-scenarios.md` → `brain/findings-2026-07-04-webui-scenarios.md` + addendum)

5 blank-slate journeys through the live web API (isolated data dirs, live
Adzuna): SC1 eng flagship, SC2 nurse routing, SC3 UK, SC4 remote-only, SC5
two-project concurrency. **21 defects (2 critical / 7 major / 12 minor); all
criticals+majors FIXED** (`04f7afa`, `edb9403`): resume bare-"Experience"
heading silently dropped work history; RNJobSite plural-industry gate;
country-skips not in structured badges; remote-only home treated as metro;
global onboarding marker → per-project; switch-under-pin visibility;
cross-project 409 mislabel; restore 413; **restore WAL-sidecar failure —
root cause: `get_conn()` LEAKS open WAL connections (context manager is
transaction-scoped, not connection-scoped) → new
`tracker.db.release_for_restore()` + sidecars excluded from backups.**

## Next-session queue (minors + parity gaps, catalogued in the findings report)

- No web create-project / new-person flow (tk App chrome not yet migrated) —
  the biggest remaining gap; blocks true multi-project web use.
- Web daily run lacks CLI knobs (max-pages/min-score); no per-source
  "why inert for my industry" surface; remote badge component placeholder;
  filter URL/history sync; garbage location_mode fails closed (should fail
  open per inclusion-over-precision); Werkzeug HTML 404 on literal `../`
  download paths (envelope inconsistency; boundary holds).
- tk-tab retirement decision + tracker/app.py deletion = Alex's call (see
  findings report GO/NO-GO).

## Needs Alex

1. Morning eyeball: `http://127.0.0.1:5002/app` (preview server left running)
   or `py -m webui`. Then: push decision (~40 commits held).
2. tracker/db.py was touched twice (read-path empty-fallback `d999e3d`,
   `release_for_restore()` `edb9403`) — scoring untouched, but they're engine
   files; review before push.
3. Carried: reload extension (popup.js :5001 removal), delete junk "T"/"C"
   tracker rows (easy now via web Tracker multi-select), CareerOneStop key,
   val-_/gu-_/gs-* project cleanup, seeded-company-list buildout (pre-empted
   by this migration, still queued).
