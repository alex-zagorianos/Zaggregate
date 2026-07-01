# Research — Indeed access paths (2026) (2026-07-01)

_Confidence: n/a_

## Summary
There is no legitimate, free, self-serve consumption API for Indeed listings in 2026 — Indeed's Publisher/XML/Job-Sync/Sponsored-Jobs programs are all employer-side (posting into Indeed), not job-seeker-side (reading out), and the last self-serve syndication path effectively died years ago. The only "official-ish" indirect path is Google-for-Jobs aggregation, reachable via SerpApi's `google_jobs` engine (already wired in JobScout as the default `SERPAPI_ENGINE`) or via JSearch/RapidAPI (already wired, 200 req/mo free) — both pull from the same underlying Google Jobs index, so they overlap rather than compound. A dedicated SerpApi "indeed" engine, which JobScout's `config.py`/`serpapi_client.py` code currently supports as an opt-in, does NOT appear in SerpApi's current public engine catalog — this needs a runtime verification/fallback, not blind trust. Apify Indeed actors work (98.7% success rate observed) and one pricing model (misceres/indeed-scraper, ~$3/1,000 results) even fits inside Apify's permanent free $5/mo credit, but scraping Indeed violates Indeed's Terms of Use and robots.txt (`Disallow: /jobs`, `/viewjob`) — CFAA-safe post-hiQ v. LinkedIn, but breach-of-contract risk remains real, which conflicts with JobScout's stated "no mass scraping" policy. The strongest, lowest-risk, already-partially-built path is the browser extension's user-gated DOM capture (`browser_ext/content.js`), which is legally the same footing as Grammarly/Huntr/Teal/Simplify's extensions (thousands of users, no known Indeed legal action) and should be hardened rather than replaced.

## Findings
## 1. SerpApi `indeed` engine — status uncertain, needs verification

JobScout already has this wired: [`search/serpapi_client.py`](search/serpapi_client.py:69) branches on `config.SERPAPI_ENGINE` and, when set to `"indeed"`, sends `{engine: "indeed", q, l, api_key}` directly to `SERPAPI_URL`. [`config.py:266-269`](config.py:266) documents it as "a direct Indeed pull — paid; different JSON shape, parsed defensively."

**Current-facts check (2026-07-01):** SerpApi's own published engine catalog (fetched from `serpapi.com/search-engine-apis`) lists 80+ engines — Google (30+ sub-APIs including **Google Jobs** and **Google Jobs Listing**), Bing, Baidu, DuckDuckGo, Yahoo, Yandex, Amazon, eBay, Walmart, Apple/Google Play Store, maps/local/travel platforms, Facebook/Instagram profile, YouTube — and **does not list a standalone "Indeed" engine**. Multiple independent searches (site:serpapi.com, changelogs, GitHub, blog posts through Sept 2025–Jan 2026) turn up no Indeed-engine documentation either. It's possible this was an undocumented/legacy engine that once existed and has since been quietly dropped, but nothing in 2025–2026 sources confirms it currently works. **Recommendation: do not trust the `indeed` engine string blindly — JobScout's `parse_results()` already handles an unrecognized shape gracefully (returns `[]`), but the code should log/surface a warning when `engine=="indeed"` and the response has no `jobs_results`, and the default should stay `google_jobs`** (documented, stable, and already the default per `SERPAPI_ENGINE = os.getenv("SERPAPI_ENGINE", "google_jobs")`).

- Pricing (verified at [serpapi.com/pricing](https://serpapi.com/pricing)): **Free = 250 searches/mo, 50/hr throughput**; paid tiers $25/1,000, $75/5,000, $150/15,000, $275/30,000 — only *successful* searches count; no rollover. JobScout's `SERPAPI_MONTHLY_LIMIT = 100` in `config.py` is conservative relative to the actual 250 free-tier cap — worth bumping to 250 (S effort, one-line config change + a quota-file migration note).
- **Legal status of SerpApi itself:** Google sued SerpApi Dec 19, 2025 (N.D. Cal., 4:25-cv-10826) alleging DMCA circumvention of Google's "SearchGuard" anti-bot system (this is about *scraping Google Search*, not Indeed data specifically). SerpApi filed a motion to dismiss Feb 20, 2026; hearing before Judge Gonzalez Rogers was set for May 19, 2026. [Google v. SerpApi docket](https://www.courtlistener.com/docket/72059948/google-llc-v-serpapi-llc/), [SerpApi's motion-to-dismiss post](https://serpapi.com/blog/google-v-serpapi-motion-to-dismiss-why-were-in-the-right/). **This is a real platform-continuity risk**: since `google_jobs` (JobScout's actual Indeed-reach mechanism via SerpApi) rides on the same scraping infrastructure Google is suing over, an adverse ruling could disrupt or shut down the whole SerpApi product, not just an Indeed-specific feature. Not an immediate action item, but a reason not to make SerpApi a single point of failure for Indeed reach.

## 2. JSearch (RapidAPI) — already wired, same underlying source as #1

[`search/jsearch_client.py`](search/jsearch_client.py) + `config.py:118-124` (`JSEARCH_MONTHLY_LIMIT = 200`, `JSEARCH_RATE_LIMIT = 5/min`) is already live. Verified 2026 facts: free BASIC tier = **200 requests/month**, no card required, burst-capped at 1,000 req/hour (i.e., the monthly count, not the hourly rate, is the real constraint). JSearch's own docs state it "pulls from Google for Jobs and the Public Web" — **meaning JSearch and SerpApi's `google_jobs` engine are functionally the same upstream data source (Google for Jobs aggregation), not independent Indeed feeds.** Running both doesn't multiply Indeed coverage the way it might feel like it should; it mostly gives two independently-rate-limited windows into the same pool, plus some de-dup value from differing normalization/ranking. `models.normalize_url`'s `jk`-collapsing (see below) is what prevents these from creating duplicate inbox entries when both surface the same Indeed posting. **No new work needed** beyond noting this overlap in `brain/scraping-sources.md` (already partially captured at line 21/44).

## 3. Apify / third-party Indeed scraper actors — works, but violates ToS; not free at meaningful volume

Tested two actor pricing models directly:
- **`misceres/indeed-scraper`** — pay-per-event, **~$3.00/1,000 job listings**, 98.7% run-success rate, 26k+ users. At this rate, Apify's **permanent free $5/mo platform credit** (confirmed at [apify.com/pricing](https://apify.com/pricing) — no card required, doesn't roll over) covers **~1,600 Indeed listings/month for $0**.
- **`curious_coder/indeed-scraper`** — $20/mo actor rental **on top of** a paid Apify plan (starts $49/mo) — not free-tier viable.

**Legal/ToS:** Indeed's Terms of Use ([indeed.com/legal](https://www.indeed.com/legal)) explicitly prohibits "robots, spiders, or other automated means" for data collection. Indeed's robots.txt (fetched live) disallows `/job/`, `/jobs`, `/viewjob`, and all `/q-`/`/l-` query-parameter search URLs for general crawlers (and even more aggressively for AI-bot user agents). Post-*hiQ Labs v. LinkedIn* (9th Cir., reaffirmed 2022), scraping **publicly accessible** data does not by itself violate the CFAA — but hiQ ultimately **lost on breach-of-contract / unfair-competition grounds** and paid $500k in the final 2022 settlement, which is the more relevant precedent here: ToS violations create real civil liability even when CFAA doesn't apply. [hiQ Labs v. LinkedIn — Wikipedia](https://en.wikipedia.org/wiki/HiQ_Labs_v._LinkedIn), [Fenwick analysis](https://www.fenwick.com/insights/publications/hiq-labs-scrapes-by-again-the-ninth-circuit-reaffirms-that-data-scraping-does-not-violate-the-cfaa-1). This is precisely the class of risk JobScout's own architecture notes reject ("NO JA3-spoofing/proxy-rotation mass scraping — ToS/legal risk," `brain/research-competitors-2026-07-01.md:49`). **Recommendation: do not integrate an Apify Indeed actor into JobScout's default pipeline.** Legal risk = **medium-high** (contract claim exposure, not criminal), inconsistent with the app's stated free+legal+local constraints, and it would need per-user BYO-Apify-key gating (like SerpApi/JSearch) to even attempt — not worth the ToS exposure for the coverage gained given the extension path exists.

## 4. Indeed Publisher Program / XML feed / Job Sync API / Sponsored Jobs API — confirmed dead-end for consumption, and getting MORE restrictive

Verified directly against `docs.indeed.com`: every documented API there (**Job Sync API**, **Sponsored Jobs API**, **Indeed Apply**, XML feed reference) is **employer/ATS-partner-side** — i.e., for pushing job postings *into* Indeed, not for a third party to pull listings *out*. There is no documented GET/search endpoint for job-seeker consumption anywhere in Indeed's partner docs.

The classic **Publisher Program** (revenue-share syndication of Indeed's aggregated listings out to third-party job-search sites) has been progressively closing since 2017 (no new *paid* job boards accepted as of March 31, 2017) and effectively became invite/relationship-only — no public self-serve signup exists in 2026; third-party WordPress integrations built on it (e.g., the "Indeed Integration" plugin) were discontinued Nov 2, 2020 after Indeed changed its API to make retrieval impossible. **2026 makes this worse, not better**: Indeed announced (July 2025, formalized Oct 2025) it is discontinuing "single-source" XML feeds entirely — **March 31, 2026 for free/organic feeds, end of 2026 for sponsored** — pushing all employer integrations to direct API partnerships. This is a supply-side tightening for *employers posting to Indeed*, and confirms there is zero movement toward reopening any consumption-side access for apps like JobScout. [Indeed Partner Docs](https://docs.indeed.com/), [HR Dive coverage](https://www.hrdive.com/news/visibility-ends-for-certain-free-single-source-xml-feeds-on-indeed/816209/). **Recommendation: treat this path as permanently closed; no further investigation warranted.**

## 5. Indeed RSS — dead since ~2013-2014, confirmed non-functional today

Indeed's native RSS feeds (`indeed.com/rss?q=...&l=...`) were discontinued around 2013-2014; a live test of that URL pattern today returns **HTTP 404**. Historical forum chatter claims an informal partial restoration, but nothing that holds up in 2026 — third-party "Indeed RSS feed generator/builder" sites (e.g., newsloth) are themselves just HTML-scraping wrappers repackaging Indeed pages as RSS, carrying the same ToS/robots.txt risk as #3 above with none of Apify's reliability engineering. `brain/scraping-sources.md:44` already correctly notes "Indeed RSS — JSearch covers Indeed with better structure." **No action needed; confirmed correctly deprioritized already.**

## 6. Browser-extension user-gated DOM capture — the compliant path, already partially built, needs hardening

This is the legally strongest and most defensible route, and JobScout already implements the core of it:
- [`browser_ext/content.js`](browser_ext/content.js:73) has a full Indeed site definition — card-list selectors (`div.job_seen_beacon`, `li[class*='JobListItem']`) plus a **detail-pane** registry (`.jobsearch-RightPane`, `#jobsearch-ViewjobPaneWrapper`) that fires only once a job is genuinely opened (id-gated on `jk`/`vjk`, per the comment at line 424-430 explaining why premature capture before the URL settles is deliberately avoided).
- [`models.py:53-72`](models.py:53) `normalize_url()` collapses every Indeed URL variant (`rc/clk`, `viewjob`, `m/viewjob`, country subdomains) to a canonical `indeed.com/viewjob?jk={jk}` identity, which is exactly right for merging extension-captured cards with SerpApi/JSearch-sourced duplicates of the same posting.
- [`browser_ext/selector_check.js`](browser_ext/selector_check.js:1) already exists as a manual selector-rot self-test — paste-and-run against a live Indeed results+detail page, reports which selectors still match.

**Legal footing:** this is architecturally identical to what Huntr, Teal, and Simplify's extensions already do at scale (Huntr's Indeed/LinkedIn card+detail capture, Teal's clipper-tracker model) — reading the DOM the user's own authenticated browser already rendered, on a page the user navigated to themselves, with no server-side bulk requests to Indeed. This is legally closer to an ad-blocker/Grammarly-class extension than to scraping: no CFAA "without authorization" access (the user IS authorized, it's their own session), and Indeed's ToS anti-automation clause is aimed at bots hitting their servers, not a user's local browser reading its own rendered page. No known Indeed legal action against any of these widely-used extensions. **Legal risk = low.**

**Reliability gap = selector rot**, the only real cost here. Concrete hardening recommendations:
- **(S)** Wire `selector_check.js` into a scheduled/CI-adjacent check rather than a manual paste-and-run — e.g., a small Playwright script that loads a real Indeed search+detail page headlessly and runs the same selector set, alerting on drift. Given JobScout already has Scrapling/Chromium wired for stealth fetches (per memory: "Scrapling lean-integrated... on-demand Chromium download"), this is a natural reuse.
- **(S)** Add a "zero cards captured" telemetry signal in `scrape/browser_receiver.py` so silent selector rot surfaces to Alex/dad quickly instead of just quietly returning empty inboxes.
- **(M)** Broaden the card selector set defensively (Indeed A/B-tests card markup periodically) — add 1-2 more fallback selectors per field the way LinkedIn's entry already does (`selector_check.js:12-38` shows LinkedIn already has 3-4 fallbacks per field vs Indeed's leaner set).

## 7. Other paths considered and ruled out

- **Common Crawl** (`discover/cc_harvest.py`): CC generally respects `robots.txt`, and Indeed's robots.txt disallows `/jobs` and `/viewjob` — so CC's index of Indeed job-listing pages is expected to be sparse-to-nonexistent. Not worth building a CC-Indeed harvester.
- **Careerjet / Jooble** (already integrated per JobScout's client list): these are legitimate metasearch/affiliate partners with their own licensing arrangements; they may already surface some Indeed-adjacent or Indeed-overlapping postings indirectly through their own aggregation deals. No new integration work needed — already covered by existing clients.
- **Google-for-Jobs structured-data (JSON-LD) on career pages**: irrelevant to Indeed specifically — this captures the originating employer page, not Indeed's own listing.

## The recommended Indeed strategy

1. **Keep SerpApi `google_jobs` as the default engine** (already the default) as the BYO-key, opt-in indirect Indeed-reach path — it's documented, stable, 250 free searches/mo, and legally clean (SerpApi bears the scraping-of-Google risk, not JobScout, and JobScout never touches Indeed's servers directly).
2. **Demote/guard the `SERPAPI_ENGINE=indeed` option** — add a runtime check that warns (not silently returns `[]`) when the "indeed" engine yields no `jobs_results`, since its current existence in SerpApi's catalog is unverified for 2026. (S effort.)
3. **Do not add Apify or any other Indeed scraper actor** — inconsistent with JobScout's free/legal/local constraints; ToS breach-of-contract risk (medium-high) for marginal coverage gain over what google_jobs/JSearch/the extension already provide.
4. **Invest further effort in the browser extension**, JobScout's actual compliant, already-partially-built Indeed path: automate `selector_check.js` (S), add silent-failure telemetry (S), and broaden Indeed's selector fallback set to match LinkedIn's robustness (M). This is the only path with long-term legal durability (low risk, no dependency on a third-party API vendor who may itself get sued out of existence — see the live SerpApi/Google litigation).
5. **No action on Indeed Publisher Program / XML feed / Job Sync API / RSS** — all confirmed dead-ends for a consumption-side app in 2026; don't revisit unless Indeed publicly reopens a job-seeker API (no evidence of that trend — the opposite is happening on the employer-feed side).

## Key recommendations

- **[S/medium/risk:none]** Add a runtime warning/fallback when SERPAPI_ENGINE="indeed" returns no jobs_results, since SerpApi's 2026 public engine catalog no longer documents a standalone Indeed engine (only google_jobs/google_jobs_listing).  
  Prevents JobScout from silently trusting an unverified/possibly-deprecated code path in serpapi_client.py while keeping the existing defensive parse_results() behavior.
- **[S/low/risk:none]** Bump SERPAPI_MONTHLY_LIMIT in config.py from 100 to SerpApi's actual verified free-tier cap of 250 searches/month.  
  Current config is more conservative than the real free-tier limit, leaving usable quota on the table.
- **[S/low/risk:medium]** Do not integrate an Apify (or any other) Indeed scraper actor into JobScout's pipeline, even as a BYO-key optional client.  
  Indeed's ToS explicitly bans automated collection and robots.txt disallows /jobs and /viewjob; post-hiQ v. LinkedIn, CFAA risk is low but breach-of-contract/unfair-competition liability is real (hiQ paid $500k on exactly that theory) and conflicts with JobScout's own no-mass-scraping policy.
- **[M/high/risk:low]** Harden the existing browser-extension Indeed capture: automate browser_ext/selector_check.js as a scheduled headless check, add zero-cards-captured telemetry to scrape/browser_receiver.py, and broaden Indeed's card/detail selector fallbacks to match LinkedIn's existing robustness.  
  This is the only Indeed-reach path with durable legal footing (user-gated, single-session DOM read, same model as Huntr/Teal/Simplify extensions) and no dependency on a third-party vendor (SerpApi is currently being sued by Google, a real platform-continuity risk).
- **[S/low/risk:none]** Document in brain/scraping-sources.md that SerpApi google_jobs and JSearch draw from the same underlying Google-for-Jobs aggregation, so running both is redundancy/dedup insurance, not additive Indeed coverage.  
  Sets correct expectations for future coverage-math work (coverage/estimators.py) that treats these as independent sources.

## Sources
- https://serpapi.com/pricing
- https://serpapi.com/search-engine-apis
- https://serpapi.com/blog/google-v-serpapi-motion-to-dismiss-why-were-in-the-right/
- https://www.courtlistener.com/docket/72059948/google-llc-v-serpapi-llc/
- https://searchengineland.com/google-sues-serpapi-466541
- https://www.openwebninja.com/api/jsearch
- https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch
- https://apify.com/misceres/indeed-scraper
- https://apify.com/curious_coder/indeed-scraper
- https://apify.com/pricing
- https://docs.indeed.com/
- https://docs.indeed.com/job-sync-api/job-sync-api-guide
- https://www.hrdive.com/news/visibility-ends-for-certain-free-single-source-xml-feeds-on-indeed/816209/
- https://community.sap.com/t5/human-capital-management-blog-posts-by-sap/indeed-s-transition-away-from-xml-feeds-what-sap-successfactors-customers/ba-p/14326692
- https://wpjobmanager.com/document/other/indeed-integration/
- https://www.indeed.com/legal
- https://www.indeed.com/robots.txt
- https://en.wikipedia.org/wiki/HiQ_Labs_v._LinkedIn
- https://www.fenwick.com/insights/publications/hiq-labs-scrapes-by-again-the-ninth-circuit-reaffirms-that-data-scraping-does-not-violate-the-cfaa-1
- https://calawyers.org/privacy-law/ninth-circuit-holds-data-scraping-is-legal-in-hiq-v-linkedin/
- https://help.huntr.co/en/articles/9859408-the-huntr-chrome-extension
- https://www.tealhq.com/tool/job-search-chrome-extension