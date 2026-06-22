---
title: Free-First Job-Discovery & Coverage-Measurement Playbook
created: 2026-06-22
status: research reference (input to WS-1/WS-2/WS-3 specs)
tags: [scraper, coverage, research, ats, discovery]
related: [[spec-2026-06-22-ws1-coverage-foundations]], [[spec-2026-06-22-ws2-coverage-engine]], [[spec-2026-06-22-ws3-ai-rerank-roundtrip]], [[scraping-sources]]
---

# Free-First Job-Discovery & Coverage-Measurement Playbook

> Web-researched 2026-06-22 (6 parallel research agents + synthesis). Captures the techniques the
> three workstream specs build on. Verify endpoints again at implementation time — ATS surfaces drift.

A practical, build-it-yourself recipe for a generic, distributable job-search crawler that, given
`(area, field)`, discovers the maximal set of employer career boards for free, pulls all their jobs,
and rates how much of the area it actually covered.

---

## 1. Generic free discovery pipeline

The winning architecture is a **two-layer funnel**: build a geography-independent **denominator** of
employers/ATS slugs, then hit each employer's **own free feed** and filter by location string.
Geography is almost never a first-class enumeration filter — enumerate employers cheaply, then filter
their postings by metro location names.

### Step 0 — Build the metro geography set (once per area)

