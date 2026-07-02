# Coverage & Breadth Review — General-User Tests 2026-07

**Lens:** Coverage and breadth. Where do jobs come from per vertical/metro, which
verticals starve, and why. Verified against source code (read-only) 2026-07-02.

**Scope:** 8 blank-slate personas × (setup → AI-seeding → live daily_run → inbox →
BYO-AI top-10 → tracking). Structured data: `_structured-results.json`; narratives:
`persona-*.md`.

---

## TL;DR

- **Every keyed local search is a de-facto Adzuna monopoly.** For the 6 metro-bound
  personas, Adzuna supplied **47.5–100%** of the inbox; strip the two seeded/tech
  personas and it's **74–100%**. Nothing else reliably delivers local, on-site,
  keyless jobs. When Adzuna rate-limits, back-offs, or mislabels, there is no second
  source to catch the miss.
- **A single HIGH bug silently zeroes the entire careers/registry path for any
  user whose field is 2+ words** (`warehouse logistics`, `mechanical engineering`,
  `data analytics`, `management consulting`). CONFIRMED at
  `scrape/company_registry.py:234` (`_industry_tag_match`) + `:287/:299`
  (`get_registry` key normalization). Blast radius: warehouse, mecheng, data
  personas each seeded 8–17 real local employers that **their own daily run never
  scraped**. Worse for `data analytics`: it returns **7 wrong-vertical health
  companies** while excluding the user's 15 real seeds.
- **Three verticals structurally starve** regardless of keys, because the places
  their jobs live are unreachable: **teacher** (districts on Frontline = no scraper,
  NEOGOV = ToS-blocked), **nurse** (hospital portals are CSRF-Workday / direct;
  the one RN-specific feed is national-unlocalized → 0 survive the metro gate),
  **warehouse** (marquee employers FedEx/Nike/AutoZone on CSRF-Workday; Indeed
  ToS-blocked = the dominant blue-collar board is off-limits).
- **Remote-only search is broken on the two keyed aggregators.** Adzuna and USAJobs
  both return **0** for `location="Remote"` — CONFIRMED as a query-construction defect
  (the literal string is sent as a geocoded place), not an API limitation.
- **CareerOneStop is unkeyed in every single run.** The app's own Guide names it the
  #1–#2 free lever and "best free source" for nurses/teachers/blue-collar — the exact
  verticals that starve. It self-skips silently in all 8 runs. This is the single
  highest-leverage coverage fix.

---

## 1. Source-mix table (per persona, inbox composition)

Inbox = what survived all gates and reached the user. `adzuna%` is of the inbox.

| Persona (metro)         | Inbox | Adzuna |   Adzuna% | careers | Other inbox sources                               |
| ----------------------- | ----: | -----: | --------: | ------: | ------------------------------------------------- |
| SWE new-grad (Austin)   |   141 |     67 | **47.5%** |      63 | hn 9, wwr 2                                       |
| Nurse (Boise)           |    29 |     22 | **75.9%** |       0 | usajobs 7                                         |
| Teacher (Columbus)      |    49 |     36 | **73.5%** |      13 | (careers=OSU only)                                |
| Consultant (Chicago)    |   196 |    187 | **95.4%** |       0 | wwr 9                                             |
| Warehouse (Memphis)     |    53 |     53 |  **100%** |       0 | —                                                 |
| Mech-eng (Seattle)      |    32 |     26 | **81.2%** |       0 | wwr 4, hn 2                                       |
| Data changer (Phoenix)  |    77 |     66 | **85.7%** |       1 | workingnomads 4, wwr 2, usajobs 2, jobicy 1, hn 1 |
| Marketing (remote-only) |     8 |  **0** |    **0%** |       8 | wwr, remoteok, himalayas (pre-gate 76 deduped)    |

**Reading it:**

- **Adzuna dependence, ranked:** warehouse 100% > consultant 95% > data 86% >
  mecheng 81% > nurse 76% > teacher 74% > SWE 48% > marketing 0%.
- The only two personas below ~75% Adzuna are the two where a _different_ channel
  worked: SWE got 63 careers rows from **seeded** boards (a single-word-safe field,
  `software_engineering`), and marketing was remote-only so the geocoded aggregators
  returned nothing and it fell back to remote boards.
- **careers/registry contributed 0 to five of eight inboxes.** For nurse, consultant,
  warehouse, mecheng that is a mix of the space/underscore bug and marquee employers
  being on CSRF-Workday. Teacher's 13 careers rows were **all OSU non-K12 noise**
  (a giant Workday board), not actual teaching jobs. Data got 1.

## 2. Where jobs come from — the source inventory

