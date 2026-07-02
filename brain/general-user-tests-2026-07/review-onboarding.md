# Onboarding & Time-to-Value Review — 8 Blank-Slate Personas (2026-07)

**Lens:** onboarding and time-to-first-value. What does a stranger experience from install to a genuinely useful inbox, and what changes get them there fastest?

**Method:** read all 8 persona narratives + `_structured-results.json`; verified every load-bearing claim against source (`ui/setup_wizard.py`, `workspace.create_project`, `scrape/company_registry.py`, `gui.py` `AddCompaniesDialog`, `ui/source_keys.py`, `ui/help.py`, `search/*_client.py`, `industry_profile.resolve_soc`). Read-only throughout; no source, projects, companies.json, or trackers modified; no daily_run/gui/setup_lanes run.

---

## 1. Headline verdict

The app is **installable, the wizard is clear (8–9/10 across every persona), and setup is fast (~18 min median).** Every persona reached a working inbox and said they would stay. But time-to-**genuinely-useful**-inbox splits sharply along one axis: **do the free keyed aggregators (Adzuna + CareerOneStop) work for you, and does your field label happen to be one word?**

- **Tech / white-collar personas** (SWE, consultant, marketer, mech-eng, data-changer) got a usable inbox in one run because Adzuna carried it — but rode ~95–100% on a single source and never noticed.
- **Non-tech, on-site personas** (nurse, teacher, warehouse) are the intended "make it easy for everyone" audience, and they are exactly the ones the current onboarding underserves: the Guide's own #1 free source for them (CareerOneStop) is **unkeyed out of the box, never nudged, and silently does nothing.**

The through-line of every persona's biggest gap is not the ranking (BYO-AI fixes that) — it is **onboarding sequencing**: the two things that decide whether the inbox is useful (turn on the right free keys; add local employers that actually scrape) are both left to the user to discover after setup, and both quietly fail for the users who need them most.

---

## 2. Setup friction — verified

### 2.1 `create_project` does NOT scaffold `preferences.{json,md}` — CONFIRMED

Claimed by SWE-Austin, teacher-Columbus, mech-eng-Seattle. **Verified:** `workspace.create_project` (`workspace.py:397-450`) writes `config.json`, an `experience.md` stub (`_EXPERIENCE_STUB`), and `output/` — and nothing else. `workspace.preferences_paths()` (`workspace.py:315`) only _returns_ the paths; it does not create the files. The ONLY writer of `preferences.{json,md}` is the wizard's `apply()` (`ui/setup_wizard.py:352-356`).

**Onboarding impact:** for a **GUI user this is invisible** — the wizard's `apply()` writes preferences before the first search. The gap only bites a **programmatic setup path** (what the persona harness and any future scripted/AI-assisted onboarding uses). It is a real footgun for the roadmap's "AI-assisted setup/seeding" direction: any code that calls `create_project` and then a search will hard-gate on an empty/absent preferences contract. Fix is cheap and localizes the invariant.

### 2.2 The wizard's field-examples list is tech/health-only — CONFIRMED, high-friction, cross-persona

`ui/setup_wizard.py:518-519` shows field examples: **"health informatics · nursing · finance · controls engineering"**. Roles examples (`:491`) add "registered nurse, controls engineer, staff accountant, HVAC technician, UX designer."

Personas who flagged that their field wasn't represented and they had to guess: **SWE** (no "software"/"software engineering"), **consultant** (no consulting example), **marketer**, **warehouse**, **data-changer**. This matters more than a cosmetic nit because **the field box is load-bearing** (`ui/help.py:105-108`: it routes sources, toggles feeds, tunes ranking, and — via `AddCompaniesDialog`'s default tag — decides whether seeded employers are even searchable). A user who guesses a two-word label silently trips §2.4.

### 2.3 Field label mostly does NOT resolve to an O*NET SOC code — CONFIRMED

`workspace._attach_onet_soc` (`workspace.py:345`) and the wizard's `_derive_industry` (`setup_wizard.py:49`) both call `industry_profile.resolve_soc`. Verified live:

