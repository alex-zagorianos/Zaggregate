---
title: Plan — expand job-board coverage (Indeed + more), field-agnostic, cheap & ToS-aware
date: 2026-06-30
status: plan (NOT built)
author: Opus planner subagent
tags: [plan, sources, indeed, scraping, scrapling, tos, coverage]
---

# Plan: more boards (Indeed + high-value), $0/near-$0, ToS-aware

## The load-bearing finding: DON'T build an Indeed scraper

Indeed has **no free, ToS-clean, machine-readable search endpoint**: organic/single-source
XML feeds discontinue 2026-03-31, there's no read search API, and `indeed.com/jobs` has
aggressive anti-bot (Cloudflare/PerimeterX-class) + a ToS ban on automated access. There is
no LinkedIn-guest analog. So a stealth Indeed client is an explicit **non-goal**. The repo
already reaches Indeed three legal ways it just doesn't fully exploit:

1. **JSearch** (`search/jsearch_client.py`) aggregates Indeed/LinkedIn/Glassdoor/ZipRecruiter
   via Google-for-Jobs (free 200/mo) — excluded from DAILY_SOURCES to protect the cap.
2. **SerpApi** (`search/serpapi_client.py`) proxies Google Jobs (surfaces Indeed) and can
   run `engine=indeed` (paid).
