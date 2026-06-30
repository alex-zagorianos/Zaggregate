# Handoff — Session 15 (2026-06-22, Opus 4.8) — Top Picks: full-inbox AI snapshot → ranked top-X

> Make the **whole relevant set trivially consumable by an AI**, let the AI judge relevance
> itself and write back a **ranked top-X shortlist** that surfaces in a new GUI **Top Picks**
> tab. Built **inline** (TDD, brainstorm→spec→plan→approve). **Committed LOCAL, push HELD**
> (awaiting Alex's `py gui.py` eyeball). Output mode: TERSE.

## TL;DR

- Rank rides in each inbox row's existing **`extras` JSON** (`rank` + `rec_batch`) — **NO DB
  migration**, no `SCHEMA_VERSION` bump. Latest `rec_batch` wins, so a fresh AI run supersedes
  the prior shortlist.
- New GUI **Top Picks** tab (best-first, Show-top-N, Track/Dismiss/Open, themed) between Inbox
  and Search. Export-for-AI gained a scope toggle (defaults **entire inbox**).
- `mcp` `list_inbox(limit=0)` now returns the **whole inbox** + `rank` + `job_key`;
  `set_fit_scores` accepts an optional `rank`. `find-jobs` skill rewritten to snapshot→rank.
- Tests **522 → 553** (+16 Top Picks, +15 from the location-filter commit that also landed this
  session). `py -m pytest -q`: **552 passed, 1 skipped** (display-guarded; transient multi-Tk).
- **NOT pushed.** Last pushed HEAD = `228b013`; **5 local commits** sit on top.

## Two locked design decisions (AskUserQuestion)

1. **Both channels** — full relevant set consumable by an AI **AND** a GUI Top Picks view of the
   AI's ranked shortlist.
2. **Relevant set = the full inbox; the AI judges relevance itself** (not the filtered view, not
   a hardcoded gate).
3. **One full snapshot, then rank** (no accumulate-by-batch loop).

Approach **A** chosen over B: reuse `extras` JSON + the rerank `new_rank` column. Achieves top-X
with zero new DB surface. Spec `brain/spec-2026-06-22-top-picks-recommendation-design.md`; plan
`brain/plan-2026-06-22-top-picks-recommendation.md`.

## What shipped (7 TDD tasks)

- **`tracker/db.py`** — `inbox_merge_extras(inbox_id, patch)`: key-preserving merge into the
  `extras` blob (a rank-only write keeps an existing `tags`); tolerant of missing/non-dict blobs.
- **`tracker/service.py`** — one place defines the extras shape:
  `new_rec_batch()` (UTC isoformat, second precision), `rank_patch(rank, batch, tags=None)`,
  `read_rank(row)`, and `top_picks(limit=10)` (keeps only `rank>=1` rows from the **latest**
  `rec_batch`, sorted best-first, capped at `limit`; `limit<=0` = all). `apply_rerank_scores`
  untouched.
- **`rerank/import_.py`** — `_extras_for(rec, batch, service)` maps CSV `new_rank`→`rank` via
  `service.rank_patch` + one per-call `rec_batch`; tags-only fallback. `apply_rerank_scores`
  write path unchanged.
- **`rerank/schema.py`** — `build_prompt` `new_rank` bullet now explains it as the Top Picks
  shortlist signal (rank 1..X, blank = not on the shortlist). `RERANK_CSV_COLUMNS` frozen.
- **`mcp_server.py`** — `list_inbox(limit=0, unscored_only=false)` returns the WHOLE inbox, each
  row + `rank`(`service.read_rank`) + `job_key`(`_job_key_for_row`); `set_fit_scores` computes one
  `batch` and, when a row carries `rank`, `db.inbox_merge_extras(iid, service.rank_patch(...))`
  (no rank → no merge, `applied` count preserved).
- **`gui.py`** — new **`TopPicksTab`** (columns rank/fit/title/company/location/why/score/source;
  `_topn` StringVar default "10", values [10,15,20,25,50,All]; `_n()`→0 for "All"; `refresh()`
  reads `tracker_service.top_picks`, empty-state hint; Track/Dismiss/Open). Wired into
  `_build_tabs`/`_rebuild_tabs`/`_on_tab_changed` between Inbox and Search. InboxTab gained an
  Export scope combobox ("Entire inbox" default / "Current view") feeding `_export_for_ai`.
- **`claude-code/skills/find-jobs/SKILL.md`** — workflow rewritten: one `list_inbox(limit=0)`
  snapshot → judge & rank all → choose top X → `set_fit_scores` with `rank` → present + point at
  the Top Picks tab.

## Tests (+16 this feature → 553 total)

- `tests/test_top_picks.py` (6, `tmp_db` monkeypatches `db.DB_PATH`), `tests/ui/test_export_scope.py`
  (1), `tests/ui/test_top_picks_tab.py` (3). Extended: `tests/rerank/test_import.py` (+2),
  `tests/rerank/test_service_rerank.py` (+1 end-to-end import→top_picks), `tests/test_mcp_server.py`
  (+2), `tests/rerank/test_schema.py` (+1). Back-compat verified: `list_inbox` defaults, the
  `apply_rerank_scores`/export/existing-mcp paths all stay green.

## Git — 5 local commits, push HELD

```
afa088f docs(skill): find-jobs snapshots whole inbox then ranks a top-X
806bda3 feat: Top Picks — full-inbox AI snapshot + ranked top-X shortlist
36b223e feat(ui): local-focus Inbox filter + dark-mode menu/dropdown fixes   (S15 also)
532811a feat(ui): light/dark mode switch + in-depth "use it with AI" guide   (S14)
a716f3f feat(ui): crisp clean-light theme + in-app Guide/Help + Setup wizard  (S14)
```

Last pushed HEAD = `228b013`. Repo private (`git@github.com:alex-zagorianos/Job-Program.git`).
`afa088f` was amended once to drop a UTF-8 BOM from PowerShell `Out-File`.

## 🟡 Needs Alex (machine / decision only)

1. **Eyeball `py gui.py`** — light **and** dark, the new **Top Picks** tab — then `git push` the
   5 local commits. Top Picks is empty until an AI writes ranks (run `find-jobs`, or
   `set_fit_scores` with `rank`).
2. Carry-over: live coverage baseline (network run); `py build_package.py` exe build + GUI launch;
   docx title-line decision; WS-3 `batch_id`; per-project scheduler; company remove/edit UI;
   delete `tracker.db.bak`.

## Pointers

- Brain: `brain/project-status.md` ("Session 15" + `## Git` updated). `_index.md` status line +
  Open list updated. Memory: `project-job-search` (Session 15 paragraph).
- DB schema untouched: the 0–100 scorer, `daily_run` gate, location filter, and `SCHEMA_VERSION`
  are all unchanged — Top Picks is purely additive over `extras`.
