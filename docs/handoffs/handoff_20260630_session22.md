# Handoff — Session 22 (2026-06-30) — search-perf + parallelization + coverage measurement + agnostic/multi-person + board planning

Ran on the cheap/3rd-party backend (NOT Opus), inline. Planning subagents = **Opus** (Alex
opted in). Output mode: terse. Project = `E:\ClaudeWork\ZAG0005 - Job Search App\`.
**859 tests green. Push HELD** (per the standing eyeball-gate).

## What shipped (committed locally)

- `e0d4a0c` **perf(search)**: parallelize fetch to (client[,keyword]) work units — all clients
  concurrent (was capped at 4) + per-keyword concurrency for keyword-parameterized clients
  (Adzuna/JSearch/SerpApi/USAJobs carry `parallel_keywords=True`); keyword-blind feeds stay one
  sequential unit (shared cached fetch + `_raw_exhausted`). + tiered timeouts (careers 20→12,
  `CAREERS_SLOW_TIMEOUT=20` for Workday), 7-day dead-URL `FAILED_TTL_HOURS` (was re-paid daily),
  GUI now respects the user's source toggles (was querying ALL_SOURCES → burned paid JSearch
  quota), per-source timing summary. `SEARCH_MAX_WORKERS=12`.
- `2170e91` **perf(search)**: cap `HIMALAYAS_MAX_JOBS` 200→100 (was a measured **61s** cold sweep
  for ~4 results — 10 requests vs a 5/min limiter → 59s sleep). Now ~0.8s.
- `50aabe7` **feat(coverage)**: `coverage/registry_coverage.py` (Chapman capture-recapture:
  `estimate_coverage`/`name_identity`/`domain_identity`) + `company_coverage.py` CLI — measures
  registry completeness (N̂ + CI + coverage%) from two INDEPENDENT lists.
- `d631cf4` **fix(match)**: exec/management-seeker gate fix (was the stress-test blocker — see below)
  - `brain/onboarding-token-efficiency.md`.

## Measured (fresh-search benchmark, isolated cold cache)

- Cold **serial 29.8s → parallel 6.0s (~5×)**, identical 272 results; warm 0.1s.
- Full DAILY_SOURCES cold parallel **3.9s** (was dominated by the 61s Himalayas wall).
- **Token audit:** compact re-rank ~**94 tok/job**; a day ≈ **1 claude.ai message**; max-coverage
  company enum ≈ ~5k tok one-time. **Fits $20 Pro trivially / free tier / ~$0.50-1/mo on Haiku.**
  Cost was never the constraint.

## Stress test (dad = VP Health Informatics) — the real finding

Token cost is fine; the blocker was **correctness**: the pre-AI gate hard-dropped
`seniority∈{manager,director} & role_type=manage` ("people-management role") with no override, so
a VP/Director/Chief search dropped **100% of relevant roles before any AI**. Fixed in `d631cf4`:
`match/rubric.py` infers management intent from the user's own target roles (`_EXEC_RE`:
vp/svp/evp/chief/cxo/president/head of/director/executive/manager) → sets `allow_management`,
`seniority_target=senior-exec`, `years_cap=25`, drops the "manage" penalty (all config-overridable;
IC profiles byte-identical). `match/gate.py` honors it. Tests: `tests/test_exec_seniority.py`.

## Live state (local, gitignored `projects/`)

- **`dad-health-informatics` project reconfigured** to the VP profile (VP/CMIO/Director keywords,
  Cincinnati+remote, no salary floor, exclude sales/contract/temp, industry=health_informatics,
  allow_management). Verified end-to-end (VP roles KEEP, sales/contract DROP).
- **Harvest run:** registry **257 → 344** (+87 ATS boards; ashby CDX endpoint 400'd — a
  known Common-Crawl quirk the host-index upgrade fixes).
- **Active project switched to `dad-health-informatics`; GUI relaunched on it** (background, still
  running). ⚠️ **Switch back to `controls` in the project switcher** for your own work.

## FOR THE NEXT SESSION — build from these 3 plans (planned this session, NOT built)

1. [brain/plan-2026-06-30-company-coverage-100.md] — **push registry to a MEASURED ~100%**, agnostic,
   nationwide-for-remote, capture-recapture loop-until-dry. **← recommended first build.**
2. [brain/plan-2026-06-30-board-expansion.md] — Indeed + more boards. Key finding: **don't scrape
   Indeed** (feeds dead 2026-03-31, no API, ToS ban) — use JSearch (free)/SerpApi engine=indeed
   (paid)/the extension. Most niche-board coverage is really a companies.json problem → converges
   with plan #1.
3. [brain/plan-2026-06-30-agnostic-multiprofile.md] — field/persona-agnostic (de-bias eng/IC/Cincy
   hardcodes; wizard even says "engineering jobs") + multi-person (a person = a project layer).

**Recommended build order:** company-coverage **P1 = deterministic $0 bulk seed** (import an open
MIT ATS dataset ~86k cos through the existing probe-verify gate) — biggest blast-radius jump, no
new deps (CSV/NDJSON via stdlib), no ranking-token change.

**Decisions Alex must make first (plan open questions):**

- Canonical bulk dataset: **jobhive** (MIT ~86k/47 ATS) vs **OpenJobs** (MIT, has industry column →
  less AI). Recommend OpenJobs if its ATS/slug fields are clean.
- **Paid SerpApi/JSearch** for a real daily Indeed pull vs free-tier + extension only.
- `loop_signal` thresholds (proposed: plateau = union growth <2% over 2 rounds AND coverage ≥85%).

## Notes / guardrails carried forward

- Token invariant for any build: **no new field in `facts_summary`, no new line in `rubric_text`**
  → keeps ~94 tok/job. All new AI = occasional company-building (cached/bounded), never per-search.
- Capture-recapture validity needs INDEPENDENT lists — registry vs harvest/dataset, **never** vs the
  LLM enumerator (correlated → inflates N̂).
- Safety unchanged: JobScout is not fleet-safety code; fine to build on the cheap backend.
