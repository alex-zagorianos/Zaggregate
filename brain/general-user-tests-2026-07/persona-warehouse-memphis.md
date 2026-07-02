# General-User Test - Terrence Brooks (Warehouse / Logistics, Memphis TN)

**Date:** 2026-07-01 · **Tester:** Opus subagent playing the persona end-to-end (blank slate: only the shipped starter registry + companies.json, no prior projects) · **Project slug:** `gu-warehouse-memphis`

Persona: 4 yrs warehouse ops, forklift certified, shift-lead experience. Wants warehouse lead / logistics coordinator / warehouse supervisor / distribution roles. Memphis, TN (20 mi radius), on-site only, $40k floor, mid-level.

---

## 1. New-user lens

Read: `README.md`, the in-app Guide (`ui/help.py` GUIDE list), and the first-run wizard (`ui/setup_wizard.py`).

**Wizard clarity: 8/10.** Five steps, all plain English: Welcome -> "What jobs are you looking for?" (roles + optional field/industry + optional career level + free-text "Anything else the AI should know?") -> "Where do you want to work?" (location, "Remote jobs are fine too" checkbox, optional salary that accepts hourly like `18/hr`) -> "Your resume (optional)" (paste or load a file) -> "Keep jobs coming" (daily updates + Build-My-List toggles). Strong touches: hourly-wage parsing, a plain-text resume is auto-structured into headings so it cannot crash scoring later, and the field box tunes routing/rubric. The Guide is genuinely excellent for a non-technical user and is honest that "the free feeds lean toward remote tech jobs" and that two free keys (Adzuna + CareerOneStop) plus a local employer list are "the 10 minutes that matters most."

Two dockings from 10: (a) the wizard never explains that a **two-word field** ("warehouse logistics") behaves differently from a one-word field for the company registry (this bites hard - see bug B1); (b) the location field takes a free-text city with no explicit radius control, so "within 20 mi" is implicit - it worked out fine here, but a user cannot set the radius.

## 2. Project setup

Created programmatically the way the wizard's `apply()` would, then authored faithful content:

- `config.json` - 8 keywords (warehouse lead, logistics coordinator, warehouse supervisor, distribution, warehouse operations, shift lead, inventory coordinator, forklift operator), `location: "Memphis, TN"`, `salary_min: 40000`, `industry: "warehouse logistics"`, `seniority_target: mid` + `years_cap: 8` (from career-level "Mid"), `exclude_titles` (director/vp/senior manager/software/engineer/driver/sales), `exclude_keywords` (cdl required/route driver/otr/...).
- `preferences.json` hard filters - `salary_min 40000`, `locations ["Memphis, TN"]`, `remote_ok false` (on-site), `seniority_exclude [director, vp]`, target_roles.
- `preferences.md` - natural-language profile (step-up goal, forklift certs, on-site only, avoid OTR/CDL/remote/senior).
- `experience.md` - full persona resume; parses cleanly with `resume.experience_parser.load_experience`.

`create_project` (`_attach_onet_soc`) did NOT attach an O*NET SOC code - "warehouse logistics" does not resolve to a non-eng occupation in `industry_profile.resolve_soc` (warehouse operations / warehouse lead / distribution / forklift all return None; only "logistics coordinator" resolves, to a _manager_ SOC). So there is no warehouse/logistics industry profile: `query_synonyms` is empty, keyword broadening is a no-op, and field routing falls back to generic. Finding, not a blocker.

## 3. Seeding (ask-your-own-AI flow)

As the persona AI, produced 16 real Memphis logistics/distribution employers + 1 deliberate junk line, pushed through the exact "+ Add Companies" pipeline (`scrape.ats_detect.parse_line` -> `probe_count` -> `scrape.company_registry.save_companies`).

| Stage                                   | Count                                                     |
| --------------------------------------- | --------------------------------------------------------- |
| Attempted                               | 17 (16 real + 1 junk)                                     |
| Parsed/detected                         | 17                                                        |
| **Added to companies.json**             | **17**                                                    |
| Live-probed with jobs                   | 2 (Flexport 129, Technicolor 0)                           |
| Direct (uncountable, best-effort later) | 6 (FedEx, XPO, GXO, Ryder, DHL, Kuehne+Nagel)             |
| Unreachable at probe                    | 9 (Workday CSRF 422 / wrong site slug 404 / dead GH slug) |

