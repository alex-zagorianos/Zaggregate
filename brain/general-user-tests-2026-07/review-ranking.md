# Ranking & Scoring Quality Review — General-User Personas (2026-07)

**Lens:** ranking and scoring quality (local `match/scorer.py` composite + the
`preferences.hard_gate` pre-AI cut). Source of claims: the 8 blank-slate persona
reports in `brain/general-user-tests-2026-07/`. Every systematic claim below was
verified against source at `file:line` and, where feasible, reproduced with a
read-only `py -3.12` snippet against the real functions.

**Read-only.** No source, projects, companies.json, or tracker.db was modified.
No `daily_run.py`/`gui.py` was run; only pure functions were called with test
values.

---

## TL;DR — the two-scorer picture

The app has **two independent ranking surfaces**, and the false positives all
live in the FIRST one:

1. **Local deterministic scorer** (`match/scorer.py`, `preferences.hard_gate`) —
   runs on every job, zero API calls, produces the `Score` column and the raw
   inbox order a **no-AI user sees**. This is where all seven false-positive
   families originate.
2. **BYO-AI Fit re-rank** (the designed mitigation) — an optional second pass the
   Guide tells the user to run. `match/facts.py` + `match/gate.py` + the rubric
   feed it a _much_ better seniority/role/restriction model. **Every persona
   reported the AI re-rank cleanly demoted the false positives.** The gap is
   real only for a user who never sets an AI key.

The core structural problem: **the strong seniority/restriction logic lives in
`match/facts.py` (the AI-batch path) and is NOT wired into the local
`score_job()` title component or the `hard_gate`.** `facts._detect_seniority`
correctly detects `Sr.` (`\bsr\.?\b`, facts.py:27), Roman `I/II/III`
(facts.py:31-32) and `8+ years` (facts.py:37-40) — but the local scorer never
calls it for downranking an IC search, so those signals are invisible to the
`Score` a keyless user ranks on.

---

## False-positive taxonomy (all 7 verified)

### (1) Seniority-blind local scoring — Sr. / II·III / "8+ years" score identically to entry

**CONFIRMED (reproduced).** For a new-grad SWE (`keywords=['software engineer']`,
Austin, floor 70k) the local scorer returns an **identical score** for a plain
"Software Engineer", "Sr. Software Engineer", "Software Engineer II", and
"Software Engineer III" — all `title 100%`, all the same composite (91 in the
isolated repro; the persona saw a III reach 100 with a fresh date + small-board
size bonus, `conf 5/5`). A III with full data present scored 88 in my repro; the
exact number floats with data completeness, but the **tie with the entry role is
the defect**.

Why:

- `_STOPWORDS` (scorer.py:33-34) contains `senior, junior, lead, staff, i, ii,
iii` — so those tokens are stripped from title-significance; "Software Engineer
  III" scores `title 100%` on "software engineer".
- The only seniority adjustment, `_seniority_fit_adj` (scorer.py:86-115), engages
  **only when the user targets management** (`target_level >= _MANAGEMENT_MIN=4`,
  scorer.py:63,101). For an IC/new-grad search `_target_level(['software
engineer']) == 2` (verified), so the exec branch never runs. The IC branch
  (scorer.py:110-115) only penalizes roles that overshoot into
  **manager/director** — it does **not** touch senior/lead/III/`8+ yrs`.
  `_seniority_fit_adj('Software Engineer III', None) == 0` (verified).
- The opt-in blocklists (`seniority_exclude`, `exclude_titles`) default **empty**
  (scorer.py:126,128) and use **word-boundary** matching (`_term_pattern`,
  scorer.py:246-254 → `_title_blocklist_penalty`, scorer.py:455-459). Reproduced:
  with `seniority_exclude=['senior']`, "Senior Software Engineer" is caught
  (-20 → 71) but **"Sr. Software Engineer", "Software Engineer III", and "Software
  Engineer, Compute (8+ YOE)" are all UNCAUGHT and stay at 91.** `\bsenior\b`
  never matches the abbreviation, the Roman numeral, or the years phrase.
