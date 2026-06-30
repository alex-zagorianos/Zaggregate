---
name: plan-job-search-projects
description: Design + phased plan for "job search projects" — scope all search config AND pipeline data (inbox/applications/dismissed/resume/reports) under a named, switchable project. Recommends a directory-per-project workspace model.
tags: [plan, feature, projects, workspace]
date: 2026-06-14
status: proposed
---

# Feature Plan — Job Search Projects

A **job search project** groups everything you do for one search campaign — its keywords/sources/filters, its resume, its inbox, its tracked applications, its dismissed list, its generated docs and reports — under one named workspace. You switch the active project to work an entirely separate campaign without the two ever mixing.

> Status legend: ⬜ todo · 🔄 in progress · ✅ done · ⏸ deferred. See also [[architecture]], [[plan-2026-06]].

---

## 1. Why — the gap today

The config layer is **already multi-profile**; the data layer is **not**.

- ✅ Config is parameterized: `user_config.json` (Alex) + `config_dad.json` (dad), selected via `--user-config` / `load_user_config(path)` ([search/cli.py](../search/cli.py)), launched by `run_dad.bat`.
- ❌ Data is global: one `tracker.db` holds `inbox` + `applications` + `dismissed` for everyone; one `experience.md` is the only resume base; `OUTPUT_DIR` is shared. If dad runs his search, his jobs land in **the same inbox** as Alex's, and the dedup/dismiss lists are shared.

So running dad's config today pollutes Alex's pipeline. "Projects" closes this by giving each campaign its own data partition — and unlocks Alex running several _of his own_ campaigns side by side (e.g. `controls-cincinnati`, `embedded-remote`, `aerospace-relocate`), each with its own tuned keywords **and** its own resume slant.

## 2. What a project owns vs. what stays shared

