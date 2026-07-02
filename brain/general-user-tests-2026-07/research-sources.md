# ToS-Safe Source Expansion for Starving Verticals

Research date: 2026-07-02. Author: Opus research subagent (read-only; no code touched).
Companion to the 8 general-user persona tests (`persona-*.md`, `_structured-results.json`).

## Why this research

The blank-slate persona runs exposed the same structural failure across every non-tech
vertical: **the local inbox rode ~95-100% on a single keyed aggregator (Adzuna)**, the
careers/registry path added little (AI can't guess ATS slugs; marquee employers sit behind
CSRF-protected Workday), the keyless sources contributed ~0, and Indeed/NEOGOV are ToS-blocked.
Every persona's `biggest_gap` named the same missing lever: **CareerOneStop unkeyed** and
**no compliant way into hospital/district/warehouse employers**.

This report answers: which ToS-safe feeds/APIs actually fill each starving vertical, with URL
evidence and a compliance note. **Nothing here recommends scraping Indeed or NEOGOV/governmentjobs.com.**

---

## HEADLINE FINDINGS (read these first)

### 1. Workday `wday/cxs` public JSON API is the single highest-value fix

Every persona that lost its marquee local employers (nurse: St. Luke's/HCA; warehouse:
FedEx/Nike/AutoZone/Int'l Paper; data-changer: Banner/Phoenix Children's/HonorHealth;
mecheng: PACCAR/McKinstry; consultant: Deloitte/McKinsey) lost them because those employers
run **Workday**, and the current scraper hits Workday's HTML/CSRF wall (HTTP 422).

Workday tenants expose a **public, unauthenticated JSON search API** at:

```
POST https://{host}.myworkdayjobs.com/wday/cxs/{tenant}/{careerSite}/jobs
Content-Type: application/json
Accept: application/json
body: {"appliedFacets":{}, "limit":20, "offset":0, "searchText":""}
```

`{host}` is a datacenter prefix (`wd1`/`wd3`/`wd5`), `{careerSite}` is usually `External` or a
custom site name. Detail pages: `GET /wday/cxs/{tenant}/{site}/job/{externalPath}`. This is the
**same host the persona probes already found** (`stlukesonline`, `autozone`, etc.) - the fix is
to POST the JSON search body instead of GET-ing HTML, which is exactly what dodges the CSRF-token
requirement. This single pattern converts most of the "unreachable Workday" seed failures into
live results and generalizes across nursing, warehouse, mech-eng, and consulting.

Caveats to design around: Akamai bot management (throttle, single well-behaved request cadence,
set a real UA + `Accept: application/json`), 10,000-result hard cap per query (slice by
location/category), and per-tenant slug/prefix discovery (the seeding UX still needs to help
users find the right `{tenant}` + `wdN` prefix - a resolver, not a guess).

### 2. CareerOneStop's _Jobs_ API is now governance-gated - the held Seed-My-Area plan's assumption is STALE

The plan (and every persona report) treats CareerOneStop as "get a free key and the #1 local
lever turns on." That is **no longer true for the job-search endpoint**. As of **August 27, 2024**,
the CareerOneStop **List Jobs / Jobs API v2** requires a request that is **"reviewed and approved
by the NLx Research Hub Governance Board,"** and public-job-board use cases "may be pointed to the
offerings provided by the NLx Research Hub" instead. The general career/LMI/occupation/skills
APIs remain self-serve free, but **the job listings are the gated part**. The Business Finder /
employer-lookup endpoints the Seed-My-Area plan wants for local employer discovery are in the
open LMI/occupation family and should still be self-serve - **verify at registration**, but plan
for the jobs feed to need an approval step (days-to-weeks, not instant), and have a fallback.

### 3. Adzuna remote querying: the persona "0 results for Remote" is a location-handling bug, not an Adzuna limit

Adzuna _does_ return US remote jobs. Two documented facts: (a) `where=remote` /
`location=remote` is an accepted query (Adzuna publishes an `adzuna.com/remote` surface and dev
integrations use `location=remote`); (b) **Adzuna duplicates each remote posting across the 10
largest metros** and appends "remote" to title+description. So the compliant strategy is: for a
remote-only user, either put the token in `what` (`what=remote marketing manager`, broad/blank
`where`) or issue `where=remote`, rather than geocoding the literal string "Remote" into a
lat/long gate (which is what the marketing-remote persona hit -> 0 results).

---

## AREA-BY-AREA RECOMMENDATIONS

### (A) K-12 EDUCATION (teacher-columbus)

Districts run Frontline/AppliTrack (no clean feed) or NEOGOV (**ToS-blocked, never scrape**).
The ToS-safe channels:

