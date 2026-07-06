# Plan S40 — AI-first setup: "paste one reply, start searching" (2026-07-06)

Approved by Alex 2026-07-06 (design presented in-session; he chose: combined
config+seeding prompt · AI path IS the first wizard screen · auto-start first
quick search on apply · surfaces = web wizard + Guide + Search tab; tk untouched).

**Goal:** the copy-prompt → any-AI → paste-reply loop is THE setup path. One
paste = search config + starter company registry + first quick search running,
zero further clicks.

## Non-negotiables (both builders)

- `py -3.12` only. Full `py -3.12 -m pytest` green BEFORE each commit. Never push.
- No scoring/filter changes (byte-parity rule). tk wizard untouched.
- Existing routes `/api/ai-setup/prompt`, `/api/ai-setup/apply`,
  `/api/companies/seed-prompt`, `/api/companies/seed-apply` keep working (compat).
- Inclusion over precision: a reply with a config block but junk/no seeds must
  still apply cleanly (config-only degrade, never block).
- Commit per builder, conventional-commit style, Co-Authored-By Claude line.

## B1 — backend (ui/ai_setup.py, webui/api/onboarding.py, webui/api/runs.py, tests)

1. `build_full_setup_prompt() -> str` in ui/ai_setup.py: the existing
   `build_setup_prompt()` contract (SAME json block, refactor to share the body
   text — do not fork the vocabulary) PLUS a second requested block:
   a fenced ```seeds block of `Company Name | https://careers-page-url` lines
   (≤25) for the user's field+metro — wording lifted from `build_seed_prompt`
   (careers PAGE not homepage/slug; unsure → main website; app verifies).
   Order: json block first, seeds block second.
2. `split_full_reply(text) -> tuple[str, str]`: (config_json_text, seed_lines_text).
   Config via the existing `_best_config_object` path; seed lines = lines inside
   a ```seeds fence if present, else any `name | http…` shaped lines OUTSIDE the
   chosen JSON block. Never throws; missing section → "".
3. `POST /api/ai-setup/apply-full` (onboarding_bp, @require_local_origin), body
   `{text, autorun?: true}`:
   - `apply_setup(config_text)` sync. No config block → same 400 message
     contract as /ai-setup/apply. (Seeds alone are NOT enough to onboard.)
   - Parse seed lines (count only, no probe inline — probing is phase 1 of the job).
   - `autorun:true` (default): start ONE exclusive JobRunner job
     `("first_run", slug)`: phase 1 = if seed lines: `apply_seed_lines(seed_text,
industry=<applied field>, probe=True)` with handle.log progress lines
     (log start, per-outcome counts, done); phase 2 = the daily ingest exactly as
     `start_daily_run` does it — REFACTOR the first-run quick-pass (B1
     last_run.json check → max_pages=1) + `_daily_ingest` call into a shared
     helper in webui/api/runs.py that both routes use; no duplication.
   - JobConflict → still return ok with `job_id: null` +
     `job_error: "another run is in progress"`. `autorun:false` → no job.
   - Response `{ok, applied:{…same as /ai-setup/apply…}, seed_count, job_id,
job_error?}`.
4. Tests (tests/ui/test_ai_setup.py + tests/webui/test_onboarding.py):
   full-prompt contains both contracts; splitter (config+seeds / config-only /
   seeds-only / junk / seeds-fence-missing / pipe-chars-inside-JSON not seeds);
   apply-full route: sync apply + job started (monkeypatch runner + ingest),
   400 no-config, origin gate 403s, autorun:false no job, conflict shape,
   quick-pass helper unit test. Route-audit meta-test must stay green
   (mutating route is origin-gated).

## B2 — frontend (after B1 merges; contract above is binding)

1. Extract shared `AiSetupPanes` from `components/ai-setup-dialog.tsx`
   (copy/paste/applied panes + state machine) with props: `promptKind:
"full"`, `autorun: boolean`, `onApplied(res)`. Dialog becomes a thin wrapper.
2. Wizard AI-first landing: `wizard-steps.ts` — replace `welcome` + `ai-offer`
   with one `start` step (label "Set up"). New `StartStep.tsx`: hero ("Fastest
   setup: let your AI fill this out"), inline AiSetupPanes (NOT a dialog),
   quiet link "I'd rather fill it in myself →" → `roles`. Manual steps unchanged.
   Delete WelcomeStep/AiOfferStep (and their step tests) — update rail logic.
3. On apply (wizard): res.job_id → close takeover, navigate to Inbox with the
   run console open on that job (reuse the existing daily-run console attach
   mechanism — sessionStorage handoff like Discover's Search-now if that's the
   established pattern; do NOT invent a new one). job_id null → old behavior
   (finish/close) + toast the job_error if present.
4. Search tab: "Set up with AI" header button → AiSetupDialog with
   `promptKind:"full"`, `autorun:false`; applied pane gains "Run search now"
   (fires the existing start-daily-run mutation) next to Done.
5. Guide: setup section re-led with the 3-step round-trip (copy → paste into
   your AI above résumé + one sentence → paste reply back = config + starter
   companies + first search). Keys/manual demoted below.
6. client.ts: `aiSetupFullPrompt()`, `applyAiSetupFull(text, autorun)` typed
   (`ApplyAiSetupFullResponse` w/ seed_count/job_id/job_error); queries.ts hook.
7. Vitest: StartStep renders panes + manual link routes; apply→navigate w/ job;
   dialog autorun:false shows Run-now; steps-rail logic updated. `npm test` +
   `npm run build` green (tsc -b catches unused). Rebuild bundle into webui/static.

## Verify (orchestrator, after B2)

Full pytest + vitest + live UI click-through (preview server; receiver stopped
during, restarted after) + review fleet (separate task).
