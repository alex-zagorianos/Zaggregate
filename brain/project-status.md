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

## Session 12 — 2026-06-22 (Opus 4.8, ultracode) — hardened + rebuilt as a distributable AI-native product

Largest build session to date. Brainstormed → spec → **5 phases**, all landed. **ALL LOCAL — push HELD** (Alex chose "keep local" pending confirming GitHub `alex-zagorianos/Job-Program` is PRIVATE; `experience.md` PII already on origin). master `e0ec05e` → **`6e1ac37`, 19 commits ahead of origin, 140 → 322 tests**, tree clean, only `master` remains (all delegate/allfixes feature branches + worktrees pruned).

**Approved design (the product):** two channels on ONE engine + data folder — (1) **EXE** with hybrid AI (clipboard bridge default + optional API auto), (2) **MCP server + Claude Code skill** where Claude Code itself is the ranker. Wide-net fetch → JSON hard-gate → cheap local scorer → AI fine-rank to `preferences.md`. Spec `brain/spec-2026-06-22-distributable-product-design.md`; plans `brain/plan-2026-06-22-phase{0,1,2}-*.md` (P3/P4 inline).

- **P0 Harden:** committed the 2026-06-19 relaunch work; **merged `claude-allfixes`** (290-test backlog; resolved 3 resume conflicts — kept relaunch ATS docx base + allfixes SSOT parser/generator + re-added Projects section); folded delegate **T4 `status_history`** (SCHEMA_VERSION 1→2); **C1 recurrence guard** (new-project resume copy now opt-in, default NO); untracked personal config (`config_dad.json`/`user_config.json`); deleted dead `resume/app.py`; pruned 8 worktrees.
- **P1 Data folder + prefs contract:** `config.USER_DATA_DIR` (external editable folder: `JOBPROGRAM_DATA` env › `./data` when frozen › repo-root in dev = unchanged); `workspace.BASE_DIR` roots there (fixes frozen `_MEIPASS` write); new **`preferences.py`** (`preferences.md` NL profile + `preferences.json` hard-gate {salary_min/locations/remote_ok/work_auth/dealbreakers/seniority_exclude} + legacy migration); **`userdata.scaffold()`/`bootstrap()`** + `data_templates/` neutral seeds.
- **P2 AI ranking:** new **`ranker.py`** anchors the existing fit prompt to `preferences.md` + experience summary; `rank_via_api` runs the same prompt+parser via API (key from env or `secrets/anthropic_key`); `gate` = hard-filter. Wired into the service so InboxTab + ApplyQueueTab both rank to preferences and `daily_run` hard-gates. **Fixed a LATENT post-merge bug:** ApplyQueueTab called the new list-returning `parse_fit_response` with the old `.items()` dict API (would crash) — rerouted through `tracker_service`.
- **P3 Packaging (buildable):** `userdata.bootstrap()` self-seed wired into gui + daily_run startup; `app.spec` PII-clean (drops `experience.md`/`user_config.json`; bundles `data_templates/` + `companies.json`); **`build_package.py`** → `dist/JobScout.zip` (app + seeded `data/` next to exe + README); `preferences.{md,json}` gitignored at root.
- **P4 Claude Code channel:** **`mcp_server.py`** — 6 stdio tools via the official `mcp` SDK's `FastMCP` (`get_preferences`/`search_jobs`/`list_inbox`/`set_fit_scores`/`track_job`/`dismiss_job`; CC is the ranker, no AI in the server) + `claude-code/` (`.mcp.json` + `find-jobs` skill + README) + `requirements-mcp.txt` (kept out of the exe build).

**🟡 REMAINING — Alex's machine/decision only:** (1) confirm repo PRIVATE → **push the 19 commits**; (2) `py build_package.py` → exe build + manual GUI test (the pyinstaller run was NOT executed here; GUI is windowed → needs a live launch; watch for an `ImportError` on a lazily-imported scraper/feed client → add it to `app.spec` `hiddenimports`, currently `anthropic, docx, bs4`); (3) docx title-line decision (kept relaunch bold-concat `Company — Title`; flip to allfixes ATS-split on request); (4) optional first-run setup wizard. Full record: HANDOFF `E:\ClaudeWork\HANDOFF.md` (2026-06-22) + memory `project-job-search`.