**Key seeding finding (B2): the Add step does NOT gate on validation.** `AddCompaniesDialog._add` saves every parsed entry via `save_companies` regardless of the Validate result - so the junk "Zip Code Nonsense LLC" and all 9 UNREACHABLE Workday/greenhouse boards were written to companies.json. The brief's "junk that fails probe = flow working as designed" is only half-true: junk is _saved_, it just returns 0 jobs on the run. Validate is purely informational.

Detailed Workday diagnosis: Nike -> 404 (public-URL site slug != CXS site id), AutoZone and International Paper -> 422 (CSRF-protected). This is the exact pattern the registry's own comments document for big industrials. So the marquee Memphis employers a warehouse worker most wants (FedEx, Nike, AutoZone, Int'l Paper) are on portals the scraper cannot pull from - seeding them adds names but no jobs.

## 4. Run

`py -3.12 daily_run.py --project gu-warehouse-memphis` (background). **Wall clock ~32 s** (23:49:11 -> 23:49:43).

**Funnel:** 479 raw -> 363 dedup -> hard-gate 161 (dropped: title 9, **location 193**) -> 53 qualified (>=40) -> **53 inboxed**. Page-2 paging added +157 raw.

Client-level source returns (page-2 pass): Adzuna 417, TheMuse 22, USAJobs 20, HN 11, WeWorkRemotely 7, Himalayas 1, RemoteOK 1; **Careers 0**, Careerjet/Jooble/CareerOneStop/Jobicy/Remotive/WorkingNomads/RNJobSite/HigherEdJobs 0.

Warnings / non-fatal (no 429s, no crashes, exit 0):

- `NOTE: only 0 registry companies match industry 'warehouse logistics'` - **this is bug B1** (below); it starved the careers path even though 17 companies were just seeded.
- CareerOneStop skipped - no key (known gap).
- Jooble / Careerjet / Brave-discovery skipped - keys unset.
- HigherEdJobs / RNJobSite inert for a non-education/non-nursing field (correct).
- The **remote-tech boards were NOT gated off** for this on-site warehouse field (RemoteOK/Remotive/Jobicy/Himalayas/HN/WeWorkRemotely/WorkingNomads all still ran) - `gate_tech_sources("warehouse logistics", ...)` returns them unchanged. They returned near-zero and their remote hits were dropped by the location gate, so wasted calls + noise, not wrong results.

## 5. Inbox analysis

`projects/gu-warehouse-memphis/tracker.db`, `inbox` table (53 rows).

- **Source mix: adzuna 53 / 53 (100%).** Every other source contributed 0 to the on-site Memphis inbox. This matches the prior finding "Adzuna = ALL non-seeded local wins" - for a keyless on-site blue-collar search, Adzuna is effectively the only working source.
- **Locality: 53/53 in-area, 0 remote, 0 wrong-area.** 36 in Memphis/Shelby, 17 in West Memphis/Crittenden AR (~10 mi across the river, inside 20 mi), a couple DeSoto MS. The location hard-gate (dropped 193 out-of-area) is the single most valuable thing the app did.
- **Score distribution:** 82 x1, 70-79 x14, 60-69 x36, 50-59 x2. Nothing >=90; compressed band.
- Salary is disclosed on nearly every row and all clear the $40k floor.

**BYO-AI re-rank (I acted as the $20/mo assistant):** wrote Fit + rationale back via `tracker.service.apply_rerank_scores` (same path as "Load AI results"). Fit cleanly separated real fits (80-95) from ~12 off-role high-Score false positives (12-30). **False positives in the top ~40 (~12):** Industrial Maintenance Tech x3 (Bosch), Production/Weld Leader (AAON), Electrical/Mechanical Lead x2 (Jabil), Quality Technician (Bosch), Warehouse Janitorial Cleaner (ABM), Warehouse Office Support (Home Depot), Starbucks store shift supervisor, Valet Shift Lead (Graceland), Brewery cellar/shift person (Wiseacre). **Why they scored high:** the on-device scorer rewards title tokens - "lead", "shift", "supervisor", "warehouse" - without understanding the domain, so a maintenance/weld/retail/hospitality "shift lead" ranks alongside a real DC lead. This is the textbook "high Score, low Fit" the Guide names, and the exact gap the AI re-rank closes.

