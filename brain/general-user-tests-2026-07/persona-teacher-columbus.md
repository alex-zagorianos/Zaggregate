# General-User Test — David Chen, 7-12 Math Teacher, Columbus OH

**Persona:** Licensed Ohio 7-12 integrated-mathematics teacher, 8 yrs, department lead.
Open to teaching, instructional coaching, or curriculum roles. Columbus, OH (25 mi),
on-site only, $50K floor, mid-career.
**Project slug:** `gu-teacher-columbus`  ·  **Date:** 2026-07-01  ·  **App version:** 1.0.0
**Tester lens:** brand-new general user + acting as the persona's $20/mo BYO-AI assistant.
Blank slate — only the shipped starter registry + the free-key signups the Guide prescribes.

---

## 1. New-user lens — README, Guide, Setup Wizard

**Wizard clarity: 8/10.** A non-technical teacher can complete it. Path a real user walks
(`ui/setup_wizard.py`), 5 steps:

1. **Welcome** (intro, no data)
2. **Roles** — free-text comma keywords + optional _Field/industry_ + optional _Career level_
   combobox + an _"Anything else the AI should know?"_ free-text box. Good inline examples
   ("registered nurse, controls engineer …") and a genuinely useful tip: use broad field terms,
   set seniority via the Career-level dropdown, not the search box.
3. **Where** — location + "Remote jobs are fine too" checkbox + optional salary (accepts `18/hr`
   and annualizes it — a nice touch for hourly fields, though teaching is salaried).
4. **Resume** — paste or load-from-file; auto-structured into `## ` headings so a plain paste
   can't crash later scoring (P0 fix visible in `structure_resume_text`).
5. **Keep jobs coming** — daily-updates checkbox + "Build my employer list now" checkbox.

**What's genuinely good for a teacher:**

- The Guide (`ui/help.py`) is excellent and honest. It flat-out says the free feeds "lean toward
  remote tech jobs," names **Adzuna** and **CareerOneStop** as _the_ two keys that matter, and
  explicitly calls CareerOneStop "the best free source for teachers, nurses, government, trades."
- There's a full "ask your own AI to build your employer list" section with a ready-made prompt
  — exactly the flow this test exercises. It even reassures: "Anything the AI got wrong simply
  fails verification — nothing bad can sneak in."

**Friction / clarity gaps a teacher would hit:**

- The wizard never mentions that the starter company registry ships with **only two industries
  (health_informatics, controls_engineering)** and **zero education employers**. A teacher who
  skips the optional Field box and the optional "Build my list" step gets a company layer that
  contributes nothing to their field. The `_maybe_offer_discovery` popup does fire for a
  recognized-but-empty field, which helps — but only if you typed a Field.
- "Career level" combobox offers Entry/Mid/Senior/Manager-Exec — fine, but for K-12 there's no
  notion of "teacher vs. coach vs. district admin," so a coaching-curious teacher can't express
  the teacher→coach→curriculum ladder except in the free-text box.
- Nothing warns that most **public school districts run Frontline or NEOGOV/governmentjobs**,
  which this app cannot scrape (Frontline: no scraper; NEOGOV: ToS-blocked). A teacher's most
  obvious targets (Columbus City, Dublin, Hilliard, Westerville district sites) are exactly the
  ones the "+ Add Companies" flow will reject.

---

## 2. Project setup

Created programmatically via `workspace.create_project(name="GU - David Chen",
slug="gu-teacher-columbus", config=…, make_active=False)`, then wrote `preferences.json`,
`preferences.md`, `experience.md` into the project dir (shapes learned from `gu-nurse-boise`).

- **config.json** — 9 keywords (math teacher, high school math teacher, secondary mathematics
  teacher, instructional coach, math interventionist, curriculum specialist/coordinator, STEM
  teacher, teacher), `location: "Columbus, OH"`, `salary_min: 50000`, `industry: "education"`,
  `seniority_target: "mid"`, `years_cap: 8`, exclude_titles (substitute/paraprofessional/aide/
  assistant/sales/recruiter).
- **preferences.json** — `salary_min 50000`, `locations ["Columbus, OH"]`, `remote_ok false`
  (on-site), dealbreakers (substitute/clearance).
- **preferences.md / experience.md** — full David Chen profile (OSU B.S. Math Ed, Ashland M.Ed
  C&I, dept lead, Algebra/Geometry, PLC/coaching, Ohio standards). No real PII.