- The `hard_gate` blocklist (`preferences.py:130`) uses a _plain substring_
  `b in title` on `dealbreakers + seniority_exclude` — same abbreviation blind
  spot from the other direction (and `"sr"` as an entry would over-match "sr" in
  unrelated words).

**Impact:** a no-AI new-grad's #1 inbox row was an SE III / 8+ YOE role (persona
swe-newgrad-austin, ~6 over-leveled in top-40). Same family dominated the
data-changer-phoenix entry-level inbox (8+ Senior/Sr/Lead/Principal in top-40).

**Minimal fix:** in `score_job`, compute `job_level = facts._detect_seniority(title,
desc)` (already handles Sr./III/8+) and apply a bounded down-nudge whenever
`job_level` exceeds the user's `seniority_target`/`years_cap` — mirroring the
exec branch but for the _below-target_ IC case (senior/lead/III → -8..-12,
manager+ already handled). This reuses the existing, correct detector and needs
no new regex. Cheaper alternative: expand the default `seniority_exclude`
matcher to also fire on `\bsr\.?\b`, `\b(?:I{2,3})\b` word-level, and
`\b\d{1,2}\+?\s*(?:years|yrs)\b` — but a graded nudge beats a hard blocklist for
entry configs (you want senior _downranked_, not hidden).

---

### (2) Remote rows get location 100% with no country / work-auth awareness

**CONFIRMED (reproduced).** `_location_score` (search_engine.py:40-61): if
`"remote" in job_location and target not in job_location`, it returns `3`
(= `l=1.0`, full marks) whenever `remote_ok=True` (line 51-52). No parsing of the
country/region inside the remote string.

Reproduced for a marketing-manager search (target New York): "Senior Marketing
Manager, EMEA @ Remote, EMEA", "Marketing Manager @ Remote (LatAm/EU/Canada/UK -
NOT US)", and a real "Marketing Manager @ New York, NY" **all got `loc 100%` and
an identical composite (94).** The EMEA/non-US-only remotes tie the genuine local
role.

The `hard_gate` compounds it: `is_remote = "remote" in loc or "remote" in title`
(preferences.py:134) keeps ANY remote row when `remote_ok`, with no country
reconciliation. And `facts._detect_restriction` (facts.py:203-207) only fires on
**description-body** phrasing ("must reside in Canada", facts.py:65-71); a bare
location label "Remote - Czech Republic" yields `restriction=None` (verified), so
the AI-batch `gate` (`_FOREIGN_RESTRICTION`, gate.py:16-17,44-46) never sees it
either unless the prose spells it out.

**Impact:** swe-newgrad-austin (~8 non-US-only remotes at 74-84: MixRank Global,
addepar UK, affinipay Czech ×2, Affirm Canada, Serve Montreal); marketing-remote
(GitLab-EMEA, StubGroup non-US in a tiny 8-row inbox).

**Minimal fix:** in `_location_score`, when the remote string carries an explicit
non-US country/region token (`czech|canada|uk|emea|latam|europe|...`) and the
user's target is a US metro, cap the remote credit (e.g. return 1, `l≈0.33`)
rather than 3 — OR add a `restriction` derived from the _location label_ (not just
body) so the existing `gate._FOREIGN_RESTRICTION` catches it. A small
"non-US remote" location-label regex feeding `facts._detect_restriction` closes
both the local-score and the AI-gate holes at once.

---

### (3) Entry-level configs do not down-rank senior titles (same root as #1)

