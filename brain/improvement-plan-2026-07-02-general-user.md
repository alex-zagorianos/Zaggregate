# Improvement Plan — General-User Readiness (2026-07-02)

> **STATUS 2026-07-02: BUILT in Session 32** — all P0s, quick wins, coverage/onboarding
> roadmaps, and strategic bets SB-1..SB-6 implemented and review-fleet-verified (13 confirmed
> findings, 0 refuted, all fixed). See `docs/handoffs/handoff_20260702_session32.md` and the
> corpus README (`brain/general-user-tests-2026-07/README.md`) for the full outcome mapping
> (S31 finding → merge commit → live-smoke evidence). Per-item `✅ BUILT S32 (merge <hash>)`
> markers are inline below. Precise caveats: **SB-1** Workday cxs built, Cloudflare-fronted
> tenants remain walled; **SB-2 Leg B** + **P0-2 CareerOneStop daily source** built KEY-GATED /
> code-ready, awaiting a CareerOneStop key. Original text below is intact — annotations only.

**Source of truth:** 8 blank-slate persona runs (`persona-*.md`, `_structured-results.json`),
4 review lenses (onboarding/coverage/ranking/lifecycle), 3 research reports
(sources/competitors/onboarding-ux), and the orchestrator note — all in
`brain/general-user-tests-2026-07/`. Extends (does not duplicate) the HELD
`brain/plan-2026-07-01-ai-assisted-setup-seeding.md`.
**Product goal this plan is ranked against:** the easiest path for a stranger to find
_exactly the job they want_.

---

## 1. Executive summary — what the night proved

All 8 personas completed the full journey (setup → seed → run → BYO-AI top-10 → tracked to
accepted/rejected/ghosted) with **zero crashes, 8/8 "would stay", 7/8 "beats manual".** The
wizard is genuinely good (clarity 8–9/10, ~18 min median) and the tracker lifecycle is
functionally complete and durable across every persona. So the app **is** general-user viable
today. But it is carried by a single leg and undercut by two silent traps. **First,
coverage is a de-facto Adzuna monopoly** — Adzuna supplied 48–100% of every metro inbox
(100% warehouse, 95% consultant, 86% data, 81% mecheng, 76% nurse, 74% teacher), and
CareerOneStop — the Guide's own #1 free local lever — was **unkeyed and silently dark in all
8 runs**, so the non-tech, on-site users the "easy for everyone" goal exists for are the ones
underserved. **Second, a one-line bug (`_industry_tag_match`) silently zeroes the entire
careers/registry path for any user whose field is 2+ words** ("mechanical engineering",
"data analytics", "warehouse logistics"): warehouse seeded 17 real employers → 0 searched,
mecheng 8 → 0, data 15 → 0. **Third, the raw local Score systematically misleads a no-AI
user** — "Sr."/"III"/"8+ YOE" tie an entry role, any "remote" string earns full location
credit regardless of country, and sub-floor comp in the JD body slips the salary gate; the
BYO-AI re-rank cleanly fixes all of it, but a keyless user sees the noisy Score. The
remote-only marketer was the only "does not beat manual" — Adzuna and USAJobs both return 0
for `location="Remote"` (a query-construction defect, not an API limit). None of the top
defects are in the tracker; they cluster in **coverage plumbing + onboarding sequencing +
local-scorer honesty** — all localized, mostly low-effort, and directly on the path to
"exactly the right job."

---

## 2. Persona scorecard

