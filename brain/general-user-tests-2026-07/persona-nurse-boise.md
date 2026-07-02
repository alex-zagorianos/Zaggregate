# General-User Test — Maria Santos, RN (Boise, ID)

**Persona:** Maria Santos, RN, BSN. 6 yrs med-surg + 2 yrs charge nurse at a
regional hospital. Wants staff RN or clinical coordinator. Boise, ID (25 mi),
on-site only (no remote), $65k floor, mid-level.
**Project slug:** `gu-nurse-boise` · **Run date:** 2026-07-01 · **App v1.0.0**
**Tester:** blank-slate general user + playing her $20/mo BYO-AI assistant.

Keys available in `.env` (per instructions): Adzuna, JSearch, USAJobs keyed.
**CareerOneStop NOT keyed** (the known general-user gap). Jooble, Careerjet,
Brave, SerpApi also unkeyed. No 429/quota events occurred this run.

---

## 1. New-user lens — what a fresh nurse actually gets

**README quickstart:** clear and honest — `py -3.12 -m pip install -r
requirements.txt` then `py -3.12 gui.py`, "a short Setup wizard on first run
asks what jobs you want, where, your salary, and your resume." Correctly sells
the local-first, BYO-AI, "never applies for you" model.

**In-app Guide (`ui/help.py`):** genuinely strong for a non-technical nurse.
The 3-step model (Find → Keep → Apply), the tab-by-tab explanation, and the
"Set up your sources — the 10 minutes that matters most" section all speak
plain English. It explicitly calls out CareerOneStop as "the best free source
for … nurses" and Adzuna as "the single biggest unlock for local, on-site jobs
… healthcare." It even scripts the ask-your-own-AI employer-list flow verbatim
("List the 25 largest employers of [your kind of work] in [your city], with a
link to each one's careers page … as Name | link"). A nurse following this
Guide would do exactly the right things.

**First-run wizard (`ui/setup_wizard.py`) — 5 steps:** Welcome → Roles (+ field

- career level + free-text "anything else") → Where (location + remote checkbox
- salary, accepts `18/hr`) → Resume (paste or load) → "Keep jobs coming" (daily
  updates + Build employer list). The wizard auto-derives the field from the
  roles when the industry box is blank (a nurse who types "registered nurse"
  gets routed as nursing, not engineering — a real P0 fix that works). Pasted
  plain-text resumes are auto-structured so scoring can't crash. It even offers a
  "Build your employer list" nudge when the field has no starter companies.

**Wizard clarity: 9/10.** The only friction a real nurse would hit: the
"Career level" combobox and "Field / industry" box are _optional_ and easy to
skip, yet the field answer is load-bearing (it turns on the nursing feed and
gates out remote-tech boards). The Guide explains this well but the wizard
itself doesn't flag how much the field answer matters at the moment you'd skip
it.

---

## 2. Project setup

Created programmatically via the wizard's own pure functions
(`build_preferences`, `_search_config`) + `workspace.create_project(...,
make_active=False)` so the concurrently-active project was never disturbed.

- `config.json`: keywords `[registered nurse, RN, clinical nurse, nurse
coordinator]`, location `Boise, ID`, salary_min 65000, industry `nursing`,
  seniority_target `mid`, exclude_titles `[travel, lpn, cna, sales, territory]`,
  exclude_keywords `[travel nurse, travel rn, 13 week, pharmaceutical sales]`.
- `preferences.json` (hard): salary_min 65000, locations `[Boise, ID]`,
  **remote_ok false** (on-site only), target_roles set.
- `preferences.md`: plain-English profile (acute-care depth, charge-nurse
  leadership, on-site only, avoid travel/remote/pharma-rep).
- `experience.md`: full BSN/med-surg/charge-nurse resume with canonical `## `
  headings.

**Setup friction / bug:** `_attach_onet_soc` did **not** stamp an
`onet_soc_code` because the industry text `"nursing"` alone does not resolve to
a SOC (only `"registered nurse"` / `"nurse"` do — both resolve to 29-1141.00).
So the stable O*NET code is silently missing for a user who types the natural
word "nursing" in the field box. Downstream nursing gating still worked (it
keys on text tokens), so this was cosmetic here — but it's a real gap.

---

## 3. Seeding — the ask-your-own-AI employer flow

Acting as Maria's AI, I produced **14** real "Name | careers URL" lines for
Boise-area health systems and pushed them through the exact `+ Add Companies`
pipeline: `ats_detect.parse_line` → `ats_detect.probe_count` (Validate) →
`company_registry.save_companies` (Add).

| Result                           | Count  | Notes                                                                                                                                                                                     |
| -------------------------------- | ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Attempted                        | 14     | St. Luke's, Saint Alphonsus, Boise VA, Primary Health, Idaho H&W, HCA West Valley, Terry Reilly, Full Circle, Elks Rehab, Intermountain, Encompass, St. Luke's Rehab, Kindred, VA Nursing |
| **Added to companies.json**      | **14** | all tagged `nursing`; `save_companies` adds regardless of probe status                                                                                                                    |
| Probed **live**                  | **0**  | —                                                                                                                                                                                         |
| `direct` (uncountable by design) | 10     | hospital portals not on a JSON-API ATS                                                                                                                                                    |
| ATS-typed but **unreachable**    | 4      | my AI-guessed slugs were wrong (see below)                                                                                                                                                |

**The core seeding finding:** _nothing verified live._ The 4 entries I typed as
real ATS boards were all wrong guesses — St. Luke's Workday (`stlukesonline:5:
External` → HTTP 422 "gone"), Primary Health Greenhouse (`primaryhealth` →
gone), St. Luke's Rehab Lever (`stlukesrehab` → gone), Kindred Workable
(`kindredhospital` → gone). The 10 `direct` hospital portals can't be counted
and several of the raw hosts don't even resolve (`trinity-health.jobs`,
`fullcirclehealth.org`, `elksrehab.org` → DNS failure; HCA → 403; Idaho H&W →
404). This is the flow _working as designed_ (bad guesses fail probe, nothing
bad sneaks in) — **but for a real nurse it means the "add your local employers"
step, the Guide's promised "biggest quality jump," produced 0 usable boards**
unless she happens to know the exact ATS tenant slugs (which no nurse does).

At daily-run time the `careers` layer scraped these 14 and returned **0 jobs**
(the direct portals JSON-LD-extracted nothing; the ATS guesses were dead). So
seeding contributed **zero** to the inbox.

---

## 4. Run

`py -3.12 daily_run.py --project gu-nurse-boise` (foreground background task).

- **Wall clock: 41 s** (23:06:13 → 23:06:54 local). Fast — nothing hung.
- **Funnel:** `623 raw → 312 dedup → hard-gate 312→154 (dropped 158 on
location) → 29 qualified (score ≥ 40) → 29 inboxed`.
- **Page-2 recall:** +148 raw beyond page 1.
- **Sources that returned raw:** Adzuna 243, RNJobSite 244, TheMuse 75, USAJobs
  61, careers 0, jobicy 0.
- **After the location/remote hard-gate**, the only survivors were **Adzuna 140
  - USAJobs 14** — RNJobSite's 244 (national, unlocalized) and TheMuse's 75 were
    entirely gated out.
- **Skipped for want of a key:** CareerOneStop, Jooble, Careerjet (each logged a
  clean one-line skip). HigherEdJobs inert for nursing (correct). Brave/SerpApi
  discovery + reach skipped (no keys).
- **Reach:** "cannot certify a coverage % — no cross-source overlap" (no SerpApi
  probe). Sample completeness estimated ~57% (Good-Turing).
- **Errors/warnings:** the seeded `direct`/ATS companies threw fetch errors
  (DNS/403/404/422 — all soft, none fatal). One benign quirk: repeated
  "[direct] … link extraction + JSON-LD — verify manually" and repeated
  BRAVE/jooble/careerjet skip lines (the page-1 + page-2 + rescore passes each
  re-log them — noisy but harmless).
- **No 429/quota events.**

The **location hard-gate is the star of this run**: 158 of 312 deduped postings
were dropped for violating on-site/Boise, exactly honoring `remote_ok=false`.

---

## 5. Inbox analysis (29 rows)

**Source mix:** Adzuna 22 (76%), USAJobs 7 (24%). Careers/RNJobSite/TheMuse: 0.

**Score distribution:** 70–84 → 8, 55–69 → 16, 40–54 → 4, 0–39 → 1.
min 38, max 76, median 66. (The lone <40 is a USAJobs Nurse Manager that the
re-score dropped just below threshold post-insert.)

**Locality:** the classifier reports **29/29 "in-area"** — _but that is the bug,
not the truth._ Adzuna geo-labels a large batch as `"Idaho City, Boise County"`
(a real tiny town in the metro's county), so they all pass a Boise/`Boise
County` text filter with loc 100%. Reading the descriptions, several are **not
in Boise metro**:

- id=7 "RN for Critical Access Hospital in **MONTANA**" — different state.
- id=3 Dialysis RN → "**Eastern Idaho**" (~250 mi away).
- id=13 GCU Adjunct Faculty → "**Twin Falls, Idaho**" (~130 mi).

**Genuine local-metro rows: ~20 of 29.** True remote leakage: 0 (the gate held).
Wrong-metro/out-of-state leakage: ~3. Off-role (see below): ~9.

### BYO-AI re-rank (playing Maria's assistant over the top 29)

**TOP 10 for the persona (staff RN / clinical coordinator, med-surg/tele/charge,
Boise, on-site):**

| #   | Title                                    | Company                                | Location    | Src     | Why                                                                                                                               |
| --- | ---------------------------------------- | -------------------------------------- | ----------- | ------- | --------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Registered Nurse (Cardiac Cath Lab)      | Veterans Health Administration         | Boise, ID   | usajobs | Real Boise acute-care RN; cardiac/tele fits her telemetry depth; federal salary band clears floor easily.                         |
| 2   | Registered Nurse (Operating Room)        | Veterans Health Administration         | Boise, ID   | usajobs | Confirmed Boise, acute hospital RN; OR is a stretch from med-surg but a strong local employer + benefits.                         |
| 3   | Registered Nurse RN Heart & Vascular SDU | Trinity Health (Saint Alphonsus)       | Boise metro | adzuna  | Step-down cardiac unit = near-perfect match for a med-surg/tele charge nurse; local health system.                                |
| 4   | Trauma & Emergency RN — Full Time        | Trinity Health (Saint Alphonsus)       | Boise metro | adzuna  | Acute hospital RN, full-time, on-site; ED is adjacent to her med-surg/rapid-response experience.                                  |
| 5   | RN PACU PT Days                          | Trinity Health (Saint Alphonsus)       | Boise metro | adzuna  | Post-anesthesia acute RN at a Boise system; days shift; strong clinical fit.                                                      |
| 6   | RN Surgical Short Stay Unit PRN Nights   | Trinity Health (Saint Alphonsus)       | Boise metro | adzuna  | Med-surg-adjacent acute unit; she's fine with nights; local. PRN is the only knock.                                               |
| 7   | Registered Nurse OB Float Pool Full-Time | Trinity Health (Saint Alphonsus)       | Boise metro | adzuna  | Full-time hospital RN, local system; OB is off her core but float pool values med-surg versatility.                               |
| 8   | Wound Ostomy RN (WON) Full-Time Days     | Trinity Health (Saint Alphonsus)       | Boise metro | adzuna  | Specialty acute RN, full-time days, local; her wound-care skill line maps here.                                                   |
| 9   | Registered Nurse — $39–$50/hr            | Saint Alphonsus Rehab Hosp (Encompass) | Boise metro | adzuna  | Local inpatient rehab RN, wage clears floor ($81k–$104k annualized), $10k sign-on; on-site.                                       |
| 10  | Staff Development Coordinator (RN)       | Life Care Center of Boise              | Boise, ID   | adzuna  | "Coordinator" RN role in Boise — matches her clinical-coordinator target; SNF setting, but on-site + local + leadership-flavored. |

### False positives in the top 29 (and why they scored high)

**~9 false positives** the local scorer ranked highly:

- **6× Grand Canyon University "Adjunct RN Faculty — PRN"** (ids 13,15,16,17,19,
  20,23). Scored 65–67 because **title matched `RN`/nurse 100%, salary 100%, loc
  100%** — but these are _academic clinical-instructor_ PRN roles spanning
  Twin Falls / multiple campuses, **not staff RN**. Off-role and often
  out-of-metro. The keyword scorer has no way to know "faculty" ≠ "bedside."
- **id=7 "RN … in MONTANA"** — scored 71 (title/salary/loc all 100%) but the
  _description_ says Montana. Adzuna's `Idaho City, Boise County` label fooled
  the location component; the scorer never reads the JD body for a truer state.
- **id=3 Dialysis RN, Eastern Idaho** — scored 75; travel/agency staffing
  (HealthTrust), out-of-metro despite the county label.
- **id=26/27 Senior Social Worker-PTSD** and **id=28 Lead Clinical Laboratory
  Scientist** (USAJobs) — scored 42–43 by matching "clinical"; **not nursing at
  all.** They cleared 40 only because federal salary + Boise location padded the
  score.

**Root cause:** the local score trusts the source's _location label_ and
_title-keyword_ overlap; it can't down-rank a wrong-state or wrong-role posting
whose label happens to say "Boise County." An AI re-rank (Fit column) is exactly
what the app tells the user to run here, and it cleanly demotes all 9 — so the
product's own recommended workflow fixes its own scorer's blind spot. That is
the design working, but it means the raw Score column is misleading for this
persona without the AI pass.

---

## 6. Tracking to completion

Used the exact GUI chain (`service.track_job` = "Track ▸ Interested";
`service.set_status` = quick-status; `service.add_interview_round`;
`service.add_status_note`), pinning the project so every DB path resolved to
`gu-nurse-boise`.

5 jobs taken through the lifecycle; **re-read the DB independently — all
persisted:**

- **All 5 → applied** (date_applied + a +7-day follow-up auto-stamped on entry).
- **2 → interviewing with rounds:** app#1 got a phone-screen + on-site round;
  app#2 got a phone-screen round (`interview_rounds` round_no auto-sequenced).
- **1 → offer → accepted (full completion):** app#1 with `offer_amount
$78,000/yr`, `offer_deadline 2026-07-25`, accepted + start-date note.
- **1 → rejected:** app#2 with a rejection note.
- **1 → ghosted:** app#3.
- Final counts: applied 2, accepted 1, rejected 1, ghosted 1. Inbox 29→24
  (tracked rows removed). `status_history` logged every transition **and** every
  note-only event; the S29 `accepted`/`ghosted` statuses + interview rounds all
  work end-to-end.

**Lifecycle gaps:** none blocking. Minor: interview rounds and offer fields live
only inside the JobDialog (double-click a row), not on the tracker list's
quick-status dropdown — a user could set status "offer" from the dropdown but
would have to open the dialog to actually record the offer amount/rounds. Not a
gap in capability, just a discoverability step.

---

## 7. Verdict

**Could Maria run her whole search on this app? Mostly yes — with one caveat.**
The daily run gave her a **clean, 100%-on-site, Boise-labeled shortlist of ~20
genuinely local acute-care RN openings in 41 seconds**, tracked five through to
an accepted offer, and never leaked a single remote job (the on-site hard-gate
is excellent for a nurse who explicitly can't work remote). For triage +
application tracking it clearly **beats manually re-running LinkedIn/Indeed
searches** and pasting jobs into a spreadsheet.

**Where it beats LinkedIn/Indeed:** the on-site/location gate, the local-first
privacy story, and the tracker (interview rounds, offer capture, ghosted status,
follow-up nudges) are better than anything free on LinkedIn/Indeed. The BYO-AI
re-rank instantly fixes the scorer's wrong-state/wrong-role false positives.

**Where it loses:** (1) The two feeds that carried the whole inbox are **Adzuna
(76%) and USAJobs (24%)** — _both keyed by Alex for this test._ A real nurse who
hasn't done the Adzuna signup would get **7 federal jobs, period.** (2) The
nursing-specific **RNJobSite feed returned 244 postings but 0 survived** because
it's national and unlocalized — the one nurse-targeted source added nothing. (3)
**Seeding produced 0 live boards** — the Guide's "biggest quality jump" is
unreachable for someone who doesn't know ATS slugs. (4) **CareerOneStop is
unkeyed** — the DOL feed the Guide itself calls "the best free source for
nurses" never ran. (5) Big local employers (St. Luke's, Saint Alphonsus's own
Workday, the Boise VA's own portal) can't be scraped directly, so their jobs
only appear when an aggregator (Adzuna) happens to re-list them.

**Single biggest improvement for THIS persona:** ship the **CareerOneStop key
path working out of the box** (or a bundled/keyless equivalent) — it is the one
free, national, all-employer government feed that would fill the gap RNJobSite
and the eng-shaped starter registry leave, without depending on the user
guessing hospital ATS slugs. Second-best: make the location gate read the JD
body (not just the source's label) so Adzuna's "Idaho City, Boise County"
mislabels and out-of-state agency postings stop clearing the on-site filter.

**Beats manual? Yes** for the local nurse who does the Adzuna signup.
**Would she stay?** Probably yes — the tracker + on-site gate alone justify it —
but only after the sources are set up; a blank-keys nurse would bounce off the
near-empty first run.
