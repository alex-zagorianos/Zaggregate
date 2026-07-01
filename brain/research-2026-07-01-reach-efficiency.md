---
title: "Research: Efficiency at 10k-100k boards — conditional fetch, tiering, concurrency, AI cost control"
date: 2026-07-01
status: research (not approved for build)
tags: [research, efficiency, scraping, ats-api, caching, cost]
---

# Efficiency roadmap: staying fast/cheap as the registry grows from ~450 to 10k-100k boards

`companies.json` today is ~3,158 lines (a few hundred companies). Session 22-23 already
built the coverage pipeline that will grow this 20-300x. This note asks: **what breaks,
and what's the cheapest fix, as N climbs into the 10k-100k range?**

## 1. What JobScout already has (grounded in code, verified, not re-litigated)

- **Concurrency**: [search/search_engine.py](../search/search_engine.py) fans out
  `(client, keyword)` units over `ThreadPoolExecutor(max_workers=SEARCH_MAX_WORKERS=12)`
  for the API aggregators; [scrape/careers_client.py](../scrape/careers_client.py) fans
  out one future per company over `ThreadPoolExecutor(max_workers=CAREERS_MAX_WORKERS=8)`.
- **Caching**: [scrape/cache_helpers.py](../scrape/cache_helpers.py) — atomic
  read/write JSON, `CACHE_TTL_HOURS=24` for content, `FAILED_TTL_HOURS=168` (7d)
  negative-cache for dead boards (`config.py:153-159`).
- **Tiered scheduling**: [scrape/tiering.py](../scrape/tiering.py) — hot/warm/cold at
  1/7/30-day intervals (`DEFAULT_INTERVALS`), classified by last-run hit count; a
  never-seen or hot board is always due, so tiering can only _defer_ quiet/dead boards.
  Wired opt-in via `CareersClient(tiered=True)`.
- **Rate limiting**: `search/http_util.py`'s `RateLimiter` (sliding 60s window,
  thread-safe) and `MonthlyQuota` (persistent JSON counter) are applied to the **API
  aggregators only** (Adzuna 25/min, JSearch 5/min+200/mo, USAJobs 50/min, Muse 20/min,
  Himalayas 5/min, HN 10/min, etc. — `config.py:107-270`). **The careers scrapers
  (Greenhouse/Lever/Ashby/…) have no rate limiter at all** — only the
  `CAREERS_MAX_WORKERS=8` concurrency cap and per-request timeouts
  (`CAREERS_REQUEST_TIMEOUT=12`, `CAREERS_SLOW_TIMEOUT=20` for Workday).
- **Retry/backoff**: `make_session()` wraps every aggregator request in urllib3
  `Retry(total=3, backoff_factor=0.5, status_forcelist=(429,500,502,503,504))`. The
  careers scrapers use bare `requests.get`/`.post` with no retry policy.
- **No conditional-fetch layer exists anywhere** — no ETag/Last-Modified storage, no
  `updated_after`-style params on any ATS client.

## 2. The single highest-leverage finding: conditional GET already works, today, undocumented

None of Greenhouse, Lever, or Ashby document `If-None-Match`/ETag support. I verified
directly against three boards already in `companies.json` (Rocket Lab/Shield AI/Crusoe):

```
GET boards-api.greenhouse.io/v1/boards/rocketlab/jobs
  -> ETag: W/"a27f3418b15b47ca5fe207e8862553fe"; Cache-Control: max-age=0, private, must-revalidate
GET api.lever.co/v0/postings/shieldai?mode=json
  -> ETag: W/"4e949b-bKojy3NVHwZpRjRXvBC1M7FgUoI"   (body was 5.1 MB)
GET api.ashbyhq.com/posting-api/job-board/crusoe?includeCompensation=true
  -> ETag: W/"job-board:2fafa5f..."; Cache-Control: public, max-age=60, stale-while-revalidate=60  (body 5.6 MB)
```

