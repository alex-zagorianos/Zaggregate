# General-User Test — Nicole Adams (Data Analytics career-changer, Phoenix AZ)

**Date:** 2026-07-02
**Persona:** Nicole Adams — former retail store manager (9 yrs) finishing a data-analytics
bootcamp. SQL / Excel / Tableau portfolio, **no professional analyst experience yet.**
**Targets:** data analyst · junior data analyst · business intelligence analyst · reporting analyst.
**Location:** Phoenix, AZ (30 mi), open to remote. **Salary floor:** $55,000. **Level:** entry.
**Project slug:** `gu-data-changer-phoenix` (created NOT-active; blank-slate general user — starter
registry only, no prior projects).
**Tester note:** I acted as both the persona AND her $20/mo BYO-AI assistant. Ran headless, never
launched the GUI. Keys present in `.env`: Adzuna + JSearch + USAJobs. **CareerOneStop NOT keyed
(known gap).** No auto-AI ranking enabled — I was the clipboard-bridge BYO-AI.

---

## 1. New-user lens

**README quickstart** is clear and honest: `pip install -r requirements.txt` → `py -3.12 gui.py`,
first-run wizard, then "Update my Inbox now." It sets the right expectation ("bring your own AI",
local-first, never auto-applies) and correctly warns the free feeds "lean toward remote tech jobs" —
exactly what a Phoenix analyst needs to hear before trusting the out-of-box net.

**Setup wizard (`ui/setup_wizard.py`) — 5 steps:** Welcome → Roles (+ optional Field/industry +
Career-level combobox + free-text "Anything else?") → Where (location, remote checkbox, salary) →
Resume (paste or load file) → "Keep jobs coming" (daily updates + Build My List). Everything a real
user configures is captured, in a sensible order.

**Wizard clarity: 8/10.** Strengths: plain language; the roles step explicitly coaches "use broad
field terms, set seniority with Career level, not in the search terms" (great advice for this
persona); hourly/annual salary auto-parse; a pasted plain-text résumé is auto-structured so it can
never crash later scoring (verified — my heading-less paste came back with `## SUMMARY`, `##
TECHNICAL SKILLS`, `## WORK EXPERIENCE`, `## EDUCATION` promoted). Deductions:

- The **industry** field is optional free text with no picker/validation. Nicole types "data
  analytics" — which later collides with an internal normalization bug (see §3/Bugs). A dropdown of
  known fields would prevent the space-vs-underscore trap entirely.
- Résumé auto-structuring left the **name + contact lines bare above the first heading** (Path A
  promotes recognized headings but does not wrap the leading contact block under `## CONTACT`), and
  "DATA ANALYTICS BOOTCAMP" (not in the alias table) stayed as body text. Nothing is lost, but the
  parser won't cleanly associate contact info. Cosmetic.

**In-app Guide (`ui/help.py`)** is genuinely good for a non-technical user and is the source of the
seeding flow I executed: _"Ask your AI: 'List the 25 largest employers of [your work] in [your
city], with a careers-page link, one per line as Name | link.' Paste into + Add Companies. Anything
the AI got wrong simply fails verification."_ It also foregrounds the two keys that matter most
(Adzuna, CareerOneStop) and is upfront that free feeds skew remote/tech.

---

## 2. Project setup

Created programmatically via `workspace.create_project(name="GU - Nicole Adams",
slug="gu-data-changer-phoenix", make_active=False)`, authoring the exact artifacts the wizard's
`build_preferences()` / `_search_config()` / `apply()` would write:

- **config.json** — keywords `[data analyst, junior data analyst, business intelligence analyst,
reporting analyst]`, `location "Phoenix, AZ"`, `salary_min 55000`, `industry "data analytics"`,
  `seniority_target "entry"`, `allow_intern true`, `years_cap 3`, default 10-source block.
- **preferences.json** (hard filters) — `salary_min 55000`, `locations ["Phoenix, AZ"]`,
  `remote_ok true`, `target_roles [...]`, empty dealbreakers/seniority_exclude.
