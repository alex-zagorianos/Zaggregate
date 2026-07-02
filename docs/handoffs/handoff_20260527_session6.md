# HANDOFF 2026-05-27 | Session 6 — Full Build-Out + Code Review

## SESSION SUMMARY

Completed every remaining planned task (Tasks 1–5 from the Session 5 plan), built the browser extension, built the job tracker, performed a full code review with 11 fixes, and made three additional improvements (Brave Search, dynamic source filter, Track All button). The tool is now functionally complete end-to-end. The only things blocking full use are two API keys Alex needs to add to `.env`.

---

## WHAT GOT DONE

### Task 1 — Git Commit Session 5 Work
Staged and pushed: `scrape/workday_scraper.py`, `scrape/company_registry.py`, `scrape/careers_client.py`, `scrape/discoverer.py`, `search/cli.py`, `config.py`, `companies.json`, `brain/project-status.md`

### Task 2 — User Config File System
- `user_config.json` (project root) — Alex's personal defaults: 10 ME keywords, Cincinnati, $85K salary_min, all sources enabled
- `config_dad.json` — Dad's health informatics config: 5 keywords, Cincinnati, $70K, industry=health_informatics
- `run_dad.bat` — double-click launcher: `py -m search.cli --user-config config_dad.json`
- `config.py` — added `USER_CONFIG_JSON` path constant; updated `ANTHROPIC_MODEL` to `claude-sonnet-4-6`
- `search/cli.py` — full rewrite: `load_user_config()`, `--user-config`, `--add-keyword`, `--sort-by`, `--edit-csv`; 3-tier resolution (CLI > user_config.json > hardcoded)

**Resolution stack:**
```
CLI flag  >  user_config.json  >  config.py DEFAULT_*
```

### Task 3 — Location Sorting
- `search/search_engine.py` — `_location_score(job_location, target)` — token matching with state abbrev lookup; remote jobs score 0
- `--sort-by location` flag in CLI
- State coverage: OH/KY/IN/PA/TX/CA/NY/VA/MI/IL/GA/FL/NC/TN

### Task 4 — Quick-Edit CSV
- `--edit-csv` flag → `os.startfile(csv_path)` after report generation (Windows)

### Task 5 — Phase 2 Resume Generator
New module: `resume/`

**Files:**
- `resume/experience_parser.py` — parses `experience.md` by `## ` headings into dict
- `resume/generator.py` — single Claude API call, returns structured JSON; `ResumeGenerationError` for all failure modes; `_parse_response()` strips markdown fences before `json.loads()`
- `resume/docx_builder.py` — `build_resume_docx()` + `build_cover_letter_docx()`, dark navy `#1A1A2E` theme, OOXML section heading borders
- `resume/app.py` — Flask on port 5000; `POST /generate` → .zip of two DOCXs; `GET /health` → `{status, api_key_set}`
- `resume/templates/index.html` — textarea, loading state JS, error display with preserved form content

**Run:** `py -m resume.app` → `http://localhost:5000`
**Requires:** `ANTHROPIC_API_KEY` in `.env`

### Browser Extension — Job Harvester
New directory: `browser_ext/`

**Files:**
- `manifest.json` — Chrome MV3, storage+activeTab permissions, 5 sites
- `content.js` — SITES registry pattern; each site is one self-contained object with CSS selector fallback lists; `first(el, selectors)` tries in order; debounced MutationObserver (600ms); SPA URL detection (1s interval); dedup by URL
- `popup.html` + `popup.js` — count badge, Send to Tool, Track All as Interested, Clear
- `background.js` — UPDATE_BADGE message handler

**Supported sites:** LinkedIn (`/jobs/*`), Indeed (`/*`), Glassdoor (`/Job/*`, `/jobs/*`), ZipRecruiter (`/jobs/*`, `/candidate/*`), Dice (`/jobs/*`)

**Adding a new site:** one object in `SITES` array in content.js + one URL pattern in manifest.json

**Selectors strategy for stability:**
- LinkedIn: `job-card-list__title--link` class
- Glassdoor: `data-test` attributes (stable across React re-renders)
- ZipRecruiter: `data-job-id`, `data-testid`
- Dice: custom elements (`dhi-search-card`) + `data-cy` attrs

**Browser receiver:** `scrape/browser_receiver.py` — Flask on port 5002; `POST /harvest` accepts `{jobs:[...]}`, converts to JobResult, generates HTML+CSV, opens report; CORS via `app.after_request`

### Job Application Tracker
New module: `tracker/`

**Files:**
- `tracker/__init__.py` (empty)
- `tracker/db.py` — SQLite `tracker.db` (gitignored); `applications` table; `init_db()`, `add_job()`, `get_all(status_filter)`, `get_counts()`, `update_job(id, **fields)`, `delete_job()`, `get_job()`
- `tracker/app.py` — Flask on port 5001; routes: `GET /` (dashboard with status filter), `GET+POST /add` (manual add + pre-fill from URL params), `POST /update/<id>`, `POST /delete/<id>`, `GET /api/jobs`, `POST /api/add` (CORS), `GET /api/status`
- `tracker/templates/tracker.html` — status filter tabs with counts, collapsible add form, 5-column job grid, inline status dropdown (auto-submits on change, color-coded), expandable notes row, delete with confirm

**Status flow:** interested → applied → phone_screen → interview → offer / rejected / withdrawn

**Pre-fill URL pattern:** `http://localhost:5001/add?title=X&company=Y&url=Z&salary=W`

**Search report integration:** "Track" button on each job card in `search/templates/report.html` links to pre-fill URL

### Code Review — 11 Issues Fixed