Re-requesting each with `If-None-Match: <etag>` returned **`304 Not Modified`, 0 bytes,
on all three.** This is not documented API behavior — it's their CDN (CloudFront for
Greenhouse, Cloudflare for Ashby) honoring standard HTTP validators — but it's real,
free, and works on unauthenticated public endpoints, per [MDN's conditional-requests
guide](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Conditional_requests)
and [Google's crawler ETag guidance](https://fylo.com/post/googles-updated-crawler-guidelines-now-recommend-using-etags).
Lever/Ashby boards routinely run multiple MB (the whole board, unfiltered, is fetched
per company); most boards don't change day to day, so most of that transfer — and the
JSON-parse + title-filter CPU — is currently pure waste, repeated every time
`CACHE_TTL_HOURS` expires.

**Workable is the exception**: `apply.workable.com/api/v1/widget/...` (the public,
no-key widget endpoint `scrape/workable_scraper.py` actually calls) returns no
ETag/Last-Modified and rejects `HEAD` (404) — no conditional-GET path exists on the
free tier. The `updated_after`/`created_after` params documented at
[workable.readme.io/reference/jobs](https://workable.readme.io/reference/jobs) belong
to Workable's **authenticated Recruiting API** (per-account API key), not the public
widget — out of reach unless a user later BYO's a Workable key.

## 3. Per-ATS incremental-fetch matrix

| ATS                                             | Public/no-key endpoint JobScout uses                         | `updated_after`-style param                                                                                                                                                               | Conditional GET (ETag)                                                                                     | Notes                                                                                      |
| ----------------------------------------------- | ------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| **Greenhouse**                                  | `boards-api.greenhouse.io/v1/boards/{slug}/jobs`             | None on job-board API ([docs](https://developers.greenhouse.io/job-board.html)); only `content=true`                                                                                      | **Yes (verified)**                                                                                         | `updated_at`/`first_published` fields exist per-job for client-side diffing after a 200    |
| **Lever**                                       | `api.lever.co/v0/postings/{slug}?mode=json`                  | None on public Postings API ([lever/postings-api](https://github.com/lever/postings-api)); `updated_at`-range filters exist only on Lever's separate authenticated Data/Opportunities API | **Yes (verified)**                                                                                         | Boards can be multi-MB; ETag is the whole win here                                         |
| **Ashby**                                       | `api.ashbyhq.com/posting-api/job-board/{slug}`               | None on public posting-api ([docs](https://developers.ashbyhq.com/docs/public-job-posting-api)); `jobPosting.list` (authenticated GraphQL) has `updatedAt`                                | **Yes (verified)**, plus explicit `Cache-Control: public, max-age=60`                                      | Server already says "safe to cache 60s"                                                    |
| **Workable**                                    | `apply.workable.com/api/v1/widget/accounts/{slug}`           | `updated_after`/`created_after` exist only on the authenticated `workable.readme.io` API                                                                                                  | **No** (no ETag/Last-Modified, HEAD unsupported)                                                           | TTL + tiering is the only lever                                                            |
| **SmartRecruiters/Recruitee/Rippling/Personio** | company-scoped public JSON endpoints                         | Not documented                                                                                                                                                                            | Untested this session — same CDN-fronted pattern is plausible; worth a 5-minute curl check before building | Treat as "maybe" until verified per-vendor                                                 |
| **Workday**                                     | POST `wd5.myworkdayjobs.com/wday/cxs/.../jobs` (CSRF-primed) | No public delta param                                                                                                                                                                     | **No** (POST body-search API, not resource GET)                                                            | Already gets the slower `CAREERS_SLOW_TIMEOUT`; TTL/tiering only                           |
| **jsonld/direct (generic company sites)**       | arbitrary company URL                                        | N/A                                                                                                                                                                                       | Sometimes — many static/CDN-fronted career pages emit Last-Modified; opportunistic only                    | A cheap `HEAD` before `GET` can skip unchanged pages even with zero ATS-specific knowledge |

## 4. Recommendations, ranked (effort/impact)

1. **[P0, low effort, high impact] Store + send ETag/If-None-Match for Greenhouse,
   Lever, Ashby.** Extend `cache_helpers.write_cache`/`read_cache` (or a thin wrapper)
   to persist `{"etag": ..., "body": ...}` alongside the existing cache file; each
   `*_scraper.py` sends `If-None-Match` when a stored ETag exists and, on `304`, reuses
   the cached body instead of re-parsing. This is additive to the existing 24h TTL (it
   doesn't replace it — a 304 still counts as "checked," so `FAILED_TTL`/tiering logic
   is untouched) and is the same mechanism GitHub/Google recommend for well-behaved
   crawlers. At current board sizes (Lever/Ashby up to 5+ MB) this is the difference
   between megabytes and ~200 bytes per unchanged board, every run.

2. **[P0, low effort, high impact] Add a per-ATS-domain RateLimiter to
   `careers_client.py`**, reusing the existing `search/http_util.RateLimiter` class
   verbatim. Today `CAREERS_MAX_WORKERS=8` bounds _concurrency_ but nothing bounds
   _rate_ — fine at a few hundred companies, but Greenhouse/Lever/Ashby each host
   **thousands of unrelated customers behind one shared domain**; at 10k-100k boards on
   these three ATSes, 8 concurrent unthrottled workers can burst well past what a
   shared CDN tolerates before it starts 429/503-ing everyone, including other
   well-behaved integrators. A conservative per-vendor-domain cap (e.g. 60-120/min,
   tune per observed 429 rate) costs one `RateLimiter()` instantiation per ATS type.

3. **[P1, low effort, medium impact] Add retry/backoff to the careers scrapers.** They
   currently use bare `requests.get`/`.post`; wrap with the same `make_session()`
   already built in `http_util.py` so a transient blip doesn't `mark_failed()` (and
   thus cold a board for 7 days) on a single bad request.

4. **[P1, medium effort, medium impact] Stagger the tiered due-set.** `tiering.is_due`
   is correct but unstaggered — every hot board becomes due on the same day-boundary,
   so a 100k-board hot tier still bursts all at once. Add a deterministic per-slug
   jitter (hash the company key into a 0-N-hour offset within its interval window) so
   the daily run's due-set — and thus its wall-clock and burst rate — smooths instead
   of spiking. Also worth ordering the due-set hot-first, so an interrupted run still
   completes the highest-value boards.

5. **[P1, medium effort, high impact at scale] Budget the daily run explicitly.**
   Illustrative math at 100k companies with a typical hot/warm/cold split (10%/30%/60%):
   daily due ≈ 10,000×1 + 30,000/7 + 60,000/30 ≈ **16,300 boards/day**, not 100,000 —
   tiering is already the dominant lever. Combined with conditional GET (most of that
   16,300 resolve to a 304 in <1s with near-zero bytes), an 8-16 worker thread pool
   comfortably clears this in well under an hour; without conditional GET, the same
   run means tens of GB of mostly-redundant JSON and a much longer wall-clock purely
   from parsing bodies nothing changed in. **Conditional GET and tiering multiply, not
   add** — do both.

6. **[P2, medium effort, low-medium impact] Opportunistic `HEAD`+Last-Modified for the
   `jsonld`/`direct` generic path.** No ATS knowledge required; a cheap `HEAD` before
   the full fetch on custom career pages skips unchanged static/CDN-fronted pages. Skip
   for JS-rendered SPAs (Scrapling fallback) where `HEAD` is meaningless anyway.

7. **[P2, low effort, real but bounded impact] Anthropic prompt caching for any
   frontier-model step that survives** (per `spec-2026-06-29-ai-pipeline-optimization.md`,
   frontier is optional/off by default — Task B batches ~10 jobs/call sharing one
   rubric). Mark the static rubric block with `cache_control: {"type":"ephemeral"}`
   (5-min TTL pays back after the 2nd batch in a run; break-even math from
   [Anthropic's prompt-caching docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching):
   cache write = 1.25x input once, then 0.1x reads). This is a small win **on top of**
   the already-planned local-model-first architecture — it only matters when a
   frontier polish/calibration pass is actually invoked, but costs nothing to wire in
   now since the rubric text is already a fixed, reused block per run.

8. **[P3, larger effort, defer] Async rewrite (httpx/aiohttp) of the careers fetch
   loop.** Not justified yet — these are I/O-bound calls and Python threads scale fine
   to low hundreds of concurrent sockets; the real ceiling at 10k-100k boards is
   **vendor-side courtesy limits** (item 2), not Python's threading model. Revisit only
   if per-host rate limiting itself becomes the bottleneck (i.e., you're intentionally
   spreading load across dozens of distinct ATS vendor domains simultaneously and
   thread-pool overhead — not politeness — is the wall-clock driver).

## 5. What NOT to do

Don't lower `CACHE_TTL_HOURS` to "fetch more often" as a freshness fix before doing #1
— that multiplies exactly the redundant-megabyte problem this note identifies. Once
conditional GET is in place, a _shorter_ content TTL becomes nearly free (a 304 costs
~200 bytes), so freshness and efficiency stop trading off against each other.

## Sources

- [Greenhouse Job Board API docs](https://developers.greenhouse.io/job-board.html)
- [Lever postings-api (GitHub)](https://github.com/lever/postings-api)
- [Ashby Public Job Posting API](https://developers.ashbyhq.com/docs/public-job-posting-api)
- [Workable /jobs API reference](https://workable.readme.io/reference/jobs) (authenticated API; public widget endpoint has no equivalent)
- [MDN: HTTP conditional requests](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Conditional_requests)
- [MDN: If-None-Match header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/If-None-Match)
- [Google crawler ETag guidance summary](https://fylo.com/post/googles-updated-crawler-guidelines-now-recommend-using-etags)
- [Anthropic prompt caching docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [Anthropic API pricing 2026 overview](https://www.finout.io/blog/anthropic-api-pricing)
- Empirical: live `curl -I` / conditional-GET checks against `boards-api.greenhouse.io/v1/boards/rocketlab/jobs`, `api.lever.co/v0/postings/shieldai`, `api.ashbyhq.com/posting-api/job-board/crusoe`, `apply.workable.com/api/v1/widget/accounts/1000heads` — run 2026-07-01, all boards already present in `companies.json`
