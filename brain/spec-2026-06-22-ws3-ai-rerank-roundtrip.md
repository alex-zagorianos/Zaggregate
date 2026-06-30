---
title: "WS-3 — AI Re-rank Round-trip (Design Spec)"
created: 2026-06-22
status: draft — pending spec review, then implementation plan
workstream: 3 of 3
depends_on: [[spec-2026-06-22-ws1-coverage-foundations]]
related: [[research-2026-06-22-job-discovery-playbook]], [[spec-2026-06-22-distributable-product-design]]
---

# WS-3 — AI Re-rank Round-trip

## 1. Context & goal

The app already ranks jobs with AI three ways (clipboard bridge, API auto, MCP) but the pipeline is
**one-way**: search → inbox → local score → manual fit-paste. You want a clean **file round-trip**:
_export the inbox as a Markdown/CSV the user hands to any AI (their own — API key, Claude.ai, Claude
Code, GLM, whatever) alongside a solid prompt; the AI returns a CSV/file; the app imports it and
re-ranks._ This makes the AI tailoring layer **fully customizable and model-agnostic**, which is the
whole point of "leverage a user's own AI."

This rides on WS-1's **`job_key`** as the stable join key (today's only join is the fragile 8-char
`fit_token`). It does **not** depend on WS-2.

## 2. Decisions locked

- **Dual-format export, single carrier:** export both `.md` (human-readable, to read/paste) and
  `.csv` (the round-trip carrier the AI fills in), each row keyed by `job_key`.
- **Tolerant import:** accept the returned **CSV _or_ JSON** (reuse `claude_bridge`'s tolerant
  JSON parse: trailing-comma repair, span guard, echo-back token check).
- **Explicit merge policy:** default **overwrite fit/rank + snapshot prior state for undo**; other
  policies (keep-existing-fit, add-only-new) selectable.
- **Pluggable ranker:** formalize a small `Ranker` interface so "file-based external AI" is a
  first-class route beside bridge/API/MCP — no logic fork (extends `ranker.py`).
- **Versioned prompt template** shipped beside the export so the instructions evolve cleanly.

## 3. Non-goals (YAGNI)

- No auto-apply (unchanged philosophy).
- No new sources / coverage math (WS-1/WS-2).
- No new AI vendor SDKs — the round-trip is **file-based and model-agnostic** by design (the user's
  AI does the thinking; we only read/write files).
- No schema rewrite — add a JSON-blob column for round-trip extras instead of per-dimension migrations.

## 4. Architecture

Extends `ranker.py`, `tracker/service.py`, `tracker/db.py`, `mcp_server.py`, `gui.py`, and adds a
small export/import module.

```
rerank/
  export.py     # inbox rows -> ranking_export.csv + ranking_export.md + prompt.md (versioned)
  import_.py    # parse returned csv|json -> validate job_key join -> merge -> snapshot
  schema.py     # the round-trip column contract + prompt template (versioned)
ranker.py        # ADD Ranker protocol; FileRanker route alongside Bridge/API/MCP
tracker/db.py    # ADD score_history table (audit/undo) + extras JSON-blob column on inbox
mcp_server.py    # ADD export_inbox / import_scores tools (bulk round-trip for Claude Code)
gui.py           # ADD Export / Import buttons + merge-policy picker in InboxTab
```

### 4.1 The round-trip file contract (`rerank/schema.py`)

CSV columns (formula-injection-guarded, reusing `report_csv` safety):

| Column                                          | Direction               | Notes                                              |
| ----------------------------------------------- | ----------------------- | -------------------------------------------------- |
| `job_key`                                       | out (stable)            | the WS-1 join key — **must echo back unchanged**   |
| `title`, `company`, `location`, `salary`, `url` | out (read-only context) | for the AI + human                                 |
| `local_score`, `current_fit`                    | out                     | what the app already thinks                        |
| `description_excerpt`                           | out                     | bounded (e.g. 1200 chars)                          |
| `new_fit`                                       | **in** (0–100)          | the AI's fit score                                 |
| `new_rank`                                      | **in** (optional int)   | explicit ordering within the batch                 |
| `fit_rationale`                                 | **in**                  | one-line why                                       |
| `tags` / `extras`                               | **in** (optional)       | free dimensions → stored in the `extras` JSON blob |

The Markdown export renders the same rows human-readably (table + per-job detail) so the user can
paste into a chat UI; the prompt template tells the AI to **return the CSV with `new_fit`/`new_rank`/
`fit_rationale` filled and `job_key` untouched** (or equivalent JSON).

## 5. Components

### 5.1 `rerank/export.py`

`export_inbox(rows, dir, *, fmt="both") -> paths`. Pulls inbox rows (via `tracker/service.py`),
computes `job_key` (WS-1) per row, writes `ranking_export.csv` + `ranking_export.md` + a copy of the
versioned `prompt.md` to `USER_DATA_DIR/output/rerank/<timestamp>/`. The prompt anchors to
`preferences.md` (verbatim) + the `_FIT_INSTRUCTIONS` scoring guide already in `claude_bridge.py`, so
the file route gives identical guidance to the bridge/API routes.

### 5.2 `rerank/import_.py`