**Minor B3:** `apply_rerank_scores` (file-import route) fills the Fit column but does NOT stamp `rank`/`rec_batch`, so `top_picks()` stays empty. Only the clipboard `Paste AI ranking` route (`score_inbox_from_reply`) populates the Top Picks tab. File-round-trip users get a Fit-sortable inbox but an empty Top Picks tab.

### Top 10 (BYO-AI ranked)

| #   | Title                             | Company                     | Location                 | Pay            | Why                                                                   |
| --- | --------------------------------- | --------------------------- | ------------------------ | -------------- | --------------------------------------------------------------------- |
| 1   | Warehouse Supervisor              | Floor & Decor               | Memphis, Shelby          | $53,669        | Direct supervisor step-up, disclosed pay well over floor - best fit   |
| 2   | Warehouse Team Lead (1st Shift)   | Bosch Group                 | West Memphis, Crittenden | $41,267        | Exact team-lead match; inbound/outbound-flow duties mirror his resume |
| 3   | Warehouse Supervisor              | Barrett Distribution Center | Memphis, Shelby          | $49,589        | 3PL DC supervisor - his exact 3PL background at the right level       |
| 4   | Distribution Center Lead          | American Tire Distributors  | Memphis, Shelby          | $52,932        | DC lead, people-lead framing fits shift-lead experience               |
| 5   | Logistics Coordinator             | Puzzle Solutions Holdings   | Memphis, Shelby          | $60-80k        | His 2nd target title, M-F day, strong pay + growth                    |
| 6   | Warehouse Associate               | Kenco (3PL)                 | Memphis, Shelby          | $51,353        | Leading 3PL, high pay, clear lead track from his 3PL history          |
| 7   | Supervisor, Distribution Center   | Hollywood Feed              | Memphis, Shelby          | $70,195        | Memphis-HQ DC supervisor, excellent pay for a step-up                 |
| 8   | Distribution Group Lead IV        | Medtronic                   | Memphis, Shelby          | $53,600-80,400 | DC lead at a major employer, strong range                             |
| 9   | Warehouse Supervisor II           | IFF                         | Memphis, Shelby          | $67,851        | In-domain supervisor; slight seniority stretch but reachable          |
| 10  | Warehouse Associate II (Evenings) | Cardinal Health             | Memphis, Shelby          | $41,039        | Reliable big-name DC role at his floor - solid fallback               |

## 6. Tracking to completion

Took 5 top jobs through the lifecycle via the same `tracker.service` verbs the GUI buttons call; re-read the DB to verify.

- All 5 tracked (inbox -> application) then -> **applied**.
- 2 -> **interview** with an interview round each (`add_interview_round`): app 1 phone (2026-07-08), app 2 onsite (2026-07-10). Both rounds persisted.
- 1 -> **offer -> accepted** (Floor & Decor), with offer_deadline + an acceptance note. Full completion.
- 1 -> **rejected** (Barrett) + note.
- 1 -> **ghosted** (American Tire) + note.
- 5th (Puzzle Solutions Logistics Coordinator) stayed **applied**.

Re-read verification: final counts `applied 1, interview 1, accepted 1, rejected 1, ghosted 1` - all 5 statuses reachable including S29's accepted + ghosted. `status_timeline` captured every transition + note (app 1 = 5 entries). Interview rounds present.

**Lifecycle gaps:**

- **B4 (data-loss trap):** `db.update_job` silently ignores unknown field names. Passing `offer_salary='53669'` (a plausible guess) was dropped with no error - the real column is `offer_amount`. A user or their AI guessing a field name loses data silently.
- phone_screen exists as a distinct status between applied and interview (not used in my path) - fine.
- Everything a user needs from the GUI (status changes, interview rounds, notes, offer fields, an ICS export helper) is reachable through the service layer.

## 7. Verdict

**Could Terrence run his whole search on this app? Yes - genuinely, and better than manual browsing for the discovery+triage+tracking loop, with one setup caveat.** The location gate delivered a 53-row inbox that was 100% real Memphis-area warehouse/distribution jobs with disclosed salaries above his floor - something LinkedIn/Indeed location filters routinely pollute with remote and out-of-metro noise. Tracking through accepted/rejected/ghosted with interview rounds and notes all worked. The BYO-AI re-rank cleanly demoted the ~12 off-role "shift lead" false positives the keyword score could not tell apart.

