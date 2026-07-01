# Competitor & Feature-Gap Research (2026-07-01)

Web research into current job-search tools to find features JobScout lacks. **Strategic finding first:**
JobScout's ATS-API + curated-registry architecture is the _correct_ and only legitimate reach mechanism.
The giants achieve breadth by being _inside_ the ATS (a req in Greenhouse/Workday auto-syndicates to
LinkedIn/Indeed/etc.) — uncopyable by a local app, and not worth trying. JobScout already out-covers
Teal/Huntr/Careerflow, which have **no scraper at all** (just a "clip this job" browser button). The real
gaps are the **enrichment/UX layer**, a **browser-extension autofill**, and **automated registry discovery**.

## Top feature gaps (ranked; S=days, M=1-2wk, L=3+wk)

1. **Automated registry discovery — Common Crawl ATS-slug harvest** (M). Query CDX for `boards.greenhouse.io`,
   `jobs.lever.co`, `*.myworkdayjobs.com`, etc.; regex out slugs. `Feashliaa/job-board-aggregator` (~95K cos)
   and MIT `kalil0321/ats-scrapers`/jobhive (86K cos, `pip install jobhive-py`). Attacks the real constraint
   (company discovery, not job access). ToS clean (Common Crawl permissive; ATS APIs public).
2. **Browser-extension autofill across ATS** (L). Simplify Copilot: 100+ ATS, 1M+ installs. Map stored
   profile → DOM fields on Workday/Greenhouse/Lever/Ashby/iCIMS. Human-triggered + manual submit = low risk.
3. **LLM semantic match score** (M). Huntr caps keyword weight <20% to prevent keyword-stuffing; weights
   qualifications/responsibilities higher. `srbhr/Resume-Matcher` (spaCy + cosine) = fully local reference.
4. **Free comp/salary overlay** (S). Adzuna **Jobsworth** salary-predictor endpoint backfills missing pay on
   ANY posting — on the Adzuna key you already hold.
5. **Adzuna `Top Companies` endpoint** (S). Returns top employers by vacancy per query → free per-search
   registry lead-gen. Feeds #1.
6. **Contact/insider-connection finder** (L). JobRight's differentiator; but email scraping = high ToS risk
   (Proxycurl was shut down Jul 2025). Safer: user-supplied CSV / public-directory enrichment only.
7. **TF-IDF cross-source dedup** (S). JobFunnel pattern: exact ID + TF-IDF cosine over title+company+desc.
   Turns dedup into a quality edge vs the giants' syndication duplication.
8. **Enterprise-ATS parsers** (M-L). Workday/iCIMS/Taleo/SuccessFactors/Bullhorn — where non-tech, large-
   employer, healthcare/gov/finance jobs live (vs startup-skewed Greenhouse/Lever/Ashby).
9. **Live resume↔JD match score in an editor** (M). Teal Match Score: matched/missing/suggested keywords.
10. **ATS-specific format advice** (S-M). Jobscan's edge; JobScout already knows each job's ATS → unique.
11. **Google-for-Jobs via SerpApi `google_jobs`** (S). 250 free/mo. Flag: Google sued SerpApi Dec 2025.
12. **Ghost-job / stale-listing detection** (S). JobRight cautionary tale (~half its "matches" expired/fake);
    check `validThrough`, repost heuristics.
13. **LinkedIn profile optimizer** (M). Careerflow's most-praised free feature (advice only, no API/scrape).
14. **Mock-interview simulator** (S-M). Straightforward with the Claude API already integrated.
15. **User-gated browser import for closed sources** (M). User browses logged-in in their own session; the
    extension captures only the explicitly-viewed posting's DOM — the only ToS-defensible LinkedIn/Indeed path.

**Anti-features to avoid** (universal complaints): auto-renew billing traps, generic un-edited AI output,
walled-garden resume builders that can't import an existing resume, no self-serve deletion. JobScout being
local/free/privacy-first with self-serve deletion is a genuine differentiator.

## How the giants get coverage

They syndicate FROM inside the ATS (LinkedIn Diamond partner, Indeed 350+ ATS integrations). JobRight scrapes
LinkedIn/Indeed/career pages (8M postings). Simplify monitors 50,000+ career pages hourly + crowdsourced
GitHub repos. **JobSpy** reverse-engineers LinkedIn guest AJAX / Indeed GraphQL / Glassdoor GraphQL with
`tls_client` JA3-spoofing + proxy rotation — **exactly what JobScout should NOT do.** A local app should
lean on: direct ATS public JSON APIs (Greenhouse/Lever/Ashby/Workable/SmartRecruiters), automated slug
discovery (Common Crawl/jobhive), and Adzuna (which already indexes 50,000+ career sites via its Getwork buy).

## Resume↔ATS match best practices

Jobscan Match Rate % (aim 75%+): weighted hard-skills + keyword frequency (exact+variant), title/experience
alignment, formatting/parseability (no tables/columns/headers that break parsers), and identify the employer's
ATS. Huntr: cap keyword weight <20%. Canonical local model: JSON Resume (MIT schema) feeds both matching and
autofill. JobScout's edge: it knows each job's source ATS → can give ATS-specific advice.

## Auto-apply landscape

Risk scales with **autonomy/volume, not autofill**. Tolerated: browser-resident, human-triggered, manual
submit (Simplify/Teal/Huntr). High-risk/banned: LazyApply, AIHawk (LinkedIn-banned, archived), LoopCV/Sonara
cloud bots. Backlash shipping: recruiters ~400% more applications ("doom loop"); Workday "Fraudulent
Application Detection" (Mar 2026) silently discards high-velocity automated applicants. **Posture for
JobScout: "fill this page I opened," review + submit yourself, nothing unattended.**

## Non-tech / healthcare remote sources

Only **Adzuna** (has Healthcare & Nursing / Accounting & Finance / Admin categories — client-side remote
filter) and **We Work Remotely** (JSON API + RSS) are cleanly wireable. FlexJobs/Virtual Vocations/Health
eCareers have the best non-tech healthcare-admin coverage but are paywalled/API-less/scrape-hostile → the
user-gated browser-capture path is the compliant way in.