**CONFIRMED.** `seniority_target=entry` / `years_cap=3` feed the **AI rubric**
(`match/rubric.py` → `gate.years_cap`, gate.py:53-56) but never reach the **local**
`score_job`. `score_job` has no `seniority_target` parameter at all (signature
scorer.py:462-477); the only seniority lever is `_seniority_fit_adj`, which
(per #1) does nothing for a non-management target. So a career-changer's
"entry-level, ≤3 yrs" config leaves a "Senior Data Analyst" and a plain "Data
Analyst" tied at `title 100%`.

**Impact:** data-changer-phoenix — 8+ Senior/Sr/Lead/Principal roles clustered at
the very top of a self-declared entry inbox; the config "barely touches the local
keyword scorer" (persona's own words, matches code).

**Minimal fix:** same as #1 — wire `seniority_target`/`years_cap` from the config
into a graded local-score nudge via `facts._detect_seniority` +
`facts._detect_required_years` (both exist and are correct). Entry target + a
`8+ yrs`/`III`/`Sr.` posting → negative nudge.

---

### (4) Title-family ambiguity — "engagement manager" flooded a consultant top-40

**CONFIRMED (reproduced).** With a consultant keyword set including "engagement
manager", the scorer returns an **identical 94** for: "Engagement Manager-
Management Consulting" (real), "AWS ProServe Engagement Manager" (cloud delivery),
"Community Engagement Manager" (outreach), "Customer Success Engagement Manager"
(SaaS CS), and "Provider Education & Engagement Manager" (medtech sales). All
`title 100%` — the literal two-word phrase matches regardless of domain.

The `_GENERIC_TITLE_TERMS` single-word cap (scorer.py:43-48,237-238) does **not**
help: it only caps a match on a _lone_ generic word, and "management" is in the
set but "engagement" is not; the phrase matches as a unit so the cap never
engages. There is no title-family / domain disambiguation in the local scorer.

**Impact:** consultant-chicago — ~19 of top-40 (~48%) false positives, ~12 AWS
ProServe EM rows took the top 3 slots at 91-93 on title+salary alone, burying
true strategy EMs.

**Minimal fix:** this is genuinely the fuzzy case the BYO-AI Fit pass is designed
for — flag it as _the_ highest-value AI use for consulting rather than trying to
hand-code the taxonomy. A cheap local half-measure: an optional per-profile
`title_context_required` list (e.g. "consulting","strategy","advisory") that,
when set, caps title credit for an ambiguous head term ("engagement manager")
unless a context token co-occurs in title/description. `industry_profile`'s
consulting `title_terms` (industry_profile.py:128-131) already lists the right
context words; reuse them.

---

### (5) Sub-floor salary in description text slips the salary hard-gate

**CONFIRMED (reproduced).** Two-part defect:

- `hard_gate` (preferences.py:127) drops a job only when
  `top = salary_max or salary_min` is a positive number below `salary_min`.
  A job whose only comp signal is the `salary_text` field "$18,000+" parses to
  `(None, None)` (verified: `salary_from_text("$18,000+") == (None, None)`— a
lone figure with a trailing`+`and no range endpoint isn't captured by`_SALARY_RE`/`_SALARY_RE_BARE`), so `top=None` → **kept** past a $90k floor.
- The gate never reads the **description body**. Reproduced: a BlueBox-style row
  with API salary fields empty and body "Compensation: US$1,500 per Month"
  **survives** a $90k floor with `remote_ok=True`. Notably
  `salary_from_text("US$1,500 per Month") == (18000.0, None)` (monthly ×12 works,
  scorer.py:307-322) — so the info to catch it EXISTS, but neither the gate nor
  `score_job`'s salary-fill (scorer.py:498-501, which only fills when _both_
  API fields are None) feeds a body-derived floor back into the hard cut.

Gate/scoring order confirmed in `daily_run.py`: `ranker.gate` (line 353) runs
**before** `score_jobs` (line 388), so at gate time the body salary hasn't even
been parsed.

**Impact:** marketing-remote — a real US$1,500/mo (~$18k) role passed a $90k floor
and landed in the 8-row inbox top-4.

**Minimal fix:** in `hard_gate`, when a job's API salary fields are empty, run
`parse_comp(job.description)` (already annualizes hourly/weekly/monthly) and gate
on that annualized floor too. Guard it to only DROP on a _confident_ sub-floor
parse (both endpoints or a single clearly-periodized figure) so an ambiguous
mention never over-cuts the wide net.

---

### (6) Location gate trusts the source label (Adzuna stamps the query location)

**CONFIRMED (reproduced).** `hard_gate` (preferences.py:133-135) gates on
`job.location` — the source-provided label. Adzuna copies the _query_ location
onto every posting, so an out-of-area/out-of-state role is labeled the target
metro and passes. Reproduced: a Tennessee "Teacher" labeled "Columbus, Franklin
County" **survives** a `locations=['Columbus, OH']`, `remote_ok=False` gate.
`facts._detect_restriction` returns `None` for a label-only mislabel (it reads
body phrasing only), so nothing reconciles label vs. body.

**Impact:** teacher-columbus (3 out-of-state Adzuna mis-stamps in top-40),
nurse-boise (a Montana RN scored 71, an Eastern-Idaho ~250mi role, 6 Twin-Falls
GCU faculty — all labeled "Boise County"), mecheng-seattle (a Butte, MT ME role
labeled "Seattle, King County" scored 64). This is an upstream data-quality
issue, but the app _trusts_ it with no cross-check.

**Minimal fix:** a "verify location against description" pass — when the body
names a city/state that contradicts the label (extract the first `City, ST` in
the description), demote or flag the row. Cheapest form: a scorer note
`loc-unverified` + a modest location-credit cap for Adzuna rows whose body's
detected state != the label's state. Do NOT hard-drop (the body parse is
best-effort); a downrank preserves the wide net.