**Where it beats manual:** one 32-second run aggregates Adzuna's full Memphis warehouse market, hard-filters to on-site + salary + non-driver, and hands back a tight ranked list he can triage with keyboard shortcuts and then track to completion - no re-searching five sites daily, no spreadsheet.

**Where it loses to LinkedIn/Indeed:** (1) It is ToS-blocked from Indeed, which for blue-collar warehouse work is _the_ dominant board - so the app misses a large slice of the real Memphis warehouse market it cannot legally touch. (2) The marquee local employers (FedEx global HQ, Nike's largest DC, AutoZone HQ, Int'l Paper HQ) are on CSRF-protected Workday/direct portals the scraper cannot pull, so seeding them yields names but no jobs. (3) No LinkedIn networking/referral surface.

**Reliance profile:** essentially 100% Adzuna. Careers-registry contribution was 0 (bug B1 + the marquee-employers-on-Workday problem). Keyless sources (Jooble/Careerjet/CareerOneStop) contributed 0. So a general user's local warehouse results ride entirely on the one keyed aggregator - fragile. **CareerOneStop (the DOL National Labor Exchange, ~3.5M postings/day including exactly this kind of blue-collar on-site work) is unkeyed and would be the single biggest equalizer** for this persona - the Guide even names it as the #2 key, but it is not wired here.

**Single most valuable improvement for THIS persona:** fix **B1** - the two-word-industry registry-match bug - so a user's own seeded local employers actually feed their careers search (today "warehouse logistics" silently matches 0 companies while "logistics" or "warehouse" match all 17). Runner-up: key CareerOneStop.

---

## Bugs / findings (with evidence)

- **B1 (real bug, data-visibility):** A **multi-word `industry` value never matches the company registry.** `get_registry` normalizes the industry key spaces->underscores (`"warehouse logistics"` -> `"warehouse_logistics"`), but company tags keep the space (`"warehouse logistics"`), and `_industry_tag_match` uses plain substring containment - the underscore breaks it both ways. Measured: `industry_company_count("warehouse logistics") == 0` while `industry_company_count("logistics") == 17` and `industry_company_count("warehouse") == 17`, with all 17 seeded companies tagged `["warehouse logistics"]`. Consequence: the daily run logged "only 0 registry companies match industry 'warehouse logistics'" and the careers path added 0 jobs despite fresh seeding. Fix: normalize spaces<->underscores symmetrically in `_industry_tag_match` (`scrape/company_registry.py`).
- **B2 (design gap):** `AddCompaniesDialog._add` / `save_companies` write every parsed line to companies.json regardless of the Validate probe result. Junk and all 9 UNREACHABLE boards were saved. No "add only validated" option. (`gui.py` ~L2428, `scrape/company_registry.save_companies`).
- **B3 (minor):** `tracker.service.apply_rerank_scores` (file-import / "Load AI results") writes Fit but not `rank`/`rec_batch`, so `top_picks()` returns empty for that route; only the clipboard `score_inbox_from_reply` populates the Top Picks tab.
- **B4 (data-loss trap):** `tracker.db.update_job` silently ignores unknown field names (only keys in `_EXTRA_COLUMNS` are written). `update_job(offer_salary=...)` dropped the value with no error; real column is `offer_amount`.
- **Not-a-bug findings:** no warehouse/logistics `industry_profile` (empty query_synonyms, no field routing); `gate_tech_sources` does not drop remote-tech boards for a warehouse field (wasted calls, no wrong results); CareerOneStop/Jooble/Careerjet/Brave keys unset (known gaps); FedEx/Nike/AutoZone/Int'l Paper on CSRF Workday = unscrapable.

## Run environment / keys disclosed

`.env` had Adzuna + JSearch + USAJobs keys (treated as the free-key signups the Guide prescribes). CareerOneStop NOT keyed (known gap). Jooble, Careerjet, Brave (discovery) keys unset. No 429/quota events. jsearch is intentionally excluded from DAILY_SOURCES. companies.json was mutated by seeding and will be restored by the janitor (I did not restore it).
