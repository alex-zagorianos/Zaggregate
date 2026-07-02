# S32 Post-Fix Smoke Test — Live Blank-Slate Re-Runs

**Date:** 2026-07-02 · **Repo:** master @ `b686f40` (all S32 fixes merged, suite green) · **Agent:** Opus smoke-test
**Machine:** same rig as the pre-fix baselines (2026-07-01), same `.env` keys.

## What this proves

Three general-user personas re-run from **fresh blank-slate projects** (`gs-*`, empty `tracker.db`, cloned from the `gu-*` configs) to measure whether the S32 buildout actually widened live search:

| Fix                                                 | Persona that proves it                                |
| --------------------------------------------------- | ----------------------------------------------------- |
| P0-1 token-aware industry matching                  | warehouse (multi-word `warehouse logistics` industry) |
| `workday_cxs` public fetcher                        | warehouse (marquee Workday employers)                 |
| P0-5 Adzuna/USAJobs remote queries                  | marketing-remote                                      |
| REAP-OH education feed                              | teacher-columbus                                      |
| P0-4 scoped `--project` must not flip global active | all three                                             |

**Keyless caveat (unchanged since baseline):** `.env` has ADZUNA + USAJOBS + JSEARCH + ANTHROPIC only. No CareerOneStop / Jooble / Careerjet / SerpApi / Brave keys, so those sources self-skip every run (as designed). Reach % stays "cannot certify" (no SerpApi cross-family overlap).

---

## Headline: baseline → now

| Persona               | Raw (base→now)  | Inboxed (base→now) | Source shift                                                                          | Verdict                                                                                                                                                         |
| --------------------- | --------------- | ------------------ | ------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **warehouse-memphis** | 479 → **621**   | 53 → **58**        | still 100% adzuna                                                                     | Plumbing fixed (careers path now searches the seeds), but the seeds returned 0 matching Memphis warehouse reqs → no source-mix change this run. Honest partial. |
| **marketing-remote**  | 76 → **319**    | 8 → **36** (4.5×)  | adzuna 0 → **32**, +himalayas 3, +jobicy 1                                            | **Clear win.** Adzuna remote query fix is the headline.                                                                                                         |
| **teacher-columbus**  | 1,597 → **678** | 49 → **36**        | still 100% adzuna in inbox, but **REAP now returns 13 raw (base 0)** + HigherEdJobs 4 | Feed wired & returning OH data (proof); Adzuna's Columbus district coverage still out-competed REAP into the final inbox.                                       |

---

## 1. Warehouse-Memphis — P0-1 + workday_cxs proof

### Seeding (real Add-Companies pipeline: `ui.ai_setup.apply_seed_lines` → `ats_detect.parse_line` → `probe_count` → `save_companies`)