- **REAP (Regional Education Applicant Program)** - a free, applicant-first network of **per-state
  public teacher job portals** (`usreap.net`, `pareap.net`, `moreap.net`, `ctreap.net`,
  `nmreap.net`, ...). Public job search is free to seekers; Missouri exposes a public search URL
  (`moreap.net/jobsrch.php`). Best structural fit for K-12 because it's state-scoped and public.
  ToS note: designed as a free public applicant service; each state portal is its own site - honor
  per-state robots.txt and prefer light HTML reads over aggressive crawling.
- **EdJoin** (`edjoin.org`) - "the nation's #1 education job board," public browse/search by
  region and keyword, no login to view (`edjoin.org/Home/JobSearch`). Very strong in CA and
  growing elsewhere. ToS note: public listings; scrape politely / check robots.txt, no login wall.
- **K12JobSpot** (`k12jobspot.com`, Frontline) aggregates **AppliTrack district jobs** and has a
  public browse path (`/Search/Opportunities`), but it's a Frontline property with account-gated
  features - lower priority; treat as HTML-fragile and ToS-ambiguous, not an API.
- **CareerOneStop/NLx** (see area E) already carries district postings via the NLx feed - a keyed
  CareerOneStop covers a lot of K-12 without touching Frontline at all.

The clean play: add REAP (state-portal-aware) + EdJoin as HTML sources, and lean on CareerOneStop/NLx
for the rest. Do **not** try to scrape Frontline/AppliTrack district portals as a general source.

### (B) HEALTHCARE / NURSING (nurse-boise, data-changer-phoenix)

