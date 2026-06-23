# Spec — Top Picks: view-all-relevant + AI top-X recommendation

- **ZAG:** ZAG0005 (JobScout)
- **Date:** 2026-06-22 (Session 15)
- **Status:** Approved design (pre-plan)
- **Approach:** A — rank-aware re-rank, derive Top Picks (no new table, no migration)

## Problem

Today an AI driving JobScout can only see **20 unscored jobs per batch**
(`list_inbox(limit=20, unscored_only=True)`), and there is **no surface that
presents a ranked shortlist** — the AI writes back `fit` scores, but nothing
shows "here are the top X, best-first, with why." The user wants the tool
arranged so an AI can _easily view all the relevant jobs in one shot_ and then
_recommend a top-X shortlist_ that the user can actually see and act on.

## Decisions (locked with user)

1. **Both channels** — make the full relevant set trivially consumable by an AI
   (MCP + file round-trip) AND add a GUI "Top Picks" view that displays the
   AI's ranked shortlist.
2. **Relevant set = full inbox; the AI judges relevance itself.** Not the
   filtered Inbox view, not a hardcoded gate — the AI gets everything and
   decides what makes the cut.
3. **One full snapshot, then rank.** The AI pulls the entire inbox in a single
   call (all signal columns), ranks it, returns top-X with rank + rationale.
   No accumulate-by-batch loop.

## Approach A (chosen) vs B (deferred)

- **A — derive from existing columns.** The re-rank CSV schema already has a
  `new_rank` column and `import_scores` already stows it in `extras`. Extend the
  AI in/out paths to carry an explicit **rank**; the GUI Top Picks view reads
  `rank` + `fit` + `rationale` already present on each inbox row. No new tables,
  no migration. The AI's shortlist = the rows it ranked.
- **B — explicit `recommendations` table (deferred).** A first-class,
  timestamped shortlist artifact (batch*id, rank, rationale). Buys
  recommendation \_history* (compare batches over time) but adds a migration and
  machinery that largely duplicates `fit` + `score_history`. Clean future add
  because the data already lives in `extras`; not built now (YAGNI).

## Design

### Unit 1 — AI sees everything in one shot (consumption)

**What it does:** lets an AI pull the entire inbox with all ranking signal in a
single call, and write back a rank alongside fit.

**MCP (`mcp_server.py`):**

- `list_inbox(limit: int = 20, unscored_only: bool = True)` — extend so
  `limit=0` means **all rows** (no cap). Keep existing defaults for
  back-compat. Each returned row gains `rank` (from `extras`, `-1`/absent when
  not ranked) and `job_key`. Existing fields unchanged
  (id, title, company, location, salary, score, fit, url, description).
- `set_fit_scores(scores)` — each item may now include an optional
  `"rank"` (int, 1 = best). Persisted into the row's `extras` JSON alongside the
  existing fit write. Items without `rank` behave exactly as today.

**File round-trip (`rerank/`):**

- The CSV schema already carries `new_rank` (out) and `import_scores` already
  _parses_ it into `extras` — the parser is unchanged. The only write-side
  change is that the apply step stamps `rec_batch` (see Unit 2) so a file
  round-trip supersedes the prior shortlist exactly like the MCP path.
- `prompt.md` gains one instruction line: _"Assign `new_rank` 1..X to the jobs
  you recommend (1 = best); leave it blank for everything else — the blank ones
  are not on the shortlist."_
- **Export-scope toggle** on `_export_for_ai` (GUI): "current view ▸ / entire
  inbox", defaulting to **entire inbox** for the rank-everything flow. The prior
  "export honors the filter" behavior remains available via "current view".

**Depends on:** `tracker/db.py::inbox_all`, `rerank/schema.py`,
`rerank/import_.py`. No DB schema change — `rank` rides in the existing `extras`
TEXT column.

### Unit 2 — Recommendation = the ranked rows (data semantics)

**What it does:** defines what "the current top-X recommendation" is, and how a
fresh run supersedes the old one, without a new table.

- A **recommendation** is the set of inbox rows carrying a `rank`. The AI
  assigns `rank` 1..X to its picks; un-ranked rows are simply not on the
  shortlist.
- **Supersede semantics:** each write **batch** computes one `rec_batch` value
  (an ISO timestamp) once per call and stamps it into every row's `extras`
  alongside `rank` — applied identically by both write paths (MCP
  `set_fit_scores` and file `import_scores`) via the single shared `extras`
  helper. "The current recommendation" = rows whose `rec_batch` equals the
  latest `rec_batch` present. A new AI run writes a newer `rec_batch`, so the
  previous shortlist falls away without an explicit clear. (Old
  `rank`/`rec_batch` values stay in `extras` harmlessly; only the latest batch
  is shown.)