**Finding — `onet_soc` not attached.** `industry_profile.resolve_soc("education")` returns
**None** (as does `"education (K-12)"`), so `create_project`'s `_attach_onet_soc` added no SOC
code. Only more specific strings resolve — `resolve_soc("math teacher")` → `25-1022.00
Mathematical Science Teachers, **Postsecondary**` (wrong level for a 7-12 teacher!). The
free-text genre router still works: `resolve("education")` cleanly routes to Muse "Education" +
title terms teacher/instructor/education/professor, and the `education` industry tag is what my
seeded companies key off. Net: routing is fine; the SOC code that would sharpen title scoring is
simply absent for the bare word "education."

---

## 3. Seeding — ask-your-own-AI employer flow

As David's AI assistant I produced 16 "Name | ATS-URL" lines for Columbus-area / Ohio-relevant
education employers, then pushed them through the **exact** "+ Add Companies" pipeline:
`ats_detect.parse_line` → `ats_detect.probe_count` → `company_registry.save_companies`.

Deliberately leaned to **charter networks, ed-tech/tutoring, ed nonprofits, higher-ed** on
scrapeable ATSes (Greenhouse/Lever/Ashby/Workday/SmartRecruiters) — because Columbus **public
districts run Frontline/NEOGOV** which this app can't take (recorded gap, see below).

| Result                      | Count  | Examples                                                                                                                             |
| --------------------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| Parsed OK                   | 16/16  | all lines parsed to CompanyEntry                                                                                                     |
| Live-with-jobs (probe)      | 4      | Newsela (17), Guild Education (11), **Ohio State Univ / Workday (1041)**, Khan Academy (22)                                          |
| Live-but-zero               | 1      | Battelle (SmartRecruiters resolved, 0 open)                                                                                          |
| Unreachable (probe → None)  | 11     | KIPP, IDEA, Uncommon, Democracy Prep, Success Academy, Amplify, IXL, Curriculum Associates, Varsity Tutors, Paper, Teach For America |
| Direct (uncountable)        | 0      | —                                                                                                                                    |
| **Saved to companies.json** | **16** | (GUI adds _all_ detected entries; probe is advisory)                                                                                 |

The 11 "unreachable" are mostly **best-effort slug guesses that 404'd** — the flow working as
designed (junk fails the probe, user sees "unreachable"). All 16 were saved tagged
`industry: education` and now resolve via `get_registry(industry="education")` → **16 companies**
(the shipped registry had **0** education companies, so the registry generalized entirely from
my seed). This validates the "companies.json ships so the registry generalizes" claim from the
S30 brain: the local layer is field-agnostic once seeded.

**Seeding friction / gaps:**

- **Frontline has no scraper.** The single biggest miss for a teacher: every traditional public
  district portal (Columbus City on Frontline, most suburbs on Frontline/NEOGOV) can't be added.
  A teacher's most-wanted employers are structurally unreachable via the company layer.
- **Probe passes ≠ jobs land.** OSU probed 1041 jobs but is capped at `max_per_company:15` and
  is mostly non-K12 university staff — huge board, low signal (see funnel).
- I only actually _added value_ from 4 boards; of those, only Newsela/Khan/Guild are
  teacher-adjacent (curriculum/ed-tech), OSU is noisy. The seed's yield into the inbox was small.

---

## 4. The run

`py -3.12 daily_run.py --project gu-teacher-columbus` (background). **Wall-clock ≈ 3 min 47 s**
(23:19:11 → 23:23:06 wall; internal pipeline log 23:19:19 → 23:23:06). Exit 0, no traceback.

**Sources active:** adzuna, usajobs, careeronestop, careers, themuse, remoteok, remotive, jobicy,
himalayas, hn, weworkremotely, workingnomads, jooble, careerjet, **higheredjobs**, rnjobsite.

**Funnel (2 pages):**

```
raw 1597  ->  1370 after dedup   (page 2 added +185 raw)
hard-gate 1370 -> 391            (dropped: title 3, location 976)
391 found  ->  72 >= score 40  ->  49 new -> inbox
capped: Columbus City School District 23 (kept 15)
```

- **The location gate is the hero here:** it dropped **976** postings for wrong location, leaving
  a genuinely local shortlist. `min_score` auto-raised to 40.
