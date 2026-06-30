# Scraping Sources

#phase1 #scraper #apis

## Active Sources

### Adzuna ✅ WORKING

- **Type:** REST API
- **Cost:** Free — 2,500 req/month
- **Coverage:** General job board, good US coverage
- **Results per page:** 50
- **Rate limit:** 25 req/min
- **Auth:** `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` in `.env`
- **Docs:** https://developer.adzuna.com/

### JSearch (RapidAPI) ⏳ KEY NEEDED

- **Type:** REST API via RapidAPI
- **Cost:** Free — **200 req/MONTH** (conserve carefully — ~10 full runs/month with 10 keywords × 1 page)
- **Coverage:** Aggregates Indeed + LinkedIn + Glassdoor — biggest coverage boost
- **Results per page:** 10
- **Rate limit:** 5 req/min (self-imposed to protect monthly budget)
- **Auth:** `JSEARCH_RAPIDAPI_KEY` in `.env`
- **Get key:** https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch
- **⚠️ Use `--max-pages 1` for JSearch to conserve budget**

### USAJobs ⏳ KEY NEEDED

- **Type:** REST API (federal government)
- **Cost:** Free — generous limits
- **Coverage:** Federal jobs only — relevant for GE Aerospace, AFRL (Wright-Patt), DoD contracts near Cincinnati
- **Results per page:** 25
- **Rate limit:** 50 req/min
- **Auth:** `USAJOBS_API_KEY` + `USAJOBS_USER_AGENT` (your email) in `.env`
- **Register:** https://developer.usajobs.gov/
- **Location note:** Must use `"Cincinnati, OH"` format (state required)

## Evaluated But Not Added

| Source                 | Reason skipped                                                                                                                                               |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| LinkedIn direct scrape | Actively blocks, ToS risk, JSearch covers it — but `linkedin_guest_client.py` + **Scrapling stealth** (below) is the unblock path if JSearch budget runs out |
| Indeed RSS             | JSearch covers Indeed with better structure                                                                                                                  |
| Glassdoor              | JSearch covers it                                                                                                                                            |
| iHireEngineering       | Possible future addition for niche engineering roles                                                                                                         |
| Dice                   | Possible future addition for controls/embedded overlap                                                                                                       |

## Tooling: Scrapling — stealth/JS fetch backstop

#scraper #tooling #candidate

**What:** [Scrapling](https://github.com/D4Vinci/Scrapling) (D4Vinci, v0.4.9, BSD-3, ~67k★) — a fully-local, free Python scrape/fetch framework. **Not a search tool** (no discovery) — it ingests URLs we already have. It's the fetch upgrade for the pages our current `requests.get` path can't get.

**Why it fits THIS project:** our `scrape/*` clients use plain `requests` + `BeautifulSoup`. That fails on (a) **JS-rendered SPA career pages** (returns empty shell) and (b) **anti-bot / Cloudflare / 403** (LinkedIn, Workday, some direct career sites). Scrapling solves both locally, free, with no API budget to conserve (unlike JSearch's 200 req/mo). It also returns clean output, cutting tokens when a page is handed to the AI rerank/parse pass.

**Three fetchers, escalate by difficulty:**

- `Fetcher` — fast HTTP w/ browser TLS-fingerprint impersonation, no browser launched (drop-in for `requests`)
- `DynamicFetcher` — Playwright/Chromium, renders JS/SPA pages
- `StealthyFetcher` — Camoufox stealth, solves Cloudflare Turnstile + interstitials
- `adaptive=True` selectors auto-relocate after a site's HTML drifts (heuristic — validate on big redesigns)

**Where to wire it (the seam):** `scrape/direct_scraper.py:_fetch_html()` — today it does `requests.get(...).text` and `mark_failed()` on exception. Add a **fallback**: when `requests` returns empty/JS-only HTML or raises 403/anti-bot, retry with Scrapling before giving up. Same pattern applies to `workday_scraper.py` (JS-heavy) and `linkedin_guest_client.py` (blocked).

```python
# fallback inside _fetch_html, after the requests attempt fails / returns empty
from scrapling.fetchers import StealthyFetcher  # import lazily — heavy (browser binaries)

page = StealthyFetcher.fetch(company.slug, headless=True,
                             network_idle=True, solve_cloudflare=True)
if page.status == 200:
    html = page.html_content        # rendered HTML → existing BeautifulSoup / jsonld_scraper path unchanged
```

_(Confirm exact method/param names against installed v0.4.9 docs — the fetcher API has shifted across versions.)_

**Install (Win11):**

```powershell
pip install "scrapling[fetchers]"   # parser + 3 fetchers (no MCP needed for in-app use)
scrapling install                   # one-time: pulls Chromium + Camoufox binaries
```

**Rules of use (don't regress the cheap path):**

1. **Backstop, not default.** Keep `requests`/`BeautifulSoup` as the first try (fast, no browser). Only escalate to `DynamicFetcher`/`StealthyFetcher` on empty-JS or block — stealth = real browser overhead (slower, more RAM).
2. **Lazy-import** Scrapling inside the fallback so a normal run doesn't pay the import cost.
3. **ToS still applies** — stealth removes the technical block, not the legal/ToS question. LinkedIn stays low-volume/last-resort; prefer JSearch/API sources.
4. Respect the existing **negative-failure cache** (`mark_failed`) so we don't browser-retry known-dead URLs every run.

**Alternatives considered:** Crawl4AI (has built-in LLM extraction — overkill, we extract via JSON-LD/BS4 + the rerank pass); Firecrawl/Jina (hosted, paid, data leaves machine). Scrapling wins here on free + local + strongest turnkey anti-bot.

**Status:** CANDIDATE — not yet wired in. Adopt when direct/Workday coverage starts losing pages to JS/anti-bot.

## Adding a New Source

1. Create `search/newclient.py` inheriting `JobAPIClient`
2. Implement `search()` and `parse_results()`
3. Add config constants to `config.py`
4. Add env vars to `.env.example`
5. Add to `build_clients()` in `search/cli.py`
