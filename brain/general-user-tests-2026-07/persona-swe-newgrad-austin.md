# General-User Test — Jordan Rivera (SWE new grad, Austin, TX)

**Date:** 2026-07-01 · **App version:** 1.0.0 · **Tester:** blank-slate general user, playing the persona and its own $20/mo BYO-AI assistant.
**Project slug:** `gu-swe-newgrad-austin` (kept). Person tag: "Jordan Rivera".

Persona: BS Computer Science, May 2026 grad. One summer SWE internship (React
dashboards), personal Python/FastAPI projects. Targets: software engineer /
junior SWE / backend / frontend dev. Austin, TX (30 mi) + open to US remote.
$70k floor. Entry level.

**Keys context (as briefed):** `.env` has Adzuna + JSearch + USAJobs keys (the
free-key signups the Guide prescribes). CareerOneStop is **not** keyed — the
known gap. Jooble + Careerjet + Brave (discovery) + SerpApi (reach) are also
unkeyed. No auto-AI ranking was enabled; I acted as the clipboard-bridge BYO-AI.

---

## 1. New-user lens — what a fresh user actually gets

Read: `README.md`, the in-app Guide (`ui/help.py` GUIDE list), and the first-run
Setup wizard (`ui/setup_wizard.py`).

**Wizard clarity: 8/10.** The wizard is genuinely good for a non-technical user
and better than most job-tool onboarding. Path (5 steps, only 4 collect data):

1. Welcome (intro, no fields)
2. **Roles** — comma list ("what jobs are you looking for?"), plus optional
   **Field/industry** and **Career level** (Entry/Mid/Senior/Manager-Exec) combobox,
   plus a free-text **"Anything else the AI should know?"** box. Good tips: use
   broad field terms, set seniority via the level box not the title.
3. **Where** — location, "Remote jobs are fine too" checkbox, optional minimum
   salary (accepts `90000`, `$90k`, or `18/hr` and annualizes hourly).