3. **Browser extension** (`browser_ext/content.js`) already parses Indeed cards + detail →
   `scrape/browser_receiver.py` ($0, uses the user's own browsing session).

### Indeed recommendation

- **Free default:** JSearch (already Indeed-capable) — document it as the Indeed route;
  optional opt-in to DAILY_SOURCES with a low `max_pages` guard (MonthlyQuota already caps it).
- **Best paid:** make `SerpApiClient` engine-selectable → `engine=indeed`/`google_jobs`
  (config-gated, small change).
- **Zero-cost manual:** the extension already harvests Indeed; just refresh selectors vs
  current DOM (Indeed churns class names) — maintenance, not new architecture.
- **Rejected:** standalone stealth Indeed scraper (ToS + brittle). Primary risk; called out.

## Other boards — ranked (value × feasibility × ToS)

| Board                                             | Method                                                    | Verdict                                                   |
| ------------------------------------------------- | --------------------------------------------------------- | --------------------------------------------------------- |
| Google Jobs                                       | SerpApi (built) / JSearch                                 | free win, already wired                                   |
| Indeed                                            | JSearch (free) / SerpApi engine=indeed (paid) / extension | see above                                                 |
| Muse/RemoteOK/Remotive/Jobicy/Himalayas/Arbeitnow | API                                                       | already present                                           |
| ZipRecruiter / Glassdoor / Monster                | JSearch / SerpApi / extension                             | **aggregation/extension only, no scraper** (ToS)          |
| Dice                                              | extension / JSON-LD (opt-in stealth)                      | no official API; schema.org JobPosting present            |
| Built In                                          | GUEST/STEALTH JSON-LD                                     | good JSON-LD guest candidate if robots permit             |
| Wellfound/AngelList                               | stealth SPA                                               | low ROI, defer                                            |
| **Niche field boards** (agnostic)                 | ATS / JSON-LD via companies.json                          | **the real agnostic lift — mechanism not hardcoded list** |

**Field-agnostic insight:** most niche boards (health: Health eCareers/HIMSS; eng: IEEE/ISA;
etc.) run on a known ATS (Greenhouse/Lever/Workday) or expose schema.org JSON-LD — already
harvested by `careers_client` + `jsonld_scraper` + the discovery funnel + `companies.json`.
So the agnostic win is mostly **feeding niche-board employers into `companies.json`** (ties to
the company-coverage plan), NOT per-board clients. Only boards with a clean cross-employer
JSON/RSS feed justify a dedicated `SingleFeedClient` — build case-by-case behind the lift-gate.

## New-client template (two shapes)

- **A. Keyword-parameterized** (query per keyword): subclass `JobAPIClient` (like Adzuna),
  set `parallel_keywords = True`.
- **B. Keyword-blind feed** (fetch once, filter client-side): subclass `SingleFeedClient`
  (like Arbeitnow/Himalayas), do NOT set parallel_keywords (one unit; per-instance paging
  state would race).
  Common: `FileCache`/`cache_subdir`, conservative `config.<NAME>_RATE_LIMIT`, `cache_key(...)`
  including every result-changing param, `page>1` short-circuit for single-page feeds,
  key-optional graceful-degrade (warn + return `[]`, never raise — only hard-keyed clients raise
  in `__init__`, caught in `build_clients`), `parse_results → JobResult` (stable md5 job_id,
  ISO created, salary annualized), register in `cli.ALL_SOURCES` + `build_clients` + `config`,
  join DAILY_SOURCES only if keyless+reliable+polite. Tests: fixture parse + registration +
  lift-gate.

### Worked example — Indeed via SerpApi engine (the recommended concrete change)

- `config.py`: `SERPAPI_ENGINE = os.getenv("SERPAPI_ENGINE", "google_jobs")` (or "indeed").
- `serpapi_client.py::search`: use `config.SERPAPI_ENGINE` (was hardcoded google_jobs at :67).
  `engine=indeed` returns a DIFFERENT JSON shape → `parse_results` branches defensively
  (unknown shape → `[]`). Include engine in `cache_key("serpapi", engine, kw, loc, page)`.
- Optional `"serpapi_indeed"` alias for separate cache/quota accounting.
- Tests: extend `test_serpapi.py` with an indeed-shape fixture + cache-key-includes-engine.

## Scrapling / stealth policy

Escalate only when a source is not API/aggregation-reachable, NOT login-walled, robots-permitted,
AND requests returns 403/JS-shell. Reuse the existing `direct_scraper._fetch_html` ladder (no
second path). Gate on `config.SCRAPLING_FALLBACK and stealth_fetch.available()`; missing pkg →
`[]`, never raise. Low RateLimiter (≤2–5/min) + 24h cache; never page deep with headless.
**Pitfall:** `network_idle=True` can hang on SPA boards → hard timeout + `network_idle=False` +
selector wait, degrade to None. **ToS hard rules:** respect robots (read Disallow), NO
login/cookie/account scraping (rules out deep LinkedIn/Indeed/Glassdoor), personal/low-volume
framing; ToS-banned boards (Indeed/Glassdoor/Wellfound) = aggregation/extension only, never stealth.

## Dedup & coverage-lift gating

- Dedup already collapses by `normalize_url` then keyless `(company, title_core)`. **Syndication
  risk:** aggregator redirect URLs (`indeed.com/rc/clk?…`, google redirects) won't normalize to
  the canonical ATS URL → look distinct → row inflation. Fix: extend `normalize_url` tracking-
  param/redirect unwrapping; add `test_dedup_accuracy.py`.
- **Lift-gate (per new source):** reuse `coverage/benchmark.run_benchmark` +
  `tests/search/test_aggregator_lift.py`: assert `after.n_clusters >= before` AND
  `composite_score >= before`. A source that only adds dupes → flat n_clusters → don't ship
  enabled. More independent sources also tighten the capture-recapture estimate (≥3 sources
  enables the log-linear path).

## Files

Modified: `config.py` (SERPAPI_ENGINE + new-client constants), `search/serpapi_client.py`
(engine select + shape branch + cache key), `search/cli.py` (register + ToS notes),
`browser_ext/content.js` (optional selector refresh), `models.py`/`search_engine.py`
(normalize_url redirect unwrap). New: `search/<board>_client.py` per dedicated board.
Tests: `test_serpapi.py`, `test_cli_registration.py`, `test_aggregator_lift.py`,
`test_dedup_accuracy.py`, `test_<board>.py` + fixtures.

## Risks

Indeed anti-bot/ToS → aggregation+extension only. SerpApi indeed shape → defensive branch.
Redirect URLs defeating dedup → unwrap + test. network_idle hang → timeout. Free-tier burn
(JSearch 200/mo, SerpApi 100/mo) → keep out of DAILY_SOURCES, MonthlyQuota caps. Extension
selector rot → multi-selector fallbacks (periodic maintenance). New source lowers signal →
lift-gate blocks it.

## Open questions

1. **Paid SerpApi/JSearch OK for a real daily Indeed pull?** Free caps (100–200/mo) won't
   sustain daily; stay free+extension, or budget a few $/mo?
2. Which niche verticals to prioritize for companies.json seeding (agnostic lift)?
3. Refresh the extension's Indeed/Glassdoor/Dice selectors vs live DOM now, or leave as-is?

## Unverifiable / out of scope

- Did not hit live endpoints (read-only + user live-testing): confirm content.js Indeed
  selectors vs current DOM + whether SerpApi free tier enables engine=indeed before shipping.
- Out: standalone stealth Indeed/Glassdoor scraper, authenticated scraping, paid Apify actors,
  hardcoded niche-board list (use ATS/JSON-LD + companies.json mechanism), Wellfound deep scrape.
