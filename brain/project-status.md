# Project Status

#status #roadmap

## Phase 1 — Job Scraper ✅ SUBSTANTIALLY COMPLETE (2026-05-26)

### API Sources
- [x] Adzuna API client — working, tested
- [x] JSearch (RapidAPI) — working, key in .env
- [x] USAJobs — working, key in .env
- [x] Multi-source architecture (base class, dedup, HTML report with source badges)
- [x] CLI: `py -m search.cli` with full flags

### Career Page Scraper (sessions 4–5)
- [x] `scrape/` module scaffolded
- [x] Greenhouse scraper — public JSON API, confirmed working
- [x] Lever scraper — public JSON API, confirmed working
- [x] Direct scraper — BeautifulSoup best-effort (limited on Workday/JS pages)
- [x] Company registry — `REGISTRIES` dict, 2 industries
- [x] `CareersClient` — slots into existing pipeline, `--sources careers`
- [x] CLI flags: `--top-n`, `--industry`, `--no-discover`, `--companies-file`
- [x] **Workday scraper** — `scrape/workday_scraper.py`, slug format `tenant:N:site`
      - Caterpillar (`cat:5:CaterpillarCareers`) confirmed working — 20 jobs returned
      - Most other tenants (Honeywell, Rockwell, Parker, Siemens, Epic, UHG, etc.) have CSRF enabled → HTTP 422 on bare POST; kept as `direct` type with correct Workday URLs
      - Key finding: Workday page size cap = 20 (limit>20 → HTTP 400)
- [x] **User-editable companies.json** — lives in project root, merged with hardcoded registry at runtime; user entries override by name; `_example` entries ignored; `--companies-file` flag for custom path
- [x] DuckDuckGo discovery — live-tested 2026-05-26; DDG returns bot challenge (`anomaly.js`); clean error message added; feature non-functional until DDG unblocks
- [ ] **Dad's launcher config** — `config_dad.json` + doc NOT yet created (next session)
- [ ] **Location sorting** — sort/filter results by proximity to target city; `--sort-by location` flag or auto-apply
- [ ] **Keyword management** — user-editable keywords file (keywords.json or keywords.txt) instead of hardcoded in config.py
- [ ] **API source toggle** — user config to enable/disable Adzuna, JSearch, USAJobs, careers sources without code editing
- [ ] **Quick-edit CSV from app** — allow editing output CSV in-place (flag rows, add notes, mark applied); `--edit-csv` flag or in-terminal editor

### Git
- [x] Session 4 commit (`1d1b4fb`) — pushed to GitHub
- [ ] Session 5 work not yet committed

## Phase 2 — Resume/Cover Letter Generator ⏳ NOT STARTED

- [ ] `resume/experience_parser.py`
- [ ] `resume/generator.py` — Claude API (Sonnet)
- [ ] `resume/docx_builder.py`
- [ ] `resume/app.py` + Flask UI
- [ ] Anthropic API key not yet added to .env

## Outstanding Info Needed from Alex

- [ ] ERP tech stack (for experience.md)
- [ ] More G90 experience detail
- [ ] GD&T tools used (software + standard)
