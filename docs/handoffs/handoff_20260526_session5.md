# HANDOFF 2026-05-26 | Session 5 — Workday Scraper + companies.json + DDG Diagnosis

## SESSION SUMMARY
Worked through four of five planned tasks. Committed Session 4 work, built the Workday scraper (`scrape/workday_scraper.py`), added a user-editable `companies.json` system wired end-to-end through the CLI, and live-tested DuckDuckGo discovery (non-functional — DDG bot-challenges all requests; added clean error message). Dad launcher config was not started.

---

## WHAT GOT DONE

### Task 1 — Git Commit
- Staged and pushed all Session 4 work: `scrape/` module (8 new files), config.py, requirements.txt, search/cli.py, search/templates/report.html, brain/project-status.md
- Commit: `1d1b4fb` — "Add career page scraper module (Phase 1 extension)"

### Task 2 — Workday Scraper
New file: `scrape/workday_scraper.py`

**How it works:**
- `CompanyEntry.slug` format for Workday: `"tenant:N:site"` (e.g., `"cat:5:CaterpillarCareers"`)
- Endpoint: `POST https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs`
- Body: `{"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "keyword"}`
- **Critical: limit must be ≤ 20** — Caterpillar returns HTTP 400 for limit > 20
- Job URL constructed as: `https://{tenant}.wd{N}.myworkdayjobs.com{externalPath}`

**CSRF investigation results (2026-05-26):**
| Company | Slug | Status |
|---|---|---|
| Caterpillar | `cat:5:CaterpillarCareers` | ✅ Works — CSRF disabled |
| Honeywell | `honeywell:5:Honeywell_Jobs` | ❌ HTTP 422 — CSRF enabled |
| Parker Hannifin | `phstock:1:Parker_Hannifin` | ❌ HTTP 422 — CSRF enabled |
| Rockwell Automation | `rockwellautomation:1:External` | ❌ HTTP 422 / 404 |
| Siemens | `siemens:3:Siemens` | ❌ HTTP 401 |
| Epic Systems | `epiccareers:5:External` | ❌ HTTP 422 — CSRF enabled |
| Optum/UHG | `uhg:5:External` | ❌ HTTP 422 — CSRF enabled |
| Meditech | `meditech:3:meditech` | ❌ HTTP 422 — CSRF enabled |

CSRF-protected tenants (all but Cat) were reverted to `"direct"` type in the registry with their correct Workday URLs. The infrastructure is in place — if browser support is added later, these can be switched to `"workday"` type.

**CareersClient wired up:** `elif company.ats_type == "workday": return scrape_workday(...)`

### Task 3 — User-Editable companies.json
- `companies.json` created in project root — ships with example entries (skipped at load if `_example` key present)
- `config.py`: added `COMPANIES_JSON = BASE_DIR / "companies.json"`
- `company_registry.py`: added `_load_user_companies()` + updated `get_registry()` to merge user entries (user wins on name collision)
- `search/cli.py`: added `--companies-file PATH` flag; plumbed through `build_clients()` → `CareersClient(companies_file=...)` → `get_registry(user_json=...)`
- `scrape/careers_client.py`: added `companies_file` param; passes to `get_registry()`

**JSON format:**
```json
{
  "companies": [
    {
      "name": "My Company",
      "ats_type": "greenhouse",
      "slug": "mycompanyslug",
      "industries": ["health_informatics"]
    }
  ]
}
```
Entries with `"_example"` key are ignored. No `"name"` key = skipped.

### Task 4 — DuckDuckGo Discovery Live Test
- Live-tested: DDG returns a bot-challenge page (`anomaly.js?cc=botnet`) for all requests
- Both `html.duckduckgo.com/html/` (POST) and `lite.duckduckgo.com/lite/` (GET) blocked
- Fix: added detection in `_ddg_fetch()` — if `"anomaly.js"` or `"cc=botnet"` in response HTML, prints: `"[discover] DuckDuckGo bot challenge — discovery skipped (try again later)"`
- **Discovery is non-functional until a different search provider is wired in or DDG unblocks**
- Possible future fix: use Brave Search API (free tier), SerpAPI, or Google CSE

---

## NOT DONE

- [ ] **Dad's launcher config** (`config_dad.json` + launch doc) — session ended before this
- [ ] **Session 5 not yet committed** to GitHub
- [ ] Phase 2 (resume generator) — not started
- [ ] Outstanding experience.md items: ERP tech stack, G90 detail, GD&T tools

---

## NEXT SESSION PRIORITIES

1. **Git commit** — Stage and push Session 5 work (workday_scraper.py, updated company_registry.py, careers_client.py, cli.py, config.py, companies.json, discoverer.py, brain/project-status.md)
2. **Dad launcher config** — Create `config_dad.json` (pre-set keywords, health_informatics industry) + `launch_dad.md` documenting the single CLI command; `.bat` file is a trivial follow-up once this exists
3. **Location sorting** — Add sorting/filtering of results by proximity to a target city. Currently results are unordered by geography. Options: distance-rank using geopy or simple state/city string match; expose via `--sort-by location` CLI flag or auto-apply when `--location` is set
4. **Keyword management** — Add a way to add/edit search keywords without touching Python. Options: `keywords.json` or `keywords.txt` file loaded at runtime (like companies.json), and/or a `--add-keyword` CLI flag that appends to it. Currently keywords are hardcoded in `config.py DEFAULT_KEYWORDS`
5. **API source toggle** — Add a way to enable/disable individual API sources (Adzuna, JSearch, USAJobs, careers) without editing code. Could be a `config_sources.json` or flags saved to a user config file; `--sources` flag already exists but requires typing each time
6. **Quick-edit CSV from app** — After a search, allow the user to open and edit the output CSV directly from the app (e.g., flag rows, add notes, mark applied). Could be a `--edit-csv` flag that opens the CSV in the default editor, or a lightweight in-terminal table editor
7. **Phase 2 kickoff** — Start `resume/` module: `experience.md` structure first, then `experience_parser.py`, then generator scaffold
8. **DDG alternative** (lower priority) — Consider Brave Search API (free, no CAPTCHA) as drop-in replacement for discovery

## MODIFIED FILES (Session 5, not yet committed)
```
scrape/workday_scraper.py       — NEW
scrape/company_registry.py      — updated: workday type, _load_user_companies, get_registry merge
scrape/careers_client.py        — updated: workday dispatch, companies_file param
scrape/discoverer.py            — updated: bot challenge detection
search/cli.py                   — updated: --companies-file flag
config.py                       — updated: COMPANIES_JSON path
companies.json                  — NEW (template, project root)
brain/project-status.md         — updated
```

## ENVIRONMENT NOTES
- Python command: `py` (NOT `python`)
- No virtual environment — packages installed globally
- All API keys in `.env` (gitignored) — Adzuna ✅, JSearch ✅, USAJobs ✅, Anthropic (empty)
- GitHub: `git@github.com:alex-zagorianos/Job-Program.git` (SSH, key configured)
- Last pushed commit: `1d1b4fb`