| user types                                       | resolve_soc result                                           |
| ------------------------------------------------ | ------------------------------------------------------------ |
| `nursing`                                        | **None** (only `registered nurse` → 29-1141.00)              |
| `education`, `education (K-12)`                  | **None** (`math teacher` → 25-1022.00, wrong: POSTSECONDARY) |
| `management consulting`, `consulting`            | **None**                                                     |
| `warehouse operations`                           | **None**                                                     |
| `digital marketing`                              | **None** (`marketing manager` → 11-2011.00)                  |
| `data analytics`                                 | **None**                                                     |
| `software engineering`, `mechanical engineering` | **None**                                                     |

The natural field word a general user types resolves for **almost no one**. `_attach_onet_soc` no-ops silently (by design, additive), so the SOC that would sharpen title scoring is usually absent. Not a crash — but it means the "tell the app your field" step under-delivers unless the user happens to type the exact O*NET occupation title. Genre/text routing still works, so this is a sharpen-not-break gap; still worth widening resolve_soc's aliases for the common field words above.

### 2.4 Multi-word field label makes seeded companies INVISIBLE — CONFIRMED, persona-blocking (warehouse, mech-eng, data-changer)

The single worst onboarding-adjacent bug. `scrape/company_registry.get_registry` (`:287`) normalizes the industry key `spaces→underscores` (`"mechanical engineering"→"mechanical_engineering"`), but `_industry_tag_match` (`:234`) compares that to the **un-normalized** company tag (`AddCompaniesDialog._add` stamps the raw field string `["mechanical engineering"]`, `gui.py:2437`). Verified empirically:

```
_industry_tag_match('mechanical_engineering','mechanical engineering') -> False
_industry_tag_match('data_analytics','data analytics')                 -> False
_industry_tag_match('warehouse_logistics','warehouse logistics')       -> False
_industry_tag_match('logistics','logistics')                           -> True   # single-word OK
```

**Effect:** a general user with any 2+word field ("mechanical engineering", "data analytics", "warehouse logistics") adds employers via + Add Companies, sees "Added N companies," and then those companies are **never scraped** by their own project — `industry_company_count` stays flat and daily_run logs "only 0 registry companies match." Warehouse-Memphis seeded 17 and got 0 careers rows; mech-eng-Seattle seeded 8 verified employers → 0; data-changer added 15 → count stayed 8. The starter registry tags are single-token (`controls_engineering`) so single-project eng users never hit it, which is why it survived to production. One-line fix (`t.replace(' ','_')` inside `_industry_tag_match`, symmetric).

### 2.5 Career-level combobox is a flat 4-item enum — CONFIRMED, minor

`_LEVELS = ("", "Entry", "Mid", "Senior", "Manager/Exec")` (`setup_wizard.py:302`, readonly at `:513`). Teacher-Columbus noted it has no notion of a teacher→coach→curriculum ladder; only the free-text "Anything else" box can express non-corporate progression. Acceptable, but the field-agnostic goal argues for letting the "about" box carry level nuance for non-corporate careers (it already feeds the AI rubric).

### 2.6 Remote-only location is a dead-end on the keyed aggregators — CONFIRMED (marketer)

`_step_where` (`:544`) offers a free-text city + a "Remote jobs are fine too" checkbox, but **no remote-only mode**. Marketing-remote typed "Remote" as the city → Adzuna and USAJobs both returned 0 (they geocode the city string), leaving her with 8 jobs from WeWorkRemotely/RemoteOK + self-seeded pages. She is the ONE persona who said the app did **not** beat manual (`beats_manual: false`) — a remote knowledge-worker gets more from one LinkedIn scroll. The remote path leans entirely on keyless remote boards + seeding; the wizard's UX actively steers the user into the failing config (type a city that geocodes to nothing).

---

## 3. Wizard clarity — scores & what actually worked

| persona              | clarity | setup min | beats manual? | would stay? |
| -------------------- | ------- | --------- | ------------- | ----------- |
| SWE new-grad Austin  | 8       | 18        | yes           | yes         |
| RN Boise             | 9       | 18        | yes           | yes         |
| HS teacher Columbus  | 8       | 18        | yes           | yes         |
| Consultant Chicago   | 9       | 18        | yes           | yes         |
| Warehouse Memphis    | 8       | 22        | yes           | yes         |
| Remote marketer      | 8       | 18        | **no**        | yes         |
| Mech-eng Seattle     | 8       | 18        | yes           | yes         |
| Data-changer Phoenix | 8       | **40**    | yes           | yes         |

