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

## Desktop GUI ✅ COMPLETE (2026-05-28) — consolidates Tracker + Resume

- [x] `gui.py` — single tkinter window, two tabs, replaces the two Flask UIs for day-to-day use
- [x] **Job Tracker tab** — Treeview with sortable columns, status filter bar with counts, add/edit modal (`JobDialog`), inline quick-status combobox, delete-with-confirm, open-URL; talks to `tracker/db.py` directly (no HTTP)
- [x] **Resume Generator tab** — paste posting → generates in a daemon worker thread → writes `output/resume_DATE.docx` + `output/cover_letter_DATE.docx`, clickable output path opens the folder
- Shares the navy `#1a1a2e` palette and `STATUS_FG` colors with the web UIs

**Run:** `py gui.py` (no servers needed for tracker + resume)

> The Flask apps still exist: `browser_receiver.py` (:5002) is required for the browser
> extension's "Send to Tool", and the web tracker/resume remain as browser-based alternatives.

⚠️ **Not yet committed** — `gui.py` is untracked in git as of this writing.

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

## Persistent discovery watchlist — 2026-06-02

`--save-discovered` (CLI): auto-discovered Greenhouse/Lever companies that returned ≥1 matching job that run ("winners") are appended to `companies.json` — tagged with the run's `--industry` (fallback `discovered`) — so they become a permanent, growing watchlist scraped on every future run. Opt-in only; dedups by slug+name; preserves file comments; atomic write. `CareersClient._record_winner`/`persist_discovered` + `company_registry.save_companies`. 5 tests in `test_discovery_persist.py`.

