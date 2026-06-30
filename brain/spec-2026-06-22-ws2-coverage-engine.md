---
title: "WS-2 — Generic Coverage Engine (Design Spec)"
created: 2026-06-22
status: draft — pending spec review, then implementation plan
workstream: 2 of 3
depends_on: [[spec-2026-06-22-ws1-coverage-foundations]]
related: [[research-2026-06-22-job-discovery-playbook]], [[scraping-sources]]
---

# WS-2 — Generic Coverage Engine

## 1. Context & goal

With WS-1 giving us a coverage _number_ and a stable `job_key`, WS-2 raises the number: maximize the
fraction of jobs found in an arbitrary area, **for free**, with optional BYO-paid escalation for the
locked-down targets. The crawler stops being seeded by the hardcoded `company_registry.py` and becomes
a **generic two-layer funnel**: discover the employer/board _denominator_ cheaply, then pull each
employer's own free feed and filter to the metro (research §1).

Every addition is gated by re-running the WS-1 benchmark to **prove the lift** — sources that don't
move the score get cut, so we don't over-build.

## 2. Decisions locked

- **Fully generic** — discovery driven by the user profile, not hardcoded slugs. **Config source is
  pinned (today's `preferences.json` has only `salary_min`/`locations`/`remote_ok`/`work_auth`/
  `dealbreakers`/`seniority_exclude` — no area/field key):** _area_ = `preferences.json.locations[]`
  (already present); _field/target-roles_ = a **new `target_roles[]` key added to `preferences.json`**,
  seeded on migration from `user_config.json.keywords` + parsed from `preferences.md`. The existing
  `company_registry` becomes a _cache of discovered boards_, not the seed.
- **Free-first, BYO-paid optional** — public/unauthenticated sources default; paid backends
  (JSearch/SerpApi/Apify) activate only if the user supplies a key in `secrets/`.
- **Legal posture (research §4):** default public sources only; LinkedIn = logged-out **guest
  endpoints** only (never account/cookie scraping); ship a ToS-warranty + indemnification note in the
  README; respect `robots.txt` + rate limits.
- **Build order inside WS-2 is set by WS-1's baseline** — attack the SOC groups / gaps where the
  measured coverage is lowest first. All four gap classes are in scope (discovery, hard targets, geo,
  match-depth/freshness).

## 3. Non-goals (YAGNI)

- No bundled paid keys; no account-login scraping; no scraping Google Jobs directly.
- No Tier-3 ATS official-API integrations (Teamtailor/BambooHR/Breezy/iCIMS/Jobvite/ADP/Paycom) — at
  most a generic JSON-LD/HTML fallback on their rendered careers pages.