`import_scores(path, *, policy="overwrite") -> ImportResult`. Detect CSV vs JSON; tolerant-parse;
**validate the `job_key` join** (report rows that don't match an inbox row; never silently drop);
clamp `new_fit` to 0–100; apply merge policy; **snapshot prior `fit`/`score`/`extras` to
`score_history`** before writing; write `new_fit`→`fit`, `fit_rationale`→`fit_why`, ranking/extras →
`extras` blob; return a summary (matched / unmatched / updated / skipped). Re-rank the inbox view.

### 5.3 `ranker.py` — `Ranker` protocol

Define `Ranker` with `build_request(rows, prefs) -> Request` and `parse_response(text, rows) ->
Scores`. Refactor the existing bridge/API into `BridgeRanker`/`ApiRanker` implementing it; add
`FileRanker` (export → wait for file → import). MCP route stays the data-tool surface. No behavior
change to existing routes — pure extraction behind the same calls (characterization-tested first).

### 5.4 `tracker/db.py` — audit + extras

- `score_history(id, inbox_id, job_key, old_fit, new_fit, old_score, source, ts)` — every fit/score
  change snapshotted; enables undo + before/after diff. (`status_history` precedent exists.)
- `extras` JSON-blob column on `inbox` — round-trip-supplied dimensions without a migration per
  dimension. Schema bump v2→v3 with a forward migration.
- `inbox_set_fit` writes through `score_history`; add `inbox_undo_last_rerank(scope)`.

### 5.5 MCP bulk tools (`mcp_server.py`)

`export_inbox(dir, fmt)` and `import_scores(path, policy)` so Claude Code can round-trip in bulk (it
currently has `set_fit_scores` per-call but no bulk export). Same `rerank/` functions under the hood.

### 5.6 GUI (`gui.py` InboxTab)

"Export for AI" (writes the trio, opens the folder), "Import scores" (file picker + merge-policy
dropdown + a dry-run preview of matched/unmatched), and "Undo last re-rank". Stale-fit handling: when
`preferences.md` changes, flag fits as stale in the view and offer a one-click re-export.

## 6. Data flow (one round-trip)

Inbox → `export_inbox` → user hands `ranking_export.md`/`.csv` + `prompt.md` to their AI → AI returns
filled CSV/JSON → `import_scores` (validate `job_key`, snapshot, merge) → inbox re-ranked by `new_fit`
/`new_rank` → (optional) `inbox_undo_last_rerank` reverts via `score_history`.

## 7. Error handling & edge cases

- **Mangled CSV** (AI added/removed quotes/commas): tolerant parse + per-row validation; bad rows
  reported, good rows still applied; never corrupt the inbox.
- **`job_key` rewritten/missing** in the return: row goes to an "unmatched" report, not silently
  dropped; offer fuzzy fallback (rapidfuzz on title+company) behind a confirm.
- **Out-of-range `new_fit`:** clamp + warn.
- **Partial return** (AI only scored some): merge only those; leave the rest (policy-dependent).
- **Double import / idempotency:** re-importing the same file is a no-op beyond a new history entry.
- **No AI available:** the export still works (it's just files); ranking falls back to local score,
  clearly labeled (existing behavior).

## 8. Testing strategy

- **Export:** golden-file tests for CSV + MD + prompt (stable columns, formula-injection guard, prompt
  anchors to `preferences.md`).
- **Import:** round-trip property test — export → simulate an AI filling `new_fit`/`new_rank`/
  `rationale` → import → inbox reflects it; CSV **and** JSON inputs; tolerant-parse cases (trailing
  commas, reordered columns, extra/missing rows); `job_key` mismatch handling; clamp; partial.
- **Merge policies:** overwrite vs keep-existing vs add-only behave per spec; `score_history`
  snapshots and `undo` restores exactly.
- **Ranker protocol:** characterization tests pin existing bridge/API behavior _before_ extraction,
  then assert the refactor is behavior-identical.
- **MCP tools:** smoke `export_inbox`/`import_scores` against a temp data folder.
- **DB migration:** v2→v3 (extras + score_history) forward-migrates an existing `tracker.db` without
  loss.
- Suite green; add ~30 tests.

## 9. Risks

- **R1 — `job_key` stability across export/import.** Mitigation: depends on WS-1's deterministic
  `job_key`; the file carries it verbatim and import validates it; fuzzy fallback is opt-in only.
- **R2 — refactoring the ranker breaks the working bridge/API routes.** Mitigation: characterization
  tests first; pure extraction; no behavior change.
- **R3 — users edit the CSV in Excel** (re-typed numbers, locale commas, BOM). Mitigation: tolerant
  parse, locale-agnostic number handling, BOM strip, dry-run preview before commit.
- **R4 — schema migration on a live `tracker.db`.** Mitigation: versioned forward migration + backup
  copy before migrate; tested on a populated fixture DB.

## 10. Done criteria

- `export_inbox` writes `.md` + `.csv` + versioned `prompt.md`, keyed by `job_key`.
- `import_scores` ingests CSV **or** JSON, validates the join, applies a chosen merge policy,
  snapshots to `score_history`, and re-ranks the inbox; `undo` reverts.
- `Ranker` protocol with `FileRanker` added; bridge/API/MCP unchanged in behavior.
- MCP `export_inbox`/`import_scores` tools; GUI export/import/undo controls.
- DB v3 migration; tests green; round-trip verified end-to-end on fixtures.