- **preferences.md** — natural-language profile (career-change story, must-avoid senior/DS/DE roles,
  Phoenix + remote).
- **experience.md** — full bootcamp/retail résumé, auto-structured.

`create_project` did NOT attach an `onet_soc_code` — `resolve_soc("data analytics")` returns None;
the field resolves through the free-text `_RULES` overlay instead (jobicy `data-science`, Muse `Data
and Analytics`, synonyms `data analyst / business intelligence`). Fine for this persona.

---

## 3. Seeding — the Guide "ask your own AI" flow

As Nicole's AI, I produced 15 real large Phoenix-area analyst employers (banks, insurers, health
systems, utilities, universities, Phoenix-HQ tech) as `Name | URL` lines and pushed them through the
**exact `+ Add Companies` pipeline**: `ats_detect.parse_line` → `ats_detect.probe_count` →
`company_registry.save_companies`.

| Result                                           | Count  | Companies                                                                                                          |
| ------------------------------------------------ | ------ | ------------------------------------------------------------------------------------------------------------------ |
| **Parsed**                                       | 15     | all 15 lines parsed to a `CompanyEntry`                                                                            |
| **Probed LIVE**                                  | **2**  | Axon (522 jobs), Carvana (2103 jobs) — both Phoenix-HQ, both hire analysts                                         |
| **Direct (uncountable, saved as manual scrape)** | 4      | ASU, Grand Canyon Univ, OpenDoor, Choice Hotels                                                                    |
| **Unreachable**                                  | 9      | Western Alliance, Progressive Leasing, Banner Health, Phoenix Children's, HonorHealth, APS, SRP, Nextiva, Trainual |
| **`save_companies` added**                       | **15** | probe is advisory only — the dialog adds all parsed entries                                                        |

**Friction / findings:**

