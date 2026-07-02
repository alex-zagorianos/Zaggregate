# HANDOFF 2026-06-14 | Session 9 — Archive · Search tightening · Projects · Add-Companies · Browser-ext verify

Model: Opus 4.8 (1M). Output mode: TERSE. Canonical brain: [[project-status]] (Session 9 sections). Spec: [[spec-2026-06-14-archive-search-projects]].

## State: everything committed + pushed, working tree clean

- HEAD **`14bdd31`** on `master`, pushed to `git@github.com:alex-zagorianos/Job-Program.git`.
- Full suite **127 passing** (`py -m pytest -q`). Python = `py`.
- **Migrated to the projects/ workspace model** — active project `controls-cincinnati` (1098-row inbox); `dad-health-informatics` seeded empty. Root data backed up to `tracker.db.bak` (gitignored). `projects/` is local-only (gitignored).

## What shipped this session (commits, newest first)

1. `14bdd31` **browser-ext: LinkedIn selectors refreshed (live-verified) + title de-dup.** LinkedIn moved to `artdeco-entity-lockup`; company/location promoted to working selectors, salary fixed (`.artdeco-entity-lockup__content` → server `_parse_salary`), titles de-doubled. manifest 1.1→1.2. Indeed = healthy, unchanged.
2. `64ff8ea` **fix:** `/harvest` receiver now applies search-tightening to harvested jobs.
3. `5457594` **feat: Add Companies via GUI** — Search tab "+ Add Companies" → paste URLs → `scrape/ats_detect.py` auto-detects ATS+slug → Validate (live counts) → save to companies.json tagged with project industry.
4. `1375889` **feat: Projects Phase 3** — GUI project switcher (dropdown + New, live tab rebuild).
5. `54200ca` **feat: Projects Phase 0–2** — `workspace.py`, `migrate_to_projects.py` (ran), `--project` on cli/daily, path seams repointed.
6. `1493571` **chore:** `rescore_inbox.py` (ran — off-target AI/ML/Data → 0).
7. `b74d696` **feat: Search tightening** — `search/query.py` boolean keywords (`"phrase"`/OR/NOT/-/()), scorer downrank (title-miss + `exclude_titles` + `seniority_exclude`), all in user_config.json.
8. `df6aa52` **feat: Archive** (soft-delete) — Tracker Delete→Archive, Archive(n) chip, Restore / Delete-permanently.
9. `53e9469` **fix: Workday/Caterpillar links** — `_job_url()` inserts site segment; `fix_workday_urls.py` backfilled 107.
10. `627bce6` committed the prior 4-session backlog.

## ⚠️ Next session — first actions / open items

- **Browser harvesting (to actually use it):** Alex must **reload the unpacked extension** (`chrome://extensions` → reload "Job Harvester") to pick up v1.2 `content.js`. LinkedIn collection requires him **logged in**; run `py -m scrape.browser_receiver` (:5002) for "Send to Tool". Re-audit selectors anytime with `browser_ext/selector_check.js` (paste in DevTools console on a jobs results page).
  - Claude-in-Chrome MCP tab is NOT logged into LinkedIn — for me to re-audit LinkedIn live, Alex logs in to the controlled window first (or runs the console snippet in his own tab). Indeed audits without login.
- **Projects Phase 4 (deferred, only remaining Projects work):** per-project scheduler — `daily_run --project` done; need per-project `setup_schedule.bat` + `daily` flag wiring (one task per active project).
- **`setup_schedule.bat` still never run** — 07:30 daily task unregistered.
- Optional `.env`: `ANTHROPIC_API_KEY` (bridge makes it unnecessary), `BRAVE_SEARCH_API_KEY` (Brave free tier dead since Feb 2026 → $5/mo).
- Could add: company **remove/edit** UI, Projects **Manage** (rename/delete), unit tests for scorer/bridge parsers.
- Delete `tracker.db.bak` from root after a release (safety copy from migration).

## Gotchas

- LinkedIn lazy-virtualizes job cards — only viewport cards render; the extension's MutationObserver harvests progressively as you scroll (so a static snapshot under-counts).
- `companies.json` is **global** (shared across projects); a project's `industry` tag filters which companies its searches use. `cache/` also global.
- `tracker/db.py` `DB_PATH=None` → resolves active project via `workspace`; tests override `DB_PATH` to a temp path.
