# Handoff — Session 40 (2026-07-06 overnight, Fable 5 orchestrating Opus fleet) — AI-FIRST SETUP shipped + review fleet + searches + cleanup

Alex (going to bed): make the copy-prompt → any-AI → paste-back loop THE focus of
setup ("get searching as quick as possible"), highlight it in setup; Opus
subagents for all implementing + another full backend/frontend efficiency+bugs
review + more testing; test buttons/functionality live; run his + dad's searches
and pick good jobs; remove old test profiles; clean the messy ClaudeWork folder.
Design approved in-session before he left (combined config+seeding prompt · AI
path IS the first wizard screen · auto-start first quick search · web wizard +
Guide + Search tab surfaces).

## 1. S40 feature — "paste one reply, start searching" ✅ (plan: brain/plan-2026-07-06-ai-first-setup.md)

- **B1 backend `868bb33`** (Opus): `build_full_setup_prompt()` (config JSON block
  - ```seeds fence, shared bodies — no forked vocabulary), `split_full_reply()`
    (never raises; seeds from fence or pipe-lines outside the config span),
    **`POST /api/ai-setup/apply-full`** {text, autorun=true} → sync `apply_setup`
    (same 400 contract) + ONE exclusive `first_run` job: phase 1 seed-probe
    (`apply_seed_lines`), phase 2 daily ingest via shared quick-pass helper
    (`runs.resolve_daily_knobs`/`run_daily_ingest` — refactor used by BOTH routes).
    Response {ok, applied, seed_count, job_id, job_error?}. +23 tests.
- **B2 frontend `b0026d0`** (Opus): shared `AiSetupPanes` (dialog = thin wrapper);
  wizard `welcome`+`ai-offer` → ONE `start` landing step (hero + INLINE panes,
  "fill it in myself →" link to the manual steps); apply → close takeover →
  Inbox with the run console attached (sessionStorage handoff
  `lib/inbox-run-handoff.ts`, Discover's pattern); **Search tab "Set up with
  AI"** button (autorun:false + Run-search-now on the applied pane); **Guide
  re-led** with the 3-step round-trip (`ui/help_core.py`); `?full=1` on GET
  /api/ai-setup/prompt (only backend edit). +14 vitest.
- **Live-test fix 1 `4e4a2b0`**: takeover overlays an ALREADY-MOUNTED InboxTab →
  mount-only handoff consume never fired (found by clicking, network log showed
  no /api/jobs call). Fix: consume keyed on `useLocation().key`.
- **Live-test fix 2 `91b8697`**: run finished but Inbox stayed "0 jobs" (API had
  46). Real root cause in SHARED `useJobConsole`: `es.close()` before reconcile
  kills native SSE auto-reconnect → silent detach at the finish boundary; +
  failed path never invalidated. Fix: resubscribe-on-still-running (2s backoff)
  - onFailed invalidation. Benefits Update-now + Search consoles too. +5 vitest.

**Flagship flow verified LIVE 3×** (real browser clicks on the preview server):
paste → apply → takeover closes → console streams seed phase + quick first run →
run done → inbox refetches. One paste = config + starter companies + first
search. Bad paste → human-readable 400 toast, nothing applied.

## 2. Review fleet (Workflow wf_f8e7b96b, 12 Opus agents: 4 find dims → adversarial verify)

**6 confirmed / 2 refuted** (full: brain/review-2026-07-06-s40-fleet-findings.json).
All 6 FIXED by an Opus fix builder in **`23c7efd`** (+4 tests):

1. minor `ui/ai_setup.py` — tolerant-JSON path lost the config span →
   preferences_md "| https://" fragments leaked as bogus seeds (verifier
   REPRODUCED incl. registry pollution). `_span_matches()` retries the span
   compare after trailing-comma stripping.
2. **major `webui/jobs.py`+`tracker/db.py`** — finished job thread never
   released its cached WAL connection → tracker.db LOCKED (the WinError 32 hit
   live tonight deleting a scratch project). New
   `close_current_thread_connection()` called in JobRunner._run finally.
3. **major `scrape/browser_receiver.py`** — harvest() swallowed inbox-scoring
   exceptions → 200 with inboxed:0, silently dropping hand-picked captures. Now
   applog-logged + additive `inbox_error` response field + popup.js surfaces it
   (old extensions unaffected).
4. minor `useJobConsole.ts` — stale terminal handlers after jobId change
   (still real post-91b8697); `alive` guard in effect cleanup.
5. minor `InboxTab.tsx` — memo'd `InboxTableRow` + stable callbacks (100-row
   table no longer fully re-renders on unrelated parent state).
6. minor `ai-setup-dialog.tsx` — prompt-fetch abort guard + copy-timer cleanup.

## 3. Searches + curated picks ✅

All 5 projects ran sequentially overnight (S27-safe; log `logs/s40_runs.log`,
all exit 0). Curated by 2 Opus agents from each project's top rows →
**`output/job-picks-2026-07-06.md`** (gitignored, user data): 11 picks for Alex
(2 Cincinnati-local mech, 3 controls onsite w/ relocation, 4 US-remote
software/AI incl. a 91-fit Emergences Labs AI/Systems role), 8 for dad
(CCH Sr BI remote 91, in-town Great American AVP/VP, Arcadia + Tivity Directors).
Curator observations worth acting on: scorer is title-seniority-blind (Senior
Staff rows outrank new-grad-viable rows); offshore-remote gets `loc 100%`
over-credit vs US-timezone remote; First Resonance "(Ohio)" rows are
geo-mislabeled LA posts duplicated 8×; dad's supply is thin at VP/Director level
(widening levers listed in the picks file).

## 4. Cleanup ✅

- **19 test profiles deleted** (registry + dirs): all gu-_/gs-_/val-_/test-_ +
  health-informatics-test. Remaining 8: controls-cincinnati,
  dad-health-informatics, mechdesign, controls, software, applied-ai, mecheng,
  eng2. Kept+flagged (ambiguous, Alex to rule): `mecheng`, `eng2`, and orphan
  dir `projects/proj-x` (on disk, not in registry).
- **E:\ClaudeWork tidied**: ZAG0005__delegates ×2, 2 stale worktree dirs
  (registered one removed via `git worktree remove` — clean, 0 unique commits),
  JobScout-Test-Run, _jobscout_eval, _jobscout_features_digest.md,
  hermes-test-01-jobapp → all moved to `_archive/zag0005-cleanup-2026-07-06/`
  (archive-not-delete; hard-delete when comfortable). `JobApplications`
  untouched (real application material).

## State at close

- Suite **3,247 passed / 0 failed** (2 pre-existing headless tk skips),
  vitest **237**, build green, bundle current in webui/static.
- Commits tonight (PUSH HELD): S39 `842aee8`+docs, S40 `868bb33`, `b0026d0`,
  `4e4a2b0`, `91b8697`, `23c7efd`, + S40 docs commit.
- Dev receiver restarted detached on 5002 with the final code for the morning.
- `docs/BETA-WALKTHROUGH.md` appeared untracked (not this session's work) —
  left uncommitted for Alex.

## New tech debt (registered here)

- **Residual DB-lock class**: fix #2 releases the JOB thread's cached WAL
  connection deterministically (unit-proven), but LIVE Flask request threads
  that served reads for a project keep their cached connections after the user
  switches away — verified live: deleting a just-switched-away project dir
  still hit WinError 32 until server stop. Harmless today (no in-app
  delete-project), but a future delete/archive feature needs a
  `close_connections_for_path(db)` sweep across the registry. Pairs with the
  S39-noted pin-semantics wart.

## Next / needs Alex

- Production exe repackage (`build_package.py`) — frozen build still pre-S39/S40.
- Scoring tune-ups surfaced by curation (title-seniority weighting, US-remote vs
  global-remote loc credit, cross-board dedup) — ranking changes need his
  byte-parity approval per standing rule.
- Rule on `mecheng` / `eng2` / `proj-x`; hard-delete `_archive/zag0005-cleanup-2026-07-06/` when ready.
- Wave-3 GOs still pending (IMAP status detection + ATS autofill).