## Session 13 — 2026-06-22 (Opus 4.8, ultracode) — measure coverage, raise it with proof, AI re-rank round-trip

Three workstreams, sequenced **measure → improve-with-proof → tailor**. All merged + **pushed** (repo confirmed private). master `6e1ac37`/`7a7dad4` → **`228b013`**, **322 → 490 tests**, tree clean, only `master` remains. Specs `brain/spec-2026-06-22-ws{1,2,3}-*.md`; plans `brain/plan-2026-06-22-ws{1,2,3}-*.md`.

- **WS-1 Coverage foundations** (merged earlier this session, `7a7dad4`): entity resolution (cleanco/rapidfuzz/datasketch, all optional behind `try/except ImportError`) + a stable **`job_key`** (`models.JobResult.job_key` cached_property → `coverage.entity.job_key_for`, `sha1` of company_canon∣soc∣loc∣title_core, 16 hex) + a **3-leg coverage benchmark** (reference-proxy ∪ capture-recapture {chapman/chao1/good_turing/loglinear} ∪ JOLTS sanity gate → weighted composite). New `_deduplicate` (URL fast-path + keyless entity key). Regression anchor `tests/fixtures/coverage/baseline.json` (synthetic Cincinnati/15-1252 pin, composite 38.2 — **not** a live area number).
- **WS-2 Coverage engine** (merged `228b013`, 17 modules / 75 tests): generic **discovery funnel** (`discover/` — Common Crawl CDX slug harvest, careers-link finder via robots/sitemap/anchors, ATS detect, user-wins `registry.merge_discovered`) replacing registry-as-seed; **Tier-1 scrapers** (`scrape/` — workable/recruitee/rippling/personio + JSON-LD schema.org extractor + XXE/billion-laughs-safe `xml_safe`); **Workday CSRF prime + offset paging** fix; **free aggregators** (`search/` — Arbeitnow/Jooble/Careerjet/LinkedIn-guest) + BYO **SerpApi** (key-gated); **geo** metro/remote filter (`geo/filter.py`); deep **title+body** matching (`scrape/text_match.keyword_matches_deep`); per-source **freshness** deltas (`search/freshness.py`); `preferences.target_roles`. **Every source gated by a coverage-lift test** proving it does not lower the WS-1 score (`test_*_lift.py`, `test_depth_lift.py` — 6 gates green). `defusedxml` added to requirements (optional).
- **WS-3 AI re-rank round-trip** (merged `14c59d7`, 20 files / 45 tests, **stdlib-only**): pluggable **`Ranker`** protocol (`ranker.py` — Bridge/Api/File rankers); inbox **export** to csv/md with a versioned prompt anchored to `preferences.md` (`rerank/export.py`); validated CSV/JSON **import** with `job_key` join (`rerank/import_.py`, `rerank/schema.py`); **`score_history`** snapshots + **undo-last-rerank** (`tracker/db.py` **SCHEMA_VERSION 2→3**, mirrors the `status_history` precedent); GUI Export/Import/Undo + MCP `export_inbox`/`import_scores`.

**Build mechanics:** authored as 3 delegate-style plans. GLM executor hit the **z.ai 5-hour usage cap** (false-green no-op — recorded as a cc-delegate reliability bug in memory `delegate-buildout`); the harness `builder` worktree-isolation also based off the wrong commit. Worked around both by building WS-2/WS-3 as **`general-purpose` Sonnet agents in manually-created worktrees off master** (`__build/ws2`, `__build/ws3`), verifying each independently (full suite + import + lift-gates), then merging `--no-ff` (disjoint file sets → zero conflicts) and re-running the suite on master. Builders found + fixed 2 WS-3 plan bugs (broken test lambda; `inbox_set_fit` second-precision ts truncation so undo reverts the whole batch) and a WS-2 Workday monkeypatch-compat regression. Worktrees + branches + 9 stale delegate job-dirs GC'd (`delegate-clean -Apply`).

**🟡 REMAINING:** (1) **live coverage baseline** — the lift-gates prove improvement on fixtures; a real area number needs a live measurement run (network/sources), best done interactively. (2) WS-3 undo's second-precision batch grouping is fine for the manual round-trip but would only partially undo a batch straddling a wall-clock second — a `batch_id` is the clean follow-up. (3) carry-over from Session 12: `py build_package.py` exe build + manual GUI launch; docx title-line decision.

## Session 14 — 2026-06-22 (Opus 4.8, ultracode) — UI/UX pass: crisp look + non-technical onboarding

A look-and-feel + usability pass so a total non-technical user can run the app unaided. Built **inline** (concentrated in `gui.py` + a new `ui/` package; visual/taste work needing a rendered eyeball; prior delegate runs hit the z.ai cap). Four confirmed decisions: **clean light & modern** theme, **all four** help surfaces, **relabel** (not hide) the AI controls, build a **first-run Setup wizard**. **Committed locally, NOT pushed** (awaiting Alex's go).

- **New `ui/` package** (keeps `gui.py` focused; fully unit-tested): `theme.py` (real ttk `clam` theme — one accent `#3b5bdb`, white surfaces, zebra tables, flat notebook tabs; widget factories `btn`/`header_bar`/`tip_strip`/`zebra`/`Tooltip`), `help.py` (scrollable **Guide** tab rendered from a `GUIDE` list + Help-menu dialogs + `open_data_folder`), `setup_wizard.py` (pure `build_preferences`/`_search_config`, `apply`, `SetupWizard`, `.onboarded` marker).
- **`gui.py`:** theme applied app-wide; **menu bar** (File/Help); 6th **❓ Guide** tab; per-tab tip strips; every `tk.Button`→`theme.btn`; zebra-striped tables; dialogs recolored; AI controls **relabeled in plain English** ("Ask AI to rank these"/"Paste AI ranking"/"Load AI results"/"Undo AI ranking"; merge dropdown "Replace it / Keep the old one / Only fill blanks"); first-run wizard auto-launches.
- **Adversarial self-review** (5-dimension Workflow → per-finding verify → synthesis): 9 findings, all verified real (1 major, 8 minor), **all fixed**:
  - **MAJOR** — wizard never collected the free-text "about" narrative (the single highest-value AI-ranking input; the generated `preferences.md` literally instructed the user to provide it) → added an optional multi-line box on the roles step, cached across re-renders, returned by `_collect()`.
  - **Project-aware preferences** (the one architectural fix) — `apply()` wrote prefs to the root while config/resume went per-project, so re-running the wizard after creating a project desynced them; `ranker`/`rerank` call `preferences.load()` bare and had the same latent **read-side** desync. Added `workspace.preferences_paths(slug)`; routed both `apply()` **and** `preferences.load()` through it. No-project common case is byte-identical (root).
  - Wizard counter "of 4" vs "three steps" copy → counter excludes the welcome intro ("Step 1–3 of 3"); **Skip now confirms**; skip/close lands the user on the **Guide** (was stranded on an empty Search tab); merge label "already scored"→"already has a Fit grade"; Guide now **defines Score-vs-Fit** and that the Inbox **starts empty** day-one; README defers to Help→Open my data folder and fixes the stale "Copy fit prompt" button name.
- **Tests:** +20 since Session 13 (14 `tests/ui/` + 6 project-aware-prefs/help) → **510** (`py -m pytest -q`, ~7s, 1 display-guarded skip headless). Live wizard-walk + full-App construct smokes pass. `app.spec` unchanged (the `ui` package is imported at `gui.py` top level → PyInstaller bundles it).

### Session 14 cont. — dark mode + deepened "use it with AI" guide (2026-06-22) ✅

Two follow-on asks, same inline approach + an adversarial review pass. **Local commit on top of the first; push still held.**

- **Light/Dark theme switch.** `theme.py` now holds `_LIGHT`/`_DARK` palettes; `set_mode()`/`current_mode()`/`toggle_mode()` rewrite the module-level color names so every `theme.X` reference picks up the active mode the next time a widget is built; `apply_theme(root, mode=None)` restyles ttk live. New `ui/settings.py` persists the choice to `USER_DATA_DIR/ui_settings.json` (best-effort; gitignored). gui.py: a **View → Dark mode** checkbutton → `_set_theme()` which persists + restyles ttk + re-syncs the legacy color aliases (`_sync_palette_aliases`) + reconfigures the root + rebuilds the project bar (grouped under `self._projbar`, packed `before=self._nb`) and the tabs (`_rebuild_tabs(select_index=…)` keeps the user's tab). Tracker status badges are now theme-aware (`theme.STATUS_BADGE`, brightened on dark). Tooltips use `TOOLTIP_BG/FG`. Saved mode applied at startup.
- **Deepened AI guidance.** `help.py` GUIDE gained "Working with AI — the heart of this app" + "Getting the most out of AI" (Score-vs-Fit, the free clipboard round-trip step-by-step, file Export/Load, feed-it-a-rich-profile, pick-a-capable-model/iterate, trust-but-verify/privacy) + a new Help → "Getting the most from AI" dialog (`show_ai_help`).
- **Adversarial review (Workflow) — partial (hit the z.ai/Anthropic session cap mid-run) but returned 4 verified findings, all fixed**, then I finished the sweep by hand: themed every un-themed `tk.Text` (PasteDialog/ResumeTab/JobDialog-notes/AddCompanies) with `bg=SURFACE/fg=INK/insertbackground=INK`; added `fg`+`selectcolor`/active colors to the InboxTab filter Source/Size/Find labels + "Unscored only" checkbutton (were black-on-dark); repointed transient status-label hex (`#e65100`/`#2e7d32`/`#666`/`#888`) to `theme.WARN/SUCCESS/MUTED`. **Accuracy fix:** the AI help had claimed an API key "ranks the inbox automatically, including the daily update" — but `rank_via_api` is only reached via `ranker.rank()`, which neither the GUI nor `daily_run` calls (daily_run only `ranker.gate`s; the GUI uses the clipboard/file bridge). Reworded so the key is correctly tied to AI **resume/cover generation**, and ranking is described as free/no-key.
- **Tests:** +13 (`test_settings.py` ×5, theme modes/badges ×6, help AI-content/accuracy ×2) → **522** (`py -m pytest -q`; 1 display-skip headless). Live dark-switch smoke: root + rebuilt tk widgets recolor, aliases re-sync, selected tab preserved, choice persists; resume/paste boxes go dark, filter labels readable, badges brightened.

## Session 15 — 2026-06-22 (Opus 4.8) — Top Picks: full-inbox AI snapshot → ranked top-X

Make the **whole relevant set trivially consumable by an AI**, let the AI judge relevance itself, and write back a **ranked top-X shortlist** that surfaces in a new GUI **Top Picks** tab. Built **inline**, TDD (brainstorm→spec→plan→approve). **Committed local, push HELD.** Handoff [[handoff_20260622_session15]]; spec `brain/spec-2026-06-22-top-picks-recommendation-design.md`; plan `brain/plan-2026-06-22-top-picks-recommendation.md`.

**Locked decisions (AskUserQuestion):** both channels (AI-consumable set **and** GUI Top Picks view) · relevant set = the **full inbox, AI judges relevance itself** · one full snapshot then rank. **Approach A** (reuse `extras` JSON + the rerank `new_rank` column) over B — top-X with **zero new DB surface**.

- **No DB migration.** Rank rides in each inbox row's existing **`extras` JSON** (`rank` + `rec_batch`); `SCHEMA_VERSION` unchanged. **Latest `rec_batch` wins** so a fresh AI run supersedes the prior shortlist. One place owns the shape: `service.rank_patch(rank, batch, tags=None)`.
- **`tracker/db.py`** `inbox_merge_extras` (key-preserving merge, tolerant of missing/non-dict blob). **`tracker/service.py`** `new_rec_batch`/`rank_patch`/`read_rank`/`top_picks(limit=10)` (latest-batch, `rank>=1`, best-first, cap). `apply_rerank_scores` untouched.
- **`rerank/`** import maps CSV `new_rank`→`extras` rank + a per-call `rec_batch`; `build_prompt` explains `new_rank` as the Top Picks signal (`RERANK_CSV_COLUMNS` frozen).
- **`mcp_server.py`** `list_inbox(limit=0)` returns the WHOLE inbox + `rank` + `job_key`; `set_fit_scores` accepts an optional `rank` (→ `inbox_merge_extras`). **`find-jobs` skill** rewritten to one-snapshot→rank.
- **`gui.py`** new **`TopPicksTab`** (rank/fit/title/company/location/why/score/source; Show-top-N 10..50/All; empty-state; Track/Dismiss/Open; themed) wired between Inbox and Search across `_build_tabs`/`_rebuild_tabs`/`_on_tab_changed`. InboxTab Export-for-AI scope toggle (default **Entire inbox**).
- **Tests:** +16 (`tests/test_top_picks.py`, `tests/ui/test_export_scope.py`, `tests/ui/test_top_picks_tab.py`, + rerank/mcp/schema extensions). Back-compat (list_inbox defaults, apply_rerank, export, existing mcp/schema) all green.

## Session 16 — 2026-06-24 (Opus 4.8, ultracode) — wire the latent gaps + mechanical-debt sweep

A familiarize → fix pass on findings from a fresh subsystem audit (9 parallel readers + a live-suite verify). All built this session; **committed local, push still HELD** (rides the Session 14/15 hold). master `6bf3722` → **+4 commits**, **553 → 572 tests** (`py -m pytest -q`, ~7s). Three behavior-changing wire-ups (all confirmed in via AskUserQuestion) + two cleanups, five clusters:

- **JSON-LD wired** (was orphaned dead code): `direct_scraper` now folds same-page schema.org/JobPosting JSON-LD into its results (deduped by `identity_key` — strictly additive, can't lower coverage); new `jsonld` ats_type; shared `_fetch_html` keeps the negative-failure cache. (`00f97f0`)
- **Discovery funnel unified** (was built-but-unreachable): new `discover/funnel.run_funnel` combines Common-Crawl-CDX harvest + per-domain careers-link finding → `registry.merge_discovered` (user-wins, additive-only), behind `py -m search.cli --discover [--discover-domains …]`. (`db82cb2`)
- **Freshness deltas surfaced** (was unintegrated): `daily_run` marks jobs new vs a project-scoped baseline (`search/freshness`, `daily:<slug>`; manual searches don't move it), stamps new inbox rows' `extras.new_batch` (schema-free, latest-batch-wins like Top Picks), GUI gains a **"New only"** Inbox filter. `JobResult.is_new` is transient; `inbox_add_many(new_batch=…)` is opt-in. (`5350056`)
- **normalize_url deduped**: `tracker/db.normalize_url` was a parity copy of `models.normalize_url` → now imported from `models` (verified byte-identical for all inputs, so the inbox `norm_url` UNIQUE key is unchanged). (`5350056`)
- **GLM-delegated mechanical bundle** (`b328f00`, via cc-delegate → glm-5.2, green/$0.65, Opus-planned+verified): `exclude_keywords` now match on **word boundaries** (was substring — "ai"⊂"maintain", "remote"⊂"remotely"); `claude_bridge.to_clipboard` **cross-platform** (clip/pbcopy/xclip/xsel) for the off-Windows distributable; `config.ANTHROPIC_MODEL` **env-overridable**; dropped the **vestigial `datasketch`** dep (never imported); `app.spec` hardened via **`collect_submodules`** (frozen-exe ImportError guard for lazily-imported app modules); scorer size-modifier docstring → its 4 bands.

Build mechanics: 9-reader audit Workflow → `AskUserQuestion` locked all 3 wire-ups in → 5 clusters built inline (TDD, each additive/lift-safe), 1 mechanical cluster delegated to GLM (fully-inlined weak-model-proof plan, file-disjoint, transferred into master after a confirming verify). +19 tests. **Doc-undercount note (now corrected here):** MCP exposes **8** tools — get_preferences/search_jobs/list_inbox/set_fit_scores/track_job/dismiss_job + **export_inbox/import_scores**; the company-size modifier has **4** bands (≤30 +8, ≤100 +4, ≤250 −2, >250 −6), not 3.

## Session 17 — 2026-06-24 (cheap-backend, autonomous) — dead-link fix + competitive Tier 1–3 buildout

Beta-test session → big autonomous build. (1) Diagnosed the AI-lane "dead links": Greenhouse
`absolute_url` is often a company JS careers SPA that never renders the job; **build the
server-rendered hosted URL** `job-boards.greenhouse.io/embed/job_app?for=slug&token=id` from slug+id
(`scrape/greenhouse_url.py`), add an inbox **liveness prune** (`scrape/inbox_health.py`,
`--prune-inbox` + GUI button, 404-only), and a repair script that fixed 914 existing rows
(browser-verified). (2) Ran a 12-agent **market-research workflow** (no product ships JobScout's
6-leg combo; closest = OSS Swiss Job Hunter 4/6) → 41 mined features (`E:\ClaudeWork\_jobscout_
features_digest.md`). (3) **Built the Tier 1–3 roadmap.** Full record: `handoff_20260624_session17`,
plan `brain/plan-2026-06-24-all-tiers-buildout.md`, decisions/questions `brain/buildout-log-2026-06-24.md`.

**Shipped:** all of **Tier 1** (T1.1 clean-dead-links + daily prune · T1.2 structured scorecard in
the detail pane via `scorer.score_breakdown` · T1.3 colored score cells · T1.4 empty states · T1.5
Tools▸Due via `db.followups_due` · T1.6 Tools▸Connect-AI key box via `config.read/write_secret` +
`ui.settings` · T1.7 Help▸Privacy) · **Tier 2** T2.8 Tools▸Funnel (`tracker/analytics.py`) · T2.9
ghost staleness + Hide-stale (`match/ghost.py`) · T2.10 skill-gap (`match/skillgap.py`) · T2.11
SmartScreen kit in `build_package.py` · T2.12 first-search on Setup finish · **Tier 3** T3.14 comp
normalizer + pay-floor filter (`match/comp.py`) · T3.18 contacts CRM (`contacts` table,
SCHEMA_VERSION **3→4**) + Tools▸Contacts · T3.22 opt-in daily discovery refresh · T3.23 T/D/O hints
· T3.24 File▸Backup/Restore. New engine modules built **in parallel via delegated worktree agents**
(Workflow), reviewed + merged; gui.py wiring done inline (single delicate file). Every new
liveness/ghost/comp/location signal is **view-level — the 0-100 score is untouched** (the
location-filter precedent).

**Not built (remaining roadmap, specced in the plan):** T2.13 browser-ext capture-on-submit; T3.15
age/repost display; T3.16 size facets; T3.17 `job_key` dedup (held — subtle); T3.19 filter presets;
T3.20 review-mode card; T3.21 onboarding checklist; T3.27 tunable weights (**Q2 — Alex's call**);
T3.28 auto-update. **Deferred (D2):** web/Tauri reskin, Gmail-OAuth email status.

**Open questions:** Q1 docx title-line; Q2 expose tunable weights?; Q3 daily auto-prune on by
default? (all default-handled, logged in the buildout log).

## Session 18 — 2026-06-25 (cheap-backend, ultracode) — modern UI (ttkbootstrap) + extension data buildout

Two requests: make the GUI modern + fix the jarring dark-mode white outlines, and build the
browser extension out to pull in as much job data as possible. Full record:
`handoff_20260625_session18`. master `1c80295`… → **+5 commits**, **683 → 696 tests**, push HELD.

**Task 1 — modern UI on ttkbootstrap.** Adopted **ttkbootstrap** as the ttk Style engine (Alex
picked "evaluate ttkbootstrap"; it passed eval — runs on 3.13, Pillow already present, no gui.py
rewrite). `ui/theme.py` stays the facade — every color name / helper / style name preserved. The
**white outlines are gone at both sources**: ttkbootstrap's element layouts are flat (the old
`clam` lightcolor/darkcolor bevel is what drew the light edge on every input), and the 5 `tk.Text`
panes now route through a new `theme.text_widget()` (themed 1px border, not the default ~white
focus ring). Modernized both palettes (indigo accent, real dark-mode surface elevation), bigger
rowheight/padding, accent-underline tabs. **Two non-obvious integration hacks** (documented in
theme.py): (a) **restore the vanilla classic-tk constructors right after importing ttkbootstrap** —
ttkbootstrap monkeypatches `tk.Frame/Label/Text` to force-recolor every classic widget to its own
palette, which would obliterate the app's hand-painted chrome (accent rules, colored status badges,
surface elevation); we want only its _ttk_ theming. (b) **build the Style singleton once and
_rebind_ it (master/tk) per root** rather than rebuilding — re-running `Style.__init__` re-triggers
a localization/msgcat init that races with pytest's many short-lived Tk roots and flakes. EXE:
`ttkbootstrap` (+submodules +localization data) + `PIL` added to `requirements.txt` + `app.spec`.

**Task 2 — extension pulls full job data.** Was card-only (title/company/location/salary), so
harvested jobs had **no description → the scorer's 25-pt skill component was always 0**. content.js
now has a **passive detail layer**: when you OPEN a job (LinkedIn/Indeed right pane or `/jobs/view`)
it reads the full **description** + a raw details blob and **upgrades that job's stored card in
place**, matched by a stable external id (LinkedIn job id / Indeed `jk`). No auto-clicking — only
jobs you open get the full record (stays "assisted, never automate"); LinkedIn + Indeed only. One
**server-side parser** owns field extraction (same DRY trick as salary, so the JS can't diverge):
`parse_details()` pulls **work mode / employment type / seniority / applicants / posted age /
easy-apply**. `_to_job_result` now threads the real **description** (honest scoring + skill-gap /
comp / ghost finally work for browsed jobs), derives `created` from the **posting age** (accurate
recency/staleness), and attaches rich metadata to the inbox row's **`extras["browse"]`** —
schema-free, **view-level, never folded into the 0-100 score**. The Inbox detail pane surfaces
"Captured while browsing: Remote · Full-time · Mid-Senior level · 47 applicants · Easy Apply"; the
popup shows "Y of N with full details" (silent detail-rot visible); `selector_check.js` now audits
the detail-pane selectors; manifest → **1.3**.

**Pre-push adversarial review** (Workflow `jobscout-session-review`, 7 agents over 5 dimensions —
theme integration, receiver parsing, extension JS, privacy/security, GUI+tests — each finding
independently verified). 2 raw findings → **1 confirmed, fixed**: an id-less detail pane (Indeed's
bare search auto-opens the first result before `vjk` is in the URL) hit the standalone-record push
with no dedup → a fresh duplicate every ~600ms observer tick (client-side only — `inbox_add_many`
dedups by `norm_url`, so the inbox never saw them). Fix: `extractDetail` now requires a
URL-identified job + the standalone push is idempotent; verified by node simulation. No
privacy/security/packaging regressions found.

**Live-verify owed (Alex, can't be done headless):** the LinkedIn/Indeed detail selectors are
best-known + generously-fallback'd but unverified against the live DOM — paste `selector_check.js`
with a job open and send the output to patch any rot.

## Session 19 — 2026-06-25 (cheap-backend, ultracode) — company-acquisition pipeline + remote-first-class

Research → plan → build. A 6-angle web-research workflow (+ adversarial fact-check of the
load-bearing stats) on **how LinkedIn/Indeed data is acquired and how jobs are actually found**
concluded: there's **no read API** for either (LinkedIn's is write-only/closed; Indeed's died ~2020),
all that's left is fragile/legally-hazardous scraping (Proxycurl, the biggest, was sued + shut down
2025), and the **safest way to touch them is the user's own browser session — exactly the existing
extension**. Structurally, LinkedIn/Indeed are **syndication layers on top of the ATS** (Greenhouse
Limited Listings + Indeed XML feeds are fed FROM the ATS), so a comprehensive **company-careers/ATS
registry captures the canonical posting, often earlier** — and **the registry (which companies to
poll) is the binding coverage constraint**, not extraction. The "80% hidden / 85% networking" stats
are debunked folklore; measured ATS data (Ashby, 38M apps) says inbound/posted applications dominate
tech hires. Residual gap of skipping the boards = the no-ATS SMB/industrial/agency tail (Indeed-only)
→ that's the extension's job. Full record: `handoff_20260625_session19`; plan
`~/.claude/plans/shimmering-moseying-wadler.md`. master → **+5 commits**, **696 → 725 tests**, push HELD.

**Built (4 phases, plan-mode approved):** **(1) Remote first-class** (`dbcc793`): `_location_score(…,
remote_ok)` credits an acceptable-remote role with full location points (was 0 — capping remote at
85/100 and burying it below local); `remote_ok` threaded through `score_job`/`score_jobs`, sourced
from `preferences.json` at daily_run/browser_receiver/GUI. **(2) Metro enumeration** (`67cd176`): the
core "add companies" engine — `discover/enumerate.py` (an LLM proposes {name,domain} for a metro +
industries; **Bridge/Api duality** like `ranker` — API if key, else clipboard-bridge) +
`enumerate_companies.py` (enumerate → resolve via `career_link`+`detect_ats` → **probe-verify gate**
→ `save_companies`). The probe gate makes LLM enumeration safe: hallucinated/dead companies resolve
to no live board and are dropped. **(3) Enterprise-ATS** (`c520849`): Workday public-URL →
`tenant:N:site` (already worked; tested); **iCIMS/Taleo/SuccessFactors** detected by host + routed to
the existing `jsonld_scraper` (their pages carry schema.org/JobPosting LD — the data Google for Jobs
reads), with a `probe_count` JSON-LD branch so enumeration can vet them. Lightweight — no bespoke
fragile API scrapers. **(4) Tiered scheduling** (`e5375d6`+`111bd84`): `scrape/tiering.py` (pure;
hot=daily/warm=weekly/cold=monthly; an active board is **never starved** so coverage can't regress)

- opt-in `CareersClient(tiered=…)` (default OFF → byte-identical) + `daily_run` `tiered_scrape` flag,
  so a 1–2k-company registry keeps the daily run fast.

**Reused ~70%:** discover/funnel + career*link + detect_ats, verify_and_add probe pattern,
company_registry.save_companies (user-wins, append-only), coverage/ benchmark + lift-gate,
geo/filter + metro_variants, ranker key/SDK + claude_bridge.\_extract_json, FileCache/RateLimiter/
ThreadPool. **Deviations (justified):** no hardcoded seed list of guessed Workday/iCIMS slugs (risks
dead entries — enumeration discovers them properly); skipped `arbeitnow` (EU-noise). **Pre-push
adversarial review** (1 agent over the diff): **no real bugs**; refined one minor wart (the cold tier
was dead in the live path → now an errored board is correctly marked cold). **Open minor:** the CLI
location-\_sort* tiebreak hardcodes remote_ok=True (inbox **scoring** honors prefs correctly).

## Git

- Sessions 14–19 = **37 local commits on `master`, NOT pushed** — awaiting Alex's `py gui.py`
  eyeball then `git push`. Now includes, on top of the S14–17 surface (colored score cells, scorecard
  detail pane, Hide-stale / Meets-pay-floor / New filters, Clean-dead-links, empty states, **Tools**
  menu [Due/Funnel/Contacts/Connect-AI], **Help▸Privacy**, **File▸Backup/Restore**): the **S18 modern
  ttkbootstrap theme + dark-mode white-outline fix** (eyeball in both light & dark), the **browser
  extension's full-detail capture** (S18), and the **S19 company-acquisition pipeline + remote-
  first-class** (metro enumeration CLI, enterprise-ATS, tiered scheduling — all opt-in/additive).
  master `fe96b71` + 37.
- **New dependency (S18):** `ttkbootstrap==1.20.4` (+ Pillow, already present) — in `requirements.txt`
  and `app.spec`. First `py build_package.py` after this needs the EXE re-tested (ttkbootstrap data +
  PIL now bundled). S19 added **no new deps** (anthropic SDK already present).
- Remote: `git@github.com:alex-zagorianos/Job-Program.git` (private).
- Full suite: **725 passed** (`py -m pytest -q`, ~9–17s; display-guarded Tk tests skip headless,
  shows as 724 + 1 skip). Python command: `py`. GUI constructs + live light↔dark toggle verified.
- Active project: `applied-ai` (672-row inbox after the S17 dead-link prune). DB schema **unchanged
  at v4** — S18 browse metadata + S19 tier state ride JSON (extras / registry_state.json; no migration).
- **S19 new entry points:** `py enumerate_companies.py` (grow the registry; API or clipboard-bridge),
  `"tiered_scrape": true` project-config flag (tiered daily run).