**Keyed aggregators (the workhorses):**

- **Adzuna** — the only broad, geocoded, all-employer, keyless-to-set-up-once source
  that returns local on-site jobs across every vertical. Carries the runs.
- **USAJobs** — federal only. Meaningful only where a big federal employer sits in
  metro (VHA in Boise gave the nurse her top-2). 0–24% share.

**Keyless free feeds that DID contribute:** WeWorkRemotely, RemoteOK, Himalayas,
HackerNews "Who's Hiring", WorkingNomads, TheMuse, Jobicy — **all remote/tech-skewed.**
They only help knowledge-work/remote personas. For on-site blue-collar/clinical they
return near-zero and whatever they do return is dropped by the location gate.

**Keyless feeds that stayed dark (no key present in test .env):**
CareerOneStop, Jooble, Careerjet — **all three were unkeyed in all 8 runs.**
CareerOneStop is the DOL National Labor Exchange (~all-employer, on-site, national);
its absence is why the starving verticals starve.

**Vertical-specific feeds:** RNJobSite (nursing), HigherEdJobs (education). Both
self-gate by industry and only activate for the right field. See §4 for why RNJobSite
returned 244 postings but 0 reached the nurse.

**careers/registry path (ATS scrapers):** the differentiator when it works, but see
§3 — it's silently disabled for multi-word fields, and the marquee employers most
users want are on CSRF-protected Workday the scraper cannot pull.

## 3. CONFIRMED HIGH BUG — multi-word industry silently zeroes the careers path

**Confirmed at `scrape/company_registry.py`:**

- `get_registry(industry=...)` line **287** and **299**:
  `key = industry.lower().replace(" ", "_")` — normalizes the _lookup key_ to
  underscores.
- `_industry_tag_match(key, tag)` line **234–241**: compares that underscored key
  against the **raw company tag**, which is stored **with spaces**. Match is plain
  substring containment (`k == t or k in t or t in k`). `"warehouse_logistics"` is
  neither equal to, nor a substring of, nor a superstring of `"warehouse logistics"`
  → **False**.
- Tags are stored with spaces because `gui.py:2437` (`AddCompaniesDialog._add`) does
  `e.industries = [ind]` where `ind = self._industry.get().strip()` — the raw field
  string, spaces intact. The wizard stores the same raw string in config.

**Reproduced read-only (`py -3.12`):**

```
_industry_tag_match('warehouse_logistics', 'warehouse logistics')  -> False
_industry_tag_match('mechanical_engineering', 'mechanical engineering') -> False
_industry_tag_match('data_analytics', 'data analytics')            -> False
_industry_tag_match('management_consulting', 'management consulting') -> False
# single-word fields are fine:
_industry_tag_match('logistics', 'warehouse logistics')            -> True
_industry_tag_match('nursing', 'nursing')                          -> True
_industry_tag_match('software_engineering', 'software_engineering') -> True
```

**End-to-end with a seeded companies.json (read-only):**

```
get_registry(industry='warehouse logistics')    -> 0 companies (17 seeded, all invisible)
get_registry(industry='mechanical engineering') -> 0 companies (8 seeded, all invisible)
get_registry(industry='data analytics')         -> 7 companies  <-- WRONG-VERTICAL
get_registry(industry='logistics')              -> 2 companies (works)
```

**Blast radius — which industry strings work vs fail:**

| Field the user types           | Stored tag                          | Normalized key           | Match?         | Effect                                                                     |
| ------------------------------ | ----------------------------------- | ------------------------ | -------------- | -------------------------------------------------------------------------- |
| `warehouse logistics`          | `warehouse logistics`               | `warehouse_logistics`    | ❌             | 0 companies; careers path dead                                             |
| `mechanical engineering`       | `mechanical engineering`            | `mechanical_engineering` | ❌             | 0; 8 seeds invisible                                                       |
| `data analytics`               | `data analytics`                    | `data_analytics`         | ❌ (own seeds) | returns 7 **health-informatics** cos (tag `analytics`), user's 15 excluded |
| `management consulting`        | `management consulting`             | `management_consulting`  | ❌             | 0; 1 live seed invisible                                                   |
| `software engineering` (space) | `software engineering`              | `software_engineering`   | ❌             | would fail — SWE persona escaped only by using the underscore token        |
| `software_engineering`         | `software_engineering`              | `software_engineering`   | ✅             | works (why SWE got 63 careers rows)                                        |
| `logistics` (1 word)           | `logistics`                         | `logistics`              | ✅             | works                                                                      |
| `nursing`                      | `nursing`                           | `nursing`                | ✅             | works (but no nursing employers in starter registry)                       |
| `controls_engineering`         | `controls_engineering` / `controls` | `controls_engineering`   | ✅             | works (starter tags are single-token)                                      |