**Consistently praised (real strengths, keep them):**

- Five plain-English steps, ~1 minute; explicit "you always click submit yourself, data stays on this computer" reassurance (`:463-469`).
- **Hourly-wage parsing** (`parse_salary_input`, `:74`): "18/hr" and a bare "18" both annualize at 2080h — a genuinely thoughtful touch for the warehouse/nurse audience.
- **Plain-text resume auto-structuring** (`structure_resume_text`, `:137`): a pasted un-headed resume can't crash later scoring. Data-changer noted a cosmetic miss (contact block left un-wrapped, "DATA ANALYTICS BOOTCAMP" not recognized as a heading) — no data lost.
- The **in-app Guide (`ui/help.py`) is repeatedly called "excellent" and "honest"** — it openly says the free feeds lean toward remote tech, names the two keys that matter, and has a strong "add your local employers" section.
- **`_maybe_offer_discovery`** (`:721`) does pop a "there aren't any {field} employers in the starter list — Build My List" nudge for empty-registry fields. A real mitigation the personas under-credited.

**Clarity ceiling:** every score is capped at 8–9 by the _silent_ stakes — the wizard doesn't tell the user that (a) the field box is load-bearing, (b) location becomes a hard gate, (c) the best free source for their field is off until they go find it.

---

## 4. The key-signup experience — the biggest time-to-value lever

### 4.1 What matters, and what silently happens when absent

Verified self-skip behavior (all non-fatal warnings, run exits 0):

| source                | key(s)                        | in `.env.example`? | in-app key box? | wizard nudge? | when absent                                                       |
| --------------------- | ----------------------------- | ------------------ | --------------- | ------------- | ----------------------------------------------------------------- |
| **Adzuna**            | `ADZUNA_APP_ID/KEY`           | **yes**            | yes             | no            | the whole local inbox for most personas                           |
| **CareerOneStop**     | `CAREERONESTOP_USER_ID/TOKEN` | **NO**             | yes             | **no**        | silent skip ("credentials missing", `careeronestop_client.py:90`) |
| USAJobs               | `USAJOBS_API_KEY/USER_AGENT`  | yes                | yes             | no            | silent skip (federal only)                                        |
| Jooble                | `JOOBLE_API_KEY`              | **NO**             | yes             | no            | silent skip (`jooble_client.py:29`)                               |
| Careerjet             | `CAREERJET_AFFID`             | **NO**             | yes             | no            | silent skip                                                       |
| Brave (discovery)     | `BRAVE_SEARCH_API_KEY`        | yes                | —               | no            | company auto-discovery off                                        |
| SerpApi (reach badge) | key                           | no                 | —               | no            | "reach: cannot certify"                                           |

### 4.2 The CareerOneStop gap is the single highest-impact onboarding fix

The in-app Guide (`ui/help.py:73-82`) names **CareerOneStop as one of "the two keys that matter most"** — "the best free source for teachers, nurses, government, trades, and every other job that never shows up on tech boards." Yet:

1. It is **not in `.env.example`** (only Adzuna/USAJobs/Brave are), so a user who configures via the file never learns it exists.
2. The **setup wizard never mentions it** — no step routes the user to the "Connect job sources" dialog at all.
3. It **silently self-skips** when unkeyed, contributing 0 with only a warning line buried in console noise.

This lands squarely on the three personas the "easy for everyone" goal exists for. **Nurse-Boise:** RNJobSite returned 244 postings but 0 survived the Boise gate; without keys she'd get ~7 federal-only jobs; her stated #1 fix is "make CareerOneStop work out of the box." **Teacher-Columbus:** K-12 district jobs live on Frontline (no scraper) + NEOGOV (ToS-blocked), so CareerOneStop is "the whole ballgame" and it's dark. **Warehouse-Memphis:** Indeed is ToS-blocked (the dominant blue-collar board), marquee employers are on CSRF Workday, so the DOL feed is the equalizer — unkeyed. **Data-changer-Phoenix:** the marquee local employers (Banner Health, Dignity, ASU, city/county) never arrive, "forcing the user back to LinkedIn."