---

### (7) industry_profile / SOC resolution holes

**CONFIRMED (all sub-claims reproduced via `resolve_soc`/`resolve`):**

| free-text industry                            | `resolve_soc`                                      | note                                            |
| --------------------------------------------- | -------------------------------------------------- | ----------------------------------------------- |
| `nursing`                                     | **None**                                           | only `nurse`/`registered nurse` → 29-1141.00    |
| `digital marketing`                           | **None**                                           | falls through to seed marketing profile, no SOC |
| `demand generation manager`                   | **11-3051.06 "Hydroelectric Production Managers"** | the exact mis-resolution cited                  |
| `growth marketing manager`                    | None                                               |                                                 |
| `management consulting`                       | **None**                                           | `consulting` also None                          |
| `warehouse`/`logistics`/`warehouse logistics` | **None**                                           | no warehouse/logistics SOC or profile           |
| `data analytics`                              | None                                               |                                                 |
| `math teacher`                                | 25-1022.00 **Postsecondary**                       | wrong level for 7-12                            |

Root causes in code:

- `industry_profile.resolve_soc` (industry_profile.py:384-399) →
  `_match_onet` → `_onet_table_lookup` (industry_profile.py:309-336): a
  **deliberately literal** exact/singular-plural dict lookup (no fuzzy match — the
  docstring explains fuzzy hands out confident-but-wrong SOCs). So "nursing",
  "management consulting", "digital marketing", "warehouse logistics" don't
  literally appear in the O*NET alt-title table → None. The literal design is
  _correct for routing safety_ but leaves these common natural phrasings
  unresolved.
- `demand generation manager` DOES literally match an O*NET alt title that maps
  to Hydroelectric Production Managers (11-3051.06) — a genuine O*NET-data
  collision the literal matcher can't defend against.
- `workspace._attach_onet_soc` (workspace.py:345-365) is best-effort/additive: a
  None resolution silently writes no `onet_soc_code`. So for nursing/consulting/
  warehouse/data-analytics users, the SOC-major-group routing
  (`SOC_MAJOR_GROUPS`, industry_profile.py:177-201) and the facts-cache SOC
  entropy (`_profile_sig`, facts.py:311-327) never engage.