| Per-project (scoped)                                                                                              | Shared (global)                                                              |
| ----------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `config.json` (keywords, location, salary_min, sources{}, industry, exclude_keywords, max_per_company, min_score) | `.env` API keys (Adzuna/JSearch/USAJobs/Anthropic/Brave)                     |
| `tracker.db` → inbox + applications + dismissed                                                                   | Source client code + rate limiters                                           |
| `experience.md` (resume base — per-project slant)                                                                 | `companies.json` + careers REGISTRIES (selected _by_ a project's `industry`) |
| `output/` (generated resumes, cover letters, reports, daily_run.log)                                              | HTTP response `cache/` (keyed by query+source; safe to share)                |
| dedup + dismiss scope (so the same posting can live in two projects)                                              | The careers scraper, scorer, resume generator (pure logic)                   |

**Dedup must be per-project.** Today `seen_urls()` is global; under projects, a posting Alex tracked in `controls-cincinnati` should still be _eligible_ to surface in `aerospace-relocate`. Separate `tracker.db` per project gives this for free.

## 3. Design decision — directory-per-project (recommended) vs. `project_id` column

|                                   | **A. Directory-per-project** ✅ recommended                                 | B. `project_id` column (single DB)                                                                |
| --------------------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Data isolation                    | Total — separate `tracker.db` per project                                   | Logical — every query must filter; one missed `WHERE` leaks                                       |
| Code churn                        | Low — repoint path constants; `tracker/db.py`, scorer, resume gen untouched | High — thread `project_id` through all ~15 db.py funcs + every GUI query + dedup + inbox_add_many |
| Dedup scoping                     | Free (separate DB)                                                          | Must add project_id to `dismissed`/`applications` + rewrite `seen_urls`                           |
| Backup / delete / share a project | `zip` / `rm` the folder                                                     | DELETE WHERE + VACUUM                                                                             |
| Cross-project aggregate view      | Iterate dirs (rare op)                                                      | One SQL GROUP BY                                                                                  |
| In-process switch (no restart)    | Needs runtime path resolution (see §4)                                      | Just change a filter var                                                                          |

**Pick A.** The codebase resolves every path from module-level constants (`BASE_DIR`, `EXPERIENCE_FILE`, `OUTPUT_DIR`, `tracker.db DB_PATH`), so "switch project" becomes "resolve those against a different root" — the entire data/scoring/resume stack keeps working unchanged. Its one cost (in-process switching needs runtime path resolution instead of import-time constants) is a contained refactor, and the MVP can simply relaunch on switch.

## 4. On-disk layout

```
ZAG0005 - Job Search App/
├── projects/
│   ├── projects.json              # registry: [{slug,name,created,active}], + "active": "<slug>"
│   ├── controls-cincinnati/       # ← migrated from current root data
│   │   ├── config.json            # was user_config.json
│   │   ├── experience.md          # was root experience.md (copy)
│   │   ├── tracker.db             # was root tracker.db (moved)
│   │   └── output/
│   └── dad-health-informatics/    # ← migrated from config_dad.json (fresh empty db)
│       ├── config.json
│       ├── experience.md
│       ├── tracker.db
│       └── output/
├── cache/                         # stays shared (HTTP cache)
├── companies.json                 # stays shared
└── ... (code unchanged)
```

`projects.json` is the single source of truth for the project list + which is active. Slugs are filesystem-safe; `name` is the display label.

## 5. Core mechanism — a `workspace` context

Introduce `workspace.py` to make paths runtime-resolved instead of import-time:

```python
# workspace.py (sketch)
def active_slug() -> str          # reads projects/projects.json -> "active"
def set_active(slug: str)         # writes "active"; (GUI then rebuilds tabs)
def project_dir(slug=None) -> Path
def db_path(slug=None) -> Path        # project_dir/tracker.db
def experience_file(slug=None) -> Path
def output_dir(slug=None) -> Path
def load_config(slug=None) -> dict    # project_dir/config.json (replaces load_user_config)
def list_projects() -> list[dict]
def create_project(name, *, copy_resume_from=None, config=None) -> str  # returns slug
```

Then the contained refactor:

- `config.py` — `EXPERIENCE_FILE` / `OUTPUT_DIR` / `USER_CONFIG_JSON` become thin wrappers over `workspace.*` (keep names for back-compat; resolve lazily).
- `tracker/db.py` — `DB_PATH` constant → `get_conn()` calls `workspace.db_path()` each time (cheap; sqlite connect is the cost, not the path lookup). All other db funcs unchanged.
- `search/cli.py` — `load_user_config()` delegates to `workspace.load_config()`; add `--project <slug>` (resolves the workspace before anything else). Keep `--user-config` as a deprecated alias.
- `resume/service.py` + `resume/experience_parser.py` — read `workspace.experience_file()` (and invalidate the mtime memoization across switches).
- `daily_run.py` — add `--project <slug>`; default = active project.

## 6. Migration (one-time, no data loss)

⬜ `scripts/migrate_to_projects.py`:

1. If `projects/` absent: create it.
2. Create `controls-cincinnati` from current root: **move** `tracker.db` → `projects/controls-cincinnati/tracker.db`; **copy** `experience.md` and `user_config.json`→`config.json`; move `output/`.
3. Create `dad-health-informatics` from `config_dad.json` → `config.json`; copy `experience.md` as a starting resume; fresh empty `tracker.db` (dad's jobs were never separated, so start clean).
4. Write `projects.json` with `controls-cincinnati` active.
5. Leave root `tracker.db`/`user_config.json` as `.bak` for one release, then delete.

Back-compat: if `projects/` doesn't exist, `workspace.*` falls back to root paths so nothing breaks pre-migration.

## 7. CLI

- `py -m search.cli --project controls-cincinnati ...` (and `daily_run.py --project ...`).
- `py -m search.cli project list` · `project new "Aerospace (relocate)"` · `project use <slug>` · `project rm <slug>`.
- Bare invocation = active project (back-compat with current muscle memory).

## 8. GUI (`gui.py`)

- **App-level header bar** above the Notebook: `Project: [ Controls — Cincinnati ▾ ]  [＋ New]  [⚙ Manage]`. (Currently each tab has its own `hdr`; add one shared top strip in the root window.)
- On switch: `workspace.set_active(slug)` → tear down + rebuild the 5 tabs (TrackerTab / ResumeTab / InboxTab / + 2) so they re-query the new project's db/config. MVP fallback: prompt "restart to switch" if live rebuild is fiddly.
- **New project** dialog: name, starting keywords/location/sources (prefill from a template or clone an existing project), and "copy resume from <project> / blank".
- Per-project badge in the title bar so you always know which campaign you're in (guards against applying out of the wrong inbox).

## 9. Daily run + scheduler

- `daily_run.py --project <slug>` scopes the whole run (config + inbox + dedup) to that project.
- `setup_schedule.bat` → register **one task per active project** (`JobSearchDaily-<slug>`), or a `run_all_active.bat` wrapper that loops `projects.json` where `daily=true`. Add a per-project `"daily": true|false` flag so you can pause a campaign's morning run without deleting it.

## 10. Phased rollout (with verification)

- **Phase 0 — `workspace.py` + back-compat fallback** ⬜ — paths resolve to root when `projects/` absent. _Verify:_ existing pytest suite green unchanged; `py gui.py` + `py daily_run.py --max-pages 1` behave exactly as today.
- **Phase 1 — migration script + `projects.json`** ⬜ — run it; confirm `controls-cincinnati` opens with all current tracked apps + inbox intact, dad project exists empty. _Verify:_ row counts before/after match; `.bak` written.
- **Phase 2 — repoint `config.py` / `tracker/db.py` / `resume` / `cli` to `workspace`** ⬜ — `--project` flag works end to end. _Verify:_ run two projects back-to-back via CLI; confirm inboxes don't cross-contaminate; dedup is per-project.
- **Phase 3 — GUI switcher** ⬜ — dropdown + New + Manage; tab rebuild on switch. _Verify:_ switch controls↔dad in a live session; each tab shows only its project's data; resume tab uses the project's experience.md.
- **Phase 4 — scheduler per project** ⬜ — `daily_run.py --project`, per-project `daily` flag, updated `setup_schedule.bat`. _Verify:_ scheduled task runs the right project into the right inbox.
- **Phase 5 (optional) — cross-project dashboard** ⏸ — an "All projects" view aggregating counts (applications by status, inbox size, last-run) across `projects/*/tracker.db`.

Sequencing note: Phase 2 overlaps [[plan-2026-06]] Phase 5 (the `services.py` extraction + path centralization) — do them together if that remediation is still pending, since both touch the same path/IO seams.

## 11. Open questions (confirm before building)

- **Resume per project, or shared base + per-project overlay?** Plan assumes a full `experience.md` copy per project (max flexibility, slight duplication). Alternative: one master `experience.md` + a per-project `emphasis.md` the generator weights. → Recommend per-project copy for v1; revisit if maintaining N resumes becomes a chore.
- **Dad = a project here, or his own install?** Treating dad as a project keeps one codebase but mixes his data into Alex's app dir. If privacy/separation matters, dad could instead get a separate copy of the tool. → Recommend project for now (it's already how `config_dad.json` works).
- **Cross-project dedup — fully independent, or warn on overlap?** v1 = independent (same posting can appear in two projects). Possible nicety: a soft "you already tracked this in <other project>" badge. → Defer to Phase 5.
- **Cache sharing** — keep `cache/` global (recommended; it's query-keyed and project-agnostic) vs. per-project. → Global.

---

_Authored 2026-06-14. Builds on the existing `--user-config` multi-profile pattern; supersedes the ad-hoc `config_dad.json` / `run_dad.bat` approach once Phase 1 lands._