**Wizard-derived strings make it worse.** When the field box is left blank the wizard
derives an industry from the user's role via O*NET
(`ui/setup_wizard.py:49 _derive_industry`). CONFIRMED live:

- `marketing manager` → **"Advertising and Promotions Managers"**. Normalized key
  `advertising_and_promotions_managers` matches _nothing_ — the marketing persona's
  seeds are tagged `digital_marketing`. `industry_company_count('Advertising and
Promotions Managers') == 0` vs `== 13` for `digital marketing`. A user who finishes
  the wizard normally seeds 13 employers the daily run then never scrapes.
- `demand generation manager` → **"Hydroelectric Production Managers"** (mis-resolve).

**Why it's insidious:** no crash, no traceback. `daily_run` logs a benign
`"only 0 registry companies match industry '<field>'"` and proceeds Adzuna-only.
Every marquee employer the user carefully seeded is invisible, and they're never told.
This is the mechanical root cause of the "careers=0" column in §1 for warehouse,
mecheng, and data. **Fix:** normalize the tag inside `_industry_tag_match`
(`t = (tag or "").lower().replace(" ", "_")` and compare against the already-normalized
key) — a one-line symmetric normalization.

## 4. CONFIRMED — RNJobSite: 244 postings, 0 survive the metro gate

**Claim:** the nurse's RN-specific feed returned 244 postings but 0 reached the Boise
inbox because it's national/unlocalized. **CONFIRMED.**

- `search/rnjobsite_client.py` fetches the **national base feed** `/rss/jobs`
  ("most recent RN jobs", nationwide) plus 3 hard-coded specialty feeds
  (Correctional, Hospice, Labor & Delivery). It applies **no location filter** — it
  emits every posting's `<jobLocation>` "City ST" verbatim (lines 110–148).
- Those 244 rows then hit `geo/filter.py filter_to_metro`, which keeps a row only if
  its location matches a Boise metro variant **or** is remote. RN bedside postings are
  neither remote nor (mostly) Boise → all dropped.
- Nurse narrative confirms the raw numbers: "Adzuna 243, RNJobSite 244" scraped;
  "RNJobSite's 244 (national, unlocalized) … 0 survived." Final source mix: Adzuna 22
  (76%), USAJobs 7 (24%), **RNJobSite 0**.

Net: the one nurse-targeted source in the whole app contributes nothing for any nurse
outside whatever metros happen to dominate the national feed that day. It is coverage
theater for a location-bound clinical user.

## 5. CONFIRMED — remote-only returns 0 on the keyed aggregators (query construction)

**Claim (marketing persona):** Adzuna and USAJobs returned 0 for `location="Remote"`.
**CONFIRMED — and it is query construction, not an API limitation.**

- `daily_run.py:248` sets `location = cfg.get("location")` and passes it verbatim
  to every client.
- `search/adzuna_client.py:60-66` puts it straight into the `where=` param. Adzuna
  geocodes `where` as a physical place; "Remote" geocodes to nothing → 0 results.
- `search/usajobs_client.py:68` sends it as `LocationName`; the client's
  `_normalize_location` (line 121) explicitly returns the string verbatim
  ("Remote"), and USAJobs treats `LocationName` as a place → 0.

Both APIs _do_ return remote jobs when queried correctly (omit the place param, or
filter on a remote flag / national scope) — so this is fixable in query construction:
detect a remote-only search and drop `where`/`LocationName` (or query country-wide)
rather than sending the literal token "Remote" as a city. Until then, a remote
knowledge-worker gets **only** the remote/tech boards (WWR/RemoteOK/Himalayas) — 8
inbox rows in one run vs 100+ in one LinkedIn scroll, and half the tail was noise
(region-locked "remote", sub-floor comp).

## 6. Which verticals starve, and why (the coverage map)