- Resolve `area` → CBSA → county/ZIP/place set via the Census crosswalk, then expand to **location
  name variants**: city, county, "Greater X", common abbreviations, neighboring suburbs
  ([Census CBP/geography](https://www.census.gov/data/developers/data-sets/cbp-zbp/cbp-api.html)).
- This string set is what every posting's `location.name` / `jobLocation` is matched against.

### Step 1 — Build the employer/slug denominator (free, geography-independent)

Run in parallel; union and dedupe the resulting slugs:

1. **Common Crawl CDX slug harvest** (the generic winner). Query the CDX index per ATS host and regex
   the slug out of every captured URL — fully sanctioned, 100% free
   ([CC index](https://index.commoncrawl.org/), [cdx_toolkit](https://github.com/commoncrawl/cdx_toolkit)):
   ```
   http://index.commoncrawl.org/CC-MAIN-2025-13-index?url=boards.greenhouse.io%2F*&output=json
   ```
   Repeat for `jobs.lever.co/*`, `jobs.ashbyhq.com/*`, `*.myworkdayjobs.com/*`,
   `jobs.smartrecruiters.com/*`, `{x}.recruitee.com/*`, `apply.workable.com/*`. Dedupe across monthly
   crawls. For bulk, use `cc-index-table` (Spark on S3 parquet).
2. **Government employer rollups** — CareerOneStop and NLx aggregate ~25k corporate career sites;
   harvest distinct employer names for the area, then map back to career sites in Step 2
   ([NLx](https://www.naswa.org/national-labor-exchange/nlx-frequently-asked-questions),
   [CareerOneStop API](https://www.careeronestop.org/Developers/WebAPI/Jobs/list-jobs.aspx)).
3. **Prebuilt GitHub slug corpora** (bootstrap only): `Feashliaa/job-board-aggregator` ships ~95k
   CC-harvested slugs — but it's **CC BY-NC 4.0 (non-commercial)**; re-harvest yourself for any
   commercial/distributed use. Also `plibither8/jobber`, `Masterjx9/OpenPostings`.
4. **`site:` dorking** (cheap fallback, lossy/rate-limited): seed only; never rely on for completeness.

### Step 2 — Resolve each company → ATS + slug (career-link discovery)

- Fetch `/robots.txt` → harvest `Sitemap:` lines (also obey `Disallow`).
- Fetch `/sitemap.xml` (+ nested index), filter `<loc>` for `job|career|position|opening|vacanc`.
- Fetch homepage, regex anchors `career|careers|jobs|join|work-with-us|opportunities`, follow one hop,
  then **detect the ATS by host** (§2) → recover slug → use the ATS JSON API instead of scraping HTML.

### Step 3 — Pull free structured feeds (per slug / per page)

- **ATS public JSON APIs by slug** — the spine (§2). One call per board, no auth.
- **JSON-LD `JobPosting` extraction** for any non-ATS career page: parse
  `<script type="application/ld+json">` for `@type=JobPosting`/`ItemList` →
  `hiringOrganization.name`, `jobLocation.address`, `datePosted`, `validThrough`, `baseSalary`.
  **One generic parser works across thousands of differently-templated sites.** Google has had **no
  read API since 2021**, so this is how you leverage "Google Jobs schema" without touching Google.
- **Keyed metro-native gov feeds** in parallel: CareerOneStop (NLx-backed, native `location+radius`),
  USAJOBS (federal only).

### Step 4 — Filter to metro

Match each posting's `location.name`/`jobLocation` against the Step-0 geography set; normalize, dedupe.

### Step 5 — Coverage check (denominator)

Census **CBP** (establishments by CBSA/NAICS) and **BLS QCEW** to know "how many employers should
exist" and weight effort by industry. Feeds the rating in §5.

**Order & fallbacks:** CC slug harvest (primary denominator) → gov rollups + prebuilt corpora →
career-link discovery for gaps → ATS JSON (primary pull) → JSON-LD parse (non-ATS fallback) →
CareerOneStop/USAJOBS (parallel gov layer) → location filter → dedupe → rate. Everything free; the
only gated-but-free items are CareerOneStop / USAJOBS / Census keys + NLx data request. Avoid paid
SERP scrapers; never scrape Google Jobs directly.

---

## 2. ATS endpoint catalog

All Tier-1 endpoints below are no-auth, single-call full-board, live-verified HTTP 200 in research.
"Slug" = company token in the URL.

### Tier 1 — Reliable: public, no-auth, one-call full board

| ATS                 | Endpoint pattern                                                                    | Notes                                                                |
| ------------------- | ----------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| **Greenhouse**      | `GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true`           | `content=true` inlines HTML; newer boards `job-boards.greenhouse.io` |
| **Lever**           | `GET https://api.lever.co/v0/postings/{slug}?mode=json`                             | Server filters: location/team/department/commitment/level/skip/limit |
| **Ashby**           | `GET https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true` | HTML+plaintext+comp; filter client-side                              |
| **SmartRecruiters** | `GET https://api.smartrecruiters.com/v1/companies/{id}/postings?limit=100&offset=0` | Paginate; filters q/country/region/city/department                   |
| **Workable**        | `GET https://apply.workable.com/api/v1/widget/accounts/{slug}`                      | Careers-widget feed, no filtering                                    |
| **Recruitee**       | `GET https://{slug}.recruitee.com/api/offers/`                                      | Slug = live careers subdomain                                        |
| **Rippling**        | `GET https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs`                | Documented public board API                                          |
| **Personio**        | `GET https://{slug}.jobs.personio.de/xml?language=en` (also `.com`)                 | **XML not JSON**; must be enabled by customer                        |

_(App already implements Greenhouse, Lever, Ashby, SmartRecruiters, Workday. NEW Tier-1 to add:
Workable, Recruitee, Rippling, Personio.)_

### Tier 2 — Flaky: public but POST/quirky/bot-protected or per-company only

| ATS              | Endpoint                                                                                                     | Gotcha                                                                                                                                                                                                      |
| ---------------- | ------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Workday**      | `POST .../wday/cxs/{tenant}/{siteId}/jobs` body `{"appliedFacets":{},"limit":20,"offset":0,"searchText":""}` | No auth but **CSRF session priming** (GET careers page first for cookie/token), **Akamai bot wall** (rotate IPs), **10k cap** (facet by location/category), per-tenant `{wdN}`/`{siteId}` read off live URL |
| **Paylocity**    | `GET https://recruiting.paylocity.com/recruiting/api/feed/jobs/{guid}`                                       | Feed GUID = key; not enumerable                                                                                                                                                                             |
| **JazzHR**       | Per-customer XML feed                                                                                        | Public XML per-account; not enumerable                                                                                                                                                                      |
| **Taleo/Oracle** | Per-section RSS/XML                                                                                          | RSS only; brittle                                                                                                                                                                                           |

### Tier 3 — Avoid as API (auth-gated / JWT-extraction-brittle): scrape rendered careers site

Teamtailor (token + `X-Api-Version`), BambooHR (token; `{slug}.bamboohr.com/careers/list` embed JSON
undocumented), Breezy (auth; scrape `{slug}.breezy.hr`), iCIMS (undocumented internal JSON,
version-sensitive), Jobvite (contracted ID+key+secret), ADP WFN (OAuth-gated), Paycom (extract
32-char portalKey + JWT from HTML).

### Company → ATS → slug detection (priority order)

1. **Careers-URL host inspection** — follow `{company}.com/careers`, read redirect host (strongest).
2. **Embed-script fingerprinting** — grep source/XHR for `grnhse_`/`boards.greenhouse.io/embed`,
   `lever-jobs`, `_ashby_embed`, `myworkdayjobs`/`wday/cxs`, `workable.com/api/v1/widget`,
   `recruitee.com/api/offers`, `BambooHR.embed`.
3. **Brute-probe** — derive candidate slug (lowercase, strip Inc/LLC; try `acme`, `acmeinc`,
   `acme-corp`), fire parallel GET/HEAD at Tier-1 endpoints, take whichever returns 200 + non-empty.

---

## 3. Aggregator & Google Jobs tier table

### Tier 1 — True free, no-auth public feeds (cache daily; remote-heavy)

Arbeitnow (no published cap, CORS, EU+remote), Remotive (≤~4×/day, remote), RemoteOK (free, **skip
first array element = legal notice; attribution required**), Jobicy (≤50/call, remote), Himalayas
(≤20/req, 24h cache, 100k+ remote).

### Tier 2 — Free but key/signup (real query APIs, broad coverage)

- **Adzuna** — 25/min, 250/day, **2.5k/mo**; best general free aggregator; salary/category; ToS-clean.
- **The Muse** — **3,600/hr** with key (500 without); global curated.
- **Jooble** — free key, 70+ countries; `POST /api/{key}`.
- **Careerjet** — ~1,000/hr, 90+ countries; **affiliate links expected**.
- **USAJOBS** — US federal, native metro scoping. **Reed** — UK. **Findwork** — tech/remote.
- **Lightcast Open Skills** — free skill/title taxonomy (not jobs) — useful for §5 normalization.

### Google for Jobs (no official free API since 2021)

- **SerpApi `google_jobs`** — 250 searches/mo free (shared across engines), legally cleanest paid.
- **JSearch (RapidAPI)** — 200 req/mo free; aggregates Google-for-Jobs (LinkedIn/Indeed/Glassdoor/ZR).
- **TheirStack** — 200 credits/mo.

_(App already has Adzuna, JSearch, USAJobs, TheMuse, RemoteOK, Remotive, Jobicy, Himalayas, HN. NEW
aggregators to add: Arbeitnow, Jooble, Careerjet. Plus JSON-LD generic extractor.)_

**Recommended free stack:** Adzuna + Muse (backbone) → Arbeitnow/Remotive/RemoteOK/Jobicy/Himalayas
(remote, dedupe heavily) → Jooble + Careerjet (country breadth) → USAJOBS/Reed → SerpApi 250/mo or
JSearch 200/mo only for high-value Google-Jobs slices, cached → Lightcast for normalization.

---

## 4. Hard targets — LinkedIn / Indeed / Workday-CSRF

- **Indeed:** official search API dead (deprecated); realistic free route = Indeed data via
  Google-for-Jobs aggregation (JSearch 200/mo or SerpApi 250/mo) — vendor absorbs scraping risk.
- **LinkedIn:** official Jobs API closed to individuals (Partner-only, not accepting new partners as
  of Oct 2025). Free + low-risk = **public guest endpoints** (logged-out, no cookie):
  - Search: `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={kw}&location={loc}&start={offset}` (HTML cards, paginate `start` by 25)
  - Detail: `https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}`
  - Rate-limited at volume → delays, rotate UA, optional proxy. **Never ship authenticated/cookie/
    fake-account scraping** (the Proxycurl pattern — sued Jan 2026, shut down July 2026).
- **Workday-CSRF:** free public CXS feed; GET the careers page first in-session to pick up
  `wday_vps_cookie`/`PLAY_SESSION` + CSRF token, then POST. Akamai wall (IP rotation), 10k cap (facet),
  per-tenant config map.

### Cheapest BYO-paid escalation (ranked)

| Provider                | Free       | Paid entry                       | Role                                                                 |
| ----------------------- | ---------- | -------------------------------- | -------------------------------------------------------------------- |
| **JSearch (RapidAPI)**  | 200/mo     | low single-$/mo                  | best starter BYO-key; one key = LinkedIn+Indeed+Glassdoor+ZR+Workday |
| **SerpApi Google Jobs** | 100–250/mo | $25/1k                           | most reliable SERP vendor, legally clean                             |
| **Apify actors**        | $5 credit  | ~$1/1k LinkedIn, ~$0.1/1k Indeed | cheapest per-record                                                  |
| **Bright Data**         | trial      | $0.75/1k                         | most battle-tested; overkill personal                                |

### Legal / ToS framing (distributable BYO-key tool)

- **hiQ v. LinkedIn + Van Buren:** scraping **publicly available** data is **not a CFAA violation**
  — covers guest endpoints, Workday CXS, Greenhouse/Lever boards, Google-for-Jobs.
- **But CFAA-clear ≠ liability-free:** hiQ still lost on contract. ToS/clickwrap, copyright, DB rights,
  CCPA/GDPR on personal data remain. Logged-out surface is safer (no clickwrap).
- **Posture:** default public/unauthenticated + BYO paid keys; ship a **ToS-compliance warranty +
  indemnification** clause; respect robots.txt + rate limits; **never bundle account-login scraping**.

---

## 5. Coverage-rating recipe (0–100 area-coverage score)

True denominator is **unobservable** → coverage is _estimated_ by triangulating three legs.
**De-duplication is the load-bearing prerequisite** — without it numerator and overlap are garbage.

### 5a. Entity resolution / dedup (mandatory prerequisite)

`canonicalize → block → score → cluster → assign job_key`:

1. **Company canonicalization** — `cleanco` (strips Inc/LLC/Ltd/GmbH), lowercase, unicode/punct
   normalize, alias table (IBM ⇄ International Business Machines).
2. **Title normalization** — map free-text → **O\*NET-SOC** (1,016 titles/867 codes) or **ESCO**;
   normalize seniority (Sr/Senior, II, Jr). Enables **per-SOC coverage**.
3. **Blocking** (10× more important than the matcher) — **`datasketch` MinHash+LSH** on shingled
   title+company+location+description; cheap fallback block = exact `canon-company + SOC + norm-location`.
4. **Pairwise scoring** — **`rapidfuzz`** `token_sort_ratio`/`token_set_ratio` titles, `WRatio`
   general; combine with location/salary/date proximity.
5. **Clustering** — Splink (Fellegi-Sunter, EM) or `dedupe` (active-learning) for scale; for our scale
   **rapidfuzz pairs + Union-Find/connected-components** → stable `job_key`. (Keep Splink optional —
   heavy dep for a frozen build.)
6. **Validate** — hand-label a few hundred pairs; report dedup precision/recall/F1 + blocking recall.

### 5b. Leg 1 — Reference-proxy (PRIMARY)

Same area+occupation query against a broad aggregator, **dedup its results**, deduped count = `D`;
your deduped matched count = `N`. **Per SOC group**, never just aggregate:

```
cov_proxy_g       = N_g / D_g
cov_proxy_weighted = Σ_g (employment_share_g × cov_proxy_g)
```

Indeed is the best single proxy. Caveats baked in: online over-represents professional/degree roles
(~80–90%) vs trades/food-service (~40–60%); aggregators inflate via multi-posting; ghost/stale jobs
inflate `D`. Treat `D` as lower-biased + segment-skewed; prefer **published aggregate counts** over
scraping cards (lower ToS risk); correct skew with `employment_share_g` weighting.

### 5c. Leg 2 — Capture-recapture (free SECONDARY — we already multi-source)

Each independent source = a "capture occasion"; overlap estimates the unseen population.

- **Pairwise Chapman** (bias-corrected): `N_hat = ((n1+1)(n2+1)/(m+1)) − 1`; `cov_CR = n_crawler/N_hat`.
- **≥3 sources → log-linear** (Poisson GLM with pairwise interactions; pure-Python via statsmodels or
  hand-rolled — no R dependency).
- **Chao1 lower bound** (assumption-light, most robust): `S_Chao1 = S_obs + f1²/(2·f2)`
  (bias-corrected `+ f1(f1−1)/(2(f2+1))`). Honest ceiling: `cov_upper = S_obs / S_Chao1`.
- **Good-Turing completeness:** `C_hat = 1 − f1/n`.
- **Job precedent:** Beresewicz et al. capture-recapture for negatively-dependent small-overlap
  sources (the job-board case) — ~10–15% undercount ([arXiv 2106.03263]).
- **Key bias:** aggregators scrape each other (positive dependence) → `N_hat` biased **down** → you
  **overstate** coverage. Always report the Chao1 ceiling + CI, not a point.

### 5d. Leg 3 — BLS JOLTS macro sanity gate (pass/fail, not folded in)

JOLTS = official monthly openings; national by industry/firm-size, state total-nonfarm, metro only 18
largest MSAs (frozen 2001–2019), no county/city. Free API v2. Use finest matching geography; treat as
order-of-magnitude **pass/fail** (point-in-time openings vs posting flow — different concept).

### 5e. Composite 0–100 + automated test

```
CoverageScore = 100 × (w1·cov_CR + w2·cov_proxy_weighted + w3·C_hat)
defaults: w1=0.5 (CR most defensible), w2=0.3, w3=0.2
```

**Always also report `cov_CR` CI, `cov_upper` (Chao1 ceiling), and the JOLTS gate separately** — never
collapse to one opaque number. Automated test: fix scope `(area, window, SOC-grouping)`; pull all
sources → dedup (5a) → job_keys + dedup F1 as metadata → compute legs + composite → persist run →
**regression gates** (fail if dedup F1 < floor, CoverageScore regresses beyond tolerance, or JOLTS gate
flips). Free stack throughout: `cleanco`/`datasketch`/`rapidfuzz`(/optional Splink) + BLS/Census APIs.

---

## 6. Feasibility verdict & risks

**Solid (build directly, free, low ToS risk):** Tier-1 ATS JSON APIs (the spine); Common Crawl CDX
slug enumeration; JSON-LD JobPosting extraction; robots/sitemap + career-link discovery;
CareerOneStop/USAJOBS/Census CBP/BLS QCEW/JOLTS; Adzuna + Muse + no-auth remote feeds; dedup stack.

**Fragile (free but operationally hard — wrap with retries/fallbacks):** Workday (CSRF priming +
Akamai + 10k cap + per-tenant config); no-auth remote feeds (tiny pages, remote-only, heavy overlap);
`site:` dorking (seed-only); capture-recapture (only as good as dedup + independence — report ceiling);
Tier-2 ATS (per-company, not enumerable).

**Avoid:** scraping Google Jobs directly; LinkedIn authenticated/cookie/fake-account scraping;
Indeed "search API"; Tier-3 ATS official APIs; prebuilt slug corpora for commercial use (CC BY-NC).

**Bottom line:** A fully free, generic, distributable crawler is feasible. **ATS-JSON spine + Common
Crawl slug denominator + JSON-LD extraction + gov keyed feeds** = high free coverage, low legal risk;
**Adzuna/Muse/remote feeds + JSearch/SerpApi free tiers** fill aggregator + Google-Jobs gaps; a
**three-leg coverage score** on a real **dedup pipeline** gives a defensible, automatable 0–100 rating.
Keep defaults public/unauthenticated, BYO-key for paid escalation, ToS-warranty + indemnification.