- **The 9 "unreachable" are the biggest local employers Nicole most wants** (Banner Health, Phoenix
  Children's, HonorHealth, APS, SRP). My AI-guessed Workday tenant slugs
  (`bannerhealth:1:bannerhealth`, `pinnaclewest:1:APSCareers`, …) were wrong or CSRF-protected, and
  the two Lever slugs (Nextiva, Trainual) 404'd. This is the Guide's promised "wrong ones fail
  verification" behavior working — but it means a career-changer gets **no path to the correct slug**
  short of hand-inspecting each ATS. The AI can't reliably know a Workday tenant string from the
  public careers URL.
- **The genuine wins (Axon, Carvana) are the _only_ two I could seed reliably** — because they use
  Greenhouse, whose slug is guessable from the board URL.
- **BUG (silent):** I tagged all 15 with the persona industry `"data analytics"` (the space-form the
  wizard stores). `get_registry(industry="data analytics")` normalizes the _key_ to `data_analytics`
  but matches it against the _un-normalized_ tag `data analytics` → containment fails both ways →
  **all 15 seeded companies are silently excluded from Nicole's own careers searches and daily run.**
  `industry_company_count("data analytics")` stayed at 8 (the health-informatics `analytics`-tagged
  companies) even after adding 15. Confirmed:
  `_industry_tag_match("data_analytics","data analytics") -> False`. See Bugs. (An existing spawned
  task already covers this — not re-filed.)

**Estimated realistic human setup time:** ~35–45 min (2 free-key signups the Guide prescribes +
writing the AI employer prompt + pasting/validating + fixing the two Lever slugs). I had Adzuna/USAJobs
keys pre-loaded ("user did the signups").

---

## 4. Run — `py -3.12 daily_run.py --project gu-data-changer-phoenix`

**Wall clock: ~43 s** (00:31:41 → 00:32:24). Single run, no concurrency. Exit 0.

**Funnel:** `649 raw → 532 dedup → 287 after hard-gate → 77 qualified (≥40) → 77 inboxed`
(page-2 recall added +196 raw; hard-gate dropped **245 on location**, correctly filtering non-Phoenix
non-remote jobs given `locations=["Phoenix, AZ"]`, `remote_ok=true`).

**Per-source raw (full pass):** Adzuna 380 · Jobicy 69 · USAJobs 45 · TheMuse 40 · WeWorkRemotely 39 ·
HN 23 · Himalayas 9 · Remotive 4 · WorkingNomads 4 · Careers 36 · everything else 0.

**Errors / warnings / quota (all expected, all self-skipped cleanly — no crashes, no 429s):**

- `NOTE: only 8 registry companies match industry 'data analytics' — the 'careers' path will add
few/no jobs.` (preflight — the seeding bug's downstream effect).
- CareerOneStop skipped — **no key (known gap; the single biggest missing local unlock for this
  persona).**
- Jooble / Careerjet / Brave-discovery skipped — no keys (self-skip, byte-identical to keyless user).
- `higheredjobs` inert (no education categories map for data-analytics), `rnjobsite` inert (not
  nursing) — correct auto-gating.
- `careers` only scraped health-informatics `analytics`-tagged cos (Bon Secours, Inovalon, Arcadia) —
  1 match reached the inbox; **none in Phoenix.**
- Reach badge: **cannot certify** — no SerpApi key → no cross-source overlap; sample completeness
  ~28% (Good-Turing).

---

## 5. Inbox analysis (tracker.db, `source` column)

**Total: 77.**

**Source mix:** adzuna 66 · workingnomads 4 · weworkremotely 2 · usajobs 2 · jobicy 1 · hn 1 ·
careers 1. **Adzuna = 86% of the inbox and 100% of the local (non-remote) wins.** This precisely
matches the app's own thesis: the keyless free feeds are remote/tech-skewed; Adzuna is the
local-jobs workhorse for any field. Without the Adzuna key this persona's inbox would be ~11 rows,
almost all remote.

**Score distribution:** 80–100 = 3 · 70–79 = 24 · 60–69 = 27 · 50–59 = 4 · 40–49 = 19 · (<40 = 0).
min 40 / max 82 / mean 62.

**Locality (of 77):** in/near Phoenix **67** · remote **10** · wrong-area **0** · unknown-loc **0**.
The location hard-gate is excellent — zero out-of-area leakage.

### BYO-AI Top 10 (re-ranked by me for an entry-level career-changer)

| #   | Title                                               | Company                           | Location             | Source        | Why (fit for Nicole)                                                                                                                     |
| --- | --------------------------------------------------- | --------------------------------- | -------------------- | ------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Business Intelligence Analyst - Hybrid              | Blue Cross Blue Shield of Arizona | Phoenix, AZ (hybrid) | adzuna        | Plain BI analyst (not senior), big stable local employer that trains; $61.5k > floor. Best entry fit.                                    |
| 2   | Contact Center Data Analyst                         | U-Haul                            | Phoenix, AZ (onsite) | adzuna        | Phoenix HQ, plain "Data Analyst", operational/contact-center metrics — maps to her retail reporting.                                     |
| 3   | Data Coordination Analyst                           | Maximus                           | Phoenix, AZ          | adzuna        | "Build/maintain dashboards, metrics, reports"; coordination (not senior); trains from ops data.                                          |
| 4   | Enterprise Data Analyst                             | Leslie's Pool Supplies            | Phoenix, AZ          | adzuna        | Phoenix-HQ retailer — her retail domain is a real edge; plain Data Analyst title.                                                        |
| 5   | Data Analyst                                        | Ryde Technologies                 | Phoenix, AZ          | adzuna        | Plain "Data Analyst", SQL/data-mapping, no seniority marker.                                                                             |
| 6   | Computer Programmer/Analyst (Data Mgmt & Reporting) | Arizona Dept of Public Safety     | Phoenix, AZ          | adzuna        | Posting explicitly says "under the guidance of more experienced developers" — a true trainee role; state job, $67k.                      |
| 7   | Revenue & Accounting Data Analyst                   | Robert Half (client)              | Phoenix, AZ          | adzuna        | "Connect accounting fundamentals with reporting" — her P&L/retail-finance background; staffing = faster entry. Caveat: interim contract. |
| 8   | Data Analyst                                        | Serco                             | Phoenix, AZ          | adzuna        | Plain "Data Analyst". Caveat: defense/logistics, may need eligibility.                                                                   |
| 9   | Online Data Analyst (US, EN/ES)                     | TELUS Digital                     | Remote (US)          | workingnomads | Genuinely entry-level freelance/remote, very low barrier — realistic first paycheck in-field while she keeps applying.                   |
| 10  | Manufacturing Data Analyst                          | Corning                           | Phoenix, AZ          | adzuna        | $70.8k Phoenix, plain "Data Analyst" (not senior), reputable. Caveat: manufacturing-data domain.                                         |

### False positives in the top 40 & why they scored high

Roughly **14–16 of the top 40 are poor fits for a no-experience career-changer**, and they cluster at
the very top. The `score_notes` show why: **a title containing "analyst"/"data" gets `title 100%`
regardless of seniority**, any disclosed salary above her $55k floor gets `salary 100%`, Phoenix gets
`loc 67%`, plus a freshness component. The entry-level config (`seniority_target: entry`,
`years_cap: 3`) feeds the _AI_ rubric but barely touches the _local keyword scorer_ — so seniors
dominate the top:

- **Seniority mismatch (want 5–8+ yrs):** #1 Senior Data Analyst (System One), #3/#11 Sr Analyst
  (Maximus), #4 Senior Data Solutions Analyst (Highmark), #5 Senior Preconstruction Data Analyst
  (Ryan), #6 Senior Analyst Data Governance (Amex), #14 Senior Financial Data Analyst, #20 Senior Data
  Analyst (Stride), #40 **Principal** BI Analyst (Cytel).
- **Wrong role labeled "analyst" (Data Scientist / ML / OR):** #15 Operations Research Analyst / Data
  Scientist (GovCIO), #23/#38/#39 Mayo "Data Science Analyst" (AI/ML/deep-learning).
- **Contract/staffing or clearance-adjacent:** #1/#8/#9 (System One, Pyramid), #19 Data Analyst
  (Network Security, Noblis), #35 Metrics Analyst (Navy). #9 also lists "$60–70/hr" and heavy
  regulatory banking depth.

None of these are _location_ false positives (locality was clean); they are **seniority/level and
role-domain** false positives. The single highest-leverage scoring fix would be to let the
entry-level setting actually down-rank Senior/Sr/Lead/Principal _titles_ in the local scorer, not
just the AI rubric.

---

## 6. Tracking to completion

Took 5 top picks (BCBS, U-Haul, Maximus, Leslie's, Ryde) through the lifecycle using the **same
`tracker.service` / `tracker.db` functions the GUI buttons call**, project pinned to
`gu-data-changer-phoenix`. Re-read from a fresh connection — **every status persisted:**

| App | Company                           | Final status  | Extras verified                                                                                                           |
| --- | --------------------------------- | ------------- | ------------------------------------------------------------------------------------------------------------------------- |
| 1   | Blue Cross Blue Shield of Arizona | **accepted**  | offer_amount `$63,000`, deadline `2026-07-25`, offer_notes; **2 interview rounds** (phone r#1, onsite r#2 outcome=passed) |
| 2   | U-Haul                            | **interview** | 1 interview round (phone r#1)                                                                                             |
| 3   | Maximus                           | **rejected**  | status note persisted                                                                                                     |
| 4   | Leslie's Pool Supplies            | **ghosted**   | status note persisted                                                                                                     |
| 5   | Ryde Technologies                 | **applied**   | —                                                                                                                         |

Full `status_history` timeline recorded every transition (interested→applied→interview→offer→accepted,
etc.). Inbox 77 → 72 (5 promoted out). `service.counts()` = applied 1 / interview 1 / accepted 1 /
rejected 1 / ghosted 1.

**Lifecycle gaps / notes:**

- All required statuses exist and work (S29's `accepted` + `ghosted` present in `STATUSES`; interview
  rounds auto-increment `round_no`; offer fields `offer_amount/deadline/notes` persist).
- **Minor:** `add_status_note` writes the note as a _same-status → same-status_ row in
  `status_history` (e.g. "accepted → accepted"), which reads oddly in a timeline view. Functionally
  correct; cosmetically it looks like a status change that didn't happen.
- Nothing blocked a real user: every step here maps to a GUI button (Track ▸ Interested, Mark Applied,
  status dropdown, Add interview round, offer fields, Rejected/Ghosted).

---

## 7. Verdict

**Could Nicole run her whole search on this app? Largely yes — with one keyless caveat.** In 43
seconds the app produced a 77-job, zero-wrong-location Phoenix analyst inbox with real target
employers (BCBS AZ, U-Haul, Mayo, Leslie's, Amex, AZ state agencies) and a working
application tracker through offer/accepted. That already beats manually re-running LinkedIn/Indeed
searches and copy-pasting into a spreadsheet.

**Where it beats LinkedIn/Indeed:** one local scored inbox across many sources; a clean location gate
(no Denver/Dallas noise); a real tracker with interview rounds + offer terms + ghosted status; fully
local/private; free. **Where it loses:** LinkedIn/Indeed surface the _biggest local employers_
(Banner, Dignity, city/county, ASU) instantly, and here those never arrived — CareerOneStop is
unkeyed, and the AI-assisted `+ Add Companies` couldn't resolve their Workday/Lever slugs. Nicole
would still open LinkedIn to catch Banner Health and the like.

**Single biggest improvement for THIS persona:** **ship a keyed (or trivially self-keyed)
CareerOneStop path** — it is the free US-DOL feed that would pull the exact local
hospital/utility/university/state analyst jobs Nicole is missing, and it's the one gap that forces her
back to LinkedIn. Runner-up: make the **entry-level setting actually down-rank Senior/Lead/Principal
titles in the local scorer** so a career-changer's top 10 isn't half senior roles. Third: **fix the
industry-tag space/underscore bug** so a general user's own added companies aren't silently dropped.

**Would she stay?** Yes as a daily triage inbox + tracker, alongside LinkedIn for the marquee local
employers — until CareerOneStop closes that gap.

---

## Bugs (with evidence)

1. **Industry-tag space-vs-underscore mismatch silently drops user-added companies.**
   `scrape/company_registry.py::get_registry` normalizes the industry _key_
   (`industry.lower().replace(" ", "_")` → `data_analytics`) but `_industry_tag_match` compares it to
   the _un-normalized_ company tag `"data analytics"` (as the wizard stores industry and as
   `AddCompaniesDialog` passes it to `save_companies`). Neither string contains the other →
   the company is excluded from the user's own careers searches / daily run.
   Repro: `py -3.12 -c "from scrape.company_registry import _industry_tag_match;
print(_industry_tag_match('data_analytics','data analytics'))"` → `False`.
   Effect here: 15 seeded companies added, `industry_company_count("data analytics")` stayed 8.
   _(No traceback — silent data-exclusion. An existing spawned task already tracks this; not re-filed.)_

2. **(Design gap, not a crash) Entry-level config doesn't down-rank senior titles in the local
   scorer.** `seniority_target: entry` + `years_cap: 3` are written to config but the local
   `score_notes` give "Senior/Sr/Principal Data Analyst" the same `title 100%` as a plain "Data
   Analyst", so senior roles top the inbox for a no-experience career-changer (8+ of top-40).

3. **(Minor) Résumé auto-structure leaves the contact block un-sectioned.** A heading-less paste
   promotes recognized ALL-CAPS headings (Path A) but does not wrap the leading name/email/phone lines
   under `## CONTACT`; "DATA ANALYTICS BOOTCAMP" (not in the alias table) stays as body text. No data
   lost; parser won't cleanly attach contact info.

4. **(Minor) `add_status_note` renders as a same-status self-transition** in `status_history`
   ("accepted → accepted"), which looks like a no-op status change in a timeline view.

No exceptions/tracebacks occurred during setup, seeding, the daily run, inbox analysis, or the full
tracking lifecycle. All missing-key events were clean self-skips, not failures.
