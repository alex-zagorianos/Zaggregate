# Phase 2 — Wide-net + AI Ranking (Implementation Plan)

> **For agentic workers:** TDD; branch `feat/phase2-ranking`. Reuses the existing
> `claude_bridge` fit machinery (build_fit_prompt / parse_fit_response / fit_token /
> match_fit_to_jobs) rather than duplicating it.

**Goal:** Rank/sort pre-scored jobs against the user's `preferences.md` profile, via one
request shared across three routes (clipboard bridge default · API auto if a key exists ·
MCP/Claude-Code), with the cheap `preferences.hard_gate` applied first.

**Architecture:** New `ranker.py` orchestrates: `build_profile` (preferences.md "what I want" +
condensed experience "what I can do") → `build_request` (= `bridge.build_fit_prompt` with that
profile) → `parse_response` (= `bridge.parse_fit_response` + `match_fit_to_jobs`). `rank_via_api`
runs the same prompt+parser through the API; `gate` applies `preferences.hard_gate`. Wide-net = a
looser-keyword fetch mode (CLI `--wide`).

**Tech Stack:** Python 3.12 (`py`), pytest, anthropic (already a dep, mocked in tests).

## Global Constraints

- `py`; commit trailers; no push (held). Suite ≥308 baseline; each task adds tests.
- One prompt, one parser — bridge / API / MCP must not diverge.
- Hard-gate before AI (never spend a call on a job that fails a hard constraint).

## File structure

- Create `ranker.py` (orchestration), `tests/test_ranker.py`.
- (Wiring) Modify `gui.py` fit path + `search/cli.py`/`daily_run.py` to use `ranker` + a `--wide`
  mode — kept thin; the testable value is `ranker.py`.

## Tasks

1. **`ranker.build_profile` / `build_request`** — combine preferences + experience into the ranking
   profile and build the shared prompt. Test: prompt contains the preferences text + the job fields.
2. **`ranker.parse_response`** — reuse `bridge.parse_fit_response` + `match_fit_to_jobs` → ordered
   `[(job, fit, rationale)]`. Test: tokens map scores to the right jobs.
3. **API auto-route** — `api_key()` (env `ANTHROPIC_API_KEY` › `secrets/anthropic_key` file),
   `has_api_key()`, `rank_via_api()` (same prompt+parser). Tests: key precedence; mocked API call.
4. **`gate`** — apply `preferences.hard_gate` before ranking. Test: hard filter drops violators.
5. **Wiring (thin)** — GUI fit path uses `ranker.build_request` (preferences profile) + an API
   auto-rank when a key exists; CLI `--wide` loosens keyword gating; `daily_run` hard-gates the inbox.
   py_compile + targeted checks (GUI not headlessly testable).

## Done criteria

`ranker` builds/parses one preference-anchored request across bridge+API, hard-gates first, and is
wired into at least one entry point. Suite green. Then Phase 3 (exe + wizard).