- Per-source (post-gate `found`, from last_run.json): **careers 234, adzuna 148, usajobs 9.**
- Raw client tallies: CareersClient 976 (OSU Workday paging dominates), HigherEdJobs 89,
  RemoteOK 42, WeWorkRemotely 25, TheMuse 14/24, USAJobs 44/69, Adzuna 211.

**Errors / warnings / quota events:**

- `[careeronestop] Skipping — credentials missing.` **The known gap, and the most damaging one
  for this persona** — the Guide itself calls CareerOneStop the best free source for teachers.
- `[jooble]` / `[careerjet]` skipped (keys unset) — many warning lines, harmless self-skip.
- `[rnjobsite] Inert for industry 'education'` — correct (nursing feed gates off).
- `[discover] BRAVE_SEARCH_API_KEY unset` — company discovery skipped, registry-only.
- 11 of my seeded Greenhouse/Lever boards logged `gone — skipping` (same dead slugs the probe
  flagged) — expected, non-fatal.
- No 429/quota events. Adzuna + USAJobs keys worked.
- **Reach probe:** "cannot certify a coverage % — no cross-source overlap … 1597 raw → 970
  distinct from 10 independent source families (sample completeness ~39% by Good-Turing)."

---

## 5. Inbox analysis (`projects/gu-teacher-columbus/tracker.db`, `inbox` table)

- **Total: 49 rows.** **Source mix: adzuna 36, careers 13** (careers = OSU Workday only; USAJobs
  had 9 in the funnel but none scored ≥40).
- **Score:** min 40, max 87, avg 64.4. Buckets: 80-89 ×3, 70-79 ×5, 60-69 ×35, 40-49 ×6.
- **Locality by stored string: 49/49 "in area."** BUT the stored location is misleading —
  **Adzuna stamps the query location ("Columbus, Franklin County") onto every posting** regardless
  of the real job site. Judging by company/description evidence: **~41 genuinely Columbus-area,
  3 clearly out-of-state (Adzuna mis-stamp), 5 ambiguous** (national online e.g. Stride/K12,
  LearnWell "Northern Ohio"). Still an excellent local hit rate — the residual noise is Adzuna's
  data quality, not the app's gate.

### BYO-AI re-rank — TOP 10 (I overrode the on-device Score for true fit)

| #   | Title                                                | Employer                  | Loc      | Src    | Why (persona = 7-12 MATH / coach / curriculum)                           |
| --- | ---------------------------------------------------- | ------------------------- | -------- | ------ | ------------------------------------------------------------------------ |
| 1   | Middle School Math Teacher (South Scioto)            | Performance Academies     | Columbus | adzuna | **Exact core**: secondary MATH, Columbus charter, $54.3K > floor.        |
| 2   | Middle School Mathematics Teacher (South Scioto)     | Performance Academies     | Columbus | adzuna | Second math seat, same network, $51.5K. Direct-fit.                      |
| 3   | TOSA: Teacher Clarity Coach (Olde Orchard/Woodcrest) | Columbus City Schools     | Columbus | adzuna | **Instructional-coach track**, CCS, $77.9K — his dept-lead/PLC exp fits. |
| 4   | TOSA Instructional Coach — Yorktown MS               | Columbus City Schools     | Columbus | adzuna | Coach role, middle-school, CCS, $53K. Strong secondary-coach fit.        |
| 5   | 9th Grade Teacher — Performance HS West              | Performance Academies     | Columbus | adzuna | Secondary teaching, HS, $53.6K. Math-teachable, same network.            |
| 6   | Instructional Coach — ELA                            | Educational Solutions Co. | Columbus | adzuna | Coaching fit (subject is ELA, but coaching skill transfers), $79.8K.     |
| 7   | Social Studies Teacher, Middle School (26-27)        | United Schools Network    | Columbus | adzuna | Secondary, reputable Columbus charter net, $57.5K; off-subject.          |
| 8   | Business Technology Teacher (6-12)                   | Columbus City Schools     | Columbus | adzuna | Secondary CCS role, $66.4K; adjacent subject, math-adjacent tech.        |
| 9   | ESL Instructional Coach                              | Columbus City Schools     | Columbus | adzuna | Coach ladder, CCS, $76.8K; ESL specialty but coaching-transferable.      |
| 10  | Nonpublic Title I Instructional Support Coach        | Columbus City Schools     | Columbus | adzuna | Coach/interventionist, CCS, $50.7K; math-intervention aligned.           |