| slug                    | setup min | inboxed | Adzuna share | verdict /10 | beats manual | biggest gap (one-liner)                                                                                                                               |
| ----------------------- | --------: | ------: | -----------: | ----------: | :----------: | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| gu-swe-newgrad-austin   |        18 |     141 |          48% |           7 |     yes      | Seniority-/country-blind Score: an SE **III scored 100** & topped the inbox; non-US remotes get full loc credit                                       |
| gu-consultant-chicago   |        18 |     196 |          95% |           7 |     yes      | Scorer can't disambiguate the "engagement manager" family → ~half of top-40 are AWS/CS/PM false positives                                             |
| gu-data-changer-phoenix |    **40** |      77 |          86% |           7 |     yes      | CareerOneStop unkeyed + Workday slugs unresolvable → marquee locals (Banner, Dignity, ASU) never arrive; entry config doesn't down-rank Senior titles |
| gu-nurse-boise          |        18 |      29 |          76% |           6 |     yes      | Whole inbox = Adzuna+USAJobs (both keyed); no-key nurse ≈ 7 federal jobs; RNJobSite 244→0 through gate                                                |
| gu-teacher-columbus     |        18 |      49 |          74% |           6 |     yes      | CareerOneStop dark + K-12 districts on Frontline/NEOGOV unreachable → the two places district jobs live are both off                                  |
| gu-mecheng-seattle      |        18 |      32 |          81% |           6 |     yes      | Industry-tag bug hides 8 verified seeded employers → careers=0; Adzuna-only in practice                                                               |
| gu-warehouse-memphis    |        22 |      53 |     **100%** |           6 |     yes      | Careers=0 (industry-tag bug + marquee employers on CSRF-Workday); rides entirely on one keyed source                                                  |
| gu-marketing-remote     |        18 |   **8** |       **0%** |           6 |    **no**    | Remote-only broken on keyed aggregators (Adzuna/USAJobs return 0 for "Remote"); 8 rows, half tail noise                                               |

Cross-persona: wizard clarity 8–9/10; **all 8 completed the full tracked lifecycle with clean
persistence**; the BYO-AI re-rank fixed every scorer false-positive family in every persona.

---

## 3. P0 confirmed defects (a lens confirmed_in_code)

Ordered by (impact × breadth ÷ effort). Every item was re-verified against source this session
where feasible.

### P0-1 — Multi-word `industry` silently zeroes the careers/registry path

> ✅ BUILT S32 (merge `6d017f8` — token-aware `_industry_tag_match`, commit `11e670b`). Smoke:
> `industry_company_count("warehouse logistics")` 0→15.

- **File:** `scrape/company_registry.py:239-241` (`_industry_tag_match`), reached via
  `get_registry` key-normalization at `:287` / `:299`; tag written raw at `gui.py:2437`
  (`AddCompaniesDialog._add`).
- **Evidence:** re-reproduced live this session — `_industry_tag_match('mechanical_engineering','mechanical engineering') → False`,
  `('data_analytics','data analytics') → False`, `('warehouse_logistics','warehouse logistics') → False`;
  single-word `('logistics','logistics') → True`, `('nursing','nursing') → True`. The current
  docstring _claims_ symmetric matching but the body never normalizes the tag. Blast radius:
  warehouse seeded 17 → 0 searched, mecheng 8 → 0, data 15 → 0 (and `data analytics` returns 7
  **wrong-vertical** health companies). Confirmed by coverage §3, onboarding §2.4, ranking, and
  the orchestrator's #1 finding.
- **Minimal fix:** normalize the tag inside `_industry_tag_match` symmetrically:
  `t = (tag or "").lower().replace(" ", "_")` and compare against the already-normalized key
  (add a regression test for the four multi-word fields + a starter single-token tag).
- **Effort:** XS (one line + test).

### P0-2 — CareerOneStop unkeyed & never surfaced (the #1 recurring "biggest gap")

> ✅ BUILT S32 (merge `c3d442f` — `.env.example` keys `cd8f558`, wizard keys step `e843d5a`,
> keyless-skip Inbox badge `5788d26`). CareerOneStop **daily source is code-ready but unkeyed** —
> needs Alex's free CareerOneStop key to go live (Jobs API governance-gated since 2024-08-27, per the caveat below).

