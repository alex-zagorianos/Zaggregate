# JobScout — Reach Source Catalog (FREE + LEGAL job sources, 2026)

**Research date:** 2026-07-01
**Scope:** Exhaustive catalog of every free + legal job source/API usable by a local desktop app (no server backend, no paid mandatory tier) as of mid-2026, with current cited quotas/ToS, ATS JSON endpoints, government banks, and non-tech-sector sources. Verified via direct fetches of official docs/ToS/robots.txt pages where possible.
**Goal bias:** JobScout's existing sources skew tech/remote/startup. Session 24 (2026-07-01) testing found the app under-reaching NON-tech/local candidates. New candidates are therefore ranked with heavy weight toward non-tech (healthcare, trades, finance, gov, admin, retail, hospitality) and US-local reach.

---

## 0. Headline findings

1. **The non-tech verticals have essentially NO open/free APIs.** Across 17 healthcare/trades/finance/hospitality boards checked, exactly two (eFinancialCareers, Snagajob) even have documented APIs — and both are _employer-posting_ APIs (data flows board-in, not app-out) and partner-gated. This sector runs on paid recruiter tooling and closed data. Confirmed dead-end, not an oversight.
2. **The biggest realistic non-tech reach gain is NOT a vertical board — it's (a) SMB-focused ATS JSON feeds** (BambooHR ~30k mostly-sub-250-employee companies: dental offices, local manufacturers, nonprofits, retail HQs — genuinely non-tech local employers) **and (b) US municipal open-data APIs** (NYC/Socrata pattern: sanitation, admin, health, clerical, public-safety roles — the archetypal non-tech local jobs).
3. **A large chunk of the classic "big name" list is now closed to new/free developers:** ZipRecruiter publisher API killed (Apr 2025), CareerBuilder+Monster bankrupt & sold to JobGet (Jun 2025), Glassdoor API closed since 2021, Indeed publisher API closed + core paths robots.txt-blocked, SimplyHired dead since 2016, Talent.com/Trovit/Jobtome are affiliate-revenue-share (not free keys), iCIMS/Taleo/Paylocity/JazzHR/Jobvite ATS all key/partner-gated.
4. **Strategic lever:** because trades/construction/general boards (e.g. ConstructionJobs.com) themselves re-aggregate Careerjet/Indeed/Appcast, the highest-ROI non-tech move is to **exploit existing broad aggregators (Adzuna, Careerjet, Jooble, The Muse) harder with non-tech query terms** rather than integrate dead-end vertical boards. The Muse alone spans 40+ categories and is already integrated.
5. **2025-2026 changes to flag in existing code:** Himalayas cut max results/request to **20** (2025-03-24); SerpApi/Google deprecated `chips`/`ltype`/`start` params (must use `next_page_token`); LinkedIn scraping risk **escalated** (2025 Proxycurl lawsuit + shutdown) — downgrade its risk label from "medium/stable" to "medium-and-rising."

---

## 1. Summary table

Legend — **Have/New**: ✅ already integrated · 🆕 new candidate · ❌ not viable (closed/paid/dead). **Non-tech strength**: 1=none/weak … 5=strong.

### Already-have sources (verify/update)

| Source              | Have/New | Type              | Auth                              | Free quota (2026)                                           | Geo / category                | Non-tech |
| ------------------- | -------- | ----------------- | --------------------------------- | ----------------------------------------------------------- | ----------------------------- | -------- |
| Adzuna              | ✅       | REST              | Free key (app_id+key)             | 25/min · 250/day · 1k/wk · 2.5k/mo (raised free on request) | ~16 countries, all industries | 4        |
| USAJobs             | ✅       | REST              | Free key + email UA header        | No published # (per-UA throttle); 500/page                  | US federal gov, all cats      | 5 (gov)  |
| The Muse            | ✅       | REST              | Optional free key                 | 500/hr anon · 3,600/hr keyed; 20/page                       | Global, 40+ categories        | 4        |
| Jobicy              | ✅       | RSS + JSON        | None (attribution)                | Soft ~1/hr; 50/page                                         | Remote, global, mixed         | 3        |
| RemoteOK            | ✅       | JSON              | None (needs browser UA; 403 else) | Feed delayed 24h + backlink; realtime=paid                  | Remote, global, tech-skew     | 2        |
| Remotive            | ✅       | JSON              | None                              | >2/min blocked; ~4/day advised                              | Remote, global, all cats      | 3        |
| Himalayas           | ✅       | REST + RSS        | None                              | **20/req (cut 2025-03-24)**; 429 on excess                  | Remote, worldwide             | 2        |
| Arbeitnow           | ✅       | REST              | None                              | No official # (empirical check advised)                     | Europe, broad, visa filter    | 3        |
| Jooble              | ✅       | REST (POST)       | Free key (instant form)           | **No documented quota** (silent-ban risk)                   | Global aggregator, all cats   | 4        |
| Careerjet           | ✅       | REST              | Free publisher key                | 1,000/hr (secondary-source only)                            | Global aggregator, all cats   | 4        |
| HN Who-is-hiring    | ✅       | REST (Algolia)    | None                              | 10,000/hr per IP                                            | Global, tech-heavy            | 1        |
| LinkedIn guest      | ✅       | Unofficial scrape | None                              | n/a (ToS-prohibited; rising risk)                           | Global, all cats              | 3        |
| SerpApi Google Jobs | ✅       | REST (SaaS)       | Free key                          | **250/mo**, 50/hr                                           | Global, all cats              | 4        |
| JSearch (RapidAPI)  | ✅       | REST (SaaS)       | Free RapidAPI key                 | **200/mo**, 1k/hr cap                                       | Global, all cats              | 4        |