**Every top-10 pick came from Adzuna.** The `careers` source (OSU) and the seeded companies
produced **zero** genuine persona fits — OSU's board is university staff + a childcare lab school.

### False positives in the top 40 — count and cause

- **~9–11 false positives** in the top 40. The worst are ranked _highest_:
  - **#1–#3 by Score (all 87): OSU "Lead Teacher 2/3"** — these are infant/toddler **childcare
    lab-school** roles, not secondary math. `score_notes`: `title 100% | loc 67% | size +4`.
    The generic keyword `"teacher"` matched 100% and OSU-Columbus + board-size bonus pushed them
    to 87. The scorer has **no grade-band awareness** — it cannot distinguish "Lead Teacher"
    (daycare) from a secondary math teacher.
  - **OSU Assistant Teacher ×3 (61)** — same childcare bleed.
  - **OSU veterinary / livestock / dentistry / poultry "Program Coordinator/Instructor" (40-44)**
    — pure keyword bleed from the 1041-job Workday board; correctly hit `title-miss -18` and sank
    to the floor, but still occupy inbox slots.
  - **Out-of-state Adzuna mis-stamps**: Paris SSD (TN), Maury County (TN), Randolph County (NC/GA)
    — geographically wrong, only "local" because Adzuna copied the query location.
  - Elementary/PK/K-2 and SpEd/OT roles (many CCS) — real Columbus, but wrong grade band / role
    for a secondary math teacher (arguably soft-FPs; a real user would skip them).
- **Root causes:** (a) the broad `"teacher"` keyword with no negative for grade band; (b) OSU's
  giant Workday board injecting non-K12 noise that the on-device scorer can't down-rank on
  domain; (c) Adzuna location stamping. All three are exactly where the **BYO-AI re-rank earns
  its keep** — I demoted every OSU/childcare/out-of-state row and surfaced the true math/coach
  seats that the raw Score buried at 64-67.

**Local-scorer quality:** solid on _location_ (the hero), weak on _role/grade-band nuance_. The
0-100 Score is a keyword+skills+loc+salary composite; it does its advertised job but is fooled by
polysemous titles ("teacher"). This is a known and acceptable limitation given the app's whole
thesis is "Score for raw overlap, Fit (AI) for nuance."

---

## 6. Tracking to completion

Drove 5 top picks through the full lifecycle via the same `tracker.service` functions the GUI
buttons call (pinned to the project). **All persisted on fresh re-read.**

| app_id | Job                                  | Path                                                   | Verified                                                                        |
| ------ | ------------------------------------ | ------------------------------------------------------ | ------------------------------------------------------------------------------- |
| 1      | MS Math Teacher (Perf. Acad.)        | interested→applied→**interview** + phone_screen round  | ✔ status=interview, round#1 phone_screen w/ Principal Ramirez                   |
| 2      | MS Mathematics Teacher (Perf. Acad.) | applied→offer(+offer_amount $56,000)→note→**accepted** | ✔ status=accepted, offer_amount=$56,000, timeline applied→offer→[note]→accepted |
| 3      | TOSA Teacher Clarity Coach (CCS)     | applied→**interview** + onsite round                   | ✔ status=interview, round#1 onsite w/ Curriculum Director Owens                 |
| 4      | TOSA Instructional Coach (CCS)       | applied→**rejected** + note                            | ✔ status=rejected                                                               |
| 5      | 9th Grade Teacher (Perf. Acad.)      | applied→**ghosted** + note                             | ✔ status=ghosted                                                                |

- `date_applied` auto-stamped (2026-07-01) on the applied transition for all 5 (and a +7d
  follow-up armed — the centralized "entered-applied" side-effect).
- Interview rounds persisted with kind/schedule/interviewer.
- Final counts: interview 2, accepted 1, rejected 1, ghosted 1, all 5. Inbox 49→44 (tracked rows
  leave the inbox — correct).

**Lifecycle gaps:** none blocking. Every status the walkthrough asked for (applied, interview,
offer, accepted, rejected, ghosted) plus interview rounds and per-stage notes exist and work
through the service layer. Minor: there's a distinct `phone_screen` _status_ AND a `phone_screen`
round _kind_; a GUI user could conflate them. `offer_amount`/`offer_deadline`/`offer_notes` are
free-text (fine). All good.

