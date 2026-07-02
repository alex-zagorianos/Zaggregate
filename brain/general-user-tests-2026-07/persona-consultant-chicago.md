# General-User Test — Priya Nair, Management Consulting (Chicago)

**Persona:** Priya Nair — engagement manager, 12 yrs strategy & management consulting, MBA.
Targets: management consultant, strategy consultant, engagement manager, principal consultant.
Location: Chicago, IL (25 mi). Remote: hybrid/remote OK. Salary floor: $140,000. Level: senior.

**Project slug:** `gu-consultant-chicago` (kept). **Date:** 2026-07-01.
**Lens:** brand-new general user, blank slate (starter registry only), acting as her own $20/mo BYO-AI.

**Keys context:** `.env` has Adzuna + JSearch + USAJobs + Anthropic keys (treated as "user did
the free-key signups the Guide prescribes"). **CareerOneStop is NOT keyed (known gap).** Also
unkeyed: Jooble, Careerjet, Brave, SerpApi. Auto-AI/Anthropic ranking was **left OFF** (I was the
BYO-AI, clipboard-bridge style). No 429/quota events occurred.

---

## 1. New-user lens & wizard clarity

Read: `README.md`, the in-app Guide (`ui/help.py` GUIDE list), and the first-run wizard
(`ui/setup_wizard.py`).

- **README quickstart** is honest and non-technical: `pip install -r requirements.txt`, `py gui.py`,
  first-run wizard, "Update my Inbox now." Clearly states local-first, BYO-AI, never auto-applies.
- **Guide** is genuinely good for a non-technical user: 3-step model, per-tab explanation, and a
  standout "**Set up your sources — the 10 minutes that matters most**" section that (a) tells the
  user the free feeds skew remote/tech, (b) prescribes the two free keys that matter (Adzuna,
  CareerOneStop), and (c) contains the **exact ask-your-AI employer-list flow** this test exercises:
  _"List the 25 largest employers of [your work] in [your city], with a link to each careers page,
  one per line as Name | link."_ It correctly promises "anything the AI got wrong simply fails
  verification." This is the right mental model — it just under-warns how _often_ that happens for
  consulting (see §3).
- **Wizard** (`SetupWizard`, 5 steps: Welcome → Roles → Where → Resume → Keep-going): clear,
  pre-fills from existing prefs, accepts hourly or annual salary, auto-structures a pasted plain-text
  resume, has an optional field + career-level, and an "Anything else the AI should know?" free-text
  box that becomes `preferences.md`. Confirms before skipping. Non-eng first run gets a "Build your
  employer list" nudge because the starter registry is eng-only.

**Wizard clarity: 9/10.** Only nits: the "field/industry" box is optional and free-text with no
consulting example in the visible hints (examples shown are health/nursing/finance/controls), so a
consulting user might leave it blank; and the resume step doesn't say the resume is _only_ used once
an AI key is set for tailoring (ranking uses `preferences.md` more than the resume).

---

## 2. Project setup

Created programmatically via the real building blocks (`workspace.create_project` +
`ui.setup_wizard.build_preferences / _search_config / structure_resume_text`), `make_active=False`,
mirroring exactly the wizard path a real user would click through.

Authored, faithful to the persona:

- **config.json** — keywords (management consultant / strategy consultant / engagement manager /
  principal consultant), `location: "Chicago, IL"`, `salary_min: 140000`, `industry: "management
consulting"`, `seniority_target: "senior"`, `years_cap: 12`, exclude_titles (intern/associate/
  analyst/junior/sales/…), full general-user source set.
- **preferences.json** — hard filters: `salary_min 140000`, `locations ["Chicago, IL"]`,
  `remote_ok true`, `dealbreakers ["security clearance","ts/sci","active clearance"]`,
  `seniority_exclude []` (she IS senior — do not exclude senior), `target_roles [...]`.
- **preferences.md** — natural-language profile (engagement-manager, C-suite delivery, corporate/
  growth strategy, operating-model & org design, market entry, M&A commercial DD + PMI; deal-breakers:
  no pure IT-implementation/staff-aug, no associate, no sales, no clearance; hybrid Chicago, floor 140k).
- **experience.md** — a plain-text resume paste (no markdown headings) that the wizard's
  `structure_resume_text()` auto-promoted (`was_restructured=True`) into `## SUMMARY / ## EXPERIENCE
/ ## EDUCATION / ## SKILLS` — the auto-structuring path worked cleanly (1,356 bytes written).

**Setup friction:** minimal. One notable observation — **`industry: "management consulting"` did NOT
resolve to an O\*NET-SOC code** in `workspace._attach_onet_soc` (no `onet_soc_code` written to
config), whereas it _does_ resolve correctly in `industry_profile` (token "consulting" → Muse
["Management","Business Operations"], jobicy "business", synonyms + consulting title-terms). So the
ranking/enumeration routing is fine; only the stable SOC-code tagging silently no-ops for consulting.

---

## 3. Seeding — the ask-your-own-AI flow (the honest headline)

As Priya's AI assistant I produced 17 "Name | careers URL" lines for consulting firms with Chicago
offices, then pushed them through the **exact "+ Add Companies" pipeline**
(`scrape.ats_detect.parse_line` → `scrape.ats_detect.probe_count` → `scrape.company_registry.save_companies`),
tagging industry `management_consulting` — the same calls `AddCompaniesDialog._detect/_validate/_add`
make in `gui.py`.

| Metric                                                | Count                                    |
| ----------------------------------------------------- | ---------------------------------------- |
| Attempted (lines parsed)                              | 17                                       |
| Probed **live with jobs**                             | **1** (Point B — `lever:pointb`, 9 open) |
| Probed **unreachable**                                | 14 (all Greenhouse/Lever slug guesses)   |
| `direct` (uncountable, JS/JSON-LD pages)              | 2 (Deloitte, McKinsey)                   |
| **Saved to companies.json** (`save_companies` return) | **17** (0 skipped)                       |

**This is the most important finding of the test.** The `+ Add Companies` dialog (and thus this
flow) saves _every parsed line regardless of probe result_ — the probe is advisory to the user, not a
gate. So 16 of 17 entries were written into the shared `companies.json` even though only Point B is
actually scrapeable. On the daily run every one of the 14 unreachable slugs logged `gone → skipping`
and the 2 `direct` pages fell back to best-effort JSON-LD ("verify results manually") — i.e. **the
seeding added ~0 usable local coverage for a consulting user.**

Why it fails for _this_ persona specifically: major consulting firms don't expose the public
Greenhouse/Lever/Ashby JSON boards the app can scrape. **Bain, BCG, Oliver Wyman, Kearney, ZS,
Simon-Kucher, L.E.K., A&M, Huron, FTI, CRA, Analysis Group, Slalom, West Monroe** all run enterprise
ATSes (Workday/Avature/custom) behind CSRF/JS, or use non-obvious slugs the AI can't guess. I
confirmed the probe pipeline itself is healthy (a SpaceX greenhouse control returned 1829; two
alternate consulting slug guesses still returned None). So the AI-guessed-slug approach is
structurally weak for consulting — the AI can name the firms but cannot reliably name their _board
URLs_, and nothing in the flow tells the user "14 of these won't work; delete them."

_(companies.json will be restored by the janitor — not restored by me.)_

---

## 4. Run

`py -3.12 daily_run.py --project gu-consultant-chicago` — one run, background, exit 0.

- **Wall clock: ~37 s** (23:36:16 → 23:36:53). Fast (blank inbox, small registry for the field).
- **Funnel:** 740 raw → **565 after dedup** → preferences hard-gate **565 → 499** (dropped: salary 2,
  title 1, **location 63**) → **235 qualified** (score ≥ 40) → **196 new → inbox**.
  - page 2 added +307 raw beyond page 1 (paging is pulling recall).
  - per-company cap fired: **Accenture 19, EY 19, PwC 1** capped this run.
- **Errors/warnings (all expected, all non-fatal):**
  - `careeronestop` skipped — credentials missing (the known unkeyed gap; the single biggest miss for
    a general local search).
  - `jooble` / `careerjet` / `brave` skipped — no keys.
  - `higheredjobs` + `rnjobsite` correctly **inert** for a non-education/non-nursing field.
  - All 15 seeded ATS companies logged `gone → skipping` (matches §3); Deloitte/McKinsey `direct`
    JSON-LD "verify manually."
  - `careers` client returned **0** despite Point B being live with 9 — worth a look (the one
    scrapeable seed produced nothing in the funnel; may be an industry-filter or tiering interaction).
- **Reach:** "cannot certify a coverage %" — no cross-source overlap (no SerpApi key to bridge
  families); 740 raw → 488 distinct from 7 families, sample completeness ~34% (Good-Turing).
- **No 429 / quota events.** Auto-backup ran.

---

## 5. Inbox analysis

`projects/gu-consultant-chicago/tracker.db` → `inbox` (196 rows). Column is `source` (confirmed).

**Source mix (inbox `source` column):** adzuna **187**, weworkremotely **9**.
_(last_run per_source_counts, measured over the scored `results` pre-cap/dedup: adzuna 452, wwr 39,
themuse 1, himalayas 1, hn 4, usajobs 2 — the delta to the 196 inboxed is the ≥40 threshold + dedup +
per-company cap. Accenture/EY/PwC show up under `source=adzuna`.)_

**Score distribution (local score):** 90-100 → 3 · 80-89 → 23 · 70-79 → 14 · 60-69 → 13 ·
50-59 → 59 · 40-49 → 83 · <40 → 1.

**Locality (my classifier over the `location` field):** Chicago-area **188**, remote **8**,
wrong-location **0**, blank **0**. Adzuna geocoded the 25-mi Chicago search; many rows carry the
label "Illinois Medical District, Chicago" (Adzuna's centroid label) but the descriptions confirm
they are Chicago-metro postings, so they count as in-area, not wrong-location. **Locality is
excellent — essentially the whole inbox is Chicago-metro or remote, with zero out-of-area leakage.**

### BYO-AI re-rank (top 10)

Acting as Priya's re-ranker over the top ~40 by local score, weighting: true strategy/management-
consulting content, EM/principal/senior level, Chicago-metro, ≥$140k, and _penalizing_ the AWS-cloud-
delivery "engagement manager" cluster that the title keyword over-rewards.

| #   | Title                                                       | Company               | Location                  | Source | Why (fit)                                                                                |
| --- | ----------------------------------------------------------- | --------------------- | ------------------------- | ------ | ---------------------------------------------------------------------------------------- |
| 1   | M&A Strategy & Governance Senior Consultant                 | Deloitte              | Chicago (IL Med District) | adzuna | Bullseye: S&T / M&A / restructuring, senior, $153k. Her DD+PMI core.                     |
| 2   | Management Consultant, Senior Project Manager – Chicago     | Voyage Advisory       | River North, Chicago      | adzuna | Pure management-consulting boutique, in-city, $165k.                                     |
| 3   | Engagement Manager – Management Consulting                  | World Wide Technology | Chicago                   | adzuna | Titled exactly to her target role; strategy+execution, $176k (note ~50% travel).         |
| 4   | Payer Back-Office Strategy/Ops Consultant, Senior Manager   | PwC                   | Chicago                   | adzuna | Big-4 advisory, operations strategy, senior-manager level, $158k.                        |
| 5   | Oliver Wyman – Operations/Supply-Chain Engagement Manager   | Marsh McLennan        | Chicago                   | adzuna | Real MBB-tier EM role, $225-240k — top comp + true strategy house.                       |
| 6   | Business Strategy Senior Consultant                         | Deloitte              | Chicago                   | adzuna | Corporate strategy, transformation, $154k — direct match to her strengths.               |
| 7   | Global Business Services (GBS) Strategy – Senior Consultant | Deloitte              | Chicago                   | adzuna | CFO/CAO operating-model advisory, $144k — her operating-model wheelhouse.                |
| 8   | Senior Managing Consultant – Enterprise Strategy            | IBM                   | Chicago                   | adzuna | Enterprise-strategy consulting, managing level, $197k.                                   |
| 9   | Consulting Engagement Manager (Lotis Blue)                  | Sch Services Inc      | West Loop, Chicago        | adzuna | Boutique strategy/people-consulting EM, in-city, $158-237k.                              |
| 10  | Sr Principal Engagement Manager                             | Coupa Software        | Chicago                   | adzuna | Principal-level EM, $152-213k — borderline (SaaS services) but senior+comp+local strong. |

**False positives in the top 40 (~19 of 40 ≈ 48%):** the local scorer over-rewards the literal
title token **"Engagement Manager,"** so it floated a large cluster that a strategy EM would skip:

- **~12 Amazon "AWS ProServe / Community Engagement Manager" rows** (ranks 1-3, 9-10, 13-17, 25, 33) —
  these are _cloud-implementation delivery_ EMs, not strategy/management consulting. They took the top
  3 slots (scores 91-93) purely on title + high salary.
- **Google gTech Ads EM** (#6, and its description shows NY/Atlanta primary — location noise).
- **Edwards Lifesciences "Provider Education & Engagement" Manager** (#21 — a medtech _sales_ team role).
- **Capital One "Project Management – Engagement Manager"** (#24, #34 — internal PM, not consulting).
- **Legora EM ×2** (#30-31 — customer-success at a legal-AI SaaS) and **Workday EM, AI Practice** (#35).
- **Guidehouse Strategy & Transformation Sr Consultant** (#39) — genuinely consulting but FEMA/Public
  Trust clearance ("ability to obtain") — borderline vs. her clearance deal-breaker.

**Local-scorer quality:** strong on _locality_ and _field_, weak on _role disambiguation_ — it can't
tell strategy-consulting "engagement manager" from cloud-delivery/customer-success "engagement
manager." This is exactly the gap the AI-rank round-trip (Fit column) is designed to close, and for
this persona it's the highest-value AI use. The deal-breaker gate (`preferences.json` dealbreakers)
did not catch the Guidehouse clearance line because it's "ability to obtain," not "active clearance."

---

## 6. Tracking to completion

Used the same `tracker.db` functions the GUI buttons call, pinning the process to the project
(`workspace.pin_active`). 5 genuine consulting fits tracked (inbox → applications), then the full
lifecycle. Re-read the DB independently — **every status persisted:**

| App | Company                       | Final status  | Extras verified                                                                                                                                                            |
| --- | ----------------------------- | ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Deloitte (M&A Strategy)       | **accepted**  | offer_amount `$205,000 base + bonus`, deadline `2026-07-25`, offer_notes set; full path interested→applied→interview→offer→accepted in `status_history`; 1 interview round |
| 2   | Voyage Advisory               | **interview** | 1 interview round (phone_screen, interviewer, notes)                                                                                                                       |
| 3   | World Wide Technology         | **rejected**  | note recorded                                                                                                                                                              |
| 4   | PwC                           | **ghosted**   | note recorded                                                                                                                                                              |
| 5   | Marsh McLennan (Oliver Wyman) | **applied**   | date_applied auto-stamped, +7d follow-up auto-armed                                                                                                                        |

- `status_history` logged all 11 transitions with timestamps; `interview_rounds` has 2 rows; offer
  fields persisted; inbox correctly dropped 196 → 191.
- The S29 statuses (**accepted**, **ghosted**) and **interview rounds** all work end-to-end from the
  module API. `date_applied` auto-stamp + follow-up auto-arm on entering 'applied' fired correctly.

**Lifecycle gaps (minor):**

1. **Stale follow-up on terminal states.** `follow_up_date` (+7d, armed at 'applied') is _not cleared_
   when an app reaches accepted/rejected/ghosted — all five rows still show `fu=2026-07-08`.
   `count_followups_due` filters to applied/phone_screen/interview so it won't nag, but the stale date
   lingers on the row (cosmetic/DB-hygiene).
2. **Offer fields are free-text only** (`offer_amount` is a string) — fine for tracking, but no
   structured comp for analytics.
3. Everything a user needs (all statuses, rounds, notes, offer terms) is reachable — no true blocker.

---

## 7. Verdict

**Could Priya run her whole search on this app? Mostly yes — better than expected for a
non-engineering, non-tech persona, and largely on the strength of Adzuna.**

- **Where it beats manual LinkedIn/Indeed:** one 37-second run produced **196 scored, deduped,
  Chicago-metro, ≥$140k consulting postings with zero out-of-area leakage** and a clean triage/track/
  apply/tracker loop with real offer + interview-round bookkeeping. The locality and salary gating are
  genuinely better than scrolling LinkedIn, and the tracker is more disciplined than a spreadsheet.
  The Anthropic/ToS-safe design (never touches Indeed/LinkedIn feeds) is respected.
- **Where it loses:** (1) **The ask-your-AI seeding flow is near-useless for consulting** — 1/15 ATS
  guesses were live; the flow silently saves the 14 dead ones. (2) The local scorer can't disambiguate
  "engagement manager," so ~half the top 40 are cloud-delivery/customer-success false positives —
  she _must_ run the BYO-AI Fit round-trip to get a usable shortlist. (3) With **CareerOneStop
  unkeyed**, essentially the entire non-Adzuna local layer is silent — the run is ~95% one source
  (Adzuna). A single-source dependency is fragile (one 429 or Adzuna outage empties the inbox).
- **Beats a purely manual search?** For _finding + tracking_, yes. For _ranking_, only once she adds
  the AI Fit step.

**Single most valuable improvement for THIS persona:** make the local scorer (or a mandatory
first-pass AI Fit) **role-disambiguate the "engagement manager" family** — separate strategy/
management-consulting EMs from cloud-delivery/customer-success/PM EMs — since that one title collision
generates the bulk of her false positives and buries true strategy roles below AWS listings.
_Runner-up:_ have `+ Add Companies` / the seeding flow **flag or withhold entries that fail the live
probe** (or resolve consulting firms to their real enterprise ATS) so the AI-employer-list step
actually adds coverage instead of dead slugs — and ship at least a small `management_consulting`
seed in the registry so day-one isn't Adzuna-only.

**Would she stay?** Yes, as a scored-inbox + tracker over Adzuna — but she'd quickly notice she's
relying on one feed and would want CareerOneStop keyed and the ranking sharpened.

---

### Appendix — artifacts

- Project: `projects/gu-consultant-chicago/` (config.json, preferences.json/.md, experience.md,
  tracker.db, last_run.json). **Kept.**
- Setup/seed/analysis/lifecycle scripts run from the session scratchpad (not committed).
- companies.json was mutated by the seeding step (16 dead + Point B live added under
  `management_consulting`); **left for the janitor to restore.**