### New candidates (viable)

| Source                                   | Have/New        | Type                          | Auth                     | Free quota                             | Geo / category                           | Non-tech             |
| ---------------------------------------- | --------------- | ----------------------------- | ------------------------ | -------------------------------------- | ---------------------------------------- | -------------------- |
| **BambooHR** (ATS)                       | 🆕              | Public ATS JSON               | None                     | None documented                        | Global, ~30k mostly-SMB cos, all sectors | **5**                |
| **US municipal open data** (NYC/Socrata) | 🆕              | REST (SODA)                   | Optional free app token  | IP-throttled anon; ~unlimited w/ token | Per-city (US), all municipal cats        | **5** (gov)          |
| **Breezy HR** (ATS)                      | 🆕              | Public ATS JSON               | None                     | None documented                        | Global, ~9.7k SMB cos                    | 4                    |
| **Comeet / Spark Hire** (ATS)            | 🆕              | Public ATS JSON               | Public token+uid in URL  | None hard (60s timeout advised)        | Global, mid-market tech-lean             | 3                    |
| **Teamtailor** (ATS)                     | 🆕              | Career-site scrape / auth API | None (site) / key (API)  | n/a                                    | EU/Nordics, ~20.6k cos                   | 3                    |
| **We Work Remotely**                     | 🆕              | RSS                           | None (attribution)       | None published                         | Remote global; dev/design/mktg/sales     | 2                    |
| **France Travail** (gov)                 | 🆕              | REST                          | Free OAuth2 client       | 4 calls/sec/app                        | France, all industries                   | 5 (intl)             |
| **Reed.co.uk**                           | 🆕              | REST                          | Free key (Basic auth)    | 100/req; ~1k/day (unverified)          | UK, all industries                       | 4 (intl)             |
| **Canada Job Bank** (open data)          | 🆕              | CSV/JSON open data            | None                     | Unlimited (monthly dumps)              | Canada, all industries                   | 5 (intl)             |
| **Bundesagentur** (gov, DE)              | 🆕              | REST                          | Static shared key header | None documented                        | Germany, all industries                  | 5 (intl, unofficial) |
| **Findwork.dev**                         | 🆕              | REST                          | Free key                 | ~60/min (unverified)                   | Global, **tech only**                    | 1                    |
| **SAP SuccessFactors** (ATS)             | 🆕 (marginal)   | XML feed (unauth)             | None (XML path)          | n/a                                    | Global enterprise                        | 3                    |
| **Juju** / **WhatJobs FeedAPI**          | 🆕 (unverified) | REST/feed                     | Publisher signup         | unverified                             | Global aggregators                       | 3                    |

### Not viable (documented dead-ends)

| Source                                                                                         | Status                                                                                            |
| ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| ZipRecruiter publisher API                                                                     | ❌ Discontinued Apr 2025, no replacement                                                          |
| CareerBuilder                                                                                  | ❌ Bankrupt Jun 2025, sold to JobGet; API partner-gated + unstable                                |
| Glassdoor                                                                                      | ❌ Public API closed since 2021; enterprise-only                                                  |
| Indeed publisher API                                                                           | ❌ Closed to new devs; core paths robots.txt-blocked; scraping ToS+robots violation               |
| SimplyHired                                                                                    | ❌ Shut down 2016, folded into Indeed                                                             |
| Talent.com / Trovit / Jobtome                                                                  | ❌ Affiliate revenue-share programs, not free data keys                                           |
| Talroo / Jobs2Careers                                                                          | ❌ Enterprise CPC ad platform, no consumer data API                                               |
| iCIMS (ATS)                                                                                    | ❌ Official API partner-gated; unofficial per-tenant JSON too unstable                            |
| Taleo (ATS)                                                                                    | ❌ No public JSON API; closed to new customers Feb 2026, managed decline                          |
| Paylocity (ATS)                                                                                | ❌ Job feed partner-gated (needs sponsoring customer)                                             |
| JazzHR (ATS)                                                                                   | ❌ Real jobs API needs per-account key                                                            |
| Jobvite (ATS)                                                                                  | ❌ JSON feed needs key+secret from Jobvite CS                                                     |
| Healthcare boards (Health eCareers, Incredible Health, Vivian, AMN, HealthJobsNationwide, AHA) | ❌ No public API; several robots.txt-block search                                                 |
| Skilled-trades boards (mikeroweWORKS, ConstructionJobs, IBEW, SkilledTrades)                   | ❌ No API; mikeroweWORKS actively blocks AI bots; ConstructionJobs re-aggregates Careerjet/Indeed |
| Finance boards (eFinancialCareers, Wall Street Oasis)                                          | ❌ eFC API = employer-posting only + partner-gated; WSO no API                                    |
| Hospitality/retail boards (Snagajob, HCareers, CoolWorks)                                      | ❌ Snagajob API = posting-only + robots-blocks search; others no feed                             |
| NEOGOV / GovernmentJobs.com                                                                    | ❌ No public API (powers 1,500+ state/local agencies — big gap, but closed)                       |
| EURES                                                                                          | ❌ API legally gated to recognized EURES partners only                                            |
| UK Find a Job / Australia JobSearch                                                            | ❌ No public listing-level API                                                                    |