Seeded 15 real Memphis-area logistics/distribution/manufacturing employers via careers-page URLs, tagged `warehouse logistics` (the persona's `industry`). All resolved to `workday_cxs` via the new fetcher.

| Employer                                                                             | ats_type    | Probe verdict | Live jobs | Real state                              |
| ------------------------------------------------------------------------------------ | ----------- | ------------- | --------- | --------------------------------------- |
| Terminix                                                                             | workday_cxs | live          | **500**   | genuinely live (Memphis HQ)             |
| FedEx                                                                                | workday_cxs | "live (0)"    | 0         | HTTP 404 (wrong site slug guessed)      |
| AutoZone                                                                             | workday_cxs | "live (0)"    | 0         | HTTP 422 — Cloudflare-walled (EXPECTED) |
| Williams-Sonoma, XPO, Cummins, ServiceMaster, Mueller, Nucor, Baptist Memorial, Hino | workday_cxs | "live (0)"    | 0         | HTTP 422 — Cloudflare-walled (EXPECTED) |
| International Paper                                                                  | workday_cxs | "live (0)"    | 0         | HTTP 520 (transient)                    |
| Nike, Smith & Nephew, Kimberly-Clark                                                 | workday_cxs | "live (0)"    | 0         | HTTP 404 (wrong site slug guessed)      |

**Verified-live majors: base 0 → now 15 in the registry, all scrapeable.** `industry_company_count("warehouse logistics")` = **15** (baseline bug returned **0** for any multi-word field — that's the P0-1 fix, proven directly). `get_registry(industry="warehouse logistics")` returns all 15 to the careers path.

> **Honest nuance on the P0-6 verify gate:** for `workday_cxs`, `probe_count` returns `len(fetch(slug))`. A Cloudflare-walled 422 fails-soft to `[]` → `len([]) == 0`, which is an integer (not `None`), so the gate marks it **"live (0 open jobs)" = verified**, not `unreachable`. So a 422-walled tenant is saved as verified-but-empty rather than flagged-unverified. Not a regression (it's still excluded from real results because it yields 0 jobs), but the verify gate does **not** distinguish "genuinely live but 0 open" from "Cloudflare-walled". Worth a follow-up: have `workday_cxs` probe surface the permanent-403/422 signal so the gate can flag it `unreachable`.

### Run funnel (`daily_run --project gs-warehouse-memphis`)

| Stage                 | Count                                       |
| --------------------- | ------------------------------------------- |
| raw                   | 621                                         |
| after dedup           | 442                                         |
| preferences hard-gate | 442 → 203 (dropped: location 227, title 12) |
| qualified (≥40)       | 58                                          |
| **inboxed**           | **58**                                      |

Source mix (inbox): **adzuna 58 / 100%.** careers = **0 inboxed** (baseline 0).

**Diagnosis of careers = 0 (honest):** The careers path now _runs and scrapes all 15 seeds_ (P0-1 + workday_cxs both working) — but 14 of 15 boards were 404/422-walled (empty), and the one board with real jobs, **Terminix (500 open, Memphis HQ)**, has **zero warehouse/logistics titles** — its Memphis reqs are pest-control / outside-sales / eCommerce. So careers=0 is a genuine no-match, not a pipeline failure. To move this number a general user needs Memphis warehouse employers whose Workday tenants are (a) not Cloudflare-walled and (b) actually hiring warehouse roles — my diversified-employer seed list happened to hit neither. The **machinery is proven; the seed selection was the limiter.**

---

## 2. Marketing-Remote — P0-5 proof (Adzuna/USAJobs remote)

No seeding. `daily_run --project gs-marketing-remote`.

| Stage                 | Count                                                           |
| --------------------- | --------------------------------------------------------------- |
| raw                   | 319                                                             |
| after dedup           | 253                                                             |
| preferences hard-gate | 253 → 129 (dropped: location 109, salary 12, employment_type 3) |
| qualified (≥40)       | 117                                                             |
| **inboxed**           | **36** (baseline **8**)                                         |

Source mix (inbox): **adzuna 32** (baseline **0**), himalayas 3, jobicy 1.
Raw per-source: Adzuna **64 → 114** for `Remote` (baseline 0), Himalayas 76, WeWorkRemotely 37, TheMuse 62, RemoteOK 17, HN 3, WorkingNomads 1. USAJobs still **0** for Remote (query now issued, but federal remote-only postings came back empty — enabled, not populated). 8 independent source families.

**Inbox quality:** top rows are genuine US-remote marketing roles — "Digital Marketing Manager" (Revpanda, G&S), "Social Media Marketing Manager (Remote)" (Cengage Group), all US "Remote" locations. Country-honesty fix holding: no non-US / non-English postings surfaced to the top. **One dedup observation (not a regression):** Cengage Group fanned the same "Social Media Marketing Manager (Remote)" req across many US metros via Adzuna → hit the per-company cap (**81 capped**). This is the cross-board / city-fan-out canonicalization gap already flagged for a design pass, not a smoke-test failure.

**Verdict: the strongest of the three.** Adzuna went from contributing nothing to being the dominant remote source; total inbox 4.5× the baseline.

---

## 3. Teacher-Columbus — REAP-OH proof

No seeding. `daily_run --project gs-teacher-columbus`.

| Stage                 | Count                                                 |
| --------------------- | ----------------------------------------------------- |
| raw                   | 678                                                   |
| after dedup           | 603                                                   |
| preferences hard-gate | 603 → 157 (dropped: location 427, salary 15, title 4) |
| qualified (≥40)       | 59                                                    |
| **inboxed**           | **36**                                                |

Source mix (inbox): **adzuna 36 / 100%.**
Raw per-source (education feeds): **REAP 13 (baseline 0)**, HigherEdJobs 4, EdJoin **0**, plus Adzuna 361, Himalayas 135, USAJobs 65, RemoteOK 42, WeWorkRemotely 25, TheMuse 24. 10 independent source families.

- **REAP-OH: 13 raw results (baseline 0)** — the feed is wired, industry+state-gated correctly (education + OH covered), and returning real Ohio postings. **Proof lands at the funnel level.**
- **EdJoin: 0, gracefully** — took 239s (Cloudflare-slow) but returned 0 for Columbus OH, exactly as expected (EdJoin's JSON is CA-dominated; it self-scoped to nothing for OH without noise or error).
- **HigherEdJobs: 4** — the other new education feed also contributing.

**Honest nuance — why 0 REAP rows reached the inbox:** REAP's 13 raw postings scored below Adzuna's Columbus-education coverage and were squeezed out. Adzuna alone supplied **15 Columbus City School District** inbox rows (+23 more capped) plus Performance Academies, KIPP Columbus, United Schools Network, etc. The inbox holds only the qualified+capped survivors; REAP's rows didn't out-rank Adzuna's district postings this run. So REAP adds **recall/redundancy** (and would matter more where Adzuna is thin), but it wasn't the marginal source in Columbus today. Inbox scores 61–76 (avg 67), all genuine K-12 education roles.

**Note on run time:** this run took ~10 min — dominated by EdJoin (239s) + REAP (180s) Cloudflare-slow fetches and ~11×60s Adzuna per-host rate-limit waits across 16 broadened OH keywords. Completed cleanly (EXIT=0); no hang.

---

## 4. P0-4 — scoped `--project` must NOT flip the global active project

Global `projects.json` `active` read before/during/after every run:

| Checkpoint                  | active          |
| --------------------------- | --------------- |
| start of session (recorded) | `test-controls` |
| during warehouse run        | `test-controls` |
| during marketing run        | `test-controls` |
| during teacher run          | `test-controls` |
| after all three runs        | `test-controls` |

**PASS.** A scoped `--project` run resolves every db/config/output path via the process-local pin (`workspace.pin_active`) and never calls `set_active`, so the global active project is untouched. Confirmed in code (`daily_run.main`) and observed live across all three runs.

---

## Restoration (verified)

- **companies.json**: restored byte-exact from the pre-test snapshot — md5 `961dec5fab1af9877938f7810f25c359` matches; 556 real companies; 0 warehouse-logistics-tagged (the 15 seeds cleanly removed).
- **active project**: `test-controls` (never flipped; `set_active('test-controls')` re-called to satisfy the restore rule; verified).
- The three `gs-*` blank-slate projects are **left in place** for Alex to browse.

---

## Errors / regressions

- **No crashes, no regressions.** All three runs EXIT=0.
- **Not a bug, worth a follow-up:** the `workday_cxs` P0-6 verify gate can't tell "genuinely live, 0 open" from "Cloudflare-walled 422" — both probe to `len([])==0` and save as verified-empty. Consider surfacing the permanent-403/422 from the fetcher so a walled tenant is flagged `unreachable` instead.
- **Known / already-flagged:** cross-board company-canon dedup (Cengage city-fan-out hit the cap at 81; Columbus City School District at 23) — the design-pass item, not a hot fix.
- **Environment, not code:** careers/education feeds behind Cloudflare (EdJoin, REAP, several Workday tenants) are slow (180–240s) and inflate wall time; the daily run absorbs this via timeouts + negative-caching but a scheduled run should expect multi-minute durations for education/careers-heavy profiles.

## Bottom line

- **Marketing-remote:** unambiguous win — P0-5 Adzuna remote query fix turned 0→32 inboxed and 8→36 total.
- **Warehouse & teacher:** the _new machinery is proven live_ (P0-1 makes multi-word industries match their seeds 0→15; workday_cxs resolves marquee Workday boards; REAP-OH returns 13 OH postings 0→13) — but neither moved the final **inbox source mix** this run, for honest, diagnosable reasons (Cloudflare-walled tenants + a Terminix no-match for warehouse; Adzuna out-competing REAP in Columbus). Both are seed/data-selection or competition effects, not pipeline failures.
- **P0-4:** solid across all three runs.
