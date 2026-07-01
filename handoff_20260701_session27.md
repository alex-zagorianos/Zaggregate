# Handoff — Session 27 (2026-07-01, Opus) — LIVE EVAL + 2 FIXES

**Task (Alex):** run two end-to-end searches (Dad = health-informatics, Me =
controls/embedded); evaluate completeness, ranking, blast radius. Then: (1) fix the
concurrency bug found; (2) fix why Dad's inbox is so much smaller than mine. Terse.

Read-me-first: `brain/eval-2026-07-01-dad-vs-controls-runs.md` (full eval + both fixes).

## What happened

Ran both projects through `daily_run.py` start→finish (free sources only). Evaluation +
the AI-fit rerank round-trip on Dad. Hit a **critical concurrency bug live** (fixed it),
and diagnosed + improved Dad's inbox size. **Suite 1220 → 1222 green. No commits yet
(28 ahead from prior sessions, push held).**

## Eval results (clean, serialized runs)

|                    | Dad — `dad-health-informatics` | Me — `controls`                           |
| ------------------ | ------------------------------ | ----------------------------------------- |
| raw → distinct     | 723 → 540 (7 families)         | 1976 → 1115 (10 families)                 |
| gate → ≥40 → inbox | 616→177→14 → **19**            | none→828 → **660** (cap 15/co)            |
| ranking            | coherent, max 64               | median 59 / max 90, 101 ≥70               |
| reach              | cannot certify · ~25% GT       | cannot certify · ~44% GT                  |
| 429s               | 0                              | **241** (unfiltered full-registry scrape) |

- **Ranking works** in both. Clinical care-delivery correctly floored to 0 (Dad); on-target
  firmware/controls/embedded on top (controls). AI-fit rerank round-trip (Dad, 19/19 matched)
  meaningfully re-orders — local's #1 (BI Manager @ Kraft Heinz 64) is NOT the best fit; the
  true VP Enterprise Analytics (local 54) → fit 85 #1.
- **Reach can't certify** either run: f2=0 (free families disjoint, no cross-source overlap →
  universe unsizable). Needs a Google-Jobs proxy (serpapi/jsearch) for overlap.
- **Semantic ranking is OFF** (`match.semantic.available()==False`) → keyword-only, so generic
  tokens ("control"/"automation"/"manager") earn title-100% false positives in controls
  (QA-automation ranked #1; an Engineering _Manager_ role at 79).

## Fix 1 — concurrency bug (CRITICAL) — DONE

`tracker.db.current_db_path()` → `workspace.db_path()` → `active_slug()` reads
`projects/projects.json` `active` on **every DB call**; `daily_run` set active once but never
pinned it → a concurrent 2nd run / GUI switch redirected inbox writes. **Hit live:** my parallel
controls run wrote ~61 engineering jobs into Dad's inbox (recovered from `tracker.db.bak-v4`).

**Fix:** `workspace.pin_active()/unpin_active()` — a process-local override `active_slug()`
honors (default None = unchanged). `daily_run.main()` pins the resolved project once;
`run_main()` unpins in `finally`. Tests: `tests/test_workspace.py::test_pin_active_overrides_projects_json`,
`::test_pin_active_none_is_noop`.
**METHODOLOGY:** never run two project-touching processes at once — serialize all
daily_run/inspect/export.

## Fix 2 — Dad inbox size (19 → 23, quality up a lot) — DONE

Root cause is **supply, not a bug**: the Cincinnati+remote gate is _correct_ (drops
non-relocatable jobs); controls is _unfiltered_ so "mine" is inflated (scrapes all 624 incl.
software 248 + applied_ai 227); the health registry (66) had **no Cincinnati-local systems**.

- **Two-tier keywords** in `projects/dad-health-informatics/config.json` (Dad-only, gitignored):
  kept exec TITLES (drive target-level → leadership ranks top) + added health field TERMS
  (health informatics, healthcare analytics, business intelligence, data governance, …) so
  recalled roles get fair title credit instead of a title-miss. Lifted real roles (Inovalon 53→79).
- **Seeded 3 probe-verified employers** into `companies.json` (health_informatics): **Cincinnati
  Children's** (Workday `cincinnatichildrens:5:careersatcincinnatichildrens`, 479 jobs/10 relevant),
  **Bon Secours Mercy Health** (Workday `easyservice:5:BonSecoursMercyHealthCareers`), **Regard**
  (ashby). Registry 66 → 69.
- **Result:** Dad inbox 19 → **23**; two LOCAL Cincinnati Children's BI roles now rank **#1 (100)**
  - **#2 (94)** (his best-fit local roles, previously unreached). Max 64→100, ≥70 count 0→3.

**Seed method (reusable for any local system):** WebSearch "<system> careers myworkdayjobs" →
tenant `<t>.wd<N>.myworkdayjobs.com/<site>` → CompanyEntry slug `t:N:site` → probe
`scrape_workday(ce,'',tmp,False)` → `save_companies()` only if jobs>0. UC Health = Oracle Cloud,
TriHealth/Christ = Phenom/SmashFly → **no app scraper** (adzuna covers them).

## Changed files (UNCOMMITTED)

- `workspace.py` — pin_active/unpin_active + active_slug honors pin.
- `daily_run.py` — pin the run's project; unpin in finally.
- `tests/test_workspace.py` — +2 pin tests.
- `companies.json` — +3 verified health employers.
- `projects/dad-health-informatics/config.json` — two-tier keywords (gitignored user-data).
- `brain/eval-2026-07-01-dad-vs-controls-runs.md` — new eval+fix report.

## Needs Alex

1. **Commit these** (28 already ahead, push still held) — or say and I'll commit locally.
2. Quick wins offered (not done): give `controls` project an `industry` filter (kills the
   624-board over-scrape + 241 429s); add "engineering manager"/"manager" to controls
   `seniority_exclude`; enable semantic ranking (Model2Vec) to kill generic-token false positives.
3. Bigger levers: a Phenom/Oracle scraper (TriHealth/Christ/UC Health) or a Google-Jobs proxy
   (adds supply AND fixes reach `f2=0`).

## State left

Dad inbox = 23 (clean; run reproducible). Controls inbox = 660 (clean). Active project restored
to `eng2`. Suite 1222 passed / 3 skipped. `py -3.12`. Output mode: terse. Nothing pushed.
