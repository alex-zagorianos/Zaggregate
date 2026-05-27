# Project Status

#status #roadmap

## Phase 1 — Job Scraper ✅ SUBSTANTIALLY COMPLETE (2026-05-26)

### API Sources
- [x] Adzuna API client — working, tested
- [x] JSearch (RapidAPI) — working, key in .env
- [x] USAJobs — working, key in .env
- [x] Multi-source architecture (base class, dedup, HTML report with source badges)
- [x] CLI: `py -m search.cli` with full flags

### Career Page Scraper (session 4)
- [x] `scrape/` module scaffolded
- [x] Greenhouse scraper — public JSON API, confirmed working
- [x] Lever scraper — public JSON API, confirmed working
- [x] Direct scraper — BeautifulSoup best-effort (limited on Workday/JS pages)
- [x] Company registry — `REGISTRIES` dict, 2 industries (28 health informatics, 19 controls)
- [x] `CareersClient` — slots into existing pipeline, `--sources careers`
- [x] New CLI flags: `--top-n`, `--industry`, `--no-discover`
- [ ] DuckDuckGo auto-discovery — coded, NOT live-tested
- [ ] **Workday scraper — NOT BUILT** (biggest gap; most large employers use Workday)
- [ ] User-editable companies file (currently hardcoded in Python)
- [ ] Dad's launcher / UX (CLI is not dad-friendly)

### Git
- [x] Initial commit made (`c5b98ed`) — pushed to GitHub
- [ ] Session 4 work not yet committed

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