**Good news for the fix:** the plumbing already exists. `ui/source_keys.py` ("Connect job sources…", Tools menu, `gui.py:3707`) exposes every key including CareerOneStop, with a live **test** button and a direct link to the free registration page. The gap is 100% **discoverability + sequencing** — the wizard never funnels the user there, and it isn't ranked by impact. This is a UX wiring change, not new infrastructure.

---

## 5. AI-assisted "+ Add Companies" seeding — probe is advisory, not a gate — CONFIRMED

Verified end-to-end: `AddCompaniesDialog._validate_worker` (`gui.py:2402`) calls `scrape.ats_detect.probe_count` and sets each row's status cell to `live (N)` / `unreachable` / `direct (manual)` — **display only**. `_add` (`gui.py:2428`) then calls `save_companies(self._entries)` with the **full** list; `save_companies` (`company_registry.py:189`) dedups only by `(ats_type, slug)` and name — **it never consults the probe result.** So every parsed line — including probed-unreachable boards and outright junk — is written to `companies.json`.

Measured across personas: SWE wrote 5 unreachable + 2 junk; nurse 4 dead ATS guesses; teacher 11 dead slugs; consultant 16 dead; warehouse 9 unreachable + 1 junk; mech-eng rejected 6 only because they were already-present dups, not because of the probe. The dead entries silently persist and re-throw soft `NameResolutionError`/`gone → skipping` on **every subsequent daily run.**

**Two onboarding consequences:**

