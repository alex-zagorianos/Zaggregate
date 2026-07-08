# Search Discovery — Plan

Base design: **corpus-mined / empirical keyword discovery** (highest judge-panel score, 3-way tally 19/19.5/17 across designs, explicit best-pick from Judge 3). This document takes that design as the spine and grafts in every idea the panel flagged, and neutralizes every fatal flaw the panel named against it (or accepts it as a documented trade-off, §7).

---

## 1. The problem, in one page

**P1 — the AI-setup ceiling.** The AI-assisted setup path asks the user's own pasted AI for a JSON block whose keyword field is capped at birth:

```
'  "target_titles": ["<job title I should search for>", "..."],\n'
```

[`src/ui/ai_setup.py:79`](../src/ui/ai_setup.py#L79), rule text _"1-5 real job titles"_ at [`src/ui/ai_setup.py:94`](../src/ui/ai_setup.py#L94), enforced by `_validate_titles()` which accepts any non-empty list but the **prompt itself never asks for more than 5** [`src/ui/ai_setup.py:178-192`](../src/ui/ai_setup.py#L178). Those titles flow, verbatim and uncapped downstream, straight into the live query set:

```python
roles = [r.strip() for r in answers.get("roles", []) if r and r.strip()]
if roles:
    cfg["keywords"] = roles
```

[`src/ui/setup_wizard_core.py:573-575`](../src/ui/setup_wizard_core.py#L573). The `field` key is similarly bottlenecked to 25 tokens: `CANONICAL_FIELDS` [`src/ui/ai_setup.py:40-47`](../src/ui/ai_setup.py#L40). There is no length cap anywhere downstream (`effective_keywords()` [`src/search/keyword_strategy.py:109-136`](../src/search/keyword_strategy.py#L109) takes whatever `cfg['keywords']` holds, no truncation) — **the ceiling is entirely in the prompt's wording**, which means it's fixable without touching a single line of the query pipeline.

**P2 — the no-AI vocabulary gap.** The manual wizard's role input is a free-text box requiring the user to already know their own industry's job-title vocabulary (`RolesStep.tsx` field picker is a plain 11-preset `<select>` [`src/ui/setup_wizard_core.py:504-517`](../src/ui/setup_wizard_core.py#L504), Tk twin same table). Nothing suggests titles. Nothing shows adjacent or exploratory options. Nothing tells the user whether a candidate keyword corresponds to any real, currently-open job before they commit.

**P3 — experience level is scoring-only, never a keyword input.** `_level_to_config()` [`src/ui/setup_wizard_core.py:548-558`](../src/ui/setup_wizard_core.py#L548) maps the 4-value level dropdown to `{seniority_target, allow_intern, years_cap, allow_management}` — pure rubric config, consumed by `match/gate.py` and `match/scorer.py`. It **never touches the query keyword set.** Meanwhile `keyword_strategy.deseniorize()` [`src/search/keyword_strategy.py:67-100`](../src/search/keyword_strategy.py#L67) actively _strips_ seniority tokens before a query is broadened, because seniority-laden titles collapse recall on Adzuna/USAJobs/etc. — a real, measured, and correct finding, but it means today's level control is a downstream filter only, disconnected from what actually gets searched.

---

## 2. What LinkedIn and Indeed actually do

**Caveat that governs this whole section:** none of LinkedIn's job-search mechanics below are officially documented by LinkedIn for the consumer search surface. Everything is reverse-engineered by third parties, unstable, and (per LinkedIn's User Agreement) off-limits to scrape. We are borrowing _design patterns_, not integrating with any of these endpoints. [source](https://gist.github.com/Diegiwg/51c22fa7ec9d92ed9b5d1f537b9e1107)

| Pattern                | LinkedIn (unofficial/reverse-engineered)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             | Indeed / our reality                                                                                                                                                                                                                                                                                                                  |
| ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Entity resolution      | Free text is resolved to a canonical numeric ID via typeahead (`f_C` company ID, `f_PP`/`geoId` place ID) before the facet ever hits the search index — the raw string is kept only as inert display metadata alongside the ID param. [source](https://www.linkedin.com/jobs/search/?f_PP=106224388&geoId=106224388)                                                                                                                                                                                                                                                                                 | Our clients send the literal keyword string with **no ID resolution** — `what=`, `Keyword=`, `keywords=` are all raw text (see table below).                                                                                                                                                                                          |
| Standardized titles    | Official, but gated: Talent Solutions partner `v2/titles` API exposes `urn:li:title:{id} → superTitle → function` (2-level hierarchy). [source](https://learn.microsoft.com/en-us/linkedin/shared/references/v2/standardized-data/titles) Requires an approved partner agreement — not a self-serve API.                                                                                                                                                                                                                                                                                             | Our closest analog is the bundled O*NET 30.3 alt-titles table, `src/data_static/onet_soc_alt_titles.tsv` (3,812,884 bytes, 50,992 lines, public domain/CC-BY 4.0), already wired via `industry_profile.resolve()`.                                                                                                                    |
| Title auto-expansion   | Confirmed official: LinkedIn Talent Insights documents ML-classified title standardization _including abbreviations_ (`"SWE" → "Software Engineer"`), then auto-expands a search to related standardized titles in that group. [source](https://www.linkedin.com/help/linkedin/answer/a187044/data-in-talent-insights) Whether the same expansion applies to the plain Recruiter title filter is **unconfirmed**.                                                                                                                                                                                    | Our `broad_query_keywords()` already does this at the industry-synonym tier (capped `_MAX_SYNONYMS=6` [`src/search/keyword_strategy.py:153`](../src/search/keyword_strategy.py#L153)) — same idea, smaller/local vocabulary.                                                                                                          |
| Experience-level facet | Two **non-interchangeable** enumerations exist: public URL `f_E=1..6` (unofficial, unverified live — a live test found `f_E=1` vs `f_E=6` returned near-identical results, inconclusive not disproof) [source](https://www.trykondo.com/blog/linkedin-job-search-hacks); vs. the official partner **Job Posting** API's `experienceLevel` string enum (`INTERNSHIP, ENTRY_LEVEL, ASSOCIATE, MID_SENIOR_LEVEL, DIRECTOR, EXECUTIVE, NOT_APPLICABLE`) used for posting ingestion, not search. [source](https://learn.microsoft.com/en-us/linkedin/talent/premium-job-posting/job-posting-field-schema) | **No client in our stack sends a seniority/experience facet to any vendor at all** — confirmed by direct read of `adzuna_client.py`, `jooble_client.py`, `careeronestop_client.py`, `jsearch_client.py`. This is a documented, deliberate choice (see `keyword_strategy.py`'s module docstring on `deseniorize()`), not an oversight. |
| Boolean syntax         | Scoped to free-text search only, never applied to structured facets, per LinkedIn's own documented split between facets and Boolean search.                                                                                                                                                                                                                                                                                                                                                                                                                                                          | Matches our own architecture exactly: `search/query.py`'s AND/OR/NOT/phrase engine is used **only** for post-fetch client-side matching (`match/scorer.py`, `scrape/text_match.py`) — never translated into any vendor's own query param.                                                                                             |
| Job-type facet         | `f_JT` (undocumented URL param) uses single LETTER codes `F/P/C/T/I/V` (includes Temporary, which the official partner-API enum omits entirely) — the official 5-value `FULL_TIME/PART_TIME/CONTRACT/INTERNSHIP/VOLUNTEER` enum belongs to a _different_, gated partner API and would silently fail if used on the URL. [source](https://github.com/spinlud/py-linkedin-jobs-scraper)                                                                                                                                                                                                                | Not modeled in Zaggregate today; out of scope for this feature.                                                                                                                                                                                                                                                                       |
| Time-posted window     | Rolling `r{seconds}` facet (`r3600`=1h, `r86400`=24h, `r604800`=week, `r2592000`=month) — a design pattern (recompute-cutoff-at-query-time), not a stable documented contract. [source](https://gist.github.com/Diegiwg/51c22fa7ec9d92ed9b5d1f537b9e1107)                                                                                                                                                                                                                                                                                                                                            | CareerOneStop already does this with a fixed 30-day window (`CAREERONESTOP_DAYS`); no change proposed here.                                                                                                                                                                                                                           |

**Which of OUR sources support which facets today** (ground truth from direct client reads, not LinkedIn's):

| Source                                                       | Keyword param                                   | Seniority facet | Location facet                               | Fan-out mode               | Rate limit                     |
| ------------------------------------------------------------ | ----------------------------------------------- | --------------- | -------------------------------------------- | -------------------------- | ------------------------------ |
| Adzuna                                                       | `what=` (literal string)                        | none            | `where=`                                     | `parallel_keywords=True`   | 25/min                         |
| USAJobs                                                      | `Keyword=` (literal)                            | none            | `LocationName=`/`RemoteIndicator=`           | parallel                   | 50/min                         |
| CareerOneStop                                                | path segment (literal, US-only)                 | none            | 25-mi radius, 30-day window                  | parallel                   | 20/min                         |
| JSearch                                                      | `query=f'{keyword} in {location}'`              | none            | folded into query string                     | parallel                   | 5/min + **200/month hard cap** |
| SerpApi                                                      | `q=f'{keyword} {location}'`                     | none            | folded into query                            | parallel (page>1 no-ops)   | 5/min + **250/month hard cap** |
| Himalayas                                                    | `q=` (literal)                                  | none            | fixed country filter                         | parallel                   | 5/min                          |
| EdJoin                                                       | `keywords=` (literal, real per-call)            | none            | ignored server-side, Python-side CA fallback | parallel                   | 5/min                          |
| Jooble / Careerjet                                           | `keywords=` (literal, real)                     | none            | `location=`                                  | **sequential**, not fanned | 10/min each                    |
| HN / LinkedInGuest                                           | `query=`/`keywords=` (literal)                  | none            | `location=`                                  | sequential                 | 10/min, 3/min (opt-in)         |
| TheMuse/RemoteOK/Remotive/Jobicy/Arbeitnow/WWR/WorkingNomads | **none** — single feed fetch, client-side match | none            | client-side                                  | N/A, cached whole-feed     | n/a                            |
| HigherEdJobs/RNJobSite/REAP/NSPE                             | fixed internal category list, client-side match | none            | client-side                                  | N/A                        | n/a                            |

**Bottom line for Search Discovery**: no vendor in LinkedIn's world or ours exposes a real seniority query facet worth wiring — the empirically-correct design keeps level out of the query string except as _tested, opt-in_ phrasing variants (§4.3), exactly as `deseniorize()` already assumes.

---

## 3. How it makes it easier for the user

### Two paths, one destination

```
                       ┌─────────────────────────────┐
                       │   keyword_pool (shared store) │
                       └──────────────┬────────────────┘
          ┌────────────────────────────┼────────────────────────────┐
          │                            │                            │
   [No-AI: type a field]      [AI: paste résumé, get reply]   [Optional: prefill from résumé]
          │                            │                            │
          └────────────────────────────┴────────────────────────────┘
                                       │
                          Discovery panel (chips, plain-language counts)
                                       │
                              Apply → cfg['keywords']
```

### Three personas, explicit "time to first search" targets

| Persona                                                                 | Entry point                                                                                                                                                                                           | Target                                                                                                               |
| ----------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| **Laid-off welder**, no résumé formatted for this, skeptical of jargon  | Types "welder" or "mechanic" into the field box, no AI                                                                                                                                                | **< 60 seconds** to a first search — sees plain counts, no SOC codes, no "yield"/"probe" language anywhere in the UI |
| **New-grad mech-eng**, doesn't know the industry's title vocabulary yet | Picks "Mechanical engineering" preset (still exists) or types it; gets adjacent/exploratory chips he'd never have typed himself (Test Engineer, Manufacturing Engineer, Product Development Engineer) | **< 2 minutes** including reading a few suggested chips                                                              |
| **Career-switching nurse**, résumé is full of the field she's leaving   | Explicitly ignores the "prefill from résumé" button (never a silent default, §7) and types her TARGET field instead                                                                                   | **< 90 seconds** — she is never auto-steered back into nursing                                                       |

### ASCII mock — Discovery panel (default/no-click state)

```
┌─ Find keywords ──────────────────────────────────────────────────┐
│  Field:  [ mechanic                                    ] 🔍       │
│                                                                    │
│  ── Core (searching now) ────────────────────────────────────────│
│  [x] Diesel Mechanic      [x] Automotive Technician  [x] Mechanic │
│                                                                    │
│  ── More like this ──────────────────────────────────────────────│
│  [ ] Fleet Maintenance Tech    [ ] Industrial Machinery Mechanic  │
│  [ ] Heavy Equipment Mechanic  [ ] Small Engine Repair Tech       │
│                                                                    │
│  ── Worth a look ─────────────────────────────────────────────────│
│  [ ] Field Service Technician   [ ] Maintenance Supervisor        │
│                                                                    │
│  💡 [ Prefill from my résumé ]        [ Check current openings ] │
│                                                                    │
│                                          [ Apply to my search ]   │
└────────────────────────────────────────────────────────────────────┘
```

### ASCII mock — after "Check current openings" (opt-in, costs real API calls)

```
│  ── Core (searching now) ────────────────────────────────────────│
│  [x] Diesel Mechanic         ~54 openings nearby                 │
│  [x] Automotive Technician   ~112 openings nearby                │
│  [x] Mechanic                ~340 openings nearby                │
│                                                                    │
│  ── More like this ──────────────────────────────────────────────│
│  [ ] Fleet Maintenance Tech   ~18 openings nearby                 │
│  [ ] Industrial Machinery Mechanic   hasn't found much lately     │
```

Note: no chip is ever hidden or removed for a zero/low count — "hasn't found much lately" is shown, not silence, matching **inclusion over precision**.

### ASCII mock — a week later, low-activity nudge (never silent removal)

```
│  ⚠ Low activity — "Small Engine Repair Tech" hasn't turned up     │
│     anything new in a week.        [ Turn off ]  [ Keep it on ]  │
```

---

## 4. How it works technically

### 4.1 The keyword pool — data assets, files, sizes, licenses, index format

| Asset                              | Path                                                                                                              | Size / rows                                                                         | License                                                                                            | Role                                                                                                                                                                                                       |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| O*NET alt-titles                   | `src/data_static/onet_soc_alt_titles.tsv`                                                                         | 3,812,884 bytes / 50,992 lines (verified `wc -l`)                                   | Public domain / CC-BY 4.0, O*NET 30.3                                                              | Existing zero-cost cold-start pool, reused as-is via `industry_profile.resolve()`                                                                                                                          |
| **NEW**: O*NET Related Occupations | `src/data_static/onet_related_occupations.tsv`                                                                    | est. low-single-digit MB (unmeasured — must be measured at build time, not assumed) | Same O*NET 30.3 release / license as the file above (pending independent re-confirmation, §7 risk) | Real cross-SOC relatedness graph (Primary-Short/Primary-Long/Supplemental tiers) — fixes the "adjacent = more alt-titles of the SAME SOC" weakness the judges flagged in the base design's cold-start tier |
| **NEW**: O*NET Technology Skills   | `src/data_static/onet_technology_skills.tsv`                                                                      | est. low-single-digit MB (unmeasured)                                               | Same O*NET 30.3 release                                                                            | Concrete tool/software skill chips (SolidWorks, Epic Systems, MATLAB) — better search keywords than abstract Skills.txt/Knowledge.txt competency labels, which are explicitly deferred to a v2 asset       |
| CBSA metro delineation             | `src/data_static/cbsa_delineation.csv`                                                                            | 46,014 bytes / 936 lines (935 CBSAs, verified)                                      | U.S. Census "List 1", public domain                                                                | Location resolution for the yield probe's geo param                                                                                                                                                        |
| Metro satellites                   | `src/data_static/metro_satellites.csv`                                                                            | 621 bytes / 31 rows, ALL one metro (Cincinnati, CBSA 17140)                         | Project-authored, no license                                                                       | Location-variant fallback — documented single-metro gap, not fixed by this feature                                                                                                                         |
| **NEW**: `keyword_pool` table      | `tracker.db` (SQLite, same DB as `applications`/`inbox` [`src/tracker/db.py:398-462`](../src/tracker/db.py#L398)) | 0 rows at cold start                                                                | Project-owned, user data (gitignored)                                                              | Live store: every candidate term, its tier, source, status, yield data                                                                                                                                     |

`keyword_pool` schema:

```sql
CREATE TABLE IF NOT EXISTS keyword_pool (
    id INTEGER PRIMARY KEY,
    term TEXT NOT NULL,
    tier TEXT NOT NULL,          -- core | adjacent | exploratory | negative
    source TEXT NOT NULL,        -- onet | related_soc | corpus | ai | manual | level_variant | resume
    status TEXT NOT NULL DEFAULT 'suggested',  -- suggested | active | inactive
    yield_count INTEGER,         -- last live-probed count, nullable
    yield_source TEXT,           -- e.g. 'adzuna:us-oh-cincinnati'
    yield_date TEXT,
    marginal_unique_7d INTEGER,  -- computed, not stored long-term; see §4.2
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    activated_at TEXT            -- NULL until user activates; drives the min-age guard (§4.2)
);
```

No index/index-format decision is needed beyond this: adjacency lookups are plain B-tree joins against the new tsv files (small — tens of thousands of rows, not the 50k-row O*NET title table), read through a **Tk-free** accessor module, not a compiled FTS index (deliberately simpler than the taxonomy-sqlite3 approach the judges flagged as unverified-in-frozen-exe risk).

```python
# src/search/discovery_core.py (new, Tk-free, follows the _core-split convention:
# see src/ui/setup_wizard_core.py:1-20 and src/ui/tab_search_core.py:1-13 for the
# established pattern this repo already uses)
```

### 4.2 The suggestion engine

**Cold start (zero network, zero prior data):**

1. `industry_profile.resolve(field)` [`src/industry_profile.py:625-701`] — existing, unchanged — resolves free-typed field text to a SOC code / `_RULES` entry.
2. Core tier = the matched `_RULES` entry's `query_synonyms` (only ~6 of 26 rules have real curated synonyms today — this is the highest-trust source) + the O*NET alt-titles for the resolved SOC.
3. **Adjacent tier = the NEW `onet_related_occupations.tsv` Primary-Short/Primary-Long relatedness graph**, not same-SOC alt-titles — this is the direct graft fixing the judges' #1 flagged weakness in the base design ("cold-start tier inherits the exact same same-SOC-only weakness... undercutting its own 'finds jobs you'd never have thought of' promise until corpus data accumulates").
4. Exploratory tier = Supplemental-tier related SOCs, or neighboring `SOC_MAJOR_GROUPS` (23 groups, [`src/industry_profile.py:279-318`]) when no seed rule exists.
5. Skill chips = the NEW `onet_technology_skills.tsv`, filtered to `hot_technology='Y'` first.

**All of this is fully offline and complete with zero API keys configured** — the guarantee judges asked for (Design 1's "network-free baseline tier" discipline).

**Live yield probe (opt-in, costs quota):**

- `probe_yield(term, location)` — ONE Adzuna page-1 call, `results_per_page=1`, reads the real `count` field. Never JSearch/SerpApi (hard monthly caps already strained by the daily reach probe, [`src/daily_run.py:123-183`]).
- **Fatal-flaw fix (jargon):** UI never shows the words "probe," "yield," or "marginal unique." Copy is "~N openings nearby" / "hasn't found much lately." Internal function/variable names may keep engineering terms; only user-facing strings are rewritten.
- **Fatal-flaw fix (mandatory click before core value):** the chip panel shows offline tiers immediately, no click required (§3 mock #1). Only the LIVE VERIFIED count is gated behind "Check current openings" — seeing _something_ is free; seeing a _verified number_ costs one click. This directly answers Judge 1's flagged friction ("requires an explicit extra click before the core differentiator appears").
- **Fatal-flaw fix (quota collision with the daily automated run):** the probe budget shares the SAME `RateLimiter` instance Adzuna's daily-run fetches already use ([`src/search/http_util.py`], `ADZUNA_RATE_LIMIT=25`/min, [`src/config.py:193`]), so probes are serialized against, not additive to, the daily run's own Adzuna traffic. A new persisted daily counter (mirroring `MonthlyQuota`, [`src/search/http_util.py:72-122`]) caps discovery probes at **10/day**, refreshed at midnight, deliberately conservative given Adzuna's 25/min ceiling must also cover the real automated run.

**Corpus mining (free, gated — fatal-flaw fix):**

- `mine_corpus()` reads the on-disk caches the single-fetch feeds already persist (TheMuse/RemoteOK/Remotive/Jobicy/Arbeitnow/WeWorkRemotely/WorkingNomads) plus a batched SQL frequency scan over `inbox`/`applications` titles.
- **Fatal-flaw fix (unconditional daily_run side effect):** `mine_corpus()` is **gated behind `cfg.get('discovery_enabled', False)`**, a new flag flipped to `True` the first time a user opens the Discovery panel. It is NOT called from `daily_run.py:run_main()` for a project that has never touched Discovery — "a user who never opens the panel pays zero cost" becomes true by construction, not by claim.
- **Fatal-flaw fix (private cache-format coupling):** rather than reaching into each of 7 clients' private cache internals by filename convention, add one new public method to the shared base each single-feed client already extends:
  ```python
  # src/search/single_feed_client.py — extend the existing base (already the
  # shared _cached() home, src/search/single_feed_client.py:52)
  def cached_titles(self) -> list[str]:
      """Public accessor for corpus mining: returns whatever titles this
      client's own cache currently holds, format-agnostic to the caller."""
  ```
  Each of the 7 feed clients implements this once (thin wrapper over its own `_cached()` payload) instead of `discovery_core.py` parsing 7 private formats — this is the `_core`-convention-consistent fix the judges asked for, at the cost of touching 7 files instead of 0.

**Provenance tagging:** the existing per-(client,keyword) fetch unit's matched keywords are unioned into the inbox row's **existing** `extras` JSON column [`src/tracker/db.py`] — purely additive, no schema change, so it cannot alter any existing run's score (preserves the byte-identical-unless-approved contract, protected by `tests/test_rescore_parity.py`-style regression tests, §6).

**Marginal-yield / low-yield flagging, with the judges' minimum-age-guard fix:**

```python
def compute_marginal_yield(term, window_days=7, min_age_days=7):
    """Only flags a term 'low yield' if BOTH:
    - it has been active >= min_age_days (a brand-new chip is never flagged —
      this is the fix for the judges' 'no minimum-activation-age guard' finding)
    - marginal_unique_7d == 0 (this term alone surfaced zero unique jobs)
    Deactivation is ALWAYS a user click. Never automatic."""
```

**Pruning (suggestions only, never active keywords):** unseen-and-inactive suggestions older than 90 days are dropped from `keyword_pool` to bound its growth. This rule is explicitly scoped to `status='suggested'` rows only — an `active` keyword is never pruned by this job, regardless of age or yield, full stop.

### 4.3 The experience-level model

Three consumers from one control, all pre-existing except the query-variant piece:

1. **Query-variant generation (NEW, additive only):** `level_query_variants(core_terms, level)` generates phrasing variants — but **only for `entry`/`mid`** (junior/associate/"Title I"), landing as `tier=exploratory, source=level_variant, status=suggested` — untested until probed/activated like any other candidate. **Fatal-flaw fix, stated as an explicit rule (graft from the Progressive Hybrid design, independently reinforced by Judge 3):** `senior`/`manager`/`exec` levels generate **zero** query-side variants, full stop — a unit test (`test_no_senior_query_variants`) asserts this, preventing the exact recall-collapse `deseniorize()` was built to guard against ([`src/search/keyword_strategy.py:67-100`]).
2. **Source queries:** any activated variant just rides the existing `parallel_keywords` fan-out ([`src/search/search_engine.py:179`]) — no vendor client changes, since none support a seniority facet (§2 table).
3. **Scoring rubric:** level continues, byte-identical, through the existing `_level_to_config()` [`src/ui/setup_wizard_core.py:548-558`] into `rubric.py`/`gate.py`/`scorer.py` — Search Discovery becomes a third caller of this exact function, protected by the existing parity suite (`test_scorer_seniority_target.py`, `test_rubric.py`, `test_rescore_parity.py`).

**Years-of-experience extraction** (existing, reused unchanged): `match/facts._detect_required_years()` — qualifier-anchored regex, rejects >30 as junk — feeds `gate.py`'s years-cap drop and `scorer.py`'s over-target nudge. No change.

**Negative/exclude keywords — the highest-risk item, resolved by direct code read (§ done in this doc, not deferred):**

`gate.py:48-51` confirms `hard_no_titles` **is a literal hard drop**:

```python
for bad in rubric.get("hard_no_titles", []):
    if bad and re.search(r"(?<!\w)" + re.escape(bad) + r"(?!\w)", tl):
        drops.append(f"excluded title: {bad}")
```

[`src/match/gate.py:48-51`](../src/match/gate.py#L48). Per the judges' explicit warning (Judge 3: _"if that key is in fact a hard filter... this design's flagship convenience feature would silently violate the one immovable rule"_), **negative chips must never write to `hard_no_titles`.** Instead:

- New cfg key: `cfg['suggested_excludes']` — a list of user-_confirmed_ (never auto-applied) exclude terms.
- Consumed ONLY as a new, additive, **downrank**-only lever in `scorer.py`, mirroring the existing `_seniority_target_adj` pattern ([`src/match/scorer.py:159-200`]) — a bounded negative score adjustment (e.g. `-6`, tunable), never a `gate.py` drop.
- A new test, `test_suggested_excludes_never_drops`, asserts a job matching a `suggested_exclude` term still appears in the inbox with a lower score — mirroring `gate.py`'s own documented "drop != hide" doctrine ([`src/match/gate.py:1-9`]).

### 4.4 API surface

New blueprint `src/webui/api/discovery.py` (`discovery_bp`), following the existing one-blueprint-per-feature convention (`onboarding.py`, `search.py`, `recommend.py`, [`src/webui/api/__init__.py`]).

| Route                                | Method               | Gate                                                                     | Purpose                                                                                                                              |
| ------------------------------------ | -------------------- | ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| `/api/discovery/propose`             | GET                  | ungated (pure read, mirrors `onboarding_state`/`salary-parse`)           | Offline tiers for a field/résumé signal                                                                                              |
| `/api/discovery/keywords`            | GET `?q=&limit=20`   | ungated                                                                  | Bounded typeahead over `_RULES` + O*NET tsv (exact/prefix only, never fuzzy — preserves the documented O*NET exact-match discipline) |
| `/api/discovery/pool`                | GET                  | ungated                                                                  | Current `keyword_pool` state for the active project                                                                                  |
| `/api/discovery/probe`               | POST `{terms:[...]}` | **gated** (`@require_local_origin` — consumes a live rate-limited quota) | Live Adzuna yield check, capped at 10/day                                                                                            |
| `/api/discovery/mine`                | POST                 | gated                                                                    | Manual corpus-mining refresh trigger                                                                                                 |
| `/api/discovery/keywords/activate`   | POST `{term}`        | gated                                                                    | Move a suggestion to `active`; writes through the SAME `setup_wizard_core._search_config()` contract, `cfg['keywords']`              |
| `/api/discovery/keywords/deactivate` | POST `{term}`        | gated                                                                    | Move `active`→`inactive`; removes from `cfg['keywords']`                                                                             |

Example response, `GET /api/discovery/propose?field=mechanic`:

```json
{
  "core": [
    { "term": "Diesel Mechanic", "source": "onet", "status": "suggested" },
    { "term": "Automotive Technician", "source": "onet", "status": "suggested" }
  ],
  "adjacent": [
    {
      "term": "Fleet Maintenance Technician",
      "source": "related_soc",
      "tier_score": "primary_short"
    }
  ],
  "exploratory": [
    {
      "term": "Field Service Technician",
      "source": "related_soc",
      "tier_score": "supplemental"
    }
  ],
  "skills": [{ "term": "OBD-II", "hot_technology": true }],
  "resolved_soc": "49-3023.00",
  "source": "onet"
}
```

Example, `POST /api/discovery/probe {"terms": ["Diesel Mechanic"]}`:

```json
{
  "results": [
    {
      "term": "Diesel Mechanic",
      "yield_count": 54,
      "yield_source": "adzuna:us-oh-cincinnati",
      "probes_remaining_today": 9
    }
  ]
}
```

Every mutating route is wrapped in `@require_local_origin` ([`src/webui/security.py:103-125`]) per the repo-wide enforced convention (a meta-test enumerates `app.url_map` and asserts `__origin_gated__` on every mutating route).

### 4.5 UI components

**Web:**

- `src/webui/frontend/src/tabs/search/KeywordPoolPanel.tsx` (new) — built entirely from existing primitives (`badge.tsx`, `button.tsx`, `card.tsx`, `sheet.tsx`) — **no new Radix dependency**, matching `select.tsx`'s documented deliberate native-only philosophy [`src/webui/frontend/src/components/ui/select.tsx:6-10`].
- Embedded as a collapsible panel/side-sheet inside `SearchTab.tsx` next to the existing "Set up with AI" button — explicitly NOT a second "Discover" tab (`DiscoverTab.tsx` is an unrelated BYO-AI career-recommendation feature; reusing the name would confuse the two, per the judges' explicit naming-collision warning).
- `RolesStep.tsx` in the onboarding wizard gets the same panel as its default view, replacing the bare `FIELD_PRESETS` `<select>`.
- Follows the `queries.ts` convention exactly: `queryKeys.discoveryPool`, `useDiscoveryPool()`, `useProbeMutation()`, `useMineMutation()`, `useActivateKeywordMutation()`, `useDeactivateKeywordMutation()`, typed wrappers in `api/client.ts`.

**Tk (parity, built for real — not deferred):**

- `src/ui/tab_search.py` gets a new "Discover keywords" button opening a `Toplevel` with a `Treeview` (term / tier / status / count) + Activate/Deactivate/Probe buttons, calling `src/search/discovery_core.py` functions **directly, in-process** — the same pattern `SearchTab` already uses for `search_job.run_search()`. This is a real, working Tk surface per this repo's established _core-split convention, not a "deferred" gap.

### 4.6 The call-budget math

Let `K` = active keyword count, `P` = daily discovery probe budget (capped at 10).

- **Discovery adds zero calls to the daily automated run** unless the user has activated new keywords — at which point those keywords are ordinary `cfg['keywords']` entries and cost exactly what any hand-typed keyword costs today (see the existing recon's per-source rate-limit table, §2).
- **Discovery's own live-probe cost is bounded and separate:** `min(terms_requested, P_remaining_today)` Adzuna page-1 calls, `results_per_page=1` (cheapest possible request shape). At `P=10`/day this is **at most 10 extra Adzuna calls/day**, against a 25/min limiter shared with, not additive to, the daily run — worst case adds ~24 seconds of serialized wait to a daily run that overlaps a probe burst (10 calls / 25-per-min ≈ 24s), negligible against the existing multi-minute run.
- **Corpus mining cost:** zero network calls (reads only already-fetched cache files + a batched SQL query, gated behind `discovery_enabled`).
- **Worked example — welder persona activates 6 core + 3 adjacent = 9 keywords, all through Adzuna (25/min):** 9 keywords × ~1 call/page × 2 pages (default `--max-pages`) ≈ 18 calls ≈ 43 seconds, same order of magnitude as today's default 5-10 keyword project. No change to the economics documented in the existing recon (JSearch 200/month, SerpApi 250/month hard caps stay untouched because Discovery never probes them).

---

## 5. Fixing the AI setup prompt

**Why the old one capped recall:** the prompt literally asks for _"1-5 real job titles"_ [`src/ui/ai_setup.py:94`] and the parser (`_validate_titles`, [`src/ui/ai_setup.py:178-192`]) accepts any non-empty list — there is **no code-level cap downstream** (`cfg['keywords']` is never truncated, [`src/ui/setup_wizard_core.py:573-575`], [`src/search/keyword_strategy.py:109-136`]). The ceiling exists purely in prompt wording. Fixing it is a text + parser change, zero pipeline risk.

**NEW PROMPT TEXT** (replaces `_config_block_body()`, [`src/ui/ai_setup.py:65-104`]):

````
You are setting up a job-search app for me. Below this prompt I will paste my
RÉSUMÉ and ONE SENTENCE describing the job I want.

I want MAXIMUM RECALL, not narrow precision — I will personally review and
prune anything irrelevant, so it is far better to give me too many candidate
titles than too few. Do not limit yourself to any fixed list of industries,
and do not limit yourself to a small number of titles.

Read them and return ONLY a single fenced code block (```json ... ```) with
EXACTLY these keys — no prose before or after:

```json
{
  "field": "<2-6 words describing my field/industry in plain language — NOT
             limited to any fixed list, just describe it>",
  "experience_level": "<one of: entry, mid, senior, manager>",
  "keywords": {
    "core": ["<3-8 job titles I'd confidently search on day one, using the
               exact phrasing a real job posting would use>"],
    "adjacent": ["<5-15 related or nearby titles — a different team, a
                   different seniority framing, or a closely related
                   discipline I probably qualify for. Cast a wide net.>"],
    "exploratory": ["<3-10 genuinely creative longer-shot titles — cross-
                      industry roles, alternate names for the same job,
                      emerging role names I might not have thought of. Be
                      bold here; these are for me to consider, not commit
                      to.>"]
  },
  "negatives": ["<0-10 terms that would clearly disqualify a posting for ME
                  specifically, e.g. 'unpaid' or 'commission only'. Leave
                  empty if none apply.>"],
  "location": {"city": "...", "state": "...", "remote_ok": true},
  "min_salary": <number or null>
}
````

Rules:

- "field" is free text — do not pick from a fixed list, just describe it.
- "keywords.core/adjacent/exploratory": be generous, not conservative. There
  is no length limit — more titles is always better than fewer.
- "negatives": suggestions only. Nothing will be auto-excluded from my search;
  I will review and confirm each one before it does anything.
- Return the block ONLY. Do not invent facts not supported by my résumé or
  sentence.

--- paste your résumé and one sentence of intent below this line ---

````

**PARSER CONTRACT CHANGE** (`src/ui/ai_setup.py`):

1. `CANONICAL_FIELDS` ([`src/ui/ai_setup.py:40-47`]) is **removed as a validation gate**. `_canonical_field()` ([`src/ui/ai_setup.py:120-149`]) already has a tolerant fallback — `industry_profile.resolve(val)` accepts any string whose `resolve()` source is `seed`/`user`/`onet`, only falling to `generic` (full-reach, never rejected) for a true non-match. This fallback becomes the **only** gate; `CANONICAL_FIELDS` remains solely as the manual wizard's dropdown suggestion list (`_FIELD_PRESETS`, unrelated file, unchanged).
2. New required object: `keywords: {core, adjacent, exploratory}` (each may be an empty list; only a non-array shape is rejected — no length is ever rejected as "too long," directly closing the P1 ceiling).
3. **Backward compatibility:** if a pasted reply still has the OLD shape (`target_titles: [...]`, no `keywords` key) — from a stale cached prompt or an older client — the parser treats `target_titles` as `keywords.core` (flattened), so nothing that worked before this change breaks:
   ```python
   def _parse_keywords_block(payload: dict) -> tuple[list[str], list[str]]:
       kw = payload.get("keywords")
       if isinstance(kw, dict):
           active = list(dict.fromkeys(kw.get("core", []) + kw.get("adjacent", [])))
           suggested = list(kw.get("exploratory", []))
           return active, suggested
       # legacy shape
       return _validate_titles(payload.get("target_titles")), []
````

4. Merge rule: `cfg['keywords'] = keywords.core + keywords.adjacent` (uncapped, matches the existing "no hard cap anywhere" invariant — confirmed no truncation exists in `daily_run.py`, `cli.py`, or `keyword_strategy.py`). `keywords.exploratory` is **not** written to `cfg['keywords']` — it upserts into `keyword_pool` as `source='ai', status='suggested'`, surfaced in the SAME Discovery panel the manual path uses (converging the two onboarding paths onto one review UI, per the judges' explicit "AI is optional sugar, not a separate mode" framing).
5. `negatives` folds into `cfg['suggested_excludes']` (§4.3), **never** `hard_no_titles` — same rule as the manual-path negative chips.
6. `experience_level` maps through the EXISTING `CANONICAL_SENIORITY`/`_SENIORITY_TO_LEVEL` table ([`src/ui/ai_setup.py:49-56`]) — unchanged, since the schema's four enum values already match verbatim.

---

## 6. Build sequence

Each phase independently shippable; existing test suite (`py -3.12 -m pytest`, ~2195 tests as of S32 per `CLAUDE.md`) must stay green after every phase.

**Phase 0 — spike (no code, half a day).** Confirm `gate.py:48-51`'s `hard_no_titles` semantics (done in this doc, §4.3) and measure the real size of `onet_related_occupations.tsv`/`onet_technology_skills.tsv` once built from the raw O*NET 30.3 source files, and re-confirm their license terms match the already-vetted alt-titles file. **Gate**: do not proceed to Phase 2 until size + license are confirmed, not assumed.

**Phase 1 — AI-prompt fix only (§5).** Rewrite `_config_block_body()`, extend `parse_setup_block()`/`apply_setup()` with the tiered schema + backward-compat fallback. Zero new files, zero new UI.

- Tests: `test_ai_setup_tiered_keywords_parse`, `test_ai_setup_legacy_target_titles_still_parses`, `test_ai_setup_field_no_longer_gated_by_canonical_list`, `test_ai_setup_negatives_never_reach_hard_no_titles`.

**Phase 2 — offline discovery core (§4.1, §4.2 cold-start only).** New `src/search/discovery_core.py`, the two new O*NET tsvs, `keyword_pool` table migration. No probe, no corpus mining, no UI yet — CLI/pytest-only.

- Tests: `test_discovery_core_propose_cold_start`, `test_discovery_core_adjacent_uses_related_soc_not_same_soc_alttitles` (regression guard against the flagged weakness), `test_discovery_core_offline_zero_network_calls`.

**Phase 3 — API surface (§4.4).** `src/webui/api/discovery.py`, all 7 routes, gated per convention.

- Tests: `test_discovery_routes_mutating_are_origin_gated` (extends the existing meta-test), `test_discovery_propose_route_shape`, `test_discovery_activate_writes_through_search_config`.

**Phase 4 — live yield probe + budget (§4.2).** `probe_yield()`, the shared `RateLimiter`, the new daily counter.

- Tests: `test_probe_budget_caps_at_10_per_day`, `test_probe_shares_adzuna_rate_limiter_with_daily_run` (regression guard against the flagged collision risk).

**Phase 5 — corpus mining, gated (§4.2).** `mine_corpus()`, the `cached_titles()` accessor added to `single_feed_client.py` and all 7 subclasses, `matched_keywords` provenance tagging in `search_engine.py`'s merge step.

- Tests: `test_mine_corpus_noop_when_discovery_disabled` (regression guard against the flagged unconditional-side-effect flaw), `test_matched_keywords_tagging_is_score_neutral` (rescore-parity style, per `tests/test_rescore_parity.py`'s existing convention), `test_cached_titles_accessor_all_7_feed_clients`.

**Phase 6 — marginal-yield / low-yield flagging (§4.2).**

- Tests: `test_low_yield_requires_min_activation_age`, `test_low_yield_never_auto_deactivates`, `test_suggestion_pruning_never_touches_active_keywords`.

**Phase 7 — experience-level query variants (§4.3).**

- Tests: `test_no_query_variants_for_senior_manager_exec` (the explicit safety rule graft), `test_entry_mid_variants_are_additive_only`.

**Phase 8 — web UI (§4.5).** `KeywordPoolPanel.tsx`, wiring into `SearchTab.tsx` and `RolesStep.tsx`.

- Tests: existing frontend test conventions (component render + mutation-hook tests per `queries.ts` pattern).

**Phase 9 — Tk UI (§4.5).** `tab_search.py` Toplevel + Treeview, calling `discovery_core.py` directly.

- Tests: `test_tk_discovery_dialog_calls_same_core_module_as_web` (parity guard).

---

## 7. Risks, trade-offs, and accepted gaps

| #   | Item                                                                                                                                                                        | Disposition                                                                                                                                                                                                                                       |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | New O*NET tsv license terms are assumed identical to the already-shipped alt-titles file but not yet independently re-confirmed                                             | **Accepted gap, gated by Phase 0.** Do not commit either new file until confirmed.                                                                                                                                                                |
| 2   | New tsv sizes are unmeasured estimates ("low single-digit MB")                                                                                                              | **Accepted gap, gated by Phase 0.** Measure at build time before committing.                                                                                                                                                                      |
| 3   | `metro_satellites.csv` covers only Cincinnati (31 rows, one CBSA) — the live-yield probe's location resolution is weaker for every other user's metro                       | **Accepted, documented trade-off** (pre-existing gap, not introduced by this feature) — belongs in `docs/KNOWN_ISSUES.md`, not blocking.                                                                                                          |
| 4   | Adzuna's `count` field is a raw national/regional total, not a true "unique jobs this term alone would surface" number                                                      | **Accepted trade-off.** UI copy says "~N openings nearby" (approximate), never a precise promise; the slower, rigorous `marginal_unique_7d` (real dedup'd count from our own inbox) is the number driving the low-yield flag, not the fast probe. |
| 5   | `cached_titles()` still requires touching 7 client files                                                                                                                    | **Accepted cost** of fixing the private-cache-coupling fatal flaw — judged worth it over the fragile alternative (reaching into private formats by naming convention).                                                                            |
| 6   | Corpus mining, once enabled, adds real (if batched/SQL-side) CPU work to `daily_run.py` for any project that has opted in                                                   | **Accepted, but strictly opt-in** via `discovery_enabled` — a user who never opens the panel pays nothing, by construction (Phase 5 test enforces this).                                                                                          |
| 7   | Probe budget (10/day) may feel restrictive for a user activating 20+ keywords at once                                                                                       | **Accepted trade-off.** Deliberately conservative given Adzuna's 25/min ceiling is shared with the real daily run; can be raised later if measured contention stays low.                                                                          |
| 8   | `suggested_excludes` is a brand-new scoring lever, not covered by the existing rescore-parity test suite until Phase 6/7 tests land                                         | **Mitigated, not accepted** — new parity tests are a required deliverable of those phases, per §6.                                                                                                                                                |
| 9   | The "prefill from résumé" button (graft from the Progressive Hybrid design) risks steering a career-switcher back toward their OLD field if it's ever made a silent default | **Neutralized by design, not just documented:** it is opt-in only, never auto-fired on wizard load — the nurse persona (§3) never sees her old titles unless she clicks the button herself.                                                       |
| 10  | This plan does not address the MCP server surface (`src/mcp_server.py`) at all                                                                                              | **Accepted gap**, flagged by all three judges as a shared blind spot across every design in the batch — out of scope for this iteration, worth a follow-up ticket.                                                                                |

---

## 8. Open questions for Alex

1. **Daily probe budget: 10/day, or a different number?** Recommendation: ship at 10, instrument actual usage in Phase 4, raise later if telemetry shows users routinely hitting the cap without contention against the daily run's own Adzuna traffic.
2. **Should `suggested_excludes`' downrank magnitude match `_seniority_target_adj`'s existing bounds (0 to -12), or get its own tunable constant?** Recommendation: start at a flat `-6`, cheaper to reason about than a graduated scale, tune after real usage data.
3. **Ship the two new O\*NET tsvs as committed binaries in the public AGPL-3.0 repo, or keep them user-machine-generated (via a `scripts/build_taxonomy_extra.py` the user runs once, never committed)?** Recommendation: commit them (matches the existing `onet_soc_alt_titles.tsv` precedent) — but only after Phase 0's license/size gate clears; if size turns out large, fall back to the generate-on-first-run alternative.
4. **Should the "prefill from résumé" button be available from the Discovery panel on day one, or held for a v1.1?** Recommendation: ship it in Phase 8/9 alongside the rest of the UI — it's a small, strictly-opt-in addition and the persona risk (#9 above) is neutralized by construction, not by discipline.
5. **90-day suggestion-pruning window — too aggressive, too lax, or configurable?** Recommendation: ship the flat 90 days, make it a `config.py` constant (`DISCOVERY_SUGGESTION_TTL_DAYS = 90`) rather than a user-facing setting, so it's a one-line change if wrong.