---

## 2. Exhaustive per-source catalog

### 2.1 Already-have — search API / feed clients (verified mid-2026)

**Adzuna** — REST (JSON/XML). Free key (`app_id`+`app_key`), register at developer.adzuna.com/signup. Free limits: 25 hits/min · 250/day · 1,000/week · 2,500/month (defaults; Adzuna raises free on request). `results_per_page` up to ~50. Multi-country (~16-19: US/UK/DE/FR/AU/CA/IN…), all industries. No 2025-2026 change. Source: developer.adzuna.com/docs/terms_of_service. **Non-tech: strong (4)** — broad aggregator, good for local non-tech query terms.

**USAJobs** — REST (JSON) `GET /api/Search` at data.usajobs.gov. Free, self-service, no approval. Headers: `Host: data.usajobs.gov`, `User-Agent: <your email>`, `Authorization-Key: <key>`. No published numeric limit (per-UA throttle at OPM discretion); 500 results/page max. US federal gov only, all agencies/categories. Source: developer.usajobs.gov/Guides/Authentication. **Non-tech: strong (5, gov).**

**The Muse (v2)** — REST (JSON). Optional free key. 500 req/hr unauthenticated, up to 3,600 req/hr keyed; 20 results/page; no paid tier. Global (100s US + international cities), **40+ categories across all industries — not tech-only**. Source: themuse.com/developers/api/v2. **Non-tech: strong (4)** — an already-integrated non-tech asset; query it with non-tech categories.

**Jobicy** — RSS + JSON REST (`GET jobicy.com/api/v2/remote-jobs`). No auth (attribution backlink required). Soft courtesy ≤1 poll/hr; `count` 1-50 (default 50). Remote-only, global, mixed tech + non-tech. Live "50k+ roles" May 2026. Source: github.com/Jobicy/remote-jobs-api. **Non-tech: moderate (3).**

**RemoteOK** — REST/JSON single GET at remoteok.com/api. No auth, **but direct fetch returns HTTP 403 without a browser-like User-Agent** (Cloudflare) — verify JobScout's client sets a UA. Free feed delayed 24h + attribution backlink required (no redirects); realtime = paid. Global remote, tech-skew, ~30k listings. Source: remoteok.com/legal. **Non-tech: weak (2).**

**Remotive** — REST/JSON; canonical docs at github.com/remotive-io/remote-jobs-api. No auth. >2 req/min blocked; ~4/day advised. `/api/remote-jobs`, `/api/remote-jobs/categories`. Remote-only global, all industries (~146k jobs). **Non-tech: moderate (3).**

**Himalayas** — REST/JSON + RSS; OpenAPI at himalayas.app/docs/openapi.json; MCP server as of 2026. No auth. **KEY 2025 CHANGE: max results/request cut to 20 (2025-03-24)**; 429 on excess. `/jobs/api`, `/jobs/api/search`. Worldwide remote, multi-category. Source: himalayas.app/docs/remote-jobs-api. **Non-tech: weak (2).**

**Arbeitnow** — REST/JSON at arbeitnow.com/api/job-board-api. No auth/key. No official numeric quota (recommend live empirical check). Jobs sourced from employer ATSs (Greenhouse, SmartRecruiters, Join, Teamtailor, Recruitee, Comeet). Primarily Europe, broad categories, `visa_sponsorship` filter. Overview updated 2026-03-09. **Non-tech: moderate (3).**

**Jooble** — REST `POST /api/{key}`. Free key, effectively self-serve (short lead form at jooble.org/api/about, instant GUID). **No documented quota anywhere** — silent-throttle/ban risk under heavy use. Global aggregator, all industries. **Non-tech: strong (4).**

**Careerjet** — REST; official Python client github.com/careerjet/careerjet-api-client-python. Free "Publisher account" key (careerjet.com/partners/register/as-publisher), Basic auth + mandatory `user_ip`/`user_agent` params. 1,000 req/hr cited by secondary dirs (not on official page — unverified). Global aggregator, all industries. **Non-tech: strong (4)** — note ConstructionJobs.com and other trade boards re-aggregate Careerjet, so heavier Careerjet querying captures trades content upstream.