1. **The AI-slug guessing gap is real and structural.** A chat-only AI reliably produces company _names_ but the ATS _slug_ is a coin-flip (SWE got 5/13 wrong; nurse 4/4 wrong; the biggest local employers a career-changer/nurse/warehouse worker wants are on CSRF-protected Workday whose tenant slug isn't derivable from a public careers URL). So the headline "ask your AI for 25 employers, paste them in" flow yields **names but few live boards** for exactly the non-tech users it's pitched to.
2. **The Guide makes a promise the code breaks.** `ui/help.py:103` tells the user: _"Anything the AI got wrong simply fails verification — nothing bad can sneak in."_ But nothing is gated on verification — the failed guesses ARE saved and re-scraped forever. The Guide's safety claim is false as written.

**Fix direction:** either (a) add an "Add only validated" checkbox / default to gating on `live (N)` and `direct`, or (b) if keeping the advisory design, correct the Guide copy and mark unreachable rows visually + let the user one-click prune them. Combined with §2.4 (multi-word tag invisibility), a general user can currently do everything right and still get 0 usable seeded coverage.

---

## 6. Real time-to-first-VALUE, per persona

"Value" = a scored inbox of jobs the user would actually apply to, without needing to go add keys/employers they were never told about. Rated from each persona's own run data.

| persona              | inbox rows | source reliance               | time-to-useful                                                                                                                | verdict                                                           |
| -------------------- | ---------- | ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| Consultant Chicago   | 196        | ~95% Adzuna                   | **Fast** — dense same-day inbox; role-disambig is a rank problem (BYO-AI fixes)                                               | one-source-fragile but immediately useful                         |
| SWE Austin           | 141        | Adzuna 47% + careers 45%      | **Fast** — seeds (Ramp/Homeward) reached top 40; strong day-one                                                               | best-served; ~3% of the SWE universe though                       |
| Data-changer Phoenix | 77         | ~86% Adzuna                   | **Fast inbox, slow to the RIGHT jobs** — 40-min setup (learning curve), Senior titles flood the top; marquee employers absent | useful triage, still opens LinkedIn                               |
| Warehouse Memphis    | 53         | **100% Adzuna**               | **Fast, but fragile** — careers path added 0 (bug §2.4); one keyed source away from empty                                     | genuinely useful for triage; one bug + one key from great         |
| Teacher Columbus     | 49         | Adzuna ~100%                  | **Adzuna-only** — CareerOneStop dark, districts unscrapeable                                                                  | useful for charters/Adzuna; misses public districts entirely      |
| Mech-eng Seattle     | 32         | ~81% Adzuna                   | **Fast local inbox**, but 8 verified employers never searched (bug §2.4)                                                      | Adzuna-only in practice                                           |
| Nurse Boise          | 29         | Adzuna 76% + USAJobs 24%      | **Thin** — nurse feed 0 through the gate; without keys → ~7 federal jobs                                                      | useful but reliant on two keyed sources; CareerOneStop is the fix |
| Remote marketer      | **8**      | keyless remote boards + seeds | **Slow / unproductive** — Adzuna+USAJobs return 0 for "Remote"; half the 8 are tail noise                                     | **only persona that did NOT beat manual**                         |

**Pattern:** time-to-first-value is Fast when Adzuna works (city-based on-site search) and collapses when it doesn't (remote-only). The _depth_ and _durability_ of that value then depends entirely on keys and seeding the user was never guided to set up — which is why non-tech and remote personas plateau below where they should.

---

## 7. Prioritized onboarding fixes — install → useful inbox, fastest

Ordered by (impact on time-to-useful-inbox × breadth across personas ÷ effort).

### P0 — do these first

1. **Add a "Connect your best free sources" step to the wizard (or a mandatory post-finish card) that funnels into the existing `source_keys` dialog, impact-ranked.** Present Adzuna + CareerOneStop as "the two 5-minute keys that unlock local jobs in your field," each with the free-registration deep link and the live Test button that already exist. This is the highest-leverage change: it converts the Guide's advice into an in-flow action and directly rescues nurse/teacher/warehouse/data-changer. _Effort: S–M (wiring an existing dialog into the flow)._ Verified plumbing: `ui/source_keys.py`, `gui.py:3707/3956`.

2. **Add `CAREERONESTOP_*` (and Jooble/Careerjet) to `.env.example`, ranked with a one-line "best free source for non-tech/on-site jobs" note.** Currently absent — a file-configuring user can't discover the #2 key. _Effort: XS._

3. **Fix the multi-word industry-tag match (`_industry_tag_match`, `company_registry.py:234`).** Normalize the tag symmetrically (`t.replace(' ','_')`). Without this, every general user with a two-word field silently gets 0 careers coverage from their own seeded employers. _Effort: XS (one line + a test)._ Verified false for mechanical engineering / data analytics / warehouse logistics.

### P1 — high value, small–medium effort

4. **Make + Add Companies honor the probe (or tell the truth).** Default to gating `save_companies` on `live/direct` (add an "include unreachable" opt-out), OR keep advisory but (a) visually flag unreachable rows, (b) offer one-click prune, and (c) **fix the false Guide claim** at `ui/help.py:103` ("nothing bad can sneak in"). Stops dead slugs from persisting and re-erroring every run. _Effort: S–M._ Verified: `gui.py:2428` + `company_registry.py:189`.

5. **Broaden the wizard field examples to span the personas** (add software engineering, consulting, marketing, logistics/warehouse, data analytics, teaching) and add a one-line "this drives which sources and rankings you get" note at the field box. _Effort: XS._ `setup_wizard.py:518`.

6. **Add a real remote-only mode.** When "remote" is the intent, skip the geocoded aggregators' city gate (or query them with an empty location + remote flag) so a remote user isn't silently zeroed on Adzuna/USAJobs. This is what turned the marketer from "beats manual" to "doesn't." _Effort: M._ `setup_wizard.py:544` + the Adzuna/USAJobs clients.

### P2 — sharpening, lower urgency

7. **Widen `resolve_soc` aliases** so the natural field words (`nursing`, `education`, `consulting`, `warehouse`, `data analytics`, `digital marketing`) resolve to the right SOC, and fix `math teacher`→POSTSECONDARY. Sharpens title scoring; today it silently no-ops for most fields. _Effort: S._ Verified None for all six.

8. **Have `create_project` scaffold `preferences.{json,md}`** (or a documented shared helper the wizard and any programmatic/AI-assisted setup both call) so the preferences contract can never be missing. Invisible to GUI users today, but load-bearing for the AI-assisted-setup roadmap. _Effort: S._ `workspace.py:397`.

9. **Collapse the duplicate console skip/verify noise** (Jooble/Careerjet/CareerOneStop/Brave skip lines re-logged per page + rescore pass) so a non-technical user reading the run output can see real signal. _Effort: S._ (nurse/teacher both flagged.)

**Net:** P0 (1–3) alone would move the nurse, teacher, warehouse, mech-eng, and data-changer personas from "useful triage, still opens LinkedIn" to "genuinely useful inbox on day one" — because their gaps are unkeyed CareerOneStop + invisible seeded employers, both fixable in the onboarding flow with infrastructure that already exists.