- **No warehouse/logistics `_RULES` entry** exists (industry_profile.py:81-166);
  the `transportation` rule (line 155-159) _does_ include "warehouse"/"logistics"
  tokens and would resolve `warehouse logistics` to a seed profile via token
  intersection — but with **no query_synonyms** (`syn: []`), so keyword-broadening
  is a no-op for that field (matches warehouse-memphis's finding).

**Note the seed-profile safety net:** even where SOC = None, `resolve()` returns a
usable **seed** profile via token intersection (source=seed) for nursing,
consulting, marketing, warehouse, data — so genre routing (Muse/Jobicy) mostly
still works. The SOC hole's real cost is (a) lost SOC-major-group routing for
O*NET-only fields, (b) no facts-cache isolation key, (c) the wrong-level
`math teacher` → Postsecondary, and (d) the Hydroelectric mis-resolution if a user
lets auto-detect set industry from a title.

**Minimal fixes:**

- Add explicit `_RULES` synonym seeds for the natural phrasings: `nursing` (map to
  the existing nurse rule's synonyms), `management consulting` (consulting rule
  already has `syn`), `digital marketing` (marketing rule), `warehouse`/`logistics`
  (add `syn: ["warehouse associate","material handler","distribution",
"forklift"]` to the transportation rule and a `titles` warehouse set).
- Add a **negative guard** for `demand generation manager` → Hydroelectric: since
  this is one bad O*NET row, either blocklist that specific alt-title→SOC mapping
  for the marketing token-set, or require the resolved SOC's major group to be
  plausibility-checked against the industry tokens before persisting
  (a "marketing" industry resolving to SOC 11-3051 energy is incoherent → reject).
- For `math teacher` → Postsecondary, add a K-12 seed synonym so secondary-teacher
  queries don't inherit a postsecondary SOC.

---

## Where the BYO-AI re-rank correctly compensated (the designed mitigation)

Every persona report states the AI Fit pass fixed exactly these blind spots:

- **swe-newgrad-austin:** AI re-rank demoted the Sr./III over-levels and the
  non-US remotes; "a new grad trusting the raw Score would apply to a Sr. role and
  a Czech-only remote job."
- **nurse-boise:** AI "cleanly demotes all 9" wrong-state/wrong-role rows.
- **teacher-columbus:** AI "demoted every OSU/childcare/out-of-state row and
  floated the true math/coach seats the raw Score buried at 64-67."
- **consultant-chicago:** the engagement-manager family is "exactly the gap the
  BYO-AI Fit round-trip is meant to close and is the highest-value AI use."
- **warehouse-memphis:** AI demoted the 12 domain-false-positives to Fit 12-30 —
  "the textbook 'high Score, low Fit' the Guide describes."
- **mecheng-seattle / data-changer-phoenix / marketing-remote:** same — AI
  re-rank demoted the "design"-token software/UX bleed, the senior over-levels,
  and the region-locked remotes.

**The exposure is the no-AI user.** The raw `Score` alone systematically misleads
on seniority (#1,#3), country-blind remote (#2), title-family (#4), sub-floor
comp (#5), and label-trusted location (#6). The product's own Guide instructs the
user to run the AI pass, which is the honest mitigation — but a keyless user's
top-of-inbox is where every false-positive family clusters.

---

## Priority ranking of fixes (local-scorer honesty for the no-AI user)

1. **#1/#3 seniority (S–M):** wire `facts._detect_seniority` +
   `_detect_required_years` into a graded local down-nudge keyed on the config's
   `seniority_target`/`years_cap`. Highest reach — hits SWE, data, teacher, nurse
   personas. Detectors already exist and are correct.
2. **#2 country-blind remote (S):** cap `_location_score` remote credit (or add a
   label-derived non-US `restriction`) when target is US and the remote string
   names a non-US region. One regex.
3. **#5 sub-floor salary (S):** have `hard_gate` parse `description` via
   `parse_comp` when API fields are empty; drop only on a confident sub-floor.
4. **#6 label-trusted location (M):** description-vs-label state cross-check →
   downrank/flag (never hard-drop). Catches the Adzuna query-stamp family.
5. **#7 SOC/profile holes (S each):** add seed synonyms for nursing/consulting/
   digital-marketing/warehouse; guard the Hydroelectric mis-resolution; K-12
   teacher SOC.
6. **#4 title-family (M / mostly AI):** optional `title_context_required` per
   profile reusing `industry_profile.title_terms`; otherwise document as the
   flagship BYO-AI use for consulting.

All findings are localized to `match/scorer.py`, `preferences.py`,
`search/search_engine.py`, `match/facts.py`, `industry_profile.py`, and
`workspace.py`; none require touching the wide-net fetch layer.