**HN "Who is Hiring" (HN Algolia)** — REST/JSON `hn.algolia.com/api/v1/search`. No auth. **10,000 req/hr per IP.** Query `tags=story&query="Who is hiring"`; monthly threads discoverable back to 2015. Global, tech-heavy. Source: hn.algolia.com/api. **Non-tech: weak (1).**

**LinkedIn guest** — unofficial scrape of public jobs-guest listings. No auth. ToS §8.2 prohibits scrapers/bots. **Risk escalated 2025-2026:** hiQ v LinkedIn ended in settlement (2022, hiQ paid $500k + injunction, only narrow CFAA carve-out survived); **LinkedIn v. Nubela/Proxycurl (N.D. Cal. filed 2025-01-24) → Proxycurl shut down permanently 2025-07-04** despite ~$10M ARR; Apollo/Seamless Company Pages deplatformed; March 2026 transparency report blocked 78.2M fake accounts + 23.5M automated sessions/quarter. JobScout's use (unauthenticated, small-scale, non-commercial public job listings, no fake accounts, not resold) is meaningfully lower-risk than Proxycurl's bulk-profile-resale model that triggers suits — but nobody calls it "safe." **Reframe from "medium/stable" to "medium-and-rising."** Sources: linkedin.com/legal/user-agreement §8.2; nubela.co/blog/goodbye-proxycurl. **Non-tech: moderate (3).**

**SerpApi Google Jobs** — REST scraping-as-a-service. Free key. **Free tier: 250 searches/month, throttled 50/hr**; ~10 results/page via `next_page_token`. Paid: $25/1k → $75/5k → $150/15k → $275/30k. Global, all industries (mirrors Google's aggregation). **2025-2026: Google deprecated `chips`, `ltype`, and the `start` offset param → pagination must use `next_page_token`; the Google Jobs feature itself is NOT deprecated.** Sources: serpapi.com/google-jobs-api, serpapi.com/pricing. **Non-tech: strong (4).**

**JSearch (RapidAPI, OpenWeb Ninja)** — REST meta-aggregator. RapidAPI key (`X-RapidAPI-Key`+`X-RapidAPI-Host`). **Free: 200 req/month (BASIC, no card), 1k/hr cap.** Paid direct: $25/10k → $75/50k → $150/200k; PAYG $0.005/req. Global, all industries (aggregates Google for Jobs + LinkedIn/Indeed/Glassdoor/ZipRecruiter). Same Google-indexing-partner exposure as SerpApi. Sources: openwebninja.com/api/jsearch, rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch. **Non-tech: strong (4).**

### 2.2 Already-have — ATS scrapers (endpoint pattern re-verified 2026)

All confirmed current, public, no-auth for GET:

- **Greenhouse**: `https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true` (Job Board API; distinct from Harvest API which is deprecating Aug 31 2026 — Job Board API unaffected).
- **Lever**: `https://api.lever.co/v0/postings/{company}?mode=json`.
- **Ashby**: `https://api.ashbyhq.com/posting-api/job-board/{company}?includeCompensation=true`.
- **Workable**: `https://apply.workable.com/api/v1/widget/accounts/{company}`.
- **SmartRecruiters**: `https://api.smartrecruiters.com/v1/companies/{company}/postings` (GET public; only writes need key).
- **Recruitee**: `https://{company}.recruitee.com/api/offers/` (tenant subdomain; no auth).
- **Personio**: `https://{company}.jobs.personio.de/xml?language=en` (XML, not JSON; some tenants `.com`).
- **Rippling**: public `https://ats.rippling.com/api/v2/board/{board_slug}/jobs` (list; detail via `/jobs/{jobId}`) — distinct from partner-gated `api.rippling.com/...` (needs Recruiting Pro). **Verify JobScout uses the public `ats.rippling.com` pattern, not the gated one.**
- **Workday CxS**: `POST https://{company}.wdN.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` (JSON body); detail `GET .../wday/cxs/{tenant}/{site}/job/{externalPath}`. Still active/widespread in 2026.
- **Generic JSON-LD (schema.org JobPosting)**: web standard, unaffected — remains the fallback for any career page with structured data.

### 2.3 New candidates — ATS public JSON APIs (implementation-ready)

**BambooHR** 🆕 — Public ATS JSON. `https://{company}.bamboohr.com/careers/list` (JSON job summaries) → `https://{company}.bamboohr.com/careers/{id}/detail` (full description/comp). No auth, no reported anti-bot. No documented rate limit. Reach: **~30k+ companies, heavily SMB (0-249 employees)** — dental/medical offices, local manufacturers, nonprofits, retail HQs, i.e. exactly the non-tech local employers JobScout under-reaches. Source: documentation.bamboohr.com/reference. **Effort S · non-tech strong (5) · legal-risk low.**

**Breezy HR** 🆕 — Public ATS JSON. `https://{company_slug}.breezy.hr/json?verbose=true` (verbose required for full description/location/comp/type). No auth, no documented rate limit. Reach: ~9,700 SMB companies (median 20-49 employees). Official REST API (`api.breezy.hr/v3/...`) needs a token — not needed; use `/json`. Source: developer.breezy.hr. **Effort S · non-tech 4 · legal-risk low.**

**Comeet / Spark Hire Recruit** 🆕 — Public ATS JSON. `https://www.comeet.co/careers-api/2.0/company/{company_uid}/positions?token={token}&details=true`. Token+uid required in URL but **not secret** — embedded client-side in any company's careers widget (like Greenhouse's board slug); Comeet publishes a public sandbox token/uid in docs. No hard rate cap (60s client timeout advised). Mid-market, tech-leaning (Comeet now = Spark Hire Recruit after acquisition). Source: developers.comeet.com/reference/careers-api-overview. **Effort S · non-tech 3 · legal-risk low.**