`--prune-companies` (CLI maintenance mode, `--prune-threshold` N default 2): probes every `companies.json` entry and removes those that 404 or have an empty board for N **consecutive** runs (streak tracked in `cache/company_health.json`; transient timeouts/connection errors are "unknown" and don't penalize). Greenhouse/Lever probed for empty-board; direct probed for 404; workday slugs skipped. Hardcoded registry is never touched. `scrape/company_health.py`; 4 tests in `test_company_health.py`. Pairs with `--save-discovered` to keep the watchlist self-cleaning.

## Hardening pass — 2026-06-02

Full review ([[review-2026-06]]) + phased remediation ([[plan-2026-06]]) executed. **76 unit tests** added (the repo had none); deps were missing from the env and reinstalled. Highlights: XSS/CORS fixed; rate-limiter rewritten + JSearch monthly cap; collision-free cache keys; resume generator on tool-use + prompt caching; engine parallelized; tracker gained follow-up/deadline/contact/JD-snapshot + cross-run dedup (`--show-tracked`); new **GUI Search tab**. New modules: `search/http_util.py`, `resume/service.py`, `tests/`. Deferred items tracked in the plan. **No git operations performed** — all changes in working tree.

## Throughput overhaul — 2026-06-09 (Session 7) ✅ SMOKE-TESTED

Pipeline rebuilt around apply-throughput ([[../handoff_20260609_session7]]): scheduled daily search → local 0–100 scoring → deduped **Inbox** → optional Claude fit-ranking via **copy-paste bridge (no API key)** → **Apply Queue** with resume prompts + "Mark Applied ▸ Next".

- [x] `match/scorer.py` — 0–100: title 35/skills 25/salary 15/location 15/recency 10, −30 per exclude keyword; skills auto-parsed from experience.md; `JobResult.score`/`score_notes`
- [x] `claude_bridge.py` — fit + resume prompts via clipboard; strict-JSON parsers tolerant of fences/prose; `clip` UTF-16; works with zero API keys
- [x] `inbox` table in tracker.db (`norm_url UNIQUE` dedup vs tracked ∪ dismissed); applications gained `score`/`fit_score`/`fit_rationale`
- [x] `daily_run.py` + `setup_schedule.bat` — headless 07:30 Task Scheduler run; free sources only (jsearch excluded to protect 200/mo quota); ≥40 score → inbox; logs `output\daily_run.log`
- [x] New free sources: `search/themuse_client.py` (keyword-blind cached fetch + client-side filter), `search/remoteok_client.py` (single cached feed)
- [x] GUI now 5 tabs: **Inbox (n)** / Search (scored, prefilled, multi-select) / **Apply Queue** / Job Tracker / Resume Generator; `PasteDialog` for bridge replies
- [x] CLI: `--sort-by score` default, `--min-score`; CSV score column; HTML score badges + "Best match" sort
- [x] `resume/service.py` — bridge-first; API optional (lazy anthropic import); company-slug DOCX filenames
- [x] **SMOKE TEST PASSED** (2026-06-09): py_compile all 13 modules, imports, scorer (70 vs 0+penalty), bridge parsers (fenced + prose JSON), DB inbox migration/dedup/track/dismiss, gui import. Live `daily_run --max-pages 1`: 3564 raw → 649 deduped → 419 ≥40 → **399 new in inbox**. 2 self-review bugs fixed (badge-before-tabs TclError; missing salary in inbox fit prompt).
- [ ] No unit tests yet for scorer / bridge parsers (only manual smoke)
- [ ] `setup_schedule.bat` not yet executed (needs Alex, possibly as admin)
- [x] **Careers-noise root cause fixed** (2026-06-09, post-smoke review). Three bugs:
  1. `careers_client.py` truncated `companies[:top_n]` — REGISTRY lists 26 health-IT entries first, so with `industry: null` the 18 controls companies were **never scraped**. Now: curated registry always scraped in full; `top_n` caps only auto-discovered additions (CLI `--top-n` help updated).
  2. `daily_run.py` never passed `industry` to `build_clients` — user_config `industry` was ignored on scheduled runs. Now passed through.
  3. Scraper keyword fallback was `any(token)` — bare "engineer" matched everything (Veeva: 208 "matches"/keyword). New shared `scrape/text_match.py::keyword_matches`: exact phrase, else **all** tokens ≥3 chars (trailing-s stripped, so "controls engineer" still hits "Control Systems Engineer"). Used by greenhouse/lever/direct `_matches`.
  - `user_config.json`: `"industry": "controls_engineering"` (Dad's config_dad.json already had health_informatics).
  4. `search/remoteok_client.py`: `_STOPWORDS` strips "engineer", so keyword "R&D engineer" reduced to `[]` and the `if toks and ...` guard let the **entire 168-job feed** through (CEO, "Farmer REMOTO", etc.). Now: empty toks → return []; match on **title+tags only** (dropped the over-loose `all(t in desc)` branch).
- [x] **VERIFIED end-to-end on Opus 4.8** (2026-06-09): all modules py_compile; `text_match.keyword_matches` unit assertions pass (matches "Control Systems Engineer", rejects "Software Engineer"). Re-ran `daily_run --max-pages 1` twice. Result: careers 0 (controls registry is all CSRF Workday "direct" portals — correct to yield 0 vs 2989 health-IT spam); **inbox 233**, sources adzuna 186 / themuse 14 / usajobs 13 / remoteok 20 (was 168). Top matches all on-target (CNC Field Service, Mechanical Design, Automation, Industrial Eng); junk tail gone. Score min/median/max 40/57/78.
  - NOTE: careers source now contributes ~0 for controls until real Greenhouse/Lever controls boards are added or Workday CSRF is solved — the API sources (Adzuna/USAJobs/TheMuse/RemoteOK) carry the pipeline.
- [x] **10 scrapeable hardware/robotics boards added to controls registry** (2026-06-09, slugs verified live via boards-api.greenhouse.io / api.lever.co): GH — spacex, andurilindustries, **pathrobotics (Columbus OH)**, formlabs, flyzipline, nuro, redwoodmaterials, relativity (Relativity Space); Lever — zoox, brightmachines. Rejected (404): shieldai, skydio, stokespace, hadrian, agilityrobotics, relativityspace.
- [x] **Verified live + 2 more bugs fixed** (2026-06-09, Opus 4.8). Re-ran `daily_run --max-pages 1`; careers jumped 0 → **~1016 results** (SpaceX, Anduril, Relativity, Zoox, Caterpillar, etc.). Two issues found and fixed: 5. `cache_helpers.slug_safe` didn't strip `:` → every Caterpillar (Workday slug `cat:5:CaterpillarCareers`) cache write threw `[Errno 22] Invalid argument` on Windows. Now regex-sanitizes all Windows-reserved chars `[<>:"/\|?*,\s]` → `_` (alphanumeric slugs unchanged, so no cache invalidation; `&` kept — filename-legal). Caterpillar now returns 20/keyword. 6. greenhouse/lever scrapers hard-coded `description=""` → all 580+ careers jobs scored identically (~52), since the scorer's 25-pt skill component had nothing to read. Now: greenhouse populates from `job["content"]` (`_clean_content`: html.unescape + strip tags + collapse ws, cap 3000); lever from `descriptionPlain`. **Score spread 52→59 median, top now genuinely Alex-shaped** (Mechatronics Engineer, Mfg Engineer Analytics, Machine Vision/Automation, SpaceX Mfg Tool & Die all 76–78). Matching still uses title+departments only (tight); description used for scoring only.
  - Final inbox: **959 jobs**, careers 726 / adzuna 186 / remoteok 20 / themuse 14 / usajobs 13. Big-board volume (Anduril 311, SpaceX 188) is fine — best matches sort to top, generic ones sink; no per-company cap needed.

- [x] **Session 8 (2026-06-09): 4-agent improvement analysis + Phase 1 + Ashby implemented & VERIFIED on Opus 4.8.** All 11 modules py_compile; `_smoke_phase1.py` all-pass (salary regex, recency neutral+decay, word-boundary skills, size modifier small84/unknown76/mega70, round-robin+migration on temp DB, fit-prompt size context); `_smoke_user_companies.py` all-pass (companies.json merge 49 entries/filters correct, user-added "User Test Robotics Co"/pathrobotics scraped 2 jobs w/ 3000-char desc — flow works end-to-end). Live `daily_run --max-pages 1`: per-company cap trimmed **977→394 (−583 Anduril/SpaceX flood)**; 44 new→inbox 1003. Round-robin inbox: first 10 rows = 10 different companies; **Gecko Robotics (bc=16, +8 boost) now tops the inbox at 82, above Anduril/SpaceX** — exactly the intended skew fix. Smoke files deleted. NOTE: the 959 pre-existing inbox rows predate board_count capture (show bc=-1/neutral) and were inserted before the cap, so Anduril 311/SpaceX 188 still physically present — round-robin handles them at display layer; a one-time cache-bypass re-run or inbox trim would backfill/cap them if wanted. Agent reports synthesized: ranking (scores cluster: title=35 pre-matched, salary constant-neutral, recency biased), sources (Common Crawl CDX slug enumeration = biggest find lever; Ashby/SmartRecruiters/HN-Algolia/Remotive/Jobicy/Himalayas endpoint-verified; Brave free tier dead since Feb 2026, now $5/mo), apply (~10–15 min/app → ~5–7 with batch resume prompts + canned ATS answers), skew (cap + round-robin beats supply alone).
      **Implemented (all uncommitted):**
  1. `models.py`: `JobResult.board_count` — total postings on the company board, free size proxy (−1 unknown).
  2. `greenhouse_scraper.py`: captures `meta.total`; `created` prefers `first_published` over `updated_at` (kills big-board "always fresh" bias). `lever_scraper.py` + new `ashby_scraper.py` set `board_count=len(postings)`.
  3. `tracker/db.py`: inbox `board_count` column + ALTER migration; `inbox_all(order="roundrobin")` default via `ROW_NUMBER() OVER (PARTITION BY company …)` — first screen = best job per company (`order="score"` = old).
  4. `daily_run.py`: per-company insert cap (`max_per_company`, default 15, 0 disables; in user_config.json).
  5. `match/scorer.py`: word-boundary skill matching (kills 'pid'⊂'rapid'); `salary_from_text` recovers pay ranges from descriptions (annualizes hourly, 30k–500k bounds, fills salary_min/max); recency unknown → 0.5 neutral (was 0), exponential 10-day half-life; size modifier ≤30→+8, ≤100→+4, >250→−6 (in score_notes).
  6. `company_registry.py`: **18 verified small/mid boards added** (5/5 spot-checked live): GH formic(31) agilityrobotics(43) apptronik(90) locusrobotics(19) carbonrobotics(24) tulip(60) paperlessparts(14, CNC shops) fictiv(70) divergent(56) ursamajor(38) stokespacetechnologies(54) seurat(3) outrider(6); Lever dexterity(8) osaro(10) copia(9, Git-for-PLC) ambirobotics(8); **Ashby gecko-robotics(10, Pittsburgh)**. Dead-slug list in comments. Earlier "agilityrobotics 404" was transient — live.
  7. New `scrape/ashby_scraper.py` (api.ashbyhq.com, verified; salary from compensation tiers, fail-soft) + `ats_type="ashby"` dispatch + companies.json instructions.
  8. `gui.py`: Inbox Size column (S/M/L/XL); `_copy_fit_prompt` no-selection default = unscored, max 2/company; `claude_bridge.py`: "Board openings: N" per job + small-company preference instruction in fit prompt.
  9. Smoke tests written, NOT run: `_smoke_phase1.py`, `_smoke_user_companies.py` (companies.json merge + live user-entry scrape). Delete after passing.
     **companies.json gotcha (traced):** with `industry` set, user entries with a non-empty `industries` list lacking the tag are silently filtered; empty list always passes.
     **Phase 2 remaining:** HN Algolia client, Remotive/Jobicy/Himalayas, SmartRecruiters, Common Crawl enumeration. **Phase 3:** batch resume prompts, cover-letter persistence (gui.py discards `_cover`), canned ATS answers, follow-up reminders, status-history analytics.

- [x] **Session 8 cont. (2026-06-09): Phase 2 sources + Phase 3 quick wins + browser→inbox — WRITTEN then VERIFIED LIVE on Opus 4.8.**
  1. New feed clients (RemoteOK pattern — single cached feed, client-side `keyword_matches` filter): `search/remotive_client.py` (≤4 fetches/day courtesy; salary text prepended to desc for `salary_from_text`), `search/jobicy_client.py` (50 jobs/engineering category; no salary fields), `search/himalayas_client.py` (paginated to 500; **pubDate unix→ISO**; min/maxSalary annualized via salaryPeriod yearly/monthly×12/weekly×52/hourly×2080, 30k–500k bounds; location from locationRestrictions).
  2. `search/hn_client.py` — 2-step Algolia: latest `author_whoishiring` "Who is hiring" story (cached) → per-keyword comment search; parses first-line `Company | Role | Location`; skips comments without pipes (replies); url=news.ycombinator.com/item?id=…; source_api="hn". Startup-heavy = small-company lever.
  3. `scrape/smartrecruiters_scraper.py` — list endpoint has NO descriptions; per-MATCH detail fetch (jobAd sections, cached per posting, capped 15/board/keyword); board_count from `totalFound`; url jobs.smartrecruiters.com/{slug}/{id}. Wired as `ats_type="smartrecruiters"` in careers_client dispatch + companies.json instructions + CompanyEntry docstring. No SmartRecruiters companies in registry yet — add when found.
  4. Wiring: config.py constants (REMOTIVE/JOBICY/HIMALAYAS/HN blocks) + DAILY_SOURCES += remotive,jobicy,himalayas,hn; cli.py ALL_SOURCES + build_clients deferred imports; user_config.json sources +4 true. daily_run/GUI pick up automatically.
     **VERIFIED LIVE (Opus 4.8, 2026-06-09):** (a) all 13 touched modules py_compile ✓. (b) Per-client smoke: Remotive 27-feed→8 SWE matches, fields/salary-prepend/dates ✓ (0 controls — remote board, software-skewed, expected); Jobicy 50-feed→44 matches, ISO dates ✓; **Himalayas BUG FOUND+FIXED** — API hard-caps 20/page & ignores `limit`, so the `len(batch)<PAGE_SIZE` break stopped after 1 page (20 jobs); now pages by `offset += len(batch)` to MAX_JOBS, PAGE_SIZE→20, MAX_JOBS→200 (10 reqs/cold-cache); re-test 200-deep→46 matches/16 w/salary; unix→ISO + annualization confirmed (added `annual`/`daily` to factor map — API returns "annual" not "annually"); HN thread 48357725 found→78–80 postings, `Company|Role|Location` parse ✓. (c) Full pipeline via cli.py: 191 raw→172 dedup, all 4 scored ✓. (d) `daily_run --max-pages 1`: integrated, cap 1028→445, **7 new→inbox (1010)**, exit 0 ✓ — niche hardware keywords yield few remote-board hits (Himalayas 2, HN 80; remote boards are bonus coverage, HN is the small-co lever). (e) DB migrations cover_path/follow_up_date/board_count all present; follow-up auto-set +7=2026-06-16 ✓; browser-receiver route parse→score(70, skills 0% as documented)→inbox ✓.
  5. **Phase 3 quick wins (same session, VERIFIED):** `tracker/db.py` +`cover_path` column (migration + \_EDITABLE); `gui.py` Apply tab persists cover letter path on both bridge-paste and API paths (was discarded); Mark Applied auto-sets `follow_up_date = today+7` when empty; Tracker header shows amber "N follow-up(s) due" count (statuses applied/phone_screen/interview, date ≤ today).
     **Phase 3 remaining:** batch resume prompts (~5 jobs/paste), canned ATS answers panel (apply/canned.py), status-history table + response-rate analytics, resume A/B variant column + filename collision fix (resume/service.py:61). **Phase 4:** Common Crawl CDX slug enumeration script (biggest find lever; ~95k slugs via Feashliaa/job-board-aggregator + index.commoncrawl.org CC-MAIN-2026-21).
  6. **Browser extension → inbox integration (same session, routing VERIFIED):** `browser_receiver.py /harvest` now also routes harvested jobs through `score_jobs` → `inbox_add_many` (no min-score floor — hand-picked; fail-soft so report still saves on DB error; response gains `inboxed` count); popup.js shows "N new to inbox". Route tested: fake LinkedIn card → salary recovered (120k–140k) → scored 70 → inboxed 1 ✓. Extension code intact & JobResult-compatible; **remaining risk = content.js selector rot (selectors from 2026-05-27, LinkedIn churns DOM) — only verifiable by ALEX browsing with extension loaded + `py -m scrape.browser_receiver` running.** Harvested jobs have empty descriptions (card scrape) → skill component 0; Claude fit prompt is the ranking signal for them.

- [ ] **Session 8 cont. 2 (2026-06-10, fable, shell blocked): post-review improvement pass — WRITTEN, NOT yet compiled/tested.**
      From the 7-point review Alex approved with "Start doing those". All code-only items done; shell items queued below.
  1. `match/scorer.py`: empty description → skill component **0.5 neutral** (was 0 — buried HN/browser-harvest/direct jobs 25 pts under described jobs for a data gap, not a signal). Docstring updated.
  2. `resume/service.py`: filename collision fixed — two roles at the same company on the same day now get `_2`, `_3` numeric suffixes instead of overwriting (checks both resume* and cover_letter* names).
  3. **Negative-failure caching** (`scrape/cache_helpers.py` `mark_failed`/`is_failed`): dead slugs (404/timeout) were retried for every keyword every run (~15 dead registry entries × 10 keywords ≈ 150 doomed requests/run). Now one attempt per TTL window. Wired into all 6 ATS scrapers: greenhouse/lever/ashby/smartrecruiters use `{"_failed": true}` JSON markers in both except blocks; `direct_scraper.py` uses string sentinel `"<!--fetch-failed-->"` (its cache is raw HTML text); `workday_scraper.py` uses a separate company-level `workday_{slug}_FAILED.json` (its results cache is per-keyword).
  4. `gui.py` **InboxTab UX overhaul**: (a) sortable column headers — click to sort (numeric cols score/fit/size start desc), click again to flip, third click returns to round-robin default; client-side over cached snapshot; ▲/▼ arrows in headings. (b) Filter bar: min score, source dropdown (auto-populated), size (S/M/L/XL/?), unscored-only checkbox, title/company text find, Clear button — all client-side, count label shows "N of M awaiting triage". (c) **Keyboard triage**: `t`=track, `d`=dismiss, `o`=open URL bound on the tree; selection auto-advances to the next row after track/dismiss (`_focus_index`/`_restore_focus`), so a screen can be cleared without the mouse. (d) Detail line → 4-line read-only Text pane: fit*why/score_notes + 600-char description preview. (e) **Dismiss Company** button: bulk-dismisses every \_visible* (filtered) row from the selected row's company, with confirm — the fast way to clear one mega-board's flood.
  5. **Batch resume prompts (~5 jobs/paste)**: `claude_bridge.py` — `_experience_corpus` factored out; `_BATCH_RESUME_INSTRUCTIONS` (JSON array, per-object `"i"` + the standard resume keys, "tailor each individually"); `build_batch_resume_prompt(postings, experience)`; `parse_batch_resume_response` → `{i: resume_data}`, skips malformed/incomplete objects (falls back to array position when `"i"` missing), raises only if nothing usable. `resume/service.py` — `build_batch_prompt(postings)` wrapper. `gui.py` ApplyQueueTab — `_BATCH_LIMIT = 5`; "Batch Prompt (5)" picks selected rows else walks the queue top-down, taking jobs that **still need docs AND have a saved description** (no per-job paste stop in batch mode), headers `Title/Company/Location` prepended, ids in `_batch_order`; "Paste Batch ▸ DOCX" saves each via `save_bundle_from_data(company=…)` (collision-safe now), updates `resume_path`/`cover_path`, fail-soft per item with an error rollup + "N missing from the reply" notice. Cuts the per-app prompt round-trips ~5×.
     **Queued for shell (Opus or recovered fable):** py_compile of the 12 touched files (gui.py, claude_bridge.py, match/scorer.py, resume/service.py, scrape/cache_helpers.py + 6 scrapers); GUI launch smoke (filter/sort/keys, batch buttons); negative-cache smoke (`*_FAILED.json` markers appear, second run skips); `py daily_run.py --prune-companies` to clean dead registry entries; **git commit (4 sessions uncommitted — Alex must approve)**.
     **Awaiting Alex's approval:** one-time trim/backfill of the 959 legacy inbox rows (bc=−1, pre-cap Anduril 311/SpaceX 188). **Still open from review:** canned ATS answers panel (apply/canned.py) — last unstarted item.

## Outstanding — Needs Alex

- [ ] `ANTHROPIC_API_KEY` in `.env` — get from console.anthropic.com
- [x] ~~ERP tech stack in `experience.md`~~ — resolved; placeholder filled, no placeholders remain (`experience.md` has uncommitted edits)
- [ ] `BRAVE_SEARCH_API_KEY` in `.env` — optional, free at api.search.brave.com; enables company auto-discovery
- [ ] **Commit `gui.py`** — currently untracked; also stage `experience.md` working-copy edits

## Session 9 — 2026-06-14 (Opus 4.8) ✅ ALL COMMITTED + PUSHED through 1493571

Caught up the repo and shipped four features + a bug fix. Spec: [[spec-2026-06-14-archive-search-projects]]. All verified; full suite **127 passing**.

- **Committed the 4-session backlog** (`627bce6`) and pushed — repo was stuck at `8fa925b`. The 2026-06-10 uncompiled pass was py_compile'd + smoke-verified first.
- **Fix: Workday/Caterpillar links** (`53e9469`). CXS `externalPath` is site-relative (`/job/...`) → `host+path` 404'd. `workday_scraper._job_url()` inserts the site (`/CaterpillarCareers/job/...`); `scripts/fix_workday_urls.py` backfilled **107/107** existing inbox links. Live-verified 200.
- **Archive** (soft-delete) (`df6aa52`). `applications.archived` col; `archive_job`/`unarchive_job`; `get_all`/`get_counts` exclude archived + `"archived"` filter. Tracker tab: Delete→**Archive**, Archive(n) chip, archive view = Restore + Delete-permanently. Archived stays in `tracked_urls()` (no resurface).
- **Search tightening** (`b74d696`). `search/query.py` boolean keywords (`"phrase"`, OR, NOT/-, ()) — back-compat; wired into `text_match` + scorer. Scorer downranks (never hides): `title_miss_penalty` (35), `exclude_titles` blocklist (profile-specific, **default empty** so Dad's data roles aren't hit; Alex's list in `user_config.json`), `seniority_exclude`. `scripts/rescore_inbox.py` ran → AI/ML/Data titles → 0, on-target kept (Mechatronics 79). `--list`/threaded through cli/daily/gui.
- **Job-Search Projects** Phases 0–3 (`54200ca`, `1375889`). `workspace.py` = call-time per-project path resolution (root fallback pre-migration). `scripts/migrate_to_projects.py` ran: 1098 inbox → `projects/controls-cincinnati/` (active), `dad-health-informatics` empty; `.bak` + row-parity OK. Repointed db/experience/output/config seams. GUI **project switcher** header (dropdown + New) rebuilds tabs live (controls 1098 ↔ dad 0). `--project` on cli/daily. `projects/` + `*.bak` gitignored (local data). **Phase 4 (per-project scheduler) DEFERRED** — the only remaining Projects work.
- **Add Companies via GUI** (`5457594`). `scrape/ats_detect.py`: `detect_ats` (greenhouse/lever/ashby/smartrecruiters/workday + direct), `parse_line`, `probe_count` (live count). Search tab **"+ Add Companies"** dialog: paste URLs → auto-detect → Validate → save to companies.json tagged with the project's industry. Live-verified counts.

**Open / next:**

- Projects **Phase 4** (per-project scheduler: `daily_run --project` is done; need per-project `setup_schedule.bat` + `daily` flag wiring).
- `setup_schedule.bat` still never run (07:30 task unregistered).
- Tooling could add: company **remove/edit** UI (currently hand-edit companies.json), Projects "Manage" (rename/delete).
- `tracker.db.bak` left in root (safety; gitignored) — delete after a release.

### Session 9 cont. — browser-extension verification (2026-06-14) ✅

Verified the LinkedIn/Indeed "collect while scrolling" pipeline end-to-end via Claude-in-Chrome live audit. Commits `64ff8ea`, `14bdd31` (pushed).

- **Receiver** (`browser_receiver` /harvest → score → inbox): verified live (POST → scored → inbox, cleanup); **fixed** it to thread `exclude_titles`/`title_miss_penalty`/`seniority_exclude` (was missing the search-tightening; harvested AI Engineer now → 0).
- **Indeed selectors: healthy** — 18/18 cards, title/company/location 100% (via the existing `data-jk`/`data-testid` fallbacks; primary `h2.jobTitle a` dead but chain holds). No change.
- **LinkedIn selectors: had silently rotted** (LinkedIn moved to `artdeco-entity-lockup`). Fixed in `content.js`: promoted the working lockup selectors to primary for company/location; **salary** now reads `.artdeco-entity-lockup__content` (was uncaptured — sits in the 2nd of two metadata wrappers w/ randomized class) and server `_parse_salary` pulls the $ (verified 5/5 salaried cards); **title de-dup** (LinkedIn repeats title in a hidden span → "T\nT", now first-line only). manifest 1.1→1.2.
- New `browser_ext/selector_check.js` = paste-in DevTools console self-audit for future rot.
- **NOTE for next use:** Alex must **reload the unpacked extension** (chrome://extensions → reload Job Harvester) to pick up v1.2; LinkedIn collection needs him logged in; `py -m scrape.browser_receiver` must run for "Send to Tool". The Claude-in-Chrome MCP tab is NOT logged into LinkedIn — selector re-audits need either his login in the controlled window or the console snippet in his own tab.

## Session 10 — 2026-06-15 (Opus 4.8) — Full review + first Hermes test slice

Full multi-agent code+product review of the whole app. **Complete findings → [[review-2026-06-15]]** (50 subsystem findings + 26 feature ideas + GUI audit + product roadmap + architecture recs + adversarial verdicts). **No code changed this session** — review + planning only.

**Headlines:**

- 🔴 **C1 (LIVE data bug):** `projects/dad-health-informatics/experience.md` is Alex's master file byte-for-byte (the migration copied it) → Dad's resumes/scoring use the wrong person's career.
- 🔴 C2 `daily_run` has no top-level error trap (silent dead 07:30 runs); 🔴 C3 `.exe` would crash on first use (no `.spec`, templates/quota under `_MEIPASS`); 🔴 C4 no global Tk exception handler (windowed `.exe` swallows errors); 🔴 C5 no WAL/`busy_timeout` on the shared `tracker.db`.
- Prior [[review-2026-06]] items are **mostly fixed**; the scorer is genuinely strong. The GUI is a **god-FILE not a god-object** — the fix is splitting `gui.py` into a package in Python, not a rewrite.
- Adversarial pass: score-compression (SCORE-1) and `norm_url` query-strip (TRACK-4) were **overstated** — real but smaller than first claimed; everything else confirmed; 6 cross-cutting items the readers **missed** (incl. C1 and inbox-score-staleness MISSED-3).

**Hermes test harness built** — `E:\ClaudeWork\hermes-test-01-jobapp\`: the first "Claude plans → Hermes executes" E2E test (the canonical job-search test from `MASTER-local-ai-stack` §P6). A high-value, unit-testable **8-fix slice** (query parser ×3, HN cache, salary parse, `_extract_json`, CSV injection, DB WAL, `daily_run` guard, dad-data + new-project seed) is written two ways: `plan.md` (Nemotron — **Windows-native**: one self-verifying `py` script per task in `staging\`, validated end-to-end → suite 140) and `claude-fallback-plan.md` (Claude). **Not yet run by Hermes.** 13 new tests; commits at end (no push); dad file backed up to `.bak`.

**Open / next (full list in [[review-2026-06-15]] §Recommended sequencing):**

- [ ] Run the Hermes test (or the Claude fallback) to apply the 8-fix slice → see `hermes-test-01-jobapp\START-HERE.md`.
- [ ] Then: C3 (`.exe`) + C4 (Tk handler) → Wave 2 `.exe` readiness → Wave 3 status-history analytics spine → Wave 4 `gui/` decomposition + service layer → Wave 5 ranking/apply polish.
- Output mode this session: **TERSE**.

## Session 11 — 2026-06-15 (Opus 4.8) — Hermes RAN the test + editing experiment staged

- **Test #01 EXECUTED by Hermes (Nemotron 30B) and PASSED.** It applied all 9 review-slice fixes via the Windows-native plan and **committed** them: **`e0ec05e`**, tree clean, **140 passing**. The "doom loop" Alex saw was only the `progress.md` free-form append (botched newline → retry loop) — the real work was done + committed. **Fixed:** staging scripts now self-log; `plan.md`/`START-HERE`/`SKILL` updated so the model never touches `progress.md`, + an anti-loop rule. Harness: `E:\ClaudeWork\hermes-test-01-jobapp\` (Windows-native, 11 `py` commands).
- **Test #02 BUILT (not yet run)** — `E:\ClaudeWork\hermes-test-02-edit\`: the real cost/capability experiment where **Claude writes only test + spec and Hermes writes the code.** 3 open fixes (SEARCH-5, SCORE-7, SEARCH-6), gradient edit→add→write-method. Validated achievable (Claude impl → 147 passing; reverted to clean 140). Run via its `START-HERE.md`; measure **how** Nemotron edits.
- **Learning:** the script approach saved ~no Claude tokens (Claude did the engineering); real savings = the test-02 division of labor. File-editing is the goal; the discipline is _verified_ editing (a test gate), not avoiding edits. Full detail: [[handoff_20260615_session11]].

> **HEAD is now `e0ec05e`, clean, 140 passing** (supersedes the stale `## Git` block below).

## Git

- HEAD `14bdd31` on `master`, **pushed; working tree clean.** Everything through Session 9 (backlog, Caterpillar fix, Archive, Search tightening, Projects 0–3, Add-Companies, browser-ext verification) is committed + on origin.
- Remote: `git@github.com:alex-zagorianos/Job-Program.git`
- Full suite: **127 passing** (`py -m pytest -q`). Python command: `py`.
- Active project workspace: `projects/controls-cincinnati/` (1098-row inbox). Switch via GUI header or `--project`.
