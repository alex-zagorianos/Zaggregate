# Search-Method Optimization + Multi-Role Live Test (S36b, 2026-07-04)

Alex's directive: "optimize our searching methods… test using all of my job
search roles (mech design, software, AI, embedded/controls) as well as my
dad's… get the jobs found as large as possible, particularly jobs that are
actually relevant." Program: live baseline across all six real projects →
fetch-side recall widening (scoring untouched) → measured re-run.

## 1. Baseline — sequential deep runs (`--max-pages 3`), 2026-07-04 afternoon

| project                | found |   ≥40 | new→inbox | inbox now |   was | mins |
| ---------------------- | ----: | ----: | --------: | --------: | ----: | ---: |
| mechdesign             | 2,305 | 1,272 |       784 |       784 |     0 |  5.4 |
| software               | 4,657 | 3,255 |     2,246 |     2,246 |     0 | 10.4 |
| applied-ai             |   481 |   257 |       188 |       969 |   781 |  4.3 |
| controls               | 1,420 |   718 |       122 |       782 |   660 |  5.6 |
| controls-cincinnati    | 2,360 | 1,290 |       299 |     1,822 | 1,523 |  4.1 |
| dad-health-informatics |   403 |    28 |         0 |        35 |    35 |  3.4 |

Alex's five role inboxes: 2,964 → **6,603 rows** in one pass (11,626 found).
mechdesign + software had NEVER been run (configs existed, inbox 0). Dad's 403
found / 28 qualified / 0 new = 7h-old last run, everything already seen —
expected, not a defect. Logs + per-source detail:
`scratchpad/baseline/*.log` (session tmp) — key figures preserved here.

Per-source shape (mechdesign, representative): CareersClient 3,187 raw
(dominant), Adzuna 541, TheMuse 60–169, Himalayas 149, WWR 75, HN 72, USAJobs
47, RemoteOK 18, Remotive 12, Jobicy 3. Jooble/Careerjet/CareerOneStop = 0
(keyless — see §4).

## 2. Optimizations landed (all fetch/view-side; match/ + ranker.py untouched)

1. **Metro satellite-city variants** (`3a299f4`) — new
   `data_static/metro_satellites.csv` (cbsa_code,city,state; seeded with 32
   Cincinnati OH-KY-IN municipalities: Mason, West Chester, Blue Ash,
   Florence KY, Covington KY, Lawrenceburg IN…). Suburb-named postings now
   classify local. State-suffixed variants only ("florence, ky" +
   "florence, kentucky") so ambiguous names never cross-match (Aurora CO vs
   IN, Loveland CO, Alexandria VA). Multi-principal-city CBSA titles
   (minneapolis-st. paul-bloomington) also split per city. Purely additive.
   Known shift: Hamilton OH promotes "state"→"metro" in sector-client
   bucketing (both kept before and after).
2. **Curated engineering query synonyms** (`4055d79`) — the eng_like resolve
   branch pinned `query_synonyms=[]` for every eng field, so query widening
   was a NO-OP for exactly Alex's roles. Named eng industries now borrow
   curated syn lists (controls→instrumentation/PLC/SCADA/process-controls;
   mech→mechanical-design/product-design/CAD/NPI; AI→MLE/MLOps/applied-
   scientist/CV/LLM; software→developer variants). Empty industry + generic
   eng fallback stay byte-identical. S32 parity pin updated (Alex-directed
   delta).
3. **Config levers** (user data, not committed): `jsearch:true` on software +
   applied-ai (manual runs only — daily_run always excludes jsearch);
   `industry` set on software ("software engineering"), applied-ai
   ("applied ai"), controls ("controls_engineering") so the synonym tier +
   routing activate for them.

## 3. Measured effect — mechdesign re-run, 35 min after its baseline pass

- Query tier: **"10 keywords (17 broadened for query)"** (was 10) — synonyms live.
- Raw pull: 4,274 → **5,079 (+19%)**; distinct 1,671 → 1,719.
- +17 new inbox rows in a same-afternoon window (marginal yield compounds on
  future daily runs as fresh postings hit the broadened queries).
- max_per_company=15 caps visible (Anduril 193→15, SpaceX 156→15…) — the cap
  is at inbox-insert, post-scoring; deliberate, not a fetch limiter.

## 4. Biggest UNTAPPED lever — free API keys (needs Alex, ~15 min of signups)

Confirmed live: these sources are fully wired (auto-on in DAILY_SOURCES once
keyed, zero code change) and currently contribute nothing:

1. **CareerOneStop** (free, US DOL/NLx ~3.5M jobs) — also unlocks the
   Seed-My-Metro employer discovery tool for Cincinnati-area registries.
2. **Brave Search API** (free tier) — unlocks per-keyword ATS-board discovery
   inside the careers source (`scrape/discoverer.py` returns [] without it);
   the single biggest "new employers per search" lever.
3. **Jooble** (free key, jooble.org/api/about) — different crawl universe than
   Adzuna/JSearch; the only run WARNING in all six logs.
4. **Careerjet** (free affid).
5. **SerpApi** (free 250/mo) — Google-Jobs source + the reach-probe that
   MEASURES true coverage (reach badge is uncertifiable without it).

## 4.5 Adversarial review wave (same afternoon) — 5 confirmed findings, ALL FIXED

A 3-reviewer × per-finding-refuter workflow over the whole S36b diff confirmed
and I fixed (`a6b8676` + `6576912`): **CRITICAL** bare hyphen-split city pieces
cross-matched other metros (Aurora IL "local" to Denver) → state-qualified like
the satellites; **MAJOR** ghost_score cache froze wall-clock staleness for the
process lifetime → UTC-day ordinal in the cache key; "deep" AI-rule token
collision → removed; mid-wizard AI paste skipped the remaining wizard steps
via the new onboarded inference → `.wizard-in-progress` sentinel; InboxBadges
relTime dedup finished. Everything re-verified: suite 2,968 / vitest 176 /
build clean.

## 5. Queued follow-ups (not done this session)

- Free sector source for mech/industrial/manufacturing (IEEE/ASME/SAE career
  boards…) following the self-gating `_higheredjobs` builder pattern — needs
  feed research first.
- Periodic `search/cli.py --discover --discover-enterprise` (Common-Crawl ATS
  harvest) to grow companies.json with enterprise-ATS industrial employers —
  cadence task, could be a scheduled job.
- "Minneapolis, MN"-style inputs never substring-match their own hyphenated
  multi-city CBSA title (pre-existing metro_variants matching gap; bare-city
  form works).
- Raising daily `--max-pages` default 2→3 for keyed-unlimited sources only
  (Adzuna/USAJobs/CareerOneStop) once CareerOneStop is keyed; avoid for
  JSearch (200/mo quota).
