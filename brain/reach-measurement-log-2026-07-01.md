# Measured findings — dad reach test (2026-06-30, live)

Profile: Dad — VP/Director Health Informatics, Cincinnati + remote-open,
20+ yrs, Epic Clarity / Power BI / healthcare analytics. Target = VP/Director/CMIO.

## Registry snapshot

- companies.json = **273 companies**, ATS mix greenhouse 99 / ashby 67 / workable 47 / lever 39 / smartrecruiters 18 / direct 3.
- Industry tags ~entirely ENGINEERING (software 97, hardware 84, embedded 81, applied_ai 81, robotics 59, controls 61...).
- **Health-ish tags: 4 companies, 2 of which are literal test fixtures** ("Example Greenhouse Co", "Example Direct Co"). Real health cos in registry: Neuralink, Noah Medical (both robotics/medical-device, not health-IT employers).
- => For dad, the entire CareersClient/registry path reaches ~0 relevant employers.

## Live reach — dad's CURRENT config (8 narrow VP-title keywords)

Per-source raw (max_pages=1): Adzuna **0**, USAJobs 8 (all staff physicians/radiologists — wrong roles),
themuse/remoteok/remotive/jobicy/himalayas/hn/arbeitnow **0** each (all tech-only boards),
jooble SKIPPED (no free key), careerjet SKIPPED (no free key), linkedin_guest **10** (only productive source),
careers/registry **0**.

- **TOTAL: 18 jobs / 10 companies** for a 20-yr VP. Dedup = 18 (no cross-source overlap).
- Score>=40: 4 kept. Score>=60: 3. **health+exec roles scoring >=60: ZERO.**
- Ranking inversion: PwC "Senior Manager" roles score 84/80; actual targets CMIO Kettering = 58, VP Quality UC Health = 28. Dad's real targets are BURIED.

## Root cause of near-zero reach: narrow-keyword regression

- Session 22 reconfigured dad's config.json keywords to exec-title phrases ("VP Clinical Informatics",
  "Chief Medical Information Officer", ...). Search APIs phrase-match => ~0 recall.
- Direct Adzuna probe: "Chief Medical Information Officer" -> 0; but "health informatics" -> 7,
  "clinical informatics" -> 5, "digital health" -> 29, "nurse" -> 50.
- **Broad field keywords across Adzuna alone -> 47 jobs / 15 companies** (vs 0). ~infinite lift.
- Lesson: search on BROAD field keywords; seniority/exec-fit belongs in SCORING/GATE, not the query string.
  The old config_dad.json HAD the right broad keywords; session 22 overwrote them.

## Source-reach reality for a remote-favoring non-tech (health) seeker

- All wired "remote" boards (remoteok/remotive/jobicy/himalayas/arbeitnow) are TECH-only => 0 for health.
  The "remote-favoring" persona is structurally unserved: no general/healthcare remote board exists in the stack.
- Only ToS-gray linkedin_guest produced relevant results under current config => fragile + legally gray primary source.
- jooble + careerjet are FREE-key aggregators (general + healthcare coverage) and are NOT configured.
- USAJobs returns physicians not informatics leaders => federal-health keyword/param tuning needed (or filter to IT series 2210 / 0671).

## BEFORE/AFTER — broad keywords = 20x reach (measured, same 4 sources)

- BEFORE (dad's narrow exec-title keywords): 18 jobs, 10 companies (only linkedin_guest productive; adzuna 0).
- AFTER (broad field keywords: "health informatics","clinical informatics","healthcare analytics",
  "digital health","population health","Epic analyst",...): **444 raw -> 361 deduped jobs, 104 companies,
  87% health-relevant, 70 leadership-titled.** Adzuna 0 -> 291. themuse only 6 (category filter caps it).
  => The keyword-strategy fix alone is a ~20x reach gain, free. This is THE headline.
- linkedin_guest gave 118 but took 189s (rate-limited, ToS-gray) — not a dependable primary source.

## Data-source research (agent) — how to build a real health + agnostic registry (all free/legal)

- jobhive (github kalil0321/ats-scrapers, MIT): 86k companies as `name,slug,url` CSV per ATS -> drop-in for
  the session-23 seed_companies.py importer. Tech-skewed (~0 health) but perfect general scaffold + schema.
- Health NAME lists (public-domain, feed the probe-verify gate): CMS Hospital General Info (~5,300),
  ONC CHPL health-IT vendor list (the definitive health-IT vendor enumeration), NPPES bulk (taxonomy filter),
  HIFLD, HRSA FQHCs, Becker's top-100 systems, manual payer seed (~50-80 UnitedHealth/Elevance/CVS/Cigna...).
- Common Crawl CDX harvest = durable field-agnostic engine (owned outright). Already partly in discover/cc_harvest.py.
- USAJobs series codes 2210 (IT) / 0669 / 0670 / 0671 (health admin) = federal health-IT targeting.
- Remote health boards: Remote.co/healthcare, HIMSS JobMine, Working Nomads (ToS-check; no clean APIs).

## Additional hardcoded eng-bias reach bugs (found by reading config.py)

- `config.THEMUSE_CATEGORIES = ["Engineering","Science and Engineering"]` — The Muse is filtered
  server-side to ENGINEERING categories only. The Muse HAS "Healthcare", "Data Science", "Business
  & Strategy", "Management" categories. => dad gets 0 from The Muse structurally, not for lack of jobs.
- `config.JOBICY_INDUSTRY = "engineering"` — Jobicy's server-side category is hardcoded engineering.
  Jobicy supports "medical", "business", "hr", "marketing"... => dad gets 0 from Jobicy structurally.
- Both should be industry/field-driven (from the active project's industry), not module constants.
- `config.DEFAULT_KEYWORDS` = 10 IC engineer titles (no seniority prefixes) — confirms a de-seniority
  keyword deriver would be a no-op for Alex (byte-identical) while fixing dad.

## USAJobs federal-health tuning (secondary)

- USAJobsClient passes only `Keyword` -> VA floods staff-physician roles. It supports `JobCategoryCode`
  (occupational series: 2210 IT, 0671 Health System Admin, 0343 Mgmt/Program Analysis, 0669) which
  would target informatics leadership. Enhancement, not critical.

## Implications (the reach improvements to build)

1. Fix keyword strategy: broad field terms for querying + exec/seniority handled in scoring. (biggest lever, ~free)
2. Seed a health / general company registry (dad's field + agnostic) — the CareersClient path is dead without it.
3. Wire a general/healthcare-inclusive aggregator that isn't tech-only or ToS-gray (jooble/careerjet free keys; Adzuna paging).
4. Fix exec-fit ranking so target-level roles rank above lower-level roles.
5. Measure reach per-source and per-field (a reach dashboard), so "are we near all companies?" has a number.
