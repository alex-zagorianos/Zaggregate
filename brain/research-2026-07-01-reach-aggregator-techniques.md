# Research — How exhaustive aggregators achieve coverage (2026-07-01)

_Confidence: high_

## Summary
The exhaustive-coverage tools split into two camps: (1) ToS-risky live scrapers of consumer job boards (JobSpy, JobFunnel, and covertly JobRight.ai) that rely on proxy rotation, headless browsers, and account/cookie spoofing against sites whose Terms of Service explicitly forbid it — legal under the CFAA per hiQ v. LinkedIn (2022, settled 2022) and Meta v. Bright Data (2024), but exposed to contract-breach and platform-enforcement risk, as shown by LinkedIn shutting down Proxycurl in July 2025; and (2) source-of-truth harvesters (HiringCafe, and JobScout's own architecture) that crawl employer ATS/career pages directly — fully legal, and arguably MORE exhaustive and fresher than LinkedIn/Indeed because those consumer boards are themselves downstream syndication targets, not job sources. The single most important insight for JobScout: a requisition posted in Greenhouse/Workday/Lever gets pushed to LinkedIn/Indeed/Glassdoor via "Job Wrapping" (an XML feed LinkedIn recrawls roughly every 24 hours) and via Indeed/Google's JSON-LD `schema.org/JobPosting` crawlers (visible ~24-72h after publish) — meaning a registry of ATS-native URLs is a legal, faster, dedup-friendly proxy for "being on LinkedIn/Indeed" without ever touching those sites. JobScout already implements the correct primitive (`scrape/jsonld_scraper.py` extracting the same structured data Google/Indeed consume) but the constraint is registry breadth, not scraping cleverness — reinforcing the Session 19/22/23 finding that company/ATS coverage, not more scrapers, is the exhaustiveness lever.

## Findings
## 1. JobSpy (open source, `speedyapply/JobSpy`, ~3.8k stars, PyPI `python-jobspy`)

**How it sources jobs:** Direct, live, unauthenticated (and for LinkedIn, session-cookie-based) scraping of LinkedIn, Indeed, Glassdoor, ZipRecruiter, Google Jobs, Bayt, and BDJobs search-results pages, run concurrently per board. [github.com/speedyapply/JobSpy](https://github.com/speedyapply/JobSpy)

**Techniques (and why they're ToS-risky):**
- **Proxy rotation** — round-robins IPs across all board scrapers specifically "to bypass blocking," a direct anti-detection countermeasure against IP-based rate limiting.
- **User-agent spoofing** — override parameter to mimic real browsers.
- **No official API use anywhere** — it scrapes the same HTML/JSON a logged-in or logged-out browser would see, which is exactly the fact pattern that made hiQ v. LinkedIn and Meta v. Bright Data turn on *contract* (ToS breach), not CFAA.
- **Known fragility/enforcement signals (2025-2026):** open GitHub issues report 429 "Blocked by ZipRecruiter for too many requests" ([issue #283](https://github.com/speedyapply/JobSpy/issues/283)) and a standing feature request to gracefully handle LinkedIn 429s instead of crash-exiting ([issue #129](https://github.com/Bunsly/JobSpy/issues/129)). The maintainer notes "LinkedIn is the most restrictive and usually rate limits around the 10th page with one IP," and all board endpoints cap near ~1000 results per query — meaning even JobSpy's live scraping can't get true exhaustive coverage of a single query, let alone a labor market.
- **No documented dedup logic** and **zero ToS/legal discussion in the README** — it is a pure capability tool with legal risk left entirely to the operator.

**Why this is unsafe for JobScout:** LinkedIn has actively litigated and shut down scraping-adjacent businesses. Most concretely, **LinkedIn's enforcement pressure caused Proxycurl (a LinkedIn-data API reseller) to shut down in July 2025 rather than fight in court** ([Bloomberg Law](https://news.bloomberglaw.com/artificial-intelligence/linkedins-war-against-bot-scrapers-ramps-up-as-ai-gets-smarter); [Social Media Today](https://www.socialmediatoday.com/news/linkedin-wins-legal-case-data-scrapers-proxycurl/756101/)). LinkedIn separately sued ProAPIs Inc. over fake-account scraping. This is the exact pattern JobScout's constraints file already forbids ("NO JA3-spoofing/proxy-rotation mass scraping (JobSpy-style)"), and the evidence confirms that prohibition is well-founded, not overcautious — this is an active, currently-litigated enforcement area, not a dormant risk. **Verdict: do not adopt JobSpy's techniques or vendor its code for LinkedIn/Indeed/Glassdoor/ZipRecruiter.**

## 2. JobFunnel (open source, `PaulMcInnis/JobFunnel`)

Older, Python, scrapes Indeed/Glassdoor/Monster into a single deduped CSV. Notable for what IS legal-adjacent: **built-in politeness — "respectfully scrape your job posts with built-in delaying algorithms," configurable `max_listing_days`, and a `company_block_list`.** [github.com/PaulMcInnis/JobFunnel](https://github.com/PaulMcInnis/JobFunnel), [readme](https://github.com/PaulMcInnis/JobFunnel/blob/master/readme.md). Dedup is CSV-row-level, keyed loosely on title+company+link — same class of naive dedup JobScout has already hardened past (`normalize_url` / `job_key`, `coverage/entity.py`, `coverage/resolve.py`). Still scrapes ToS-restricted boards directly; same legal caveat as JobSpy, just lower velocity (less blocking, also less coverage). **Adoptable idea: the rate-limit/politeness pattern and per-company block-list UX, not the scraping targets.**

## 3. HiringCafe — the closest **legal** analog to what JobScout should be

Founded by ex-Meta/DoorDash/Rippling and a Stanford CS PhD; scans **"tens of thousands of company career pages multiple times per day"** and links every result directly to the employer's own application portal — no intermediary redirect. Currently **2.8M+ listings aggregated from 46 ATS platforms**, with a stated 2026 goal to raise US job coverage from **35% to 80%** (an explicit admission that even a well-funded, AI-heavy operation is registry/coverage-bound, not scraping-bound). [Scoutify review](https://scoutify.com/blog/hiringcafe-review/), [Apify listing](https://apify.com/blackfalcondata/hiringcafe-scraper), [hiring.cafe](https://hiring.cafe/). This is a direct validation of JobScout's registry-first architecture (`companies.json`, `discover/cc_harvest.py`, `discover/enumerate.py`, ATS detectors in `scrape/ats_detect.py`) — HiringCafe is doing at commercial scale exactly what JobScout's discovery pipeline does, and even they cap out around a third of the US market from a curated registry. This is strong evidence that **registry breadth is the actual bottleneck**, matching the Session 19/22/23 conclusion already in the project brain.

## 4. JobRight.ai — cautionary tale on syndication-without-consent

Adds ~400K+ jobs/day, 10M+ job descriptions used to train its matcher, and filters spam in real time. But it has been **observed re-posting scraped employer jobs onto LinkedIn under its own "Apply" redirect** — i.e., syndicating OTHER companies' postings back onto LinkedIn without being the employer, which likely violates LinkedIn's job-posting policies and sits adjacent to the ToS-breach fact pattern from hiQ ([search result summary, no single canonical article found — treat as user-report-level, corroborated across multiple job-search review sites]). It also has documented data-freshness/accuracy problems (stale postings showing "15 hours ago" when the underlying LinkedIn post is 3 months old), a direct consequence of scraping without registry-level source-of-truth tracking. **Lesson for JobScout: never re-host or redirect through JobScout's own domain for jobs sourced from third-party boards — always deep-link to the ORIGINAL ATS/career-page URL** (JobScout already does this by design via `scrape/*_scraper.py` + `models.normalize_url`), and always carry `datePosted` from the JSON-LD/ATS API rather than "seen date" to avoid the same freshness-lie problem.

## 5. Simplify Copilot / Teal / Huntr — the compliant "browser capture" model, already in JobScout

None of these three run server-side scrapers against LinkedIn/Indeed at all. They are **browser extensions that passively capture the page the logged-in user is already viewing** and autofill/track from there:
- Simplify Copilot autofills across 100+ ATS portals (Workday, Greenhouse, iCIMS, Taleo, Avature, Lever, SmartRecruiters) and auto-logs the application to a tracker after the user submits — explicitly "not an auto-apply bot," the user stays in the loop. [simplify.jobs/copilot](https://simplify.jobs/copilot), [help.simplify.jobs](https://help.simplify.jobs/articles/1749022-installing-and-setting-up-copilot)
- Teal's extension **saves jobs from 40+ boards** (LinkedIn, Indeed, Glassdoor, BuiltIn) by clipping the page the user opened. [tealhq.com](https://www.tealhq.com/tool/job-search-chrome-extension)
- Huntr does the same across aggregators + ATS, with a manual copy-paste fallback for unsupported sites. [huntr.co](https://huntr.co/), [help.huntr.co](https://help.huntr.co/en/articles/9859408-the-huntr-chrome-extension)

This is legally clean because it's **user-initiated, single-page, authenticated-as-the-user capture**, not automated mass crawling of a platform the operator has no account relationship with — it is consent-based data portability, not scraping. **This is exactly JobScout's existing `browser_ext/` + `scrape/browser_receiver.py` design** (Session 18: "browser-extension full-data buildout... passive detail capture on open"). Confirming this pattern is correct and matches how well-funded, legally-scrutinized competitors solve the exact same "get LinkedIn/Indeed data legally" problem validates NOT building a server-side LinkedIn/Indeed scraper and instead deepening the extension (more ATS field-parsers, more boards captured on open, richer `extras["browse"]` metadata).

## 6. Otta / Welcome to the Jungle — curated-only, not exhaustive by design

Otta merged into Welcome to the Jungle (Jan 2024); the resulting platform (5.3M monthly visitors, Dec 2025) sources jobs via **direct employer submissions/partnerships and ATS integrations (e.g., a native Lever integration)**, not scraping — and is explicitly curated/vetted rather than exhaustive. [Lever help](https://help.lever.co/hc/en-us/articles/20087305319453-Enabling-and-using-the-Welcome-to-the-Jungle-formerly-Otta-integration), [uk.whatjobs.com](https://uk.whatjobs.com/news/what-reviews-welcome-to-the-jungle-otta-2026/). Not a coverage-technique model for JobScout, but confirms that "exhaustive" and "curated/legal" are usually in tension — HiringCafe chose exhaustive-via-registry, Otta/WTTJ chose curated-via-partnership; JobScout's registry-with-a-probe-verify-gate is closer to the HiringCafe model and should stay there.

## 7. The ATS-syndication mechanism, concretely (the key architectural insight)

This is the load-bearing fact for JobScout's whole coverage strategy, and it is now well-documented from LinkedIn's own developer docs:

- **LinkedIn "Job Wrapping"**: employers point LinkedIn Recruiter at a static XML feed URL (or SFTP-hosted feed) generated by their ATS; **"LinkedIn recommends updating the feed every 12 hours"** and Recruiter/Jobs pulls it on an ongoing basis — LinkedIn's own help center states wrapped jobs refresh **"at least every 24 hours, up to multiple times per day."** [Microsoft Learn / LinkedIn XML Feeds FAQ](https://learn.microsoft.com/en-us/linkedin/talent/job-postings/xml-feeds-faq?view=li-lts-2026-03), [LinkedIn Job Wrapping FAQ](https://www.linkedin.com/help/recruiter/answer/a414344/job-wrapping-faqs?lang=en). Greenhouse explicitly supports this: "job wrapping allows automatic posting and promotion of all jobs on LinkedIn from your ATS or career site," and Greenhouse can also auto-post free listings to Glassdoor/Indeed. [Greenhouse LinkedIn integration docs](https://support.greenhouse.io/hc/en-us/articles/115003795152-Use-LinkedIn-with-Greenhouse-Recruiting), [LinkedIn+Greenhouse](https://business.linkedin.com/talent-solutions/linkedin-hiring-integrations/greenhouse). Workday has an equivalent Indeed "ATS Sync" integration. [Indeed ATS integrations](https://www.indeed.com/hire/resources/howtohub/indeed-ats-integrations)
- **Indeed/Google organic indexing**: driven by `schema.org/JobPosting` JSON-LD on the employer's own career page (required fields: `title`, `hiringOrganization`, `jobLocation`, `datePosted`, `description` — missing any one silently drops the whole listing from Google's index). Google/Indeed crawlers pick these up and jobs typically surface **within ~24-72 hours** of publish. [Google Search Central](https://developers.google.com/search/docs/appearance/structured-data/job-posting), [Cavuno](https://cavuno.com/blog/job-posting-schema)
- **Practical consequence**: a job posted natively in Greenhouse/Lever/Workday/Ashby is, within roughly 24-72 hours, ALSO on LinkedIn, Indeed, and Google for Jobs — for free, automatically, with zero JobScout action required. The reverse is also true and important: **"companies that post directly to their ATS without enabling job board syndication are invisible to aggregator-based searches"** — some employers deliberately don't wrap, or gate certain reqs with LinkedIn's `#LI-DNI` ("do not index") tag specifically to keep a req off LinkedIn while it's still live in the ATS. This means an ATS-native registry can occasionally see MORE (and always sees jobs FASTER) than LinkedIn/Indeed, not less.
- **Indeed's own API is now closed to new integrators**: the legacy `Get Job`/Publisher Jobs API is deprecated for new integrations; Indeed now only offers the `Job Sync API` (employer-side posting, not search) and a paid `Sponsored Jobs API` (from Feb 1, 2026, billed per-call, gated to active ad spenders). [Indeed Partner Docs](https://docs.indeed.com/job-sync-api/job-sync-api-guide), [Sponsored Jobs API usage policy](https://docs.indeed.com/sponsored-jobs-api/sponsored-jobs-api-usage-policy). There is no legal, free path into Indeed's search index as a consumer of aggregated results — reinforcing that the only legal way to "cover" Indeed's job set is to source it upstream, at the ATS, before it ever reaches Indeed.

## 8. What this implies for JobScout, concretely

1. **`scrape/jsonld_scraper.py` is already the right primitive** — it extracts the same `schema.org/JobPosting` structured data that feeds Google for Jobs and Indeed's organic crawl. No change needed to the extraction technique; the leverage is in *where it's pointed* (registry breadth), confirmed by HiringCafe needing 46 ATS platforms and still only reaching ~35% US coverage.
2. **Treat `companies.json` + `discover/cc_harvest.py` + `discover/enumerate.py` as the actual coverage lever**, not new scrapers — this validates (not just reiterates) the Session 19/20/22/23 pivot to registry-acquisition over scraper-count. Session-24's finding (dad's real-world test: 18 jobs from exact-title search vs 361 from broad field keywords) is the demand-side mirror of this same supply-side truth: coverage is bounded by breadth-of-source, not query cleverness.
3. **Never build a LinkedIn/Indeed/Glassdoor/ZipRecruiter scraper** (JobSpy-style) inside JobScout's server-side pipeline — this is exactly the fact pattern LinkedIn has actively enforced against as recently as July 2025 (Proxycurl). `legal_risk: high`.
4. **Keep and deepen the browser-extension capture path** (`browser_ext/`, `scrape/browser_receiver.py`) as the ONLY legitimate channel to LinkedIn/Indeed/Glassdoor content — it mirrors Simplify/Teal/Huntr's proven-compliant, user-initiated, single-page model. `legal_risk: none` (user's own authenticated session, one page at a time, no automation against the platform).
5. **Use ATS-refresh SLAs as a freshness benchmark, not a target to beat by scraping**: since LinkedIn/Indeed lag the ATS by ~24-72h anyway, an ATS-native registry that's re-crawled daily is *already at parity or ahead* of what a live LinkedIn scrape would show — there's no coverage or freshness reason to risk the scrape.
6. **Add a "coverage confidence" signal derived from ATS-detection breadth**, since JobScout's own `coverage/estimators.py`/`coverage/registry_coverage.py` capture-recapture math is well-suited to answering "what fraction of postings at detected-ATS companies are we actually pulling," the same self-honesty metric HiringCafe publishes (35%→80% goal) — this would let JobScout report an honest, quantified coverage number to users instead of an implicit "trust us" claim, which is a differentiator most of these competitors don't offer.
7. **Do not redirect/re-host** postings sourced from any third party the way JobRight.ai has been observed doing — always deep-link straight to the ATS/employer URL, which JobScout already does via its per-ATS scrapers and is worth explicitly protecting as a design invariant when adding new source types.

## Sources
- [JobSpy — speedyapply/JobSpy](https://github.com/speedyapply/JobSpy)
- [JobSpy Issue #283 — ZipRecruiter 429](https://github.com/speedyapply/JobSpy/issues/283)
- [JobSpy Issue #129 — LinkedIn 429 handling](https://github.com/Bunsly/JobSpy/issues/129)
- [JobFunnel — PaulMcInnis/JobFunnel](https://github.com/PaulMcInnis/JobFunnel)
- [HiringCafe review — Scoutify](https://scoutify.com/blog/hiringcafe-review/)
- [Hiring.Cafe Scraper — Apify (46 ATS platforms)](https://apify.com/blackfalcondata/hiringcafe-scraper)
- [hiring.cafe](https://hiring.cafe/)
- [Jobright.ai](https://jobright.ai/)
- [Simplify Copilot](https://simplify.jobs/copilot), [Simplify install guide](https://help.simplify.jobs/articles/1749022-installing-and-setting-up-copilot)
- [Teal Chrome Extension](https://www.tealhq.com/tool/job-search-chrome-extension)
- [Huntr Chrome Extension help](https://help.huntr.co/en/articles/9859408-the-huntr-chrome-extension)
- [Welcome to the Jungle / Otta merger — Lever integration docs](https://help.lever.co/hc/en-us/articles/20087305319453-Enabling-and-using-the-Welcome-to-the-Jungle-formerly-Otta-integration)
- [hiQ Labs v. LinkedIn — Wikipedia](https://en.wikipedia.org/wiki/HiQ_Labs_v._LinkedIn)
- [Ninth Circuit CFAA ruling analysis — Fenwick](https://www.fenwick.com/insights/publications/hiq-labs-scrapes-by-again-the-ninth-circuit-reaffirms-that-data-scraping-does-not-violate-the-cfaa-1)
- [Meta v. Bright Data ruling — Fox Rothschild](https://www.fbm.com/publications/major-decision-affects-law-of-scraping-and-online-data-collection-meta-platforms-v-bright-data/)
- [LinkedIn vs. Proxycurl shutdown, July 2025 — Bloomberg Law](https://news.bloomberglaw.com/artificial-intelligence/linkedins-war-against-bot-scrapers-ramps-up-as-ai-gets-smarter)
- [LinkedIn Job Wrapping FAQ](https://www.linkedin.com/help/recruiter/answer/a414344/job-wrapping-faqs?lang=en)
- [LinkedIn XML Feeds FAQ — Microsoft Learn](https://learn.microsoft.com/en-us/linkedin/talent/job-postings/xml-feeds-faq?view=li-lts-2026-03)
- [Greenhouse + LinkedIn integration](https://support.greenhouse.io/hc/en-us/articles/115003795152-Use-LinkedIn-with-Greenhouse-Recruiting)
- [Indeed ATS integrations (Workday sync)](https://www.indeed.com/hire/resources/howtohub/indeed-ats-integrations)
- [Google JobPosting structured data requirements](https://developers.google.com/search/docs/appearance/structured-data/job-posting)
- [Indeed Job Sync API guide (current API surface)](https://docs.indeed.com/job-sync-api/job-sync-api-guide)
- [Indeed Sponsored Jobs API usage policy (Feb 2026 pricing)](https://docs.indeed.com/sponsored-jobs-api/sponsored-jobs-api-usage-policy)

## Key recommendations

- **[S/Avoids high legal exposure for near-zero coverage gain since ATS-native sourcing is already faster/fresher./risk:high]** Never build/vendor a JobSpy-style live scraper against LinkedIn/Indeed/Glassdoor/ZipRecruiter inside JobScout's server-side pipeline (search/*_client.py, scrape/*).  
  LinkedIn actively enforces against this pattern (Proxycurl shutdown July 2025); ToS breach-of-contract risk survives even though hiQ/Bright Data cleared the CFAA path.
- **[M/HiringCafe (46 ATS platforms, well-funded) still only reaches ~35% of US jobs from registry breadth alone -- validates this is the real bottleneck, matching Session 19/22/23/24 findings already in the brain./risk:none]** Treat companies.json + discover/cc_harvest.py + discover/enumerate.py registry breadth as THE coverage lever; keep investing in dataset_seed/enterprise-ATS import over adding new scraper types.  
  Registry-based ATS harvesting is the same technique HiringCafe uses at commercial scale, fully legal (crawling employer-owned career pages with public JSON-LD).
- **[M/Matches the proven-compliant model used by Simplify Copilot, Teal, and Huntr (all funded, all still browser-extension-only for these boards) -- gives JobScout LinkedIn/Indeed data with essentially zero legal exposure./risk:none]** Keep browser_ext/ + scrape/browser_receiver.py as the ONLY channel for LinkedIn/Indeed/Glassdoor content, deepen it (more ATS field parsers, richer extras["browse"] capture) rather than adding server-side scraping of those sites.  
  User-initiated, single-page, authenticated-as-the-user capture is consent-based data portability, not automated mass access -- the same fact pattern courts treat very differently from CFAA/ToS scraping cases.
- **[M/Differentiator vs. every competitor reviewed (none publish an honest coverage percentage except HiringCafe's stated 35%->80% roadmap goal); builds trust with non-technical users like Alex's dad./risk:none]** Add a published 'coverage confidence' number derived from coverage/estimators.py capture-recapture math against detected-ATS company counts, surfaced to the user.  
  The coverage math already exists in JobScout (coverage/estimators.py, coverage/registry_coverage.py) but is 'mostly unwired' per the architecture notes -- this wires it into a user-facing signal.
- **[S/Avoids the JobRight.ai pattern (observed re-posting scraped jobs onto LinkedIn under its own redirect, plus documented stale-date bugs from not tracking source datePosted)./risk:medium]** Enforce a design invariant: JobScout must always deep-link to the original ATS/employer application URL for any job, never redirect through a JobScout-hosted intermediary page.  
  Re-syndicating third-party job content without being the employer sits adjacent to the same ToS/breach-of-contract theory that has driven LinkedIn enforcement actions.

## Sources
- https://github.com/speedyapply/JobSpy
- https://github.com/speedyapply/JobSpy/issues/283
- https://github.com/Bunsly/JobSpy/issues/129
- https://github.com/PaulMcInnis/JobFunnel
- https://github.com/PaulMcInnis/JobFunnel/blob/master/readme.md
- https://scoutify.com/blog/hiringcafe-review/
- https://apify.com/blackfalcondata/hiringcafe-scraper
- https://hiring.cafe/
- https://jobright.ai/
- https://simplify.jobs/copilot
- https://help.simplify.jobs/articles/1749022-installing-and-setting-up-copilot
- https://www.tealhq.com/tool/job-search-chrome-extension
- https://help.huntr.co/en/articles/9859408-the-huntr-chrome-extension
- https://help.lever.co/hc/en-us/articles/20087305319453-Enabling-and-using-the-Welcome-to-the-Jungle-formerly-Otta-integration
- https://en.wikipedia.org/wiki/HiQ_Labs_v._LinkedIn
- https://www.fenwick.com/insights/publications/hiq-labs-scrapes-by-again-the-ninth-circuit-reaffirms-that-data-scraping-does-not-violate-the-cfaa-1
- https://www.fbm.com/publications/major-decision-affects-law-of-scraping-and-online-data-collection-meta-platforms-v-bright-data/
- https://news.bloomberglaw.com/artificial-intelligence/linkedins-war-against-bot-scrapers-ramps-up-as-ai-gets-smarter
- https://www.linkedin.com/help/recruiter/answer/a414344/job-wrapping-faqs?lang=en
- https://learn.microsoft.com/en-us/linkedin/talent/job-postings/xml-feeds-faq?view=li-lts-2026-03
- https://support.greenhouse.io/hc/en-us/articles/115003795152-Use-LinkedIn-with-Greenhouse-Recruiting
- https://www.indeed.com/hire/resources/howtohub/indeed-ats-integrations
- https://developers.google.com/search/docs/appearance/structured-data/job-posting
- https://docs.indeed.com/job-sync-api/job-sync-api-guide
- https://docs.indeed.com/sponsored-jobs-api/sponsored-jobs-api-usage-policy