# HANDOFF 2026-05-26 | Session 4 — Career Page Scraper (Phase 1 Extension)

## SESSION SUMMARY
Built a hybrid career page scraping module (`scrape/`) that adds a fourth job source: direct company career pages. Uses Greenhouse and Lever public JSON APIs (no auth) for the majority of targets, plus a BeautifulSoup fallback for direct pages. Introduced a structured company registry with two industries (health_informatics, controls_engineering), extensible by adding new dict keys. Added DuckDuckGo auto-discovery (coded, not yet live-tested). Also added all three API keys to .env and made the initial git commit + push to GitHub.

---

## WHAT GOT DONE

### API Keys & Git
- JSearch (RapidAPI) key added to `.env`
- USAJobs key + email added to `.env`
- All three sources live-tested and working
- Bug fixed: `None` location/created fields crashing dedup and sort — fixed in `models.py` and `search/search_engine.py`
- **Initial git commit made** (`c5b98ed`) — 24 files, 1,567 lines
- **Pushed to GitHub**: `git@github.com:alex-zagorianos/Job-Program.git`

### Career Scraper Module (`scrape/`)
New files created:
- `scrape/__init__.py`
- `scrape/cache_helpers.py` — shared `read_cache()`, `write_cache()` (atomic via `.tmp` + `os.replace()`), `slug_safe()`
- `scrape/company_registry.py` — `CompanyEntry` dataclass + `REGISTRIES` dict (2 industries, 47 companies total); `get_registry(industry)` function
- `scrape/greenhouse_scraper.py` — hits `boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true`, caches per-company, filters by keyword in title/department
- `scrape/lever_scraper.py` — hits `api.lever.co/v0/postings/{slug}?mode=json`, caches per-company, converts ms epoch timestamps
- `scrape/direct_scraper.py` — BeautifulSoup link extraction for non-ATS pages (best-effort, limited on JS-rendered Workday pages)
- `scrape/discoverer.py` — DuckDuckGo HTML search for `site:boards.greenhouse.io "{keyword}"` and `site:jobs.lever.co "{keyword}"`, parses slugs, caches HTML 24h
- `scrape/careers_client.py` — `CareersClient(JobAPIClient)` shim: page 1 runs full pipeline + returns serialized results; page >1 returns `{}` to break SearchEngine pagination loop; parallel scraping via `ThreadPoolExecutor`

### Modified files
- `requirements.txt` — added `beautifulsoup4==4.12.3`
- `config.py` — added `CAREERS_MAX_WORKERS`, `CAREERS_DDG_SLEEP_SECONDS`, `CAREERS_REQUEST_TIMEOUT`
- `search/cli.py` — added `"careers"` to `ALL_SOURCES`; new flags `--top-n`, `--industry`, `--no-discover`; `build_clients()` signature updated
- `search/templates/report.html` — added `.source-careers` CSS (blue badge) + "Careers" dropdown option

### Slug Verification (2026-05-26)
Live-tested against both APIs. **Confirmed working:**
| Company | ATS | Slug |
|---|---|---|
| Inovalon | greenhouse | `inovalon` |
| Doximity | greenhouse | `doximity` |
| Elation Health | greenhouse | `elationhealth` |
| athenahealth | greenhouse | `athena` |
| CareDx | greenhouse | `caredxinc` |
| PointClickCare | lever | `pointclickcare` |
| Arcadia | lever | `arcadia` |
| Veeva Systems | lever | `veeva` |

**All other companies in the registry** (Epic, Caterpillar, Honeywell, etc.) use Workday or custom portals — marked as `direct` with their real careers URLs. BeautifulSoup scrapes them best-effort but Workday pages are JS-rendered and likely return little.

---

## SMOKE TEST RESULTS
```
py -m search.cli --keywords "health informatics" --sources careers --top-n 8 --no-discover --industry health_informatics
→ 12 results (Inovalon: 6, CareDx: 1, Veeva: 6 — minus 1 dedup)  ✅

py -m search.cli --keywords "analyst" --sources careers --top-n 5 --no-discover --no-cache --industry health_informatics
→ 9 results (Doximity: 6, Inovalon: 3)  ✅
```

---

## NOT DONE YET

- [ ] **DuckDuckGo discovery NOT live-tested** — coded but never actually fired against DDG. May need debugging.
- [ ] **Workday scraper NOT built** — biggest coverage gap. Most large employers (Epic, Caterpillar, Honeywell, Rockwell, Optum, etc.) use Workday. Workday has a consistent JSON endpoint: `https://{company}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/External/jobs` — no JS needed, returns JSON. Slug/tenant discovery is the hard part.
- [ ] **User-editable companies file** — adding companies requires editing Python. Should load from a `companies.json` or `companies.yaml` at runtime.
- [ ] **Dad's launcher / UX** — CLI is not dad-friendly. Needs a `.bat` double-click launcher or Flask web UI with pre-configured keywords.
- [ ] **Git commit for session 4 work** — not yet committed
- [ ] Phase 2 (resume generator) not started
- [ ] Outstanding experience.md items: ERP tech stack, more G90 detail, GD&T tools

---

## NEXT SESSION PRIORITIES
1. Live-test DuckDuckGo discovery: `py -m search.cli --keywords "health informatics analyst" --sources careers --top-n 10 --industry health_informatics` (no `--no-discover`)
2. Build Workday scraper — JSON endpoint approach, find 2–3 known tenant slugs to test against (Epic: `epiccareers`?, Caterpillar: `cat`?)
3. User-editable `companies.json` — load additional companies at runtime, merged with registry
4. Dad's launcher — `.bat` file + `config_dad.json` with his keywords pre-set
5. Git commit + push session 4 work

## REGISTRY STRUCTURE (for reference)
```python
# To add a new industry:
REGISTRIES["my_industry"] = [
    CompanyEntry("Company Name", "greenhouse", "slug-here", ["my_industry", "tag2"]),
    CompanyEntry("Another Co",   "lever",      "slug-here", ["my_industry"]),
    CompanyEntry("Big Corp",     "direct",     "https://careers.bigcorp.com/", ["my_industry"]),
]
```
CLI usage: `--industry my_industry`

## ENVIRONMENT NOTES
- Python command: `py` (NOT `python`)
- No virtual environment — packages installed globally
- All API keys in `.env` (gitignored) — Adzuna ✅, JSearch ✅, USAJobs ✅, Anthropic (empty)
- GitHub: `git@github.com:alex-zagorianos/Job-Program.git` (SSH, key configured)