| # | Issue | File(s) |
|---|---|---|
| 1 | `checkReceiver()` re-enabled Send when 0 jobs | `popup.js` |
| 2 | `debug=True` on resume app | `resume/app.py` |
| 3 | `_parse_salary` matched any number, not just `$`-prefixed | `browser_receiver.py` |
| 4 | `datetime.utcnow()` deprecated (Python 3.12+) | `browser_receiver.py` |
| 5 | Em dash `—` in print crashed Windows cp1252 | `cli.py` |
| 6 | Popup subtitle listed 2 of 5 sites | `popup.html` |
| 7 | No CSS badge rule for `*_browser` source_api values | `report.html` |
| 8 | JobResult→dict→JobResult roundtrip in CareersClient | `careers_client.py`, `base_client.py`, `search_engine.py` |
| 9 | `get_registry()` called per keyword (registry is static) | `careers_client.py` |
| 10 | Port numbers hardcoded in 3 files | `config.py` + all Flask apps |
| 11 | 3 terminals required to start everything | `run_servers.bat` (new) |

**Design change detail (item 8):**
- Added `search_and_parse()` to `JobAPIClient` base class with default implementation
- `CareersClient` overrides it to return `list[JobResult]` directly
- `search_engine.py` calls `client.search_and_parse()` instead of `search()` + `parse_results()`
- `CareersClient.search()` and `parse_results()` now stub out (satisfy ABC, never called)

### Additional Improvements (post-review)
- **Brave Search replaces DuckDuckGo** in `scrape/discoverer.py` — REST API, returns JSON, no bot challenges; add `BRAVE_SEARCH_API_KEY` to `.env` to enable; skips silently if key absent; free 2,000 req/month at `api.search.brave.com`
- **Report source filter is now dynamic** — built from actual card data via JS instead of hardcoded options; correctly shows linkedin_browser, indeed_browser, etc.
- **"Track All as Interested" button** in browser extension popup — POSTs each collected job directly to `tracker /api/add`, clears storage on success, reports per-job failures

---

## CURRENT STATE

**Fully functional (no blockers):**
- Job search CLI (`py -m search.cli`)
- Career page scraper
- Browser extension harvest + send to report
- Browser extension Track All → tracker
- Job tracker (`py -m tracker.app`)

**Functional but untested end-to-end:**
- Resume generator — code complete, API key not yet added

**Non-functional / optional:**
- Company auto-discovery — needs `BRAVE_SEARCH_API_KEY` in `.env`

---

## OUTSTANDING — NEEDS ALEX

1. **`ANTHROPIC_API_KEY`** — add to `.env` (get from console.anthropic.com → API Keys). Without this, the resume generator returns a clear error message but does not work.
2. **ERP tech stack** — fill in line 109 of `experience.md` (`[ADD TECH STACK WHEN READY]`). Optional but improves resume generator output quality for software-adjacent roles.
3. **`BRAVE_SEARCH_API_KEY`** — optional, free, enables company discovery. Sign up at api.search.brave.com.

---

## KEY ARCHITECTURE NOTES

**Port map:**
| Service | Command | Port |
|---|---|---|
| Resume generator | `py -m resume.app` | 5000 |
| Job tracker | `py -m tracker.app` | 5001 |
| Browser receiver | `py -m scrape.browser_receiver` | 5002 |
| Job search CLI | `py -m search.cli` | — |

All port constants live in `config.py`: `PORT_RESUME`, `PORT_TRACKER`, `PORT_RECEIVER`.

**Start all three servers:** `run_servers.bat` (double-click)

**Browser extension workflow:**
1. Load `browser_ext/` as unpacked extension in Chrome
2. Browse LinkedIn / Indeed / etc.
3. Extension collects jobs automatically while you scroll
4. Popup shows count
5. **"Send to Tool"** → generates HTML+CSV report (requires receiver running)
6. **"Track All as Interested"** → sends directly to tracker (requires tracker running)

**User config workflow:**
```
py -m search.cli                           # uses user_config.json defaults
py -m search.cli --add-keyword "robotics"  # appends to defaults
py -m search.cli --user-config config_dad.json  # Dad's health IT config
run_dad.bat                                # same as above, double-click
```

---

## COMMITS THIS SESSION
```
ac71809  Add Workday scraper, user companies.json, DDG bot detection (Session 5)
         [files: workday_scraper.py, company_registry.py, careers_client.py,
          discoverer.py, cli.py, config.py, companies.json, brain/project-status.md]

4a43988  Add job application tracker (Session 6)
         [files: tracker/__init__.py, tracker/app.py, tracker/db.py,
          tracker/templates/tracker.html, .gitignore, search/templates/report.html]

5002f65  Code review fixes: bugs, design debt, efficiency (Session 6)
         [files: popup.html, popup.js, config.py, resume/app.py,
          browser_receiver.py, careers_client.py, base_client.py, cli.py,
          search_engine.py, report.html, tracker/app.py, run_servers.bat]

ae59a08  Replace DuckDuckGo discovery with Brave Search; browser ext tracker integration
         [files: config.py, discoverer.py, report.html, popup.html, popup.js, .env.example]
```

**HEAD:** `ae59a08` on `master`

---

## ENVIRONMENT
- Python: `py` (not `python`)
- No venv — packages installed globally
- API keys in `.env` (gitignored): Adzuna ✅, JSearch ✅, USAJobs ✅, Anthropic ❌ (needed), Brave Search ❌ (optional)
- GitHub: `git@github.com:alex-zagorianos/Job-Program.git` (SSH configured)
- Last verified working: `py -m search.cli` with Adzuna + USAJobs sources