4. **Resume** — paste or load from file (optional; auto-structured into headings
   so a bare paste can't crash scoring later — a nice P0 fix).
5. **Keep jobs coming** — "update inbox every morning" + "build my employer list
   now" checkboxes (both default ON).

What's clear: plain English, sensible examples, salary parsing is forgiving,
resume auto-structuring is thoughtful, and the industry→field routing is
explained in the Guide. The Guide's "the 10 minutes that matters most" section
correctly warns the free feeds skew remote-tech and pushes Adzuna + CareerOneStop

- the ask-your-AI employer-list flow — exactly the workflow I then exercised.

Why not higher: (a) A SWE new grad reading the field examples
("health informatics · nursing · finance · controls engineering") gets **no
guidance that "software"/"software engineering" is a valid field** — I had to
know to use `software_engineering` to keep the tech boards on. (b) The wizard
asks for a **city string** but never explains the 30-mi radius model or that the
location becomes a _hard gate_ — a user who types "Austin" vs "Austin, TX" gets
different metro-variant expansion. (c) Nothing tells a new grad that a broad
`senior`/`lead` exclusion list will silently cut ~half their raw results (see
funnel). None of these block a user; they'd just leave money on the table.

---

## 2. Project setup

Created programmatically exactly as the wizard's pure transforms produce
(`build_preferences` + `_search_config` + `_level_to_config`), then authored the
faithful persona files. `workspace.create_project(name="GU - Jordan Rivera",
slug="gu-swe-newgrad-austin", config=<cfg>, make_active=False, person="Jordan Rivera")`.

- **config.json** — keywords (4 titles), `location: "Austin, TX"`, `salary_min:
70000`, `industry: "software_engineering"`, `seniority_target: entry`,
  `allow_intern: true`, `years_cap: 3`, `exclude_titles`/`exclude_keywords`
  (senior words + clearance), tech sources ON.
- **preferences.json** (hard filters) — `salary_min 70000`, `locations
["Austin, TX"]`, `remote_ok true`, `dealbreakers` (clearance/ts-sci),
  `seniority_exclude` (senior/staff/principal/lead/director/vp/manager/architect),
  `target_roles`.
- **preferences.md** — natural-language profile with a rich "About me" paragraph
  (backend-leaning full-stack new grad, wants mentorship + code review, avoid
  over-leveled/clearance/5+-yr roles).
- **experience.md** — full structured resume (UT Austin CS, Brightgrid internship,
  3 personal projects, Python/FastAPI + React/TS skills). No real PII (fabricated
  persona with example.com email + 555 phone).

`create_project` scaffolds `config.json`, a stub `experience.md`, and `output/`;
`preferences.{json,md}` are NOT scaffolded — the wizard's `apply()` writes them,
so I wrote them via `workspace.preferences_paths(slug)`. `onet_soc` attach ran
and correctly left the config clean (software resolves to eng-like → None).

---

## 3. Seeding — the ask-your-own-AI flow

Acted as Jordan's AI assistant: produced 15 "Name | careers-URL" lines for major
Austin-area tech employers, then drove the **exact** `+ Add Companies` pipeline:
`scrape.ats_detect.parse_line` → `probe_count` → `scrape.company_registry.save_companies`
(the same functions `gui.py:AddCompaniesDialog._detect/_validate_worker/_add` call),
tagging all with `software_engineering`.

| Metric                                           | Count  |
| ------------------------------------------------ | ------ |
| Attempted (paste lines)                          | 15     |
| Parsed to CompanyEntry (`parse_line`)            | 15     |
| Probed **live** (`probe_count` returned a count) | 8      |
| Probed **unreachable** (bad slug/tenant guess)   | 5      |
| `direct` (uncountable — 2 were deliberate junk)  | 2      |
| **Added to companies.json (`save_companies`)**   | **15** |
| Rejected/skipped by save                         | 0      |

Live at probe: Cloudflare (226), Palantir (276), Notion (151), Ramp (126),
Homeward (5), Indeed (0), Netflix (0), Square/SmartRecruiters (0). Unreachable:
CrowdStrike, Bumble, SailPoint (my Greenhouse slug guesses were wrong), Gusto
(Lever slug wrong), Tesla (my Workday `tenant:5:site` guess wrong). Junk lines
(Oracle Austin fake host, "totally junk line no url here") parsed as `direct` and
later failed with `NameResolutionError` during the run — **the flow working as
designed**: junk can't sneak in, it just produces zero jobs + a soft error line.

**Friction / finding (important):** `save_companies` adds **all 15 parsed
entries regardless of probe result** — the probe/Validate step is _advisory in
the GUI_, not a gate. A real user who pastes an AI list, glances at "unreachable"
statuses, and clicks "Add" still writes dead boards into `companies.json`. They're
harmless (skipped/soft-error at scrape time) but they clutter the registry and
cost a wasted request each run. A gentle "5 of these look unreachable — add
anyway?" confirmation would help. Also: an AI assistant is genuinely bad at
guessing ATS slugs (I got 5/13 board slugs wrong on real, well-known companies) —
the parse succeeds but the slug is a coin-flip. This is the single most
frustrating part of the "ask your AI" flow.

---

## 4. Run

`py -3.12 daily_run.py --project gu-swe-newgrad-austin` (background, one at a time).

- **Wall clock:** ~2m9s (22:53:12 → 22:55:21). ~2 min of that was two ~60s
  Adzuna rate-limit back-offs ("waiting 59s for rate limit…" ×2).
- **Exit 0**, `last_run.json.errors: []`.

### Funnel

| Stage                      | Count                                                               |
| -------------------------- | ------------------------------------------------------------------- |
| Raw (all sources, 2 pages) | 2230                                                                |
| After dedup                | 1900                                                                |
| Preferences **hard-gate**  | 1900 → **198** (dropped: salary 1, **title 984**, **location 717**) |
| Found (post-gate)          | 198                                                                 |
| ≥ min_score (40)           | 143                                                                 |
| **New → inbox**            | **141**                                                             |

Raw per-source (from the engine tally): Careers 1451, Adzuna 366, HN 146, Jobicy
89, WeWorkRemotely 70, The Muse 44, USAJobs 32, Himalayas 17, WorkingNomads 8,
Remotive 6, RemoteOK 1. **Zero** from Careerjet, HigherEdJobs, Jooble, RNJobSite.

### Errors / warnings / quota events

- `careeronestop` **skipped — credentials missing** (the known unkeyed gap; the
  single biggest miss for local coverage, per the Guide's own advice).
- `jooble` + `careerjet` **skipped — free key/affid unset** (both ship in
  DAILY_SOURCES but do nothing without a free signup). 4 warning lines each.
- `higheredjobs` + `rnjobsite` **inert for software_engineering** (correct — they
  self-disable off-field).
- Brave company discovery **skipped — BRAVE_SEARCH_API_KEY unset**.
- SerpApi reach probe still ran via capture-recapture on the 11 keyed families:
  **"seeing ~3% of the reachable universe … ~40,137 of ~41,430 estimated postings
  still unseen (2230 raw → 1293 distinct)."** Sobering but honest.
- Two Adzuna **rate-limit back-offs** (~60s each). No hard HTTP 429 surfaced; no
  quota-exhaustion error. My two junk seed URLs logged soft `[direct] … fetch
error -- NameResolutionError` lines (non-fatal).
- One `JobicyClient` cache tmp-rename note did **not** recur this run (the S30
  Windows `:`-filename fix appears to have held — jobicy returned 89 raw).

---

## 5. Inbox analysis (141 rows)

**Source mix (inboxed rows):** Adzuna 67 · Careers 63 · HN 9 · WeWorkRemotely 2.
(Adzuna + the careers registry carry the whole inbox; the remote-tech feeds
contribute almost nothing after the location/seniority gate.)

**Score distribution:** min 44, max 100, mean 69.2 — 40-54: 4 · 55-69: 75 ·
70-84: 51 · 85-100: 11.

**Locality (30-mi Austin model):** **77 Austin-area · 64 remote · 0
wrong-location · 0 Texas-not-Austin · 0 unknown.** The location hard-gate is
tight and clean — nothing leaked in from Ohio/California-onsite/etc. Every
non-Austin row is a legitimately remote posting (the persona is open to remote).
This is the app at its best: no geo garbage.

### BYO-AI re-rank — TOP 10 (judged against the persona)

Judged the top ~40 by local score as Jordan's AI would: prioritize Austin-local
or clean US-remote, entry/junior-appropriate, backend/frontend/full-stack, real
mentorship signals; demote over-leveled, non-US-remote, QA, and intern rows.

| #   | Title                                         | Company             | Location              | Source         | Why                                                                                            |
| --- | --------------------------------------------- | ------------------- | --------------------- | -------------- | ---------------------------------------------------------------------------------------------- |
| 1   | Software Engineer, Data (L1)                  | acrisureinnovation  | Austin, TX            | careers        | Austin, explicitly **L1/entry**, Python/data — near-perfect fit.                               |
| 2   | Software Engineer                             | uShip               | Austin, Travis County | adzuna         | Austin, generic IC SWE, **$120k disclosed** (>>floor), logistics product.                      |
| 3   | Software Engineer – Simulation Backend        | Avride              | Austin, TX            | careers        | Austin, backend, Python/C++ AV sim — strong backend match.                                     |
| 4   | Software Engineer                             | allencontrolsystems | Austin, TX            | careers        | Austin, IC SWE, small company (mentorship-friendly).                                           |
| 5   | Frontend Software Engineer                    | KoBold Metals       | Remote (US)           | careers        | Clean US-remote, React/frontend — matches internship strength.                                 |
| 6   | Frontend Web Developer React/TypeScript       | Zensors             | California (Remote)   | weworkremotely | US-remote, **React/TS exact-match** to the internship stack.                                   |
| 7   | Software Engineer – Logs Infrastructure       | Avride              | Austin, TX            | careers        | Austin, backend infra — good stretch-but-reachable IC role.                                    |
| 8   | Software Engineer II, Backend (Capital Orch.) | Affirm              | Remote US             | careers        | US-remote backend at a strong eng org; **SE II** is a slight stretch but fintech backend fits. |
| 9   | Backend Software Engineer                     | Enveritas (YC S18)  | Remote (Global)       | hn             | US-eligible remote, Python backend, non-profit — mentorship-y; verify work-auth.               |
| 10  | Software Engineers                            | MixRank (YC S11)    | 100% Remote           | hn             | Remote generalist SWE at a small YC co (mentorship); verify US-remote OK.                      |

(I deliberately dropped the #1-by-score **6sense "Software Engineer III"** — high
score but over-leveled for a new grad.)

### False positives in the top 40 — count & why

Roughly **14–16 of the top 40** are poor fits for THIS persona:

- **Over-leveled (6):** 6sense "Software Engineer III" (**scored 100**),
  addepar "Sr. Backend", airtable "Compute (8+ YOE)", CDK "Sr. Software Engineer",
  Reliable Robotics "Sr. Simulation" + "Sr. Flight". **Why they scored high:** the
  local scorer gave every one `title 100%` because "software engineer" is in the
  string; the `exclude_titles`/`seniority_exclude` list only word-boundary-matches
  "senior" — so **"Sr." (the abbreviation) sails straight through** the gate and
  the downrank. This is a real scorer bug for new-grad users (see Bugs).
- **Non-US-only remote (~8):** MixRank "Global", Homeward "Latin America",
  addepar "Remote, UK", affinipay ×2 "Czech Republic", Affirm several "Remote
  Canada", Serve "Montreal", Enveritas "Global". **Why:** the scorer gives any row
  containing "remote" full `loc 100%` credit (remote_ok=true) with no
  US-work-authorization awareness — a US-only new grad can't take a Canada/Czech/UK
  remote role, but the app treats all "remote" as equal.
- **Wrong role-type / not-full-time (2–3):** "Software Tester" (QA, not SWE),
  "Summer Software Engineering Intern" (not full-time), and Baseten "Internal
  Platform" (fine role, but its "intern"-substring nearly tripped my own filter —
  a reminder the local score can't tell an intern posting from an internal one).

**Local-scorer quality verdict:** the deterministic score is a _decent first cut_
but has two systematic new-grad blind spots — (1) seniority abbreviations ("Sr.",
Roman numerals like "III", "8+ YOE") aren't downranked, and (2) "remote" is
treated as universally acceptable regardless of country/work-auth. Both are
exactly what the BYO-AI re-rank is meant to fix, and here it clearly earned its
keep — but a new grad who trusts the raw Score would apply to a Sr. role and a
Czech-Republic-only remote job.

---

## 6. Tracking to completion

Drove 5 top jobs through the lifecycle via the same `tracker.service` verbs the
GUI buttons call (`track_job`, `set_status`/`update_job`, `add_interview_round`,
`add_status_note`), pinned to the persona DB. Re-read with a **fresh SQL
connection** to confirm persistence (not in-process caching).

- All 5 promoted inbox → application (interested → **applied**, `date_applied`
  auto-stamped 2026-07-01; confirmed `db.update_job` auto-sets date + a +7-day
  follow-up on any path into 'applied').
- **2 → interview** (Avride, uShip), each with 1 `phone_screen` round.
- **1 → offer → accepted** (acrisureinnovation): interview → 2 rounds
  (technical, onsite w/ outcome "passed") → offer (`$95,000`, 14-day deadline,
  notes) → **accepted** + a status note. 5 timeline entries.
- **1 → rejected** (KoBold) + note. **1 → ghosted** (Affirm) + note.
- Verified via fresh connection: applications table shows accepted/interview×2/
  rejected/ghosted; `interview_rounds` has all 4 rounds with correct `round_no`;
  `status_history` has 15 transition rows; inbox dropped 141 → 136.
- `counts()` = interview 2, accepted 1, rejected 1, ghosted 1, all 5. ✔

**Lifecycle gaps / friction (minor):**

- Two overlapping ways to model a phone screen: a `phone_screen` **status** AND a
  round `kind="phone_screen"`. A user could reasonably do either; the GUI wiring
  isn't obvious about which is canonical.
- `add_interview_round` takes free-text `kind`/`outcome` with no enum validation —
  fine for power use, but a GUI without a dropdown could produce inconsistent
  values. (Didn't verify the GUI dialog's field types here.)
- Everything a user needs from the GUI (Interested → Applied → Interview + rounds
  → Offer + amount/deadline → Accepted/Rejected/Ghosted, notes, timeline) is
  reachable through the service layer. No missing status. The S29 accepted +
  ghosted statuses and interview rounds all work.

---

## 7. Verdict

**Could Jordan run their whole search on this app? Yes, mostly — and it's already
better than raw LinkedIn/Indeed for the _triage + tracking_ half of a job hunt.**

Where it **beats** LinkedIn/Indeed:

- **One local, de-duped, scored inbox** across Adzuna + ~hundreds of company ATS
  boards + HN/WWR, with a genuinely clean 30-mi Austin location gate (77 local +
  64 real-remote, **zero** geo garbage). No feed, no ads, no "promoted" spam.
- **Full local tracker** with a real lifecycle (offer amount, interview rounds,
  ghosted, follow-up reminders) that LinkedIn's "saved jobs" can't touch.
- **BYO-AI re-rank** is the right idea and here it fixed the exact things the
  local score gets wrong for a new grad (seniority, non-US-remote).

Where it **loses**:

- **LinkedIn/Indeed still have the volume + the brand-name postings** the app
  can't see. Reach probe: **~3% of the reachable Austin SWE universe**. The two
  biggest boards a new grad actually lives on (LinkedIn, Indeed) are ToS-blocked
  and only reachable via the manual browser-extension capture.
- **CareerOneStop unkeyed** = the single biggest local-coverage miss the Guide
  itself flags — and there's no key in `.env`. For a general user this is the one
  free signup that most changes local recall, and it silently did nothing.
- The **seeded employer list barely paid off**: of my 15 Austin seeds, only Ramp
  and Homeward reached the top 40 (both sub-optimal, over-remote), and 5/13 real
  boards were unreachable due to AI slug-guessing. The strong Austin-local hits
  came from **Adzuna + the pre-existing shared careers registry**, not my seeds.

**Single most valuable improvement for THIS persona:** fix the **seniority-aware
scoring** so "Sr.", "III/IV", and "8+ YOE" titles are downranked/gated for an
entry-level user (today a Sr. role scored **100** and topped the list), AND add
**US-work-authorization awareness to remote scoring** so Canada/Czech/UK-only
remote rows don't get full location credit. Those two fixes alone would clean up
~14 of the top-40 false positives _before_ the AI re-rank ever runs — which is
what a new grad without a paid AI would actually see.

Runner-up improvement: ship a **CareerOneStop key path in onboarding** (or make
its absence a loud, first-run banner), since it's the app's own stated #1 lever
for local, non-remote coverage and it's the difference between 3% reach and
meaningfully more.

---

## Bugs & anomalies (with evidence)

1. **Seniority-abbreviation gate miss (scorer).** `exclude_titles` /
   `seniority_exclude` word-boundary-match "senior" but NOT "Sr.". Result:
   `Sr. Software Engineer` (CDK), `Sr. Backend Software Engineer` (addepar),
   `Sr. Simulation/Flight Software Engineer` (Reliable Robotics), and
   `Software Engineer III` all survived AND scored 75–100 with `title 100%`. The
   #1 inbox row overall was **6sense "Software Engineer III" @ score 100** — the
   worst possible top pick for a new grad. Roman numerals ("III") and "8+ YOE"
   are likewise not downranked. No traceback (correctness bug, not a crash).
2. **Remote scoring ignores country / work-auth.** Any row containing "remote"
   gets `loc 100%`. Czech-Republic-only, UK-only, and Canada-only remote rows
   (affinipay, addepar, several Affirm) scored 75–84 and ranked above real Austin
   jobs, despite being unreachable for a US-only new grad.
3. **`+ Add Companies` adds unreachable boards without confirmation.**
   `save_companies` persists all parsed entries regardless of `probe_count`
   result; the Validate step is advisory. 5 of my 15 seeds were unreachable and
   2 were junk, and all 15 were written to `companies.json`. Evidence — soft
   errors during the run:
   `[direct] Oracle Austin: fetch error -- NameResolutionError("… Failed to
resolve 'not-a-real-ats.example.com' …")` and the same for the junk line
   (host `totally%20junk%20line%20no%20url%20here`). Working as designed, but a
   confirmation on unreachable rows would reduce registry clutter.
4. **Adzuna rate-limit back-off ×2 (~60s each)** added ~2 min to a 2m9s run.
   No hard 429 surfaced; not a failure, but on a slower connection / larger
   keyword set this could compound. Recorded as a quota/rate event per the brief.
5. **Keyless sources silently contribute nothing.** Jooble, Careerjet, and
   CareerOneStop are all in the daily net but returned 0 with only warning lines.
   A general user won't notice their local coverage is quietly capped. (Config /
   onboarding gap, not a code bug.)

## Reproduction artifacts

- Setup, seeding, analysis, and lifecycle scripts under the session scratchpad;
  full run log captured. Persona project kept at
  `projects/gu-swe-newgrad-austin/` (config.json, preferences.json,
  preferences.md, experience.md, tracker.db, last_run.json).
- `companies.json` was modified by seeding (15 rows tagged
  `software_engineering`); per instructions it will be restored by the janitor —
  **not** restored by this test.