- **File:** onboarding gap, not a code bug: `careeronestop_client.py:90` self-skips;
  `CAREERONESTOP_*` is absent from `.env.example`; the wizard (`ui/setup_wizard.py:416`) never
  routes the user to the existing `ui/source_keys.py` dialog (`gui.py:3707`), which already has
  the free-registration deep link **and** a live Test button.
- **Evidence:** unkeyed and silently dark in **all 8 runs**; named the single biggest miss by
  nurse, teacher, warehouse, and data-changer. It is the DOL/NLx all-employer on-site feed — the
  exact coverage the four starving verticals lack. Confirmed by onboarding §4.2, coverage §5/§8.
- **Minimal fix (this defect = discoverability):** (a) add `CAREERONESTOP_*` (+ Jooble/Careerjet)
  to `.env.example` with a one-line "best free source for non-tech/on-site jobs" note [XS]; (b)
  add a "Connect your best free sources" wizard step that funnels into the existing
  `source_keys` dialog, impact-ranked Adzuna + CareerOneStop first [S–M]. **Caveat, per
  research-sources §2/§E: the CareerOneStop _Jobs_ API is governance-gated since 2024-08-27** —
  register the key now but request Jobs-API access early and plan a fallback; the LMI/Business-Finder
  family stays self-serve.
- **Effort:** XS (env) + S–M (wizard step).

### P0-3 — Seniority-blind local Score (Sr./II·III/"8+ YOE" tie an entry role)

> ✅ BUILT S32 (merge `b86c3b3` — seniority/country/label levers `0d65ca9`, threaded through all 5
> callers `fdac6d1`). **Note:** the review fleet caught a CRITICAL rescore-drift that erased these
> levers on every run — fixed in `025b0ce` (merge `80ce359`) + a lever-tripping parity test.

- **File:** `match/scorer.py` — `_STOPWORDS` at `:33` strips `senior/junior/lead/staff/i/ii/iii`;
  `_seniority_fit_adj` engages only for management targets; the correct detector
  `facts._detect_seniority` (handles `\bsr\.?\b`, Roman I/II/III, `8+ years`) is **never called by
  `score_job`**. Opt-in `seniority_exclude` uses word-boundary matching so "Sr." sails through.
- **Evidence:** ranking review reproduced identical composites for "Software Engineer" vs
  "Sr./II/III". SWE persona's **#1 inbox row was an SE III at score 100**; data-changer's entry
  inbox had 8+ Senior/Sr/Lead/Principal in the top-40. Confirmed by ranking #1/#3.
- **Minimal fix:** in `score_job`, compute `facts._detect_seniority(title, desc)` and apply a
  bounded down-nudge when the detected level exceeds the config's `seniority_target`/`years_cap`
  (senior/lead/III → −8..−12). Reuses the existing correct detector; no new regex.
- **Effort:** S–M.

### P0-4 — `daily_run.py --project X` persistently flips the GLOBAL active project

> ✅ BUILT S32 (merge `266cb1c` — drop `set_active` on the scoped path, commit `e5f3c20`).
> **Verified live in smoke:** `active` stayed `test-controls` before/during/after all three runs.

- **File:** `daily_run.py:218` `workspace.set_active(args.project)` writes `projects.json`;
  the process-local pin at `:225` (`pin_active`) already provides all in-process isolation, and
  `unpin_active` at `:629` does **not** restore the prior active.
- **Evidence:** confirmed live — after the overnight run the registry pointed at the last persona
  and the orchestrator had to manually restore test-controls; teacher persona logged the flip.
  Confirmed by lifecycle L1.
- **Minimal fix:** delete the `set_active(args.project)` call on the scoped-run path and rely on
  `pin_active`; gate any "run and make active" behind an explicit `--set-active` flag.
- **Effort:** XS (~1 line).

### P0-5 — Remote-only search returns 0 on the keyed aggregators (query construction)

> ✅ BUILT S32 (merge `75d80a8` — Adzuna/USAJobs remote query + national-feed localization, commit
> `78defbe`). **Headline smoke win:** marketing-remote 8→36 inboxed; Adzuna remote 0→114 raw / 32 inboxed.