- No coverage-math changes (that's WS-1); WS-2 only feeds more jobs into it.
- No AI round-trip (WS-3).

## 4. Architecture

Extends the existing `scrape/` and `search/` packages plus a new discovery layer. All new ATS
scrapers follow the established dispatcher pattern in `scrape/careers_client.py`; all new aggregators
inherit `search/base_client.py` (caching + rate-limit + normalize) and register in
`search/cli.build_clients`.

```
discover/                         # NEW: generic denominator builder (replaces registry-as-seed)
  cc_harvest.py    # Common Crawl CDX -> ATS slugs per host (the generic winner)
  career_link.py   # company domain -> robots/sitemap/homepage -> careers URL -> ATS+slug
  ats_detect.py    # (move/extend scrape/ats_detect) host-inspection + embed-fingerprint + brute-probe
  registry.py      # merge discovered boards into companies.json (cache, user-wins)
scrape/                           # NEW Tier-1 ATS scrapers + generic extractor
  workable_scraper.py · recruitee_scraper.py · rippling_scraper.py · personio_scraper.py
  jsonld_scraper.py    # generic schema.org/JobPosting extractor for non-ATS career pages
  workday_scraper.py   # UPGRADE: CSRF session-priming + faceted paging + per-tenant config
search/                           # NEW aggregators + hard targets (BYO)
  arbeitnow_client.py · jooble_client.py · careerjet_client.py
  linkedin_guest_client.py   # logged-out guest endpoints (free, public)
  jsearch_client.py / serpapi_client.py   # BYO-paid Google-Jobs backends (key-gated)
geo/                              # geo radius + remote-region filter (uses coverage/geography.py)
```

## 5. Components (grouped by gap class)

### 5.1 Generic discovery (replaces registry-as-seed)

- **`discover/cc_harvest.py`** — query Common Crawl CDX per ATS host
  (`index.commoncrawl.org/CC-MAIN-*-index?url={host}%2F*&output=json`), regex slugs, dedupe across
  monthly crawls, persist to `companies.json` with provenance + last-seen. Bounded/paged; cached so a
  full harvest runs occasionally, not per search.
- **`discover/career_link.py`** — given a company domain (from gov rollups / user input / aggregator
  hits): fetch `robots.txt` (harvest `Sitemap:`, obey `Disallow`), `sitemap.xml` (filter
  `job|career|position|opening|vacanc`), homepage careers-anchor regex + one-hop follow → hand off to
  detection.
- **`discover/ats_detect.py`** — extend the existing `scrape/ats_detect.py`: (1) careers-URL host
  inspection, (2) embed-script fingerprinting on own-domain careers pages, (3) brute-probe candidate
  slugs against Tier-1 endpoints (200 + non-empty wins). Returns `(ats_type, slug)`.
- **Fix the silent-failure bug:** discovery with no Brave/CC reachability must **log loudly**, not
  return empty silently (current `discoverer.py` gap).
- **Gov rollups** as a free employer-name source: CareerOneStop / USAJOBS / NLx (keyed-but-free) feed
  employer names → `career_link` → boards.

### 5.2 New Tier-1 ATS scrapers (research §2)

`workable` (`apply.workable.com/api/v1/widget/accounts/{slug}`), `recruitee`
(`{slug}.recruitee.com/api/offers/`), `rippling`
(`api.rippling.com/platform/api/ats/v1/board/{slug}/jobs`), `personio`
(`{slug}.jobs.personio.de/xml` — XML). Each: implement `fetch(slug) -> list[JobResult]`, register in
the `careers_client` dispatcher + `ats_detect` patterns, normalize to `JobResult`, unit-test against a
recorded fixture.

### 5.3 Generic non-ATS extractor

**`scrape/jsonld_scraper.py`** — parse `<script type="application/ld+json">` for
`@type=JobPosting`/`ItemList`, map `hiringOrganization`/`jobLocation`/`datePosted`/`validThrough`/
`baseSalary` → `JobResult`. Used as the upgrade to the low-confidence `direct_scraper` and for Tier-3
ATS rendered pages. One parser, thousands of sites (research §1, §6).

### 5.4 Hard targets (BYO / public-guest)

- **`linkedin_guest_client.py`** — logged-out guest search endpoint
  (`/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=&location=&start=`, paginate by 25) + job
  detail; HTML-card parse; conservative delays + UA rotation; **no auth, no cookies, no accounts**.
  Off by default with a one-line ToS notice; user opts in.
- **`workday_scraper.py` upgrade** — GET careers page in-session to prime CSRF cookie/token, then POST
  `wday/cxs` with faceted paging (work around the 10k cap by faceting on location/category); per-tenant
  `{wdN}`/`{siteId}` config map; retry/backoff on the Akamai wall.
- **`jsearch_client` / `serpapi_client`** — BYO-paid Google-Jobs backends (cover Indeed + LinkedIn +
  Glassdoor + ZR). Key-gated; conserve quota (the existing JSearch budget tracker pattern); cache hard.

### 5.5 Geo radius + remote filter

- Build the metro **location-variant set** from `coverage/geography.py` (WS-1) and apply it as the
  post-fetch filter for ATS sources (which have no server-side geo) and as the query param where the
  source supports it (Lever `location`, SmartRecruiters `city`, Adzuna `where` + distance).
- **Remote-region filter:** classify remote postings and gate by region (US-only / commute-distance-
  remote) per `preferences.json`, so global remote feeds stop adding noise.

### 5.6 Match depth + freshness

- **Title+body matching** on career pages: extend `scrape/text_match.py` to match the boolean query
  against title **and** description/department (currently title-only), recovering generically-titled
  reqs. Keep title as a score boost.
- **Freshness:** capture `datePosted`/`validThrough`; add a "new since last run" delta per source
  (compare `job_key` set vs the previous run); drop expired postings.

## 6. Data flow (one search)

`preferences.json (area, field)` → discovery layer (CC harvest cache + career-link for gaps) →
company/board set → ATS fanout (Tier-1 JSON + Workday/JSON-LD fallbacks) **in parallel with**
aggregator + guest/BYO sources → normalize → `coverage/resolve()` dedup (`job_key`) → geo+remote
filter → match-depth filter → freshness delta → score → inbox. Then `run_benchmark` rates the run.

## 7. Error handling & edge cases

- Any source down / rate-limited / key-missing → that source degrades to empty **with a logged
  warning** (never silent); the run continues. Missing required-for-a-source key is surfaced in the
  GUI/log.
- Workday Akamai block → backoff + IP-rotation hook (BYO proxy if configured) → skip tenant with a
  note rather than hang.
- CC harvest unavailable → fall back to existing registry + `site:` seed; log degraded mode.
- Per-company timeout (existing 20s) keeps truncating large boards → make it configurable + log when a
  board is truncated (don't silently undercount).
- JSON-LD malformed / partial → best-effort field extraction; skip unparseable, count skips.

## 8. Testing strategy

- **Per new ATS scraper:** recorded-fixture unit test (parse → normalized `JobResult`s); detection
  test (URL/embed → correct `(ats_type, slug)`); brute-probe test against mocked endpoints.
- **Discovery:** `cc_harvest` slug-regex unit tests on captured CDX lines; `career_link`
  robots/sitemap/anchor extraction on fixtures; loud-failure test (no reachability → raises/logs, not
  empty-silent).
- **JSON-LD extractor:** parse a set of real-world `JobPosting`/`ItemList` HTML fixtures.
- **Geo/remote/match-depth/freshness:** unit tests on the filters with crafted jobs.
- **Coverage-lift gate (the proof):** for each gap class, a test that runs `run_benchmark` (WS-1) on a
  before/after cached fixture and asserts the CoverageScore _increased_ (or per-SOC recall increased)
  — this is the "verification" that each addition actually helped.
- Network-touching tests use recorded fixtures (`responses`/VCR-style) — no live calls in CI.
- Suite stays green; add tests per component.

## 9. Risks

- **R1 — endpoint drift / bot walls.** ATS + LinkedIn guest surfaces change. Mitigation: fixtures +
  graceful per-source degradation + a "source health" log; re-verify at build time.
- **R2 — legal/ToS.** Mitigation: public/guest-only defaults, BYO paid keys, README warranty +
  indemnification, robots/rate-limit respect; never bundle account scraping (research §4).
- **R3 — Common Crawl volume.** Full per-host harvest is large/slow. Mitigation: incremental/cached
  harvest, bounded paging, store provenance; harvest is a background/occasional job, not per-search.
- **R4 — noise from wide net.** More sources → more borderline jobs. Mitigation: WS-1 dedup +
  per-SOC benchmark keeps it honest; the AI ranking (WS-3) is the tailoring layer that makes wide
  usable.
- **R5 — over-building low-yield sources.** Mitigation: the lift-gate test — cut sources that don't
  move the score for the test areas.

## 10. Done criteria

- Generic discovery (CC harvest + career-link + upgraded detection) replaces registry-as-seed; runs
  for an arbitrary `(area, field)` with no hardcoded slugs.
- 4 new Tier-1 ATS scrapers + JSON-LD extractor + 3 new aggregators + LinkedIn guest + Workday CSRF fix
  landed, each with fixtures + tests, each degrading gracefully.
- Geo radius/remote filter, title+body matching, and freshness delta in the pipeline.
- The WS-1 CoverageScore for the test area(s) **measurably beats the WS-1 baseline**, with the lift
  attributable per source. Tests green.