- **Workday `wday/cxs` JSON API** (Headline #1) is the fix for the hospital systems the nurse
  persona lost (St. Luke's, HCA-family, most large IDNs run Workday). Highest impact here.
- **SmartRecruiters public Posting API** - already have a fetcher; confirm it's used for health
  employers. `GET https://api.smartrecruiters.com/v1/companies/{companyId}/postings` is **public,
  no key**, JSON, paginated. Many hospital/health-services employers use SmartRecruiters. ToS note:
  the Posting API is explicitly the public/published-jobs endpoint (only the POST-application path
  needs auth).
- **Greenhouse Job Board API** - `GET https://boards-api.greenhouse.io/v1/boards/{token}/jobs`,
  **public, no auth**, JSON. Health-tech and some provider orgs use it (persona nurse seeds that
  probed live were Greenhouse). Already partly wired; ensure the health registry uses it.
- **Health eCareers / HospitalCareers** - large nursing/hospital boards, but **no public API or
  RSS was found**; access requires a direct partner/employer relationship. **Do not** treat as a
  drop-in feed. (Included so the answer is "we checked - no compliant feed exists yet.")

Net: the nurse vertical is solved far more by (Workday JSON + SmartRecruiters/Greenhouse public
APIs for the actual local systems) + (a keyed CareerOneStop/NLx national feed) than by any
nursing-branded board.

### (C) WAREHOUSE / HOURLY (warehouse-memphis)

Indeed is forbidden and is the dominant hourly board, so the answer is **assemble the employers,
not find a hourly-board API**:

- **Workday `wday/cxs` JSON API** - FedEx, GXO, Ryder, DHL, Kuehne+Nagel, AutoZone, Int'l Paper,
  Nike DCs largely run Workday. Headline #1 directly recovers the marquee Memphis employers the
  persona lost to CSRF 422s.
- **CareerOneStop / NLx** (area E) - the NLx feed is **strong on blue-collar/on-site** and is the
  Guide's stated #2 lever for exactly this persona; a keyed CareerOneStop is the biggest single
  win for warehouse.
- **Snagajob** - large hourly board, **but its documented XML feed is INBOUND only** (employers
  POST jobs _into_ Snagajob with CPC/CPA budgets); there is **no public outbound feed** for
  aggregators. **Do not** recommend consuming Snagajob - confirmed not a source.
- Keep USAJobs (federal warehouse/logistics roles do appear) and the Greenhouse/SmartRecruiters
  public APIs for 3PLs that use them.

### (D) NATIONAL LABOR EXCHANGE (NLx / usnlx.com)

- **What it is:** DirectEmployers + NASWA public-private partnership; **4M+ verified, deduped,
  employer-direct postings**, updated daily, shared with all states + a vetted syndication network.
- **Access model:** gated by the **NLx Data Trust Governance Board** via signed data-use agreements.
  Currently approved use cases are (i) state workforce-agency LMI and (ii) discrete nonprofit
  research. Product-development / job-matching / AI use cases must **submit a data request**;
  **public job boards (free to all users) may be directed to a different source**. API 2.0 exists
  for existing NLx Research Hub users (email `nlxresearchhub@naswa.org`).
- **Cost:** not published; governed access, not a self-serve free API. Redistribution behind a
  paywall is excluded.
- **Verdict for Zaggregate:** do **not** integrate NLx directly - the governance/agreement overhead
  is wrong for a solo desktop app. **Consume NLx indirectly through CareerOneStop's Jobs API**,
  which is the official public gateway to the NLx feed (subject to area E's gating).

### (E) CareerOneStop API - confirm signup, limits, and Seed-My-Area coverage

- **Auth:** `userId` + Bearer **API token** in the `Authorization` header.
- **List Jobs endpoint:**
  `GET /v1/jobsearch/{userId}/{keyword}/{location}/{radius}/{sortColumns}/{sortOrder}/{startRecord}/{pageSize}/{days}`
  (v2 adds `enableJobDescriptionSnippet` + `enableMetaData`). Parameters map cleanly to the app's
  keyword/location/radius model. **Underlying data = the National Labor Exchange.**
- **Data license:** "open data under USDOL's Open Data Policy" - the _cleanest_ ToS posture of any
  source here.
- **THE CATCH (updates the held plan):** the **Jobs API is governance-gated since Aug 27 2024**
  (NLx Research Hub Governance Board approval; public-job-board use may be redirected). The
  occupation/LMI/skills/Business-Finder family stays self-serve free. **Action:** register for the
  free key, request Jobs API access early (it may take approval time), and confirm the **Business
  Finder / employer-lookup** endpoints the Seed-My-Area plan relies on are in the open family
  (expected yes) - the plan should not assume the _jobs_ feed is instant.

### (F) REMOTE VERTICALS beyond WWR / RemoteOK / Himalayas

The app already has WWR, RemoteOK, Jobicy, Himalayas, WorkingNomads, Remotive - good coverage.
Marginal adds:

- **Himalayas has a `search` endpoint** (`https://himalayas.app/jobs/api/search`, keyless) with
  `q/country/seniority/employment_type/timezone` filters - if the app currently pulls the _browse_
  feed, switching to `search` fixes the marketing-remote persona's "region-locked remote / non-US"
  false positives (filter `country=US`). **Compliance:** Himalayas requires **attribution + a
  link back**, and **prohibits re-submitting its jobs to Jooble/Neuvoo/Google Jobs/LinkedIn** -
  honor this (don't forward Himalayas rows into any Jooble-keyed path).
- **jobdataapi.com** - free-tier public ATS aggregator with a `has_remote=true` filter; keyless
  testing tier, key lifts the hourly rate limit. Useful breadth, US+global. Verify per-endpoint ToS.
- **Arbeitnow** (`arbeitnow.com/api/job-board-api`) - free, **no key**, ATS-sourced, has `remote`
  - `visa_sponsorship` fields - but **Europe-skewed**, so low value for US personas. Optional.

### (G) Adzuna remote querying (fixes marketing-remote's #1 bug)

- Adzuna **does** serve US remote jobs; the persona's "0 for Remote" came from geocoding the
  literal city "Remote."
- **Strategy:** for remote-only users, don't geocode "Remote" into the lat/long location gate.
  Instead either (a) put remote in `what` with a broad/blank `where`
  (`what=remote+<role>`, `where=` empty = nationwide), or (b) pass `where=remote`. Adzuna also
  **fan-copies each remote job across the 10 largest metros** and appends "remote" to
  title+description - so a metro search (e.g. the user's home metro) will already surface remote
  roles, and a title/description "remote" check is reliable.
- Call `GET /v1/api/jobs/us/categories` first to use valid category tags; free tier has a rate
  limit (the persona already saw back-off), so keep the remote fan-out modest.

---

## COMPLIANCE SUMMARY (what NOT to do)

- **Indeed:** ToS-blocked - never scrape. Not recommended anywhere above.
- **NEOGOV / governmentjobs.com:** ToS-blocked - never scrape. (K-12 answer routes around it via REAP/EdJoin/NLx.)
- **Snagajob:** inbound-only feed - not a consumable source; excluded.
- **Health eCareers / HospitalCareers:** no public feed found - excluded (partner-only).
- **NLx direct:** governed data-use agreement - consume via CareerOneStop instead.
- **Himalayas:** allowed _with_ attribution + link-back; must NOT be forwarded to Jooble/Google Jobs.
- **Workday `wday/cxs`, SmartRecruiters Posting API, Greenhouse Job Board API:** documented public,
  unauthenticated GET/POST endpoints for _published_ jobs - the compliant, intended read path
  (application submission is the only auth-gated part).

## SUGGESTED PRIORITY (impact x compliance-cleanliness)

1. **Workday `wday/cxs` JSON search** - unlocks nursing/warehouse/mech-eng/consulting marquee employers. (L)
2. **Register CareerOneStop key + request Jobs API access now** - the recurring #1 gap; open-data license. (S to key, gated to jobs)
3. **Adzuna remote strategy fix** - one location-handling change, big remote-user win. (S)
4. **Himalayas `search` endpoint + `country=US`** - fixes remote false positives, keyless. (S)
5. **REAP + EdJoin** for K-12; ensure Greenhouse/SmartRecruiters public APIs cover health/3PL. (M)
6. **jobdataapi.com** free tier as breadth backstop. (M)
