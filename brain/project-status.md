# Project Status

#status #roadmap

---

## Phase 1 — Job Scraper ✅ COMPLETE (2026-05-27)

### API Sources
- [x] Adzuna API client — working, tested
- [x] JSearch (RapidAPI) — working, key in .env
- [x] USAJobs — working, key in .env
- [x] Multi-source architecture (base class, dedup, HTML report with source badges)
- [x] CLI: `py -m search.cli` with full flag set (see below)

### Career Page Scraper
- [x] Greenhouse scraper — public JSON API
- [x] Lever scraper — public JSON API
- [x] Workday scraper — slug format `tenant:N:site`; Caterpillar confirmed working; most others CSRF-protected (kept as `direct` type)
- [x] Direct scraper — BeautifulSoup best-effort for custom portals
- [x] Company registry — `REGISTRIES` dict, 2 industries (controls_engineering, health_informatics); 40+ entries
- [x] `CareersClient` — slots into pipeline via `search_and_parse()` override (no dict roundtrip)
- [x] User-editable `companies.json` — merges with hardcoded registry, user wins on name collision
- [x] Company discovery — **Brave Search API** (replaced DDG); requires `BRAVE_SEARCH_API_KEY` in `.env`; skips gracefully if key absent; free 2,000 req/month

### CLI Features
- [x] `--keywords` / `--add-keyword` / `--user-config` — 3-tier resolution: CLI > user_config.json > defaults
- [x] `--location` — default falls through to user_config.json then hardcoded DEFAULT_LOCATION
- [x] `--salary-min` — same resolution chain
- [x] `--sources` — comma-separated; respects `sources` dict in user_config.json
- [x] `--sort-by date|location` — location uses `_location_score()` in search_engine.py
- [x] `--industry` — filters company registry
- [x] `--top-n`, `--max-pages`, `--no-cache`, `--no-discover`, `--companies-file`
- [x] `--edit-csv` — opens output CSV in default app after search (Windows)

### User Config Files
- [x] `user_config.json` — Alex's personal defaults (10 ME keywords, Cincinnati, $85K)
- [x] `config_dad.json` — Dad's health informatics config
- [x] `run_dad.bat` — double-click launcher for Dad
- [x] `run_servers.bat` — starts all three Flask servers in separate windows

### Output
- [x] HTML report — dynamic source filter dropdown (built from actual cards), Track button per job
- [x] CSV report — opens automatically with `--edit-csv`

---

## Phase 2 — Resume & Cover Letter Generator ✅ COMPLETE (code) (2026-05-27)

- [x] `resume/experience_parser.py` — parses experience.md by `## ` headings
- [x] `resume/generator.py` — Claude API call, structured JSON response, fence-stripping
- [x] `resume/docx_builder.py` — resume DOCX + cover letter DOCX, dark navy theme
- [x] `resume/app.py` — Flask on port 5000, returns .zip of both DOCXs
- [x] `resume/templates/index.html` — paste job posting, loading state, error display
- [ ] **`ANTHROPIC_API_KEY` not yet added to `.env`** — required to use
- [ ] **ERP tech stack gap in experience.md** (line 109 placeholder) — affects output quality

**Run:** `py -m resume.app` → `http://localhost:5000`

---

## Browser Extension — Job Harvester ✅ COMPLETE (2026-05-27)

- [x] Chrome MV3 extension — `browser_ext/`
- [x] SITES registry pattern — 5 sites: LinkedIn, Indeed, Glassdoor, ZipRecruiter, Dice
- [x] Adding a new site: one object in SITES array + one URL pattern in manifest.json
- [x] Debounced MutationObserver (600ms) + SPA URL change detection (1s)
- [x] Dedup by URL in chrome.storage.local
- [x] Popup: count badge, **Send to Tool** (→ report via browser_receiver), **Track All as Interested** (→ tracker direct), Clear
- [x] `scrape/browser_receiver.py` — Flask on port 5002, converts to JobResult, generates HTML+CSV report

**Send to Tool:** requires `py -m scrape.browser_receiver`
**Track All:** requires `py -m tracker.app`

---

## Job Application Tracker ✅ COMPLETE (2026-05-27)

- [x] `tracker/db.py` — SQLite (`tracker.db`, gitignored), full CRUD, 7 statuses
- [x] `tracker/app.py` — Flask on port 5001
- [x] `tracker/templates/tracker.html` — status tabs with counts, add form (collapsible, pre-fill from URL params), inline status dropdown (auto-submits), expandable notes, delete
- [x] Status flow: interested → applied → phone_screen → interview → offer / rejected / withdrawn
- [x] JSON API: `POST /api/add` (CORS enabled) — used by browser extension Track All
- [x] Pre-fill path: `http://localhost:5001/add?title=...&company=...&url=...&salary=...`
- [x] "Track" button on every job card in search HTML reports

**Run:** `py -m tracker.app` → `http://localhost:5001`

---

## Code Quality — Reviewed & Fixed (2026-05-27)

- [x] Port constants centralized in config.py (`PORT_RESUME=5000`, `PORT_TRACKER=5001`, `PORT_RECEIVER=5002`)
- [x] `CareersClient.search_and_parse()` — eliminates JobResult→dict→JobResult roundtrip
- [x] Registry loaded once in `CareersClient.__init__()`, not per keyword
- [x] `base_client.py` — added default `search_and_parse()` wrapping search+parse
- [x] `_parse_salary` regex requires `$` prefix (matches content.js behavior)
- [x] `datetime.utcnow()` → `datetime.now(timezone.utc)` (Python 3.12 deprecation)
- [x] All print statements ASCII-safe (Windows cp1252)
- [x] `debug=False` on all Flask apps

---

## Outstanding — Needs Alex

- [ ] `ANTHROPIC_API_KEY` in `.env` — get from console.anthropic.com
- [ ] ERP tech stack in `experience.md` line 109 — optional but improves resume quality
- [ ] `BRAVE_SEARCH_API_KEY` in `.env` — optional, free at api.search.brave.com; enables company auto-discovery

## Git
- Last commit: `ae59a08` — pushed to `git@github.com:alex-zagorianos/Job-Program.git`
- Python command: `py` (not `python`)
- No venv — packages installed globally