- **File:** `daily_run.py:248` passes `location` verbatim; `search/adzuna_client.py:60-66` puts it
  in `where=` (geocoded → "Remote" resolves to nothing); `search/usajobs_client.py:68/121` sends
  it as a verbatim `LocationName`.
- **Evidence:** marketing-remote got **8 inbox rows, 0 from Adzuna/USAJobs**, and was the only
  `beats_manual=false`. Both APIs return remote jobs when queried correctly (research-sources §3/§G:
  put remote in `what` with blank `where`, or use `where=remote`). Confirmed by coverage §5.
- **Minimal fix:** detect a remote-only intent and drop `where`/`LocationName` (or query
  country-wide + remote flag) instead of sending the literal token "Remote" as a place.
- **Effort:** M.

### P0-6 — `+ Add Companies` saves unreachable/junk boards; Guide claims otherwise

> ✅ BUILT S32 (merge `6d017f8` — probe-status gates saving+scraping, commit `5c7864c`). Two review-fleet
> follow-ups also landed: the re-verify upgrade path (`c2c9589`+`8249683` → merge `b5e3ba6`, so a corrected
> board clears its unverified flag) and the walled-vs-empty probe verdict (`b67a85e`+`62f449e` → merge
> `f3b07ee`, so a Cloudflare-422 tenant is flagged unreachable not "verified-empty" — this last one's
> lineage is the live smoke, not the fleet).

- **File:** `gui.py:2428` `_add` calls `save_companies(self._entries)` with the **full** list;
  `scrape/company_registry.py:189` `save_companies` dedups only by `(ats_type, slug)`/name and
  **never consults the probe result**. The Guide (`ui/help.py:103`) tells the user
  "_Anything the AI got wrong simply fails verification — nothing bad can sneak in_" — false as written.
- **Evidence:** every persona wrote dead/junk boards (consultant 16/17 dead, nurse 4/4 dead,
  teacher 11 dead, warehouse 9 unreachable + 1 junk); these re-throw soft errors on **every**
  subsequent run. Confirmed by onboarding §5, coverage §7.
- **Minimal fix:** split Add into "Add verified (live/direct)" (default) vs "Add unverified
  anyway"; visually flag unreachable rows + one-click prune; and correct the false Guide copy at
  `ui/help.py:103`.
- **Effort:** S–M.

### P0-7 — `tracker.db.update_job` silently drops unknown fields (data-loss trap)

> ✅ BUILT S32 (merge `266cb1c` — UnknownFieldError + round/status coherence, commit `9641d4b`).

- **File:** `tracker/db.py:678` filters to `_EDITABLE` (`:73`) and returns `None` regardless;
  same class in `update_interview_round` (`:847`, `_ROUND_EDITABLE`).
- **Evidence:** warehouse persona lost `offer_salary='53669'` silently (real column is
  `offer_amount`). This is the most dangerous defect for the "BYO-AI drives the tracker" story —
  fails silently and destructively. Confirmed by lifecycle L3.
- **Minimal fix:** return the count of applied fields (or raise/log) on an unknown key; propagate
  through `service.update_job`; apply the same guard to `update_interview_round`.
- **Effort:** XS–S.

---

## 4. Quick wins (days, not weeks)

High-leverage, small items from any input. (P0-1, P0-4, P0-7, and the `.env.example` half of
P0-2 are also quick-win-sized — listed above; not repeated here.)

- **QW-1 — Broaden wizard field examples** to span the personas (add software engineering,
  consulting, marketing, logistics/warehouse, data analytics, teaching) + a one-line "this drives
  which sources & rankings you get" note. `ui/setup_wizard.py:518`. Every non-tech persona flagged
  their field was unrepresented. **[XS]** — ✅ BUILT S32 (validated field-preset picker `ce57725` → merge `2e83a2a`).
