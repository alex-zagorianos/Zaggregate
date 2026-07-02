# General-User Test — Alan Park, Mechanical Engineer (Seattle, WA)

**Date:** 2026-07-02
**Persona:** Alan Park, PE. Mechanical engineer, 10 yrs product design + HVAC/building systems.
SolidWorks + FEA daily. Targets: mechanical engineer / senior mechanical engineer / product
design engineer. Seattle WA, 30 mi radius, hybrid ok, remote acceptable. Salary floor $110K.
Level: senior.
**Project slug:** `gu-mecheng-seattle`
**Blank slate:** only the shipped starter registry; no prior projects touched.

---

## 1. New-user lens — what a fresh user gets

Read: `README.md`, the in-app Guide (`ui/help.py` `GUIDE`), and the first-run wizard
(`ui/setup_wizard.py`).

**Wizard clarity: 8/10.** The 5-step flow (Welcome → What jobs? → Where/salary → Resume →
Keep jobs coming) is genuinely plain-English and asks exactly the right things in the right
order: roles (comma list), optional field/industry + career level, an "anything else" free-text
box for the AI, location + remote checkbox + salary (accepts "18/hr" and annualizes), optional
resume paste (auto-structured into headings so it can't crash later scoring), and a closing
step for daily updates + build-my-list. Good touches: the roles step warns against over-narrow
titles; salary parsing is forgiving; a pasted headingless resume is auto-wrapped
(`structure_resume_text`). The Guide's "Set up your sources — the 10 minutes that matters most"
and "ask your AI to build your employer list" sections are excellent and set correct expectations.

Points off: (1) the field/industry box is free text with no validation or matching against
the registry's actual tags, which is the source of the biggest bug below; (2) a senior user has
to encode "senior" via the Career-level combobox, not the role text — correct but easy to miss;
(3) nothing tells the user their two-word field label won't match seeded companies.

---

## 2. Project setup

Created programmatically (mirroring the wizard's `apply()` on-disk contract), `make_active=False`,
`person="Alan Park"`:

- `config.json` — 5 keywords (mechanical engineer, senior mechanical engineer, product design
  engineer, HVAC engineer, mechanical design engineer); `location: "Seattle, WA"`;
  `salary_min: 110000`; `industry: "mechanical engineering"`; `seniority_target: "senior"`,
  `years_cap: 12`; all 15 daily sources on; sensible `exclude_titles`
  (intern, technician, sales, software engineer, firmware).
- `preferences.json` — hard filters: salary_min 110000, locations ["Seattle, WA"], remote_ok true,
  dealbreakers (clearance/ts-sci).
- `preferences.md` — a rich natural-language profile (PE, SolidWorks/FEA/GD&T product design +
  HVAC/ASHRAE building systems, senior IC, what to avoid, geography/comp/seniority notes).
- `experience.md` — a faithful headed resume (no real PII) that parses cleanly
  (`resume.experience_parser.load_experience` → 8 sections).

All files load and parse without error.

---

## 3. Seeding (the Guide "ask your own AI" flow)

Acting as Alan's $20/mo AI assistant, I produced Seattle-area / PNW aerospace, robotics,
manufacturing, and product-design employers as `Name | URL` lines and pushed them through the
EXACT "+ Add Companies" pipeline: `scrape.ats_detect.parse_line` → `probe_count` (validate) →
`scrape.company_registry.save_companies`, tagged with the project industry.

**Counts (final list): attempted 15 parsed → 8 verified-live + 1 direct (Boeing) → added 8
(1 skipped as already present) → 6 rejected on 404 probe.**

- Verified live (probe returned an open-job count): Stoke Space (54), Radiant (18), Divergent (56),
  Zipline (283), Relativity Space (322), Formic (25), Fictiv (75), Seurat (4).
- Direct/uncountable but addable: Boeing.
- Rejected (probe 404 = harmless failure, "flow working as designed"): Blue Origin, Glowforge,
  Carbon Robotics, Kymeta, McKinstry (Workday), PACCAR (Workday).

**Friction / the real story of seeding as an AI:** an AI without live web access (me) reliably
produces _company names_ but frequently _wrong ATS slugs_. My first-pass guesses for Blue Origin,
Glowforge, Carbon Robotics, Kymeta all 404'd — the boards exist but under slugs I couldn't
guess. The pipeline correctly rejected them (network was fine — Divergent 200'd in the same run),
so nothing bad was added. To hand Alan a genuinely useful list I fell back to slugs I could
verify (several already in the starter registry). **Takeaway:** the "ask your AI for Name | URL"
flow only works well if the AI can browse; a chat-only AI's hit rate on ATS slugs is low, and the
user sees mostly "unreachable". The dialog handles this gracefully but the _yield_ is low.

> Note: the shared `companies.json` will be restored by the janitor; I did not restore it.

---

## 4. The run

`py -3.12 daily_run.py --project gu-mecheng-seattle` (background). Exit 0.

**Wall-clock: 33 s** (00:20:19 → 00:20:52).

**Funnel:**

- Raw: page-1 pass 397 → dedup 266; full 2-page pass **628 raw → 396 after dedup** (page 2
  added +231 raw).
- Preferences hard-gate: **396 → 114** (dropped: title 2, **location 280** — the location gate
  is doing the heavy lifting and doing it well).
- Qualified (score ≥ 40): **32**.
- Inboxed: **32** (all new; per-company cap not hit).
- Reach: "cannot certify a coverage %" — no cross-source overlap (628 raw → 324 distinct from
  7 independent families, sample completeness ~48% Good-Turing). No SerpApi key → no probe overlap.

**Source contribution (raw `found`=114 per last_run.json):** adzuna 62, weworkremotely 33, hn 16,
usajobs 2, themuse 1.
**Inbox source mix (the 32 that landed):** adzuna 26, weworkremotely 4, hn 2.

**Errors / skips / gaps (all non-fatal):**

- `NOTE: only 0 registry companies match industry 'mechanical engineering'` → **careers path
  contributed 0 jobs** (this is the headline bug, §8).
- CareerOneStop skipped — credentials missing (known gap; this is _the_ general-user equalizer
  for local jobs and it's unkeyed).
- Jooble, Careerjet, Brave discovery — all skipped, keys unset.
- higheredjobs / rnjobsite — correctly inert for a mechanical field.
- No 429 / quota events. jsearch correctly excluded from the daily net.

---

## 5. Inbox analysis (32 rows)

**Score distribution:** min 41, max 73, mean 62.7, median 64. Buckets: 70–79 ×5, 60–69 ×23,
50–59 ×1, 40–49 ×3. `fit` = −1 on all 32 (correct — no auto-AI ranking was enabled; I am the
BYO-AI).

**Locality (30 mi Seattle):** **25 in-area, 6 remote, 1 wrong.** The location hard-gate that
dropped 280 rows is the reason this is so clean — nearly every Adzuna row is genuinely
"Seattle, King County". One genuine locality false positive: **Kosmos "Mechanical Engineer"**
scored 64 and shows "Seattle, King County" but the description is **Butte, MT** with relocation —
the _source_ mislabeled the location, not the app.

### Top 10 (BYO-AI re-rank for Alan)

| #   | Title                                          | Company                        | Location    | Source | Why                                                                 |
| --- | ---------------------------------------------- | ------------------------------ | ----------- | ------ | ------------------------------------------------------------------- |
| 1   | Sr. Mechanical Engineer (HVAC/Plumbing Design) | K2 Staffing                    | Seattle, WA | adzuna | Bullseye: HVAC + PE, $124.8–183K, exactly his building-systems half |
| 2   | Senior Mechanical Engineer (Seattle, WA)       | IMEG Consultants               | Seattle, WA | adzuna | MEP consulting, $107–149K; classic PE-stamp HVAC role               |
| 3   | Contract Senior Mechanical Design Engineer     | Simplexity Product Development | Seattle, WA | adzuna | SolidWorks product design, $113.6K; his product half                |
| 4   | Lead Mechanical Engineer - Buildings           | WSP                            | Seattle, WA | adzuna | Building-systems lead IC, $118–175K                                 |
| 5   | Senior Mechanical Engineer                     | DLR Group                      | Seattle, WA | adzuna | MEP / buildings, $100–140K (edge of floor)                          |
| 6   | Senior Mechanical Engineer - P2S               | Legence                        | Seattle, WA | adzuna | MEP/HVAC, $142K                                                     |
| 7   | Sr. Mechanical Engineer                        | Cowboy Space                   | Seattle, WA | adzuna | Aerospace product mechanical, $150–200K; senior, hands-on           |
| 8   | Senior Mechanical Engineer                     | PBK Architects                 | Seattle, WA | adzuna | Building MEP, $120–148K                                             |
| 9   | Mechanical Engineer, Structures                | Gravitics                      | Seattle, WA | adzuna | Aerospace structures / FEA, $110–140K                               |
| 10  | Senior Staff Mechanical Engineer               | Agile Space Industries         | Seattle, WA | adzuna | Aerospace product design, $146–247K; top of his range               |

Runners-up: Amazon Data Center Mechanical Engineer roles (71/70/67 — strong comp, but data-center
mechanical is a niche he may or may not want), TKDA Lead PE Mechanical (63), Endurance Energy (63).

### False positives in the top 40 (all 32 here) and why they scored high

The local scorer's `score_notes` reveal the mechanism: **title match dominates and skills is a
weak counterweight.** Titles containing keyword tokens get "title 100%" even when the role is
software:

1. **Railway** (73, HN) — "Infra Eng… Brand Designer… Product Eng" → title 100%, skills 12%.
   Software infra. Highest score in the inbox and a total miss.
2. **Hospitable — Staff UI/UX Product Designer** (72, WWR) — "product designer" ≈ "product design
   engineer" → title 100%, skills 25%. Software UX.
3. **jerry.ai — Staff Product Designer** (68, WWR) — same mechanism, title 100%/skills 12%.
4. **DigitalOcean — Product Security Engineer, Secure Design (Kernel)** (67) — "design" token →
   title 100%, skills 0%. Software security.
5. **BrowserStack — Manager, Product Design** (62, WWR) — software product design.
6. **Qualtrics — Staff Program Manager, Product, Design & Engineering** (50) — PM, not IC design.
7. **Solace Health — Mobile Engineer** (43, HN) — software.
8. **Kosmos — Mechanical Engineer** (64) — real ME role but Butte MT (source location error).

Root pattern: for a general user whose keywords include "product design engineer", the token
"design"/"designer" pulls in a whole category of software/UX roles at high title-scores; only the
skills sub-score (which reads the resume) pushes back, and it's outweighed. This is exactly what
the BYO-AI re-rank is _for_ — and it cleanly demotes all of them.

---

## 6. Tracking to completion

Drove 5 top jobs through the lifecycle using the same `tracker.service` / `tracker.db` functions
the GUI buttons call (project pinned so DB paths resolve to `gu-mecheng-seattle`):

- All 5 tracked (inbox → application, status `interested`) then → `applied`
  (date_applied + +7-day follow-up auto-stamped centrally by `db.update_job`'s applied branch —
  verified in code, so the GUI "Mark Applied" path arms the same engine).
- 2 → `interview` with rounds: K2 (1 phone screen), Cowboy Space (phone screen **and** onsite —
  multi-round verified).
- 1 → full completion: IMEG `offer` → `accepted`, with `offer_amount=$138,000`,
  `offer_deadline=2026-07-25`, `offer_notes` all persisted.
- 1 → `rejected` (Simplexity) with a status note that persisted.
- 1 → `ghosted` (WSP).

**Re-read DB in a fresh process — all persisted:** applications count 5, status counts
{accepted 1, ghosted 1, interview 2, rejected 1}; interview_rounds 3 rows (Cowboy has 2);
offer fields present on IMEG; the rejected note is in `status_history`; inbox dropped 32 → 27.
`status_history` logged every transition (old→new + changed_at).

**Lifecycle gaps:** none blocking. The S29 statuses (`accepted`, `ghosted`) and interview rounds
all work from the service layer. Minor: the timeline API returns note/changed_at but folds the
status into the history table under old/new columns — a GUI reading it must join those; not a
user-facing problem.

---

## 7. Verdict (as Alan)

**Could he run his whole search here? Mostly yes, for the local-jobs half — and better than
LinkedIn/Indeed for triage + tracking.** In 33 seconds he got 32 scored, de-duplicated, almost-
entirely-in-Seattle senior-ME postings with salary data, then a private local tracker that took
an offer all the way to "accepted." No account, no telemetry, no scrolling past sponsored junk.
The location gate is genuinely good: 25/32 truly in-area. The salary floor and dealbreaker gate
work. The BYO-AI re-rank is the piece that turns a noisy 62-median list into a clean top 10 and
kills the software/UX false positives the keyword scorer lets through.

**Where it loses to LinkedIn/Indeed:** breadth of _this specific field_ out of the box. Almost
every good result came from **one source — Adzuna**. The starter company registry is invisible to
him (bug below), CareerOneStop (the DOL local-jobs feed the Guide calls the #2 unlock) is unkeyed,
and Jooble/Careerjet are unkeyed. So he's effectively running Adzuna + a couple of remote-tech
boards. LinkedIn would surface more Seattle MEP/aerospace employers and let him see who's hiring
at named firms. Indeed (ToS-blocked here, correctly) would add volume.

**Single biggest improvement for THIS persona:** **fix the industry-tag matching bug (§8) so a
two-word field label like "mechanical engineering" actually matches seeded companies** — right now
his careers path is silently empty and his 8 verified employers never get searched. Second:
ship a CareerOneStop key path that a general user can actually fill, since that's the promised
local-jobs equalizer and it's the difference between "Adzuna-only" and "wide net."

- **wide-use 1–10:** 6
- **beats manual triage:** yes (for scoring, locality filtering, and tracking)
- **would he stay:** yes for tracking + daily triage; he'd still keep a LinkedIn tab open
- **biggest gap:** careers/registry path yields 0 for his field (industry-tag bug) + unkeyed
  CareerOneStop → over-reliance on Adzuna.

---

## 8. Bugs

### BUG 1 (HIGH, persona-blocking): industry tags with spaces never match their own filter

**Where:** `scrape/company_registry.py` — `get_registry()` (user-entry filter, ~line 300) calls
`_industry_tag_match(key, t)` where `key` is normalized (spaces→underscores,
`"mechanical engineering"` → `"mechanical_engineering"`) but the company tag `t` is passed
**raw** (`"mechanical engineering"`, with a space). `_industry_tag_match` (line 234) does NOT
normalize the tag:

```python
def _industry_tag_match(key: str, tag: str) -> bool:
    k = key.lower(); t = (tag or "").lower()
    return bool(t) and (k == t or k in t or t in k)
```

For k=`"mechanical_engineering"`, t=`"mechanical engineering"`: `k==t` False;
`"mechanical_engineering" in "mechanical engineering"` False (underscore vs space);
`"mechanical engineering" in "mechanical_engineering"` False → **no match.**

**Repro (measured this run):**

```
_industry_tag_match('mechanical_engineering', 'mechanical engineering')  -> False   # as get_registry calls it
_industry_tag_match('mechanical_engineering', 'mechanical_engineering')  -> True    # if the tag were normalized
get_registry(industry='mechanical engineering')  -> 0 companies   (8 seeded, all tagged 'mechanical engineering')
industry_company_count('mechanical engineering') -> 0
```

**Impact:** The "+ Add Companies" dialog tags every company with the **active project's industry
verbatim**. Any general user whose field is a **two-or-more-word phrase** ("mechanical
engineering", "product design", "supply chain", "data science") adds companies that then **never
appear in their own careers searches** — the daily run logs `only 0 registry companies match
industry '<field>'` and the careers path contributes 0. Single-word fields ("nursing", "finance")
happen to work; the starter registry's own tags are single-token-with-underscore
(`controls_engineering`) so single-project engineering users (Alex) don't hit it, which is why
it's gone unnoticed. It bit this persona directly: 8 verified live employers, 0 searched.

**No traceback** — it's a silent wrong-result, not a crash. **Fix sketch:** normalize the tag the
same way as the key inside `_industry_tag_match` (`t = t.replace(" ", "_")`), or normalize both
sides once at the top. (Not fixed — hard rule: no source edits.)

### BUG 2 (LOW, data-quality, upstream): source location mislabeling

Adzuna returned "Seattle, King County" for a **Butte, MT** role (Kosmos), which passed the
location gate and scored 64. Not the app's fault (source metadata), but it means the location
gate can't catch every out-of-area role; the description contradicts the location field. A
description-vs-location sanity check would catch it.

### Non-bugs worth noting

- careers=0, CareerOneStop/Jooble/Careerjet/Brave skipped — all **unkeyed**, expected, logged
  clearly. Findings, not failures. No 429/quota events.
- The 6 probe-404 rejects in seeding are the flow working as designed.

---

## Appendix — friction list

1. AI-generated ATS slugs are often wrong without live web access → low seeding yield ("unreachable").
2. Industry-tag space bug → seeded companies silently invisible for two-word fields (BUG 1).
3. CareerOneStop unkeyed → the promised local-jobs equalizer is off; effectively Adzuna-only for local.
4. Keyword scorer over-weights title-token matches → software/UX false positives at high scores
   (the BYO-AI re-rank is required to clean them).
5. One source location error slipped through the gate (Kosmos → Butte MT labeled Seattle).