**Teamtailor** 🆕 — Career-site scrape (published jobs readable with no key) OR authenticated REST `api.teamtailor.com/v1/jobs` (needs `Authorization: Token token=...`; a "Public Read" key scoped to published jobs exists; regional hosts `api`/`api.na`/`api.au`). **No clean documented unauthenticated JSON path** — plan to discover exact JSON shape per live tenant (network tab) before hardcoding. Reach: strong EU/Nordics, ~20.6k companies (mostly 100-249 employees). Source: docs.teamtailor.com. **Effort M · non-tech 3 · legal-risk low-medium.**

**SAP SuccessFactors** 🆕 (marginal) — Unauthenticated XML feed only: `https://career{N}.successfactors.com/career?company={companyID}&career_ns=job_listing_summary&resultType=XML` (title/description/location/employer). Real JSON is OData v2 (`/odata/v2/JobRequisition`) needing per-tenant OAuth2+SAML across ~15 regional data centers. **XML-only for the free path** + per-tenant `career{N}` host discovery = high friction. Massive enterprise reach but low priority. Source: SAP KBA 2428902. **Effort L · non-tech 3 · legal-risk low.**

**Not viable ATS** (documented above in §1 table): JazzHR (per-account key), iCIMS (partner-gated official / unstable unofficial), Taleo (no public JSON, closing to new customers Feb 2026), Paylocity (partner-gated feed), Jobvite (key+secret).

### 2.4 New candidates — government / national job banks

**US municipal open data (NYC / Socrata SODA pattern)** 🆕 **[US-relevant NOW]** — REST. NYC: `https://data.cityofnewyork.us/resource/kpav-sd4t.json` ("Jobs NYC Postings"), plus DOT/DCA/Workforce1 datasets (e.g. `.../resource/ay9k-vznm.json`). Optional free Socrata app token (dev.socrata.com/docs/app-tokens.html) — without it, IP throttling; with it, effectively unthrottled. **Non-tech STRONG (5)**: municipal roles = admin, sanitation, health, clerical, public safety, maintenance — archetypal non-tech local jobs. Caveat: per-city onboarding (NYC confirmed; other Socrata cities — Chicago, SF, LA, Austin, etc. — follow the same pattern but need per-city dataset IDs). **Effort M (reusable Socrata client, per-city config) · legal-risk low.**

**France Travail (ex-Pôle Emploi)** 🆕 **[international-expansion-later]** — REST "Offres d'emploi" API, the most mature EU option. Free OAuth2 client id/secret (francetravail.io/data/api/offres-emploi). **4 calls/sec/app** (platform ceiling 100/sec), 429+`Retry-After` on excess. Real-time French offers, all industries + reference data. **Non-tech 5 (for France).** Governed by a signed license (not fully "no strings"). **Effort M · legal-risk low.**

**Canada Job Bank (ESDC open data)** 🆕 **[international-expansion-later]** — Open-data CSV/JSON, no auth. Monthly "Job Postings Advertised on Canada's National Job Bank" dumps (EN/FR) under Open Government Licence, back to Jan 2023, with JSON/DCAT/Atom metadata feeds (open.canada.ca dataset ea639e28…). All of Canada, NOC/NAICS coded. (A real-time XML feed exists but is partner-gated.) **Non-tech 5 · Effort S · legal-risk low.**

**Bundesagentur für Arbeit / Jobsuche (Germany)** 🆕 **[international-expansion-later]** — REST, **no official public API** (community-reverse-engineered). Header `X-API-Key: jobboerse-jobsuche` (shared static key). `https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs` (search), `.../pc/v4/jobdetails/{base64(refnr)}` (detail). No documented quota. All German listings, all industries. Source: github.com/bundesAPI/jobsuche-api. **Non-tech 5 · Effort S · legal-risk medium (unofficial/undocumented ToS).**

**Reed.co.uk** 🆕 **[international-expansion-later, UK]** — REST `api.reed.co.uk/1.0/search`, Basic auth (key as username, blank password). Free self-serve key. 100 results/request; hourly rate-limit not stated on jobseeker docs (sibling recruiter API = 2,000/hr; third-party claims ~1k/day for jobseeker, unverified). UK-only, all industries. Source: reed.co.uk/developers/jobseeker. **Non-tech 4 · Effort S · legal-risk low.**