- `fit` history and undo (`score_history`, `inbox_undo_last_rerank`) keep
  working unchanged — rank is orthogonal, stored in `extras`, not in the fit
  audit trail.

**Helper (`tracker/service.py`):** `top_picks(limit: int = 10) -> list[dict]`
— returns the latest-`rec_batch` rows ordered by `rank` asc, capped at `limit`
(`0` = all ranked rows). Pure read over `inbox_all()` + `extras` parsing; the
single source of truth for both the GUI and any caller.

### Unit 3 — GUI "Top Picks" tab (presentation)

**What it does:** shows the current recommendation, best-first, capped to N.

- New tab between **Inbox** and **Apply Queue**, labeled **Top Picks**.
- Top bar: a "Show top **[N]**" spinbox (default **10**; `0`/"All" shows every
  ranked row) and a Refresh button.
- Treeview columns: **# (rank) · Title · Company · Location · Fit · Why
  (rationale) · Score · Source**, ordered by rank.
- Row actions reuse Inbox's: double-click opens the URL; **Track ▸ Interested**;
  **Dismiss**. Light/dark theme via the existing `ui/theme` helpers (no raw
  colors).
- **Empty state** when nothing is ranked: _"No AI picks yet — go to Inbox ▸
  Export for AI (or run a re-rank), then come back."_
- Data comes solely from `tracker_service.top_picks(N)` — the tab does not run
  AI itself; it displays whatever rank/fit the round-trip, API bridge, or MCP
  path produced.

**Depends on:** `tracker/service.py::top_picks`, `ui/theme`, and the existing
Inbox row-action helpers (factored/shared as needed).

### Unit 4 — find-jobs skill (the AI's playbook)

Rewrite `claude-code/skills/find-jobs/SKILL.md` to the snapshot-then-rank flow:

1. `get_preferences` — what they want + hard filters.
2. (optional) `search_jobs` — refresh the inbox.
3. `list_inbox(limit=0, unscored_only=False)` — **the full relevant snapshot,
   one call**.
4. Judge relevance + fit across **all** of it; choose the top X (default 10, or
   whatever the user asked for).
5. `set_fit_scores` with `[{id, fit, rank, rationale}, ...]` — `rank` 1..X for
   the shortlist.
6. Present the top X best-first (`# · title · company · location · fit ·
one-line why`) and note they now appear in the GUI **Top Picks** tab. Offer
   to `track_job` the ones they like.

## Out of scope / untouched

- The 0–100 local match scorer (`match/scorer.py`) — unchanged.
- The daily-run gate and search/hard-gate pipeline — unchanged.
- The location view-filter (`geo/filter.py`) — unchanged; still governs the
  Inbox _view_ and the "current view" export scope.
- The DB schema — **no migration**; `rank`/`rec_batch` ride in `extras`.
- Approach B's `recommendations` table — deferred.

## Testing

- **tracker:** `top_picks` returns latest-batch rows ordered by rank, honors
  `limit` (incl. `0` = all), ignores stale batches; rank read from `extras`
  tolerant of missing/garbage JSON.
- **MCP:** `list_inbox(limit=0)` returns the whole inbox and includes `rank` +
  `job_key`; `set_fit_scores` persists an optional `rank` round-trip.
- **rerank:** `import_scores` with `new_rank` populates `extras` and a fresh
  batch supersedes (latest `rec_batch` wins).
- **GUI Top Picks:** sort-by-rank + top-N cut, empty state, theming — using the
  existing headless-skip `root` fixture pattern.
- Full suite stays green (currently 537 pass).

## Files

`gui.py`, `mcp_server.py`, `tracker/db.py`, `tracker/service.py`,
`rerank/schema.py` (prompt line), `rerank/import_.py` (rec_batch stamp),
`claude-code/skills/find-jobs/SKILL.md`, plus tests under
`tests/tracker/`, `tests/` (mcp), `tests/rerank/`, `tests/ui/`.

## Risks

- **`extras` overloading** — rank/rec_batch share the JSON blob with
  `new_rank`/`tags`. Mitigation: a single `extras` read/write helper in
  `tracker/service.py` so the shape is defined in one place; tolerant of
  missing/garbage values.
- **Back-compat of `list_inbox`** — defaults unchanged (`limit=20`,
  `unscored_only=True`); only `limit=0` and the new output keys are additive.
- **Top Picks vs Inbox duplication** — Top Picks is a thin read over
  `top_picks()`; shared row actions avoid a second copy of Track/Dismiss logic.