| Vertical               | Where its jobs actually live                                                                               | Reachable by app?                                   | Result                                                                                                                       |
| ---------------------- | ---------------------------------------------------------------------------------------------------------- | --------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| **Teacher (K-12)**     | District portals on **Frontline** (no scraper) + **NEOGOV/governmentjobs** (ToS-blocked)                   | ❌ both dark                                        | Adzuna does ~100% of useful work; careers=OSU daycare/childcare noise only. CareerOneStop (Guide's #1 for teachers) unkeyed. |
| **Nurse**              | Hospital systems on CSRF-Workday / direct portals; RN feed national-unlocalized                            | ❌ portals unscrapeable; RN feed 0 survive gate     | 76% Adzuna + 24% USAJobs(federal). A no-key nurse gets ~7 federal jobs. Starter registry has 0 nursing employers.            |
| **Warehouse**          | FedEx/Nike/AutoZone/Int'l Paper on **CSRF-Workday**; **Indeed** = dominant blue-collar board (ToS-blocked) | ❌ marquee unscrapeable; Indeed off-limits          | 100% Adzuna. Careers=0 (also hit by §3 bug).                                                                                 |
| **Data changer**       | Banner/Phoenix Children's/HonorHealth/APS/SRP on **Workday**; ASU/GCU direct                               | ❌ Workday slugs unguessable                        | 86% Adzuna. §3 bug returns 7 wrong-vertical cos.                                                                             |
| **Mech-eng**           | Boeing/PACCAR/Blue Origin/McKinstry on **Workday**; smaller cos on Greenhouse (seedable)                   | ⚠️ 8 seeded but §3 bug hides them                   | 81% Adzuna; careers=0 despite 8 verified seeds.                                                                              |
| **Consultant**         | Deloitte/McKinsey/PwC on **Workday/Avature/custom** behind CSRF/JS                                         | ❌ enterprise ATSes unscrapeable                    | 95% Adzuna. 1 live seed (Point B) returned 0 rows anyway.                                                                    |
| **SWE new-grad**       | Tech cos on **Greenhouse/Lever/Ashby** (seedable, single-word field)                                       | ✅ careers worked (63 rows)                         | Only 48% Adzuna — the healthy case, because the field was single-token and the vertical lives on scrapeable ATSes.           |
| **Marketing (remote)** | Remote-first cos on Greenhouse/Lever; remote boards                                                        | ⚠️ aggregators 0 (§5); remote boards + seeds worked | 0% Adzuna; 8 rows from remote boards + 4 seeds.                                                                              |

**Structural pattern:** the app is strong exactly where a vertical (a) lives on
public Greenhouse/Lever/Ashby boards and (b) is described in a single-token field.
It starves wherever jobs live on CSRF-Workday/NEOGOV/Frontline/Indeed — which is
precisely blue-collar, clinical, K-12, and enterprise-consulting, i.e. most
non-tech general users.

## 7. Secondary coverage findings

- **`gate_tech_sources` mis-classifies warehouse/logistics as knowledge work.**
  CONFIRMED: `is_knowledge_work('warehouse logistics')` and `('logistics')` both
  return **True** (`search/keyword_strategy.py:283`), so the 7 remote-tech boards
  (`TECH_SKEWED_SOURCES`) are NOT gated off for an on-site warehouse worker — wasted
  calls whose remote hits are then dropped by the location gate. Nursing correctly
  returns False and drops them. Not wrong results, but wasted budget + console noise.
- **Adzuna location-label trust (upstream, but a coverage-quality issue).** Adzuna
  stamps the query location onto every posting, so out-of-state/out-of-metro rows leak
  in labeled as local (teacher: 3 TN/NC rows shown "Columbus"; nurse: a Montana RN
  shown "Boise County"; mecheng: a Butte MT role shown "Seattle"). The location gate
  trusts the label, not the JD body. Because Adzuna is ~the only source, its label
  errors pass straight through with no cross-source corroboration.
- **`save_companies` persists unreachable/junk boards without gating** (advisory
  probe only). Not a coverage-reducer per se, but it means dead seeds re-scrape and
  throw soft errors every run, and the user is never told which of their seeds are
  live — masking how little real coverage seeding added (e.g. consultant: 16 of 17
  dead, silently kept).

## 8. Recommendations (coverage-ranked)

1. **Fix the multi-word industry match** (`_industry_tag_match` tag normalization).
   One line; unblocks the careers/registry path for every 2+word and wizard-derived
   field. Highest leverage: turns "careers=0" into real coverage for warehouse,
   mecheng, data, consultant, and the wizard-default marketing case.
2. **Key CareerOneStop out of the box (or bundle a keyless equivalent).** It is the
   only broad, national, all-employer, on-site source that would fill the gap for the
   four starving verticals. The Guide already sells it as #1–#2; it's simply unwired.
3. **Fix remote-only query construction** — detect a remote search and stop sending
   the literal "Remote" as a geocoded place to Adzuna/USAJobs.
4. **Localize or drop RNJobSite for metro-bound nurses** — a national feed that
   contributes 0 after the gate is pure noise; either pre-filter by state or surface
   it only for remote/national nurse searches.
5. **Reduce Adzuna single-source fragility** — the whole product's local coverage
   currently rides one keyed aggregator; #1 and #2 above are the concrete diversifiers.