**Not viable gov:** EURES (API legally gated to recognized EURES partners), UK Find a Job (no public API — only adjacent apprenticeship API), Australia Workforce Australia/JobSearch (no listing-level public API; only aggregate IVI stats), NEOGOV/GovernmentJobs.com (powers 1,500+ US state/local agencies but **no public API** — the single biggest closed non-tech-gov gap), US state boards (CalCareers/WorkInTexas/OhioMeansJobs — portals only, no APIs).

### 2.5 New candidates — general aggregators & remote

**We Work Remotely** 🆕 — Public RSS `https://weworkremotely.com/remote-jobs.rss` (valid RSS 2.0; category-specific feeds exist). No auth, no published rate limit. **ToS caveat:** their API terms prohibit scraping/storing beyond what the API exposes and bar building a competing product; ambiguous whether the public RSS counts as "the API" — treat conservatively (attribute, cache-don't-persist-republish). Global remote, heavy dev/design/marketing/sales. Source: weworkremotely.com/remote-jobs.rss. **Effort S · non-tech 2 · legal-risk low-medium.**

**Findwork.dev** 🆕 — REST `GET /api/jobs/`. Free token (findwork.dev/developers). ~60 req/min (third-party-cited, unconfirmed on official docs). Global, **tech jobs only** — adds to existing tech skew, low priority for the non-tech goal. **Effort S · non-tech 1 · legal-risk low.**

**Juju** 🆕 (unverified) — Historically a free self-serve "Juju Publisher API" (REST/XML, key via signup, spec at juju.com/publisher/spec/). Site live in 2026 (~2.18M jobs). **Not re-verified functioning this cycle — probe before relying.** Global aggregator. **Effort S · non-tech 3 · legal-risk low.**

**WhatJobs FeedAPI** 🆕 (unverified) — Documented publisher "FeedAPI" (REST, JSON/XML), listed by directories as a free public API; auth/quota not confirmed on official page. Probe whatjobs.com/affiliates before integrating. Global. **Effort M · non-tech 3 · legal-risk low.**

**Not viable aggregators:** ZipRecruiter (publisher API discontinued Apr 2025), CareerBuilder (bankrupt Jun 2025, sold to JobGet), Glassdoor (API closed since 2021), Indeed (publisher API closed + `/jobs`,`/viewjob`,`/cmp/` robots.txt-disallowed + AI crawlers blocked — direct scraping = ToS+robots violation, **high risk / avoid**), SimplyHired (dead 2016), Talroo/Jobs2Careers (enterprise CPC ad platform), Talent.com/Trovit/Jobtome (affiliate revenue-share — require becoming a monetized publisher showing their sponsored redirects, not a free data key; a business/ToS decision, not an engineering one).

### 2.6 Non-tech vertical boards — confirmed dead-ends (documented for completeness)

- **Healthcare:** Health eCareers, Incredible Health, Trusted/Vivian Health, AMN Healthcare (enterprise VMS portal, not job search), HealthJobsNationwide (Jobiqo white-label, `/search` robots-blocked), AHA Health Career Center (search robots-blocked) — **zero public APIs; several robots.txt-block search paths.**
- **Skilled trades:** mikeroweWORKS (**explicitly blocks ClaudeBot/GPTBot/CCBot + 403 on search — do not scrape**), SkilledTrades.com, IBEW (fragmented across ~800 locals on UnionActive CMS), ConstructionJobs.com (**re-aggregates Careerjet/Indeed/Appcast** — chase those upstream instead) — **zero APIs.**
- **Finance:** eFinancialCareers (real API but employer-posting/resume-search only, partner-gated), Wall Street Oasis (no API) — **no retrieval API.**
- **Hospitality/retail/blue-collar:** Snagajob (biggest hourly platform — API is posting-only + robots-blocks `/search?q=*`), HCareers/Hospitality Online (no feed), CoolWorks (seasonal; no feed, thin robots.txt) — **no retrieval API.**

**Takeaway:** the non-tech vertical-board layer offers no free/legal API surface. Non-tech reach must come from (a) SMB ATS feeds, (b) municipal open data, (c) harder exploitation of existing broad aggregators.

---

## 3. Ranked NEW candidates (weighted for NON-tech + US-local reach)

Ranking weights: non-tech/local reach (heaviest), US-relevance-now, legal-safety, low implementation effort. International-expansion sources ranked lower for _now_ but flagged as high-value when JobScout expands.

| Rank   | Source                                   | Why                                                                                                                                                                            | Non-tech | US-now?              | Effort | Risk    |
| ------ | ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------- | -------------------- | ------ | ------- |
| **1**  | **BambooHR** (ATS)                       | ~30k mostly-sub-250-employee cos = dental/medical/local-mfg/nonprofit/retail — the exact non-tech local employers the app misses. Public no-auth JSON, clean 2-call pattern.   | 5        | ✅ (global incl. US) | S      | low     |
| **2**  | **US municipal open data** (NYC/Socrata) | Municipal roles = admin/sanitation/health/clerical/public-safety — archetypal non-tech local. Free, no-auth, official gov data. Reusable Socrata client across many US cities. | 5        | ✅                   | M      | low     |
| **3**  | **Breezy HR** (ATS)                      | Another ~9.7k SMB employers, public no-auth JSON, trivial to add alongside BambooHR (same client shape).                                                                       | 4        | ✅                   | S      | low     |
| **4**  | **Comeet / Spark Hire** (ATS)            | Public token-in-URL JSON, mid-market breadth beyond Greenhouse/Lever. Cheap incremental reach.                                                                                 | 3        | ✅                   | S      | low     |
| **5**  | **Teamtailor** (ATS)                     | ~20.6k EU/Nordic employers absent from current ATS set; broadens geography. Needs per-tenant JSON-shape discovery.                                                             | 3        | partial              | M      | low-med |
| **6**  | **We Work Remotely** (RSS)               | Fast RSS add, fills remote breadth; but tech/design/marketing skew = low non-tech payoff. ToS caution.                                                                         | 2        | ✅                   | S      | low-med |
| **7**  | **France Travail** (gov)                 | Best-in-class official EU gov API, all industries incl. heavy non-tech — top pick **when expanding to France**.                                                                | 5        | ❌ intl              | M      | low     |
| **8**  | **Reed.co.uk**                           | Clean free UK API, all industries — top **UK-expansion** pick.                                                                                                                 | 4        | ❌ intl              | S      | low     |
| **9**  | **Canada Job Bank** (open data)          | Free open-data dumps, all industries — easy **Canada-expansion** win.                                                                                                          | 5        | ❌ intl              | S      | low     |
| **10** | **Bundesagentur** (gov, DE)              | All German listings, all industries — **Germany-expansion**; but unofficial key = ToS-review-first.                                                                            | 5        | ❌ intl              | S      | med     |
| **11** | **SAP SuccessFactors** (ATS)             | Enterprise reach but XML-only free path + per-tenant multi-DC host discovery = poor effort/reward.                                                                             | 3        | ✅                   | L      | low     |
| **12** | **Findwork.dev**                         | Free tech API but adds to existing tech skew — deprioritize for the non-tech goal.                                                                                             | 1        | ✅                   | S      | low     |
| **13** | **Juju / WhatJobs FeedAPI**              | Possible free aggregator feeds — probe/verify before committing.                                                                                                               | 3        | ✅                   | S-M    | low     |

---

## 4. Key recommendations (top 8)

Effort S/M/L, impact = reach/coverage gain, legal_risk with reasoning.

**1. BambooHR ATS client** — **Effort S · Impact HIGH · Risk LOW.**
The single highest-value non-tech move. `{company}.bamboohr.com/careers/list` + `/careers/{id}/detail`, public no-auth JSON, no anti-bot. ~30k mostly-SMB employers (dental offices, local manufacturers, nonprofits, retail) — directly attacks the Session-24 under-reach of non-tech/local candidates. Legal: low — public endpoint intended to power the company's own careers page, same trust model as the already-accepted Greenhouse/Lever pattern. Slots into existing `scrape/*_scraper.py` + `company_registry`/`cc_harvest` discovery infra.

**2. US municipal open-data client (Socrata/SODA)** — **Effort M · Impact HIGH (non-tech gov) · Risk LOW.**
Build one reusable Socrata client, config per city (dataset ID + optional free app token). Start with NYC (`data.cityofnewyork.us/resource/kpav-sd4t.json`), extend to other Socrata cities (Chicago, SF, LA, Austin…). Pure non-tech local reach (admin/health/sanitation/clerical/public-safety). Legal: low — official open-government data explicitly published for programmatic use. Fills the gap left by NEOGOV being closed. The per-city config is the only friction.

**3. Breezy HR ATS client** — **Effort S · Impact MEDIUM · Risk LOW.**
`{company}.breezy.hr/json?verbose=true`, public no-auth. ~9.7k more SMB employers. Nearly free to add once BambooHR's SMB-ATS pattern exists. Legal: low (public careers-page endpoint).

**4. Comeet / Spark Hire ATS client** — **Effort S · Impact MEDIUM · Risk LOW.**
`comeet.co/careers-api/2.0/company/{uid}/positions?token={token}&details=true`. Token+uid are public (embedded in careers widgets; Comeet ships a sandbox pair). Broadens mid-market coverage. Legal: low — public by design, comparable to a Greenhouse board slug.

**5. Teamtailor ATS client** — **Effort M · Impact MEDIUM (EU breadth) · Risk LOW-MEDIUM.**
~20.6k EU/Nordic employers not covered by the current ATS set. Requires discovering the exact JSON shape per live tenant (network tab) since official docs only document the auth-gated API; the "Public Read" key option is a fallback. Legal: low for reading published jobs; medium only in that the exact ingestion path is less clearly "blessed" than Greenhouse's documented board API.

**6. We Work Remotely RSS client** — **Effort S · Impact LOW-MEDIUM · Risk LOW-MEDIUM.**
Quick RSS add for remote breadth. Tech/design/marketing skew limits non-tech payoff. Legal: low-medium — their API ToS prohibits scraping/storing beyond the API and bars competing products; it's ambiguous whether the public RSS is "the API," so attribute and cache rather than persist/republish. Add only after the non-tech ATS work above.

**7. France Travail (gov API)** — **Effort M · Impact HIGH-when-international · Risk LOW.**
Best EU gov API: free OAuth2, 4 calls/sec/app, all industries incl. heavy non-tech. Not US-relevant now — build when JobScout targets France. Legal: low (official gov API under a signed free license).

**8. Reed.co.uk (+ Canada Job Bank open data)** — **Effort S each · Impact MEDIUM-when-international · Risk LOW.**
Clean free national sources for UK and Canada expansion respectively, both all-industry (good non-tech). Reed = free key + Basic auth; Canada = open-data dumps, no auth. Build on international expansion, not before.

**Cross-cutting recommendation (no new client needed):** Before/alongside adding sources, **exploit existing broad aggregators harder for non-tech**. Adzuna, Careerjet, Jooble, and The Muse (40+ categories) already cover all industries; the Session-24 under-reach was partly a _query-term_ problem (tech-biased search terms), not only a source-coverage problem. Careerjet especially picks up trades/construction content that vertical boards (ConstructionJobs.com) merely re-aggregate from it. This is the cheapest non-tech reach gain of all.

**Explicit legal-risk flags:**

- **Indeed direct scraping = HIGH risk / avoid** — publisher API closed, core paths (`/jobs`, `/viewjob`, `/cmp/`) robots.txt-disallowed, AI crawlers named-blocked; ToS + robots both violated. Keep reaching Indeed only indirectly via SerpApi/Google Jobs aggregation as the app already does.
- **LinkedIn guest = MEDIUM-and-rising** (already accepted by the app) — 2025 Proxycurl lawsuit + permanent shutdown, Apollo/Seamless deplatforming, ramped detection. Still usable at JobScout's small non-commercial scale but re-label the risk and keep volume low.
- **Public ATS JSON APIs (BambooHR/Breezy/Comeet/Teamtailor) = LOW risk** — endpoints exist to serve public careers pages, intended for programmatic read.
- **Government APIs (municipal Socrata, France Travail, Canada, Reed) = LOW risk** — official, published for consumption.
- **Affiliate aggregators (Talent.com/Trovit/Jobtome) = business/ToS decision, not low-risk drop-ins** — require becoming a monetized publisher displaying their sponsored redirects.
- **Bundesagentur (DE) = MEDIUM** — works but relies on an unofficial shared key with undocumented ToS; legal review before shipping.

---

## 5. Cited sources (primary)

Adzuna developer.adzuna.com/docs/terms_of_service · USAJobs developer.usajobs.gov/Guides/Authentication · The Muse themuse.com/developers/api/v2 · Jobicy github.com/Jobicy/remote-jobs-api · RemoteOK remoteok.com/legal · Remotive github.com/remotive-io/remote-jobs-api · Himalayas himalayas.app/docs/remote-jobs-api · Arbeitnow arbeitnow.com/blog/job-board-api · Jooble jooble.org/api/about · Careerjet careerjet.com/partners/api · HN Algolia hn.algolia.com/api · LinkedIn linkedin.com/legal/user-agreement §8.2, nubela.co/blog/goodbye-proxycurl · SerpApi serpapi.com/google-jobs-api + /pricing · JSearch openwebninja.com/api/jsearch · Greenhouse support.greenhouse.io API overview · SmartRecruiters developers.smartrecruiters.com/docs/endpoints · Recruitee docs.recruitee.com/reference/intro-to-careers-site-api · Rippling developer.rippling.com/documentation/job-board-api · Workday jobspipe.dev/blog/workday-api-guide · Breezy developer.breezy.hr · BambooHR documentation.bamboohr.com/reference · Comeet developers.comeet.com/reference/careers-api-overview · Teamtailor docs.teamtailor.com · iCIMS developer-community.icims.com · Taleo treegarden.io/blog/taleo-alternatives-2026 · SAP SuccessFactors SAP KBA 2428902 · Paylocity paylocity.egain.cloud (PCTY-106364) · NYC data.cityofnewyork.us/resource/kpav-sd4t · Socrata dev.socrata.com/docs/app-tokens.html · France Travail francetravail.io/data/api/offres-emploi · Canada open.canada.ca dataset ea639e28 · Bundesagentur github.com/bundesAPI/jobsuche-api · Reed reed.co.uk/developers/jobseeker · We Work Remotely weworkremotely.com/remote-jobs.rss · Findwork findwork.dev/developers · ZipRecruiter jobboardsecrets.com (2025-02-10) · CareerBuilder/Monster bankruptcy washingtonpost.com (2025-06-24) · Glassdoor glassdoor.com/developer · Indeed docs.indeed.com + indeed.com/robots.txt · EURES eures.europa.eu · Talent.com talent.com/publishers · Snagajob docs.snagajob.com · eFinancialCareers recruiterhub.efinancialcareers.com/hire-api-documentation.html · mikeroweWORKS jobs.mikeroweworks.org/robots.txt · ConstructionJobs.com robots.txt (Careerjet/Indeed/Appcast re-aggregation).