- **QW-2 — Country-blind remote credit cap.** `_location_score` (`search/search_engine.py:51-52`)
  returns full marks (3) for any "remote" string. When the remote label carries a non-US region
  token (`czech|canada|uk|emea|latam|europe|…`) and target is a US metro, cap the credit. One
  regex; also feed a label-derived `restriction` so `gate._FOREIGN_RESTRICTION` catches it. Fixes
  SWE non-US remotes + marketer EMEA/LatAm rows. **[S]** (ranking #2) — ✅ BUILT S32 (country-blind remote cap in the scorer levers `0d65ca9` → merge `b86c3b3`).
- **QW-3 — Sub-floor salary in JD body slips the gate.** In `hard_gate` (`preferences.py:127`),
  when API salary fields are empty, run `parse_comp(job.description)` and gate on the annualized
  floor — drop only on a confident sub-floor parse. Marketer's $18k/UK role passed a $90k floor.
  **[S]** (ranking #5) — ✅ BUILT S32 (body-salary floor in the scorer levers `0d65ca9` / `75d80a8` → merge `b86c3b3`; review fleet then fixed a bonus/commission false-drop, `a93ca54` → merge `80ce359`).
- **QW-4 — Dedup console skip/verify noise.** Keyless-source + "verify manually" warnings print
  once per pass ×3 passes (`search/cli.py:72-157`, `scrape/direct_scraper.py:122`,
  `jooble_client.py:29`, `careerjet_client.py:29`). Module-level warned-set reset at run start.
  Nurse/teacher both flagged the noise burying real signal. **[S]** (lifecycle L7) — ✅ BUILT S32 (warn-once dedup `a32b242` → merge `75d80a8`).
- **QW-5 — File-import re-rank leaves Top Picks silently empty.** `service.apply_rerank_scores`
  writes `fit` but not `rank`/`rec_batch` unless the file has `new_rank`; the clipboard route
  always derives a shortlist. Make the file route fall back to ranking by `new_fit` desc (mirror
  `score_inbox_from_reply`), or surface "0 shortlisted — include new_rank". Warehouse B3.
  **[S]** (lifecycle L2) — ✅ BUILT S32 (file-import fit-fallback shortlist `265d180` → merge `75d80a8`).
- **QW-6 — `add_status_note` renders as a phantom `accepted→accepted` self-transition in CSV
  export.** The interactive timeline tags it `kind='note'`; `status_timeline_all`
  (`tracker/db.py:1562`) does not. Format `old==new` rows as a note in the CSV. Data-changer B4.
  **[low]** (lifecycle L6) — ✅ BUILT S32 (CSV note fix folded into `9641d4b` (L4/L6) → merge `266cb1c`).
- **QW-7 — Market own-your-data + no-auto-apply as the headline.** Zero code. The "90% of job
  platforms sell your data" and "auto-apply ≈ 0.01% success vs 4–6% tailored" stats are a moat no
  SaaS rival can answer, and the persona tests' honest false-positive/reach reporting is the
  antithesis of ghost-job opacity. **[S, positioning]** (competitors §7/§8B) — ✅ BUILT S32 (README/Guide positioning copy `ed95263` → merge `c7f67e7`).

---

## 5. Coverage roadmap by vertical

Merges lens-coverage findings with research-sources recommendations. Every source labeled with
its ToS posture and effort. **The single cross-vertical unlock is the Workday `wday/cxs` public
JSON API** (research-sources Headline #1): POST the JSON search body to
`https://{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` instead of GET-ing HTML — this
is the documented public read path that dodges the CSRF wall, and it recovers the marquee
employers _every_ non-tech persona lost. Needs a tenant/`wdN`-prefix resolver, not a guess.
**ToS: public/unauthenticated published-jobs endpoint; the intended read path. [L]**

| Vertical                 | Where jobs live / why it starves                                                                | Recommended ToS-safe adds                                                                                                                                                                                | ToS note                                                                                                                                                 | Effort                                |
| ------------------------ | ----------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------- |
| **Education (K-12)**     | Districts on Frontline (no scraper) + NEOGOV (ToS-blocked); teacher got Adzuna-only + OSU noise | **REAP** state portals (`usreap.net` family); **EdJoin** (`edjoin.org`, public browse); lean on keyed **CareerOneStop/NLx** for district postings                                                        | REAP/EdJoin = public applicant sites, honor per-state robots.txt, light HTML reads; **never scrape Frontline/NEOGOV**                                    | M                                     |
| **Healthcare / nursing** | Hospital systems on CSRF-Workday/direct; RNJobSite national-unlocalized (244→0 through gate)    | **Workday `wday/cxs` JSON** (St. Luke's, HCA, most IDNs); **SmartRecruiters Posting API** (public, no key); **Greenhouse Job Board API** (public); keyed **CareerOneStop**                               | Workday/SmartRecruiters/Greenhouse = public published-jobs endpoints; Health eCareers/HospitalCareers = **no public feed, partner-only, exclude**        | L (Workday) + S (confirm SR/GH wired) |
| **Hourly / warehouse**   | FedEx/Nike/AutoZone/Int'l Paper on CSRF-Workday; **Indeed = dominant board, ToS-blocked**       | **Workday `wday/cxs` JSON** (marquee 3PLs/industrials); keyed **CareerOneStop/NLx** (strong on blue-collar on-site)                                                                                      | Workday public; **never scrape Indeed**; **Snagajob = inbound-only feed, not consumable, exclude**                                                       | L + S (key)                           |
| **Remote-only**          | Aggregators return 0 for "Remote" (P0-5); leans on WWR/RemoteOK/Himalayas + seeds               | Fix Adzuna/USAJobs remote query (P0-5); switch Himalayas to its **`search` endpoint** with `country=US` to kill region-locked false positives; optional **jobdataapi.com** free tier (`has_remote=true`) | Himalayas: **attribution + link-back required; must NOT forward its jobs to Jooble/Google Jobs**; jobdataapi verify per-endpoint                         | M (P0-5) + S (Himalayas)              |
| **General (all)**        | ~95–100% Adzuna monopoly; keyless feeds remote/tech-skewed; CareerOneStop dark                  | Key **CareerOneStop** (P0-2); **Workday `wday/cxs`** as the registry's marquee-employer path; fix P0-1 so seeded employers are actually searched                                                         | Adzuna already the workhorse; CareerOneStop = USDOL open-data (cleanest posture), **jobs feed governance-gated since 2024-08-27** — request access early | S (key) + L (Workday)                 |

**NLx direct: do NOT integrate** (signed data-use agreement, wrong overhead for a solo desktop
app) — consume it indirectly through CareerOneStop's Jobs API. Secondary coverage fix:
`gate_tech_sources` mis-classifies `warehouse logistics` as knowledge work
(`search/keyword_strategy.py:283` `is_knowledge_work` → True), so 7 remote-tech boards run for an
on-site warehouse worker — wasted calls, not wrong results. **[S]**

---

## 6. Onboarding roadmap — stranger → genuinely-useful inbox in < 15 min

Merges review-onboarding with research-onboarding-ux. Median setup is 18 min today but
time-to-**useful** collapses on unkeyed CareerOneStop + the multi-word field bug. The machinery
already exists (keys dialog with live Test, ATS probe, reach badge, ask-your-AI flow); the fix is
overwhelmingly **sequencing, placement, and framing** — value first, motivated friction second
(the core TTFV finding: first value in-session → 3–5× retention).

**Recommended re-sequenced first run (research-onboarding-ux §5):**

1. **Welcome → bundled sample inbox** (~20 pre-scored rows) so the aha (a scored, location-clean
   inbox) lands in seconds and demonstrates Score-vs-Fit before anything is connected. **[M]**
   (Pattern 3a: sample data cut first-insight from days to ~8 min in the cited case)
2. **Field picker (validated presets), not free text** — presets the correct industry token +
   source routing + any known local employers per field. **This alone kills the P0-1 multi-word
   bug and the marketing health-synonym pollution at the source.** **[S–M]** (Pattern 3d)
3. **Optional "set me up with my AI" paste** — a copyable prompt: paste résumé + one sentence →
   AI emits a canonical config block the app parses. BYO-AI-honest; returns canonical field tokens
   (also sidesteps the space/underscore trap). **[M]** (Patterns 2a/2b; extends the HELD plan's
   Leg A to the _profile_, not just seeding)
4. **Roles / Where / Salary / Résumé** (existing, largely fine; add remote-only mode → P0-5).
5. **Forced first action: "Update my Inbox now"** as the unmissable terminal wizard button;
   guided empty state ("Run your first update →") not a blank table. **[S]** (Pattern 3b: +20–30pp
   activation)
6. **Motivated keys step, framed by the reach just felt:** "You're seeing ~X local jobs — add one
   free key to see the rest." Deep-link Adzuna + CareerOneStop registration pages, paste-detect
   both Adzuna values, auto-run the existing `source_keys.test_source()` on paste with inline
   green/red. **[S–M]** (this is P0-2's wizard step; Patterns 1a–1c, 3c)
7. **Company seeding:** ask the AI for the **careers-page URL only** (which it gets right) and let
   the app's ATS detector resolve the slug; default to "Add verified" (P0-6). **[S–M]** (Pattern 2c)
8. **Reach badge becomes actionable:** when reach is low/uncertifiable, name the reason + the fix
   ("mostly remote/tech because Adzuna + CareerOneStop aren't connected — [Connect a free key]").
   Ties coverage-honesty to key conversion. **[S]** (Pattern 4a)

Supporting sharpeners: widen `industry_profile.resolve_soc` aliases so natural field words
(`nursing`, `education`, `consulting`, `warehouse`, `data analytics`, `digital marketing`)
resolve, fix `math teacher`→POSTSECONDARY, and guard the `demand generation manager`→
"Hydroelectric Production Managers" mis-resolution [S each, ranking #7]; have `create_project`
scaffold `preferences.{json,md}` via a shared helper so the AI-assisted-setup path can't hit an
empty preferences contract [S, onboarding §2.1].

---

## 7. Strategic bets

Bigger swings, ranked by leverage on the product goal. All consistent with assisted-not-auto,
own-your-data.

- **SB-1 — Workday `wday/cxs` JSON fetcher + tenant resolver.** The single highest-value coverage
  bet: recovers the marquee local employers nurse/warehouse/data/mecheng/consultant all lost, and
  generalizes across four starving verticals at once. Pairs with P0-1 (so seeded employers are
  searched) and the HELD Seed-My-Area plan (the resolver becomes the "supply side" that plan
  identified as the missing half). **[L]** (research-sources Headline #1) — ✅ BUILT S32 (public
  `wday/cxs` JSON fetcher + detection/dispatch/discovery `e1db6ba`/`1babd2f` → merge `5762e3e`;
  registry migration `0f20b99` moved CCH 479 + Bon Secours 96 jobs to cxs). **Caveat:**
  Cloudflare-fronted tenants (FedEx/AutoZone/Banner/etc.) still 422-wall → fail-soft; compliant
  capture for those = extension/browser layer (future decision).
- **SB-2 — Seed-My-Area, re-scoped against new evidence.** The HELD plan's Leg B assumed
  "get a free CareerOneStop key → #1 lever turns on." **That is now stale: the CareerOneStop Jobs
  API is governance-gated (2024-08-27).** Re-scope: (a) Leg A BYO-AI seeding stays, but per the
  AI-slug coin-flip evidence (SWE 5/13 wrong, nurse 0/14 live, consultant 1/17) prompt for the
  **careers-page URL only** and resolve slugs locally; (b) prefer the **verified-directory** path —
  CareerOneStop **Business Finder** (LMI family, still self-serve) for employer discovery, feeding
  the SB-1 Workday resolver — over pure ask-your-AI. **[L, re-scope of held plan]** — ✅ BUILT S32
  **KEY-GATED**: Leg A URL-only seeding + BYO-AI setup module + MCP `seed_companies` (`ed3371b` →
  merge `3f0a1fa`); Leg B CareerOneStop Business Finder client + `seed_my_metro` + Tools dialog
  (`e2b1238`/`05c37bb` → merge `6f87d00`). **Leg B awaits a CareerOneStop key** — endpoint
  provisional; drop one real Business Finder response at `COS_BF_FIXTURE` to confirm mapping once keyed.
- **SB-3 — Browser-clip-to-seed** (competitor-inspired, assisted-not-auto). Simplify/Huntr sidestep
  the slug coin-flip entirely because the _user is already on the real career page_ when they clip.
  A one-click "add this live board to my registry" that verifies at clip time converts coin-flip
  seeding into ~100% valid boards — the competitors' proven mechanic without cloud or auto-apply.
  **[L]** (competitors §8C) — ✅ BUILT S32 (`/clip` receiver + `resolve_board` verified-at-clip gate
  - extension v1.5 `272e7ea`/`ce953f3` → merge `a52a4e7`). **Alex must reload the unpacked extension** (manifest 1.5).
- **SB-4 — Reframe the daily inbox as a "Jobs For You" curated feed** and fold the P0-3/QW-2/QW-3
  scorer fixes in, so the **free** recommender is trustworthy _before_ BYO-AI. Jobright's
  most-loved feature is the matched feed framing; the engine already exists (`daily_run`).
  **[M]** (competitors §8A, MED) — ✅ BUILT S32 ("Jobs For You" inbox framing + forced first action `9a3d1a9` → merge `2e83a2a`).
- **SB-5 — Visual Kanban tracker view.** Huntr's #1-loved feature; the lifecycle data already
  exists and is complete — this is a pure GUI add over the existing DB. Highest love-per-effort
  emotional-anchor bet. **[S–M]** (competitors §8A, HIGH) — ✅ BUILT S32 (Board tab over the tracker DB
  `f4a557d` → merge `c7f67e7`; stage-aware clock + live cross-tab event `963ebd4` → merge `ad6a432`).
- **SB-6 — Coverage/reach badge upgrade** (honest → actionable), plus a free **local ATS-detected
  match hint** (Jobscan-lite) using the ATS detection already in `ats_detect` — a free local answer
  to a $50/mo tool, on-brand with own-your-data. **[M]** (competitors §8A, onboarding-ux §4) — ✅ BUILT S32
  (actionable reach badge `4602bed` + local `match/ats_hint.py` Jobscan-lite `493c4cc` → merge `2e83a2a`/`c7f67e7`).

---

## 8. Explicit non-goals

- **No auto-apply / bulk-send.** Auto-apply measures ≈0.01% success vs 4–6% tailored; recruiters
  are actively AI-filtering the spam (Greenhouse "doom loop"), and Wonsulting shut its bulk feature.
  The assisted, human-submits, tailored-not-sprayed posture is the whole moat. (competitors §6/§7)
- **No scraping Indeed.** ToS-blocked. Route around it via Adzuna + Workday + CareerOneStop.
- **No scraping NEOGOV / governmentjobs.com.** ToS-blocked. K-12/government routed via REAP/EdJoin/NLx.
- **No Snagajob, Health eCareers, HospitalCareers as feeds** — inbound-only / partner-only,
  no compliant public feed exists.
- **No direct NLx integration** — signed data-use agreement; consume via CareerOneStop only.
- **Nothing that breaks own-your-data / local-first** — no bundled paid LLM, no cloud account, no
  telemetry, no sending the résumé to a server. BYO-AI (user pays their own key, keeps the value)
  is the deliberate anti-subscription-rent, anti-data-sale stance and must stay.
- **No forwarding Himalayas jobs into any Jooble/Google-Jobs path** (their attribution ToS).