---

## 7. Verdict — could David run his whole search here?

**Mostly yes, with one blocking caveat.**

**Where it beats LinkedIn/Indeed for this persona:**

- **Locality.** The hard-gate turned 1370 postings into 49 that are essentially all Columbus-area
  — LinkedIn/Indeed bury local K-12 seats under national/remote noise and sponsored posts. This
  is the single best thing the app did.
- **Aggregation + one triage surface.** Adzuna alone surfaced Performance Academies, United
  Schools Network, KIPP Columbus, and CCS TOSA coach roles in one inbox, scored and dedup'd.
- **Tracking.** The applied→interview→offer→accepted/rejected/ghosted lifecycle with rounds and
  notes is genuinely better than a spreadsheet, and better than Indeed's thin "applied" flag.
- **BYO-AI re-rank** cleanly fixes the one thing the on-device Score can't: demoting the
  daycare/vet/out-of-state false positives and floating the real math/coach seats.

**Where it loses:**

- **CareerOneStop is unkeyed** — the app's _own Guide_ says this is the #1 free source for
  teachers, and it silently self-skips. For a K-12 persona this is the biggest coverage hole.
- **Frontline/NEOGOV are unreachable** — the public-district portals David most wants to watch
  can't be added at all (no Frontline scraper; NEOGOV ToS-blocked). Indeed/LinkedIn _do_ surface
  district Frontline jobs.
- **Company layer added ~nothing** — of 16 seeded employers, only Adzuna's aggregation actually
  fed the top 10; the seeded charter/ed-tech boards were dead slugs or noise (OSU).

**Beats manual?** For the _aggregation + local filter + tracking_ loop, yes — it saved real
triage time and produced a clean, honest local shortlist. But it does **not** yet replace a
teacher checking Frontline + CareerOneStop directly, so it's a strong complement, not a full
replacement, until those two gaps close.

**Single highest-leverage improvement for THIS persona:** **ship a keyed (or shared-proxy)
CareerOneStop path + a Frontline-aware "add district" flow.** CareerOneStop is the NLx/state-job-
bank firehose where K-12 district postings actually live; wiring it in (even a guided free-key
step surfaced _in the wizard for education fields_) plus any way to watch Frontline district
boards would move this from "great for charters/ed-tech" to "runs a public-school-teacher's
entire search."

---

## Bugs / observations (no source edits made)

- **No crashes / tracebacks.** Run exited 0; all API calls (create_project, seeding pipeline,
  lifecycle) succeeded first try.
- **Observation (not a bug):** `daily_run.py --project X` calls `workspace.set_active(X)`
  (line 218), so running the persona's update flipped the on-disk `projects.json` _active_ pointer
  from `gu-nurse-boise` to `gu-teacher-columbus`. Documented behavior, but a general user running
  one project's update silently changes which project the GUI opens to next time.
- **Data-quality (upstream, not the app's fault but worth surfacing to users):** Adzuna stamps the
  query location onto every posting; 3/49 inbox rows are out-of-state employers shown as
  "Columbus, Franklin County." A "verify location in description" pass would catch these.
- **Scorer limitation (known/acceptable):** generic `"teacher"` keyword → title-100% bleed floats
  daycare "Lead Teacher" roles to the top; no grade-band awareness. This is precisely what the
  BYO-AI channel exists to fix, and it did.
- **Stale companies.json note:** I added 16 education companies; per instructions I did NOT
  restore companies.json (the janitor handles that).

## Reliance snapshot (disclose)

- `.env` has **Adzuna + JSearch + USAJobs** keys (JSearch excluded from daily net by design).
  **CareerOneStop unkeyed** (gap). **Jooble/Careerjet/Brave/SerpApi unkeyed.**
- **Every non-OSU local win came from Adzuna.** Careers/seeded-companies contributed 13 rows, all
  OSU, all non-persona-fit. USAJobs contributed 9 to the funnel, 0 to the inbox. Keyless remote
  feeds (RemoteOK/WWR/Remotive/Jobicy) contributed **0** to the gated inbox (on-site gate cut
  them). For an on-site K-12 teacher, **Adzuna is doing ~100% of the useful work**, which makes
  the missing CareerOneStop key the whole ballgame.
