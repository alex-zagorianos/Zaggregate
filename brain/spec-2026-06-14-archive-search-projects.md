---
name: spec-2026-06-14-archive-search-projects
description: Approved design+sequencing for three features — Archive (soft-delete) · Search tightening (boolean queries + auto-strict scoring) · Job Search Projects (per-campaign data). Built in that order, commit per feature.
tags: [spec, feature, archive, search, projects]
date: 2026-06-14
status: approved
---

# Spec — Archive · Search Tightening · Projects

Approved by Alex 2026-06-14. Build order **Archive → Search → Projects**, one
branch, a commit per feature, pytest/smoke green before each next step. Decisions
locked: off-target = **downrank, keep visible** (never hide); search control =
**both** boolean syntax + config auto-strict; Projects = **full Phase 0–4**.

## Feature 1 — Archive (replaces hard-delete)

- `tracker/db.py`: add `archived INTEGER DEFAULT 0` via the `_EXTRA_COLUMNS` ALTER.
  `archive_job(id)` / `unarchive_job(id)`. `get_all` excludes archived by default;
  `status_filter="archived"` returns only archived. `get_counts` excludes archived
  from per-status + `all`, adds `counts["archived"]`. `delete_job` kept = permanent.
- `gui.py` TrackerTab: "Delete"→**Archive** (confirm kept). New **Archive (n)** chip
  in the status filter bar. In archive view the action bar swaps to **Restore** +
  **Delete permanently** (only place a true DELETE fires).
- Archived rows keep their URL in `tracked_urls()` so they don't resurface in search
  (archive ≠ "show again" — that's Dismiss). _(confirmed)_

## Feature 2 — Search tightening (downrank, never hide)

- **2a Boolean syntax** `search/query.py` (new): `"exact phrase"`, `OR`, `NOT`/`-`,
  implicit AND, parens → predicate tree. Plain keyword w/o operators == today
  (back-compat). Wired into `text_match.keyword_matches` (scrape) + scorer title.
- **2b Auto-strict** `match/scorer.py` + config:
  - `title_miss_penalty` (default −35): title_score==0 → heavy penalty + raise title
    weight so off-target can't clear the floor on neutral salary/recency.
  - `exclude_titles` list (ai, machine learning, data scientist, frontend, full
    stack, devops, …): word-boundary hit in TITLE = strong penalty. Kills "AI Engineer".
  - seniority parsed from title; `seniority_exclude` (director/manager/…) → penalty.
  - All thresholds in `user_config.json`; every adjustment shown in `score_notes`.

## Feature 3 — Job Search Projects (full, Phase 0–4)

Per [[plan-job-search-projects]], v1 recommendations accepted (per-project
experience.md copy; Dad = a project; independent per-project dedup; global cache).
P0 `workspace.py` + root fallback · P1 `scripts/migrate_to_projects.py` + projects.json
· P2 repoint config/db/resume/cli to workspace + `--project` · P3 GUI switcher · P4
`daily_run --project` + per-project scheduler. Archive's `archived` column rides the
init_db ALTER against whatever db_path resolves to.

## Verification

New tests: boolean parse, scorer penalties (title-miss/exclude_titles/seniority),
archive db ops, workspace path resolution, migration row-count parity. Restart the
GUI to test each feature (running instance won't reflect edits).
