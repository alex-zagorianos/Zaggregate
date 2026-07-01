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
- **⚠️ Same upstream as SerpApi `google_jobs` — NOT an independent source.** JSearch's
  own docs state it "pulls from Google for Jobs and the Public Web," and SerpApi's
  `google_jobs` engine reads the same Google-for-Jobs aggregation index. Running
  both widens rate-limit/quota headroom and gives some de-dup insurance (differing
  normalization/ranking), but does **not** multiply Indeed/LinkedIn coverage the
  way two truly independent sources would. `coverage/independence.py` already
  encodes this — both `serpapi` and `jsearch` collapse to the `google_jobs`
  independence family so capture-recapture coverage math (`coverage/benchmark.py`)
  counts a job found by both as ONE capture, not two. (research-2026-07-01-reach-indeed-access.md #2)

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

| Source                 | Legal risk                                | Reason skipped                                                                                                                                                                                                          |
| ---------------------- | ----------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| LinkedIn direct scrape | **medium** (civil/contract, not criminal) | Not added as a full/authenticated scraper. The public **guest** endpoint (no login) is already wired opt-in as `search/linkedin_guest_client.py` — see the dedicated writeup below for its current risk classification. |
| Indeed RSS             | n/a (dead endpoint)                       | Discontinued ~2013-2014, returns HTTP 404 today; JSearch covers Indeed with better structure                                                                                                                            |
| Glassdoor              | n/a                                       | JSearch covers it                                                                                                                                                                                                       |
| iHireEngineering       | n/a                                       | Possible future addition for niche engineering roles                                                                                                                                                                    |
| Dice                   | n/a                                       | Possible future addition for controls/embedded overlap                                                                                                                                                                  |

### LinkedIn — public guest endpoint (`linkedin_guest_client.py`) — legal_risk: MEDIUM

#scraper #linkedin #legal

**Status (2026-07-01, live-verified):** the unauthenticated `jobs-guest` HTML endpoint
(`https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search`) still
returns data, and is already wired opt-in (off by default — the user must add
`linkedin_guest` to `--sources`), rate-limited to 3 req/min (`config.py`
`LINKEDIN_GUEST_RATE_LIMIT`), no login/cookies/accounts. **It is aggressively
blocked/monitored, not silently tolerated:**

- **robots.txt** (fetched live from `linkedin.com/robots.txt`) explicitly lists
  `Disallow: /jobs-guest/` under every named crawler group, **and** ends with a
  catch-all `User-agent: * / Disallow: /` — any UA string not explicitly
  whitelisted (including our spoofed Chrome UA) falls under a blanket disallow
  of the entire site.
- LinkedIn's **Crawling Terms** (`linkedin.com/legal/crawling-terms`) separately
  flag UA-spoofing itself as a policy violation, independent of the scraping
  question.
- LinkedIn's **User Agreement §1.2** states the contract "applies to Members
  **and Visitors**" — i.e. it's drafted to bind unauthenticated/guest traffic
  too, closing the "logged-out scraping isn't ToS-bound" loophole that _Meta v.
  Bright Data_ (2024) opened for Meta specifically. §8.2 separately bans
  bots/scraping.

**Why legal_risk = medium, not low:** post-_Van Buren_ (2021) and the 9th
Circuit's _hiQ Labs v. LinkedIn_ remand (2022), scraping a page with no access
controls does **not** violate the CFAA — criminal exposure is genuinely low, and
DOJ's 2022 charging policy will not prosecute a pure ToS violation. **But** _hiQ_
itself lost on **breach of contract** even while winning on CFAA (Nov 2022
summary judgment; Dec 2022 consent judgment — $500,000 + permanent injunction to
stop scraping and destroy derived data). LinkedIn has since (2025-2026)
aggressively litigated commercial-scale LinkedIn scrapers on exactly that theory
(Proxycurl sued Jan-2025, shut down permanently Jul-2025; ProAPIs sued
Oct-2025, settled 2026) — no comparable cheap third-party LinkedIn-jobs API has
re-emerged. No case found targets an individual/hobbyist low-volume no-account
tool, which is the fact pattern our client matches (opt-in, 3 req/min, no
account, no proxy/IP rotation, no resale) — but "no known suit yet" is not "zero
risk," hence **medium**, not low.

**Posture (unchanged, now documented accurately):** keep `linkedin_guest_client.py`
opt-in/off-by-default/rate-limited exactly as-is; do **not** add proxy rotation,
IP rotation, or Scrapling-stealth bypass specifically to push past LinkedIn's
blocks (`scrape/stealth_fetch.py`'s allowlist guard enforces this — it only ever
renders a URL whose host is already in the curated company-career-page registry,
never linkedin.com/indeed.com); prefer the user-gated **browser extension**
(`browser_ext/`) as the durable, low-risk LinkedIn/Indeed channel going forward —
same legal footing as Teal/Huntr/Simplify/Jobscan's extensions (thousands of
users, no known legal action; reads the DOM of a page the user already opened in
their own session, not a bot HTTP request). Full citations:
`research-2026-07-01-reach-linkedin-access.md`, `research-2026-07-01-reach-stealth-legal.md`.

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

**Status (updated 2026-07-01):** WIRED IN — `scrape/stealth_fetch.py` + the
`scrape/direct_scraper.py:_fetch_html()` escalation described above. `scrapling`
is now version-pinned in `requirements.txt` (unpinned before 2026-07-01 — an
upgrade could otherwise silently change the default stealth engine/fingerprint
underneath us). As of Scrapling ≥0.3.13 `StealthyFetcher`'s default engine is
**Patchright** (a CDP-patched Playwright/Chromium fork), not Camoufox as
originally written above when this section was drafted against v0.4.9 docs;
Camoufox remains available as an opt-in alternate engine. Two legal-boundary
guards were added this session (research-2026-07-01-reach-stealth-legal.md):
a same-host/registry-domain allowlist (`fetch_html` only ever renders a URL
belonging to a company already in `scrape/company_registry.py` — never
LinkedIn/Indeed/an arbitrary URL) and a per-domain `RateLimiter` before every
browser escalation (previously this path had no rate limiting at all), plus an
explicit `robots.txt` Disallow check (`discover/career_link.py:is_disallowed`)
before escalating — good-faith only, not a security boundary.

## Adding a New Source

1. Create `search/newclient.py` inheriting `JobAPIClient`
2. Implement `search()` and `parse_results()`
3. Add config constants to `config.py`
4. Add env vars to `.env.example`
5. Add to `build_clients()` in `search/cli.py`
