# Handoff — Session 23 (2026-06-30) — built the 3 Session-22 plans (coverage-100 · board-expansion · agnostic/multi-person)

Ran on the cheap/3rd-party backend (NOT Opus), inline (no delegation — this session IS the
executor). Output mode: terse. Project = `E:\ClaudeWork\ZAG0005 - Job Search App\`.
**859 → 925 tests green (+66). Push HELD** (standing eyeball-gate). 8 commits, `56e5366`→`fdf0483`.

Picked up where Session 22 left off: it planned 3 builds but shipped none. This session BUILT all
three, in the recommended order, TDD, each phase committed + full-suite-green, everything config-gated
so Alex's engineering/controls flow stays byte-identical.

## Plan 1 — company registry to a measured ~100% (P1–P6)

- **P1 `56e5366` — deterministic bulk ATS-slug seed.** New `discover/dataset_seed.py` +
  `seed_companies.py` CLI: import an open MIT ATS-slug dataset (jobhive/OpenJobs) straight through the
  existing live probe-verify gate, skipping the JS-SPA-blind careers-link resolver. stdlib CSV/TSV/
  NDJSON/JSON parse, auto-detected columns (+`column_map`/`--col-*` override), ATS-vocab normalize,
  URL-column fallback via `detect_ats`. `verify_boards` = probe-only gate (skips known w/o probing,
  drops unprobeable/dead) + a `classify=` seam. Idempotent (save_companies dedups). **$0, no
  hallucination, no new deps.**
- **P2 `f234832` — industry-derived angles + `config.DEFAULT_INDUSTRY`.** `discover.enumerate.
angles_for_industry(industry, keywords, scope)`: empty/eng-like → `DEFAULT_ANGLES` byte-identically;
  any other field → neutral angles NAMING it; `scope='national'` → nationwide set.
  `enumerate_companies._resolve_industry` (mirrors `_resolve_metro`) selects angles.
- **P3 `477956b` — relevance classification gate.** `discover/classify.py`: `title_keywords_for` +
  `is_relevant_deterministic` (True match / False off-topic / None no-sample) + `classify_boards`
  (deterministic-first; ambiguous-only → optional batched AI `{relevant,subsector}`, cached by
  (ats,slug,industry); NEVER drops a no-sample board; keep-all w/o AI unless `drop_ambiguous`).
  `make_classifier` seam wired into `run_funnel` + `seed_companies --classify/--drop-offtopic`
  ($0 deterministic default via `sample_titles_for`).
- **P4 `5a4ec08` — per-industry capture-recapture loop + history.** `registry_coverage.
estimate_coverage_industry` + `loop_signal(history)→rising|plateau|dry` (plateau = union growth
  <2% two rounds AND coverage ≥85%; dry = flat union). New `coverage/registry_history.py` appends to
  `cache/coverage/registry/<industry>.jsonl` (injectable clock, nan→null). `company_coverage.py`
  `--record/--loop-signal` (already had `--industry`).
- **P5 `d92ba96` — nationwide/remote-first enumeration pass.** `enumerate_companies` runs a metro pass
  PLUS a national pass when the project allows remote (`hard.remote_ok`; `--national/--no-national`
  override). National pass uses the national angle set, excludes metro-pass domains (cross-pass dedup),
  tags adds `national`+`remote` (jobs surface under the inbox's remote/all geo views — anti-drown).
- **P6 `397fb4a` — host-level CC harvest + enterprise ATS.** `cc_harvest.harvest_host_index`:
  registered-domain CDX (`matchType=domain`) spans every subdomain/tenant (far more complete than the
  per-URL `host/*` prefix; dodges the ashby CDX 400), paginated via `showNumPages`. `run_funnel`
  `host_level/enterprise/max_pages`; enterprise harvests myworkdayjobs/icims/taleo/successfactors
  (where health systems & industrials live). CLI `--discover-host-level/--discover-enterprise/
--discover-max-pages`.

## Plan 2 — board-expansion `d07d8cb`

`config.SERPAPI_ENGINE` (google_jobs | indeed). `serpapi_client` reads it (Indeed engine's separate
`l` location param), engine in the cache key, defensive parse (indeed shape; unknown → `[]` not a
raise). **No standalone Indeed scraper** (ToS). `models.normalize_url` now unwraps Google/generic
redirect wrappers and collapses any Indeed URL to its `jk`, so an aggregator click-redirect and the
direct posting dedup to ONE inbox row. BC: normal ATS URLs untouched.

## Plan 3 — field-agnostic (GOAL 1 `b7bcd44`) + multi-person (GOAL 2 `fdf0483`)

- **GOAL 1.** Wizard: neutral welcome/examples + optional **Field/industry** entry & **Career-level**
  combobox (`_search_config` writes `industry` + translates level → rubric keys). `has_industry()`
  gates a post-setup "build your employer list" hint for a non-eng first run. **1E (the trap):**
  `match.facts` industry-gated — tech/empty keeps the eng role map + skill vocab (byte-identical);
  other fields merge universal role buckets (care/admin/finance/trade) + use profile-derived skills;
  `facts_for` caches under a profile signature so a health seeker's facts never leak from an eng
  seeker's cache. `ranker` threads `(industry, skill_terms)` from cfg (only non-tech → profile skills).
- **GOAL 2.** A person = a set of projects. `workspace.create_project(person=)` + `people()` /
  `projects_for_person()` / `person_of()`. GUI project bar: **+ Person** button (name → blank campaign,
  NO resume copy across identities, then the wizard) + "Person — Campaign" labels. Ranking follows the
  active person for free (slug-less paths); the GOAL-1 cache signature prevents cross-person facts leak.
  No migration.

## Autonomous decisions (Alex was away — "keep working until done"); every open-Q used the plan's default

1. **Dataset choice (P1 open-Q):** built the importer **dataset-agnostic** (auto-detect columns +
   `--col-*`/`column_map`), so jobhive OR OpenJobs both work — the actual bulk import (download the
   ~86k-row file → optional parquet→csv → `py seed_companies.py --dataset …`) is **your data-op step**;
   unit tests use fixtures. Recommend **OpenJobs** (has an industry column → less classify AI).
2. **loop_signal thresholds:** plateau = <2% growth ×2 rounds AND coverage ≥85% (the plan's proposal);
   config-overridable via `loop_signal(..., plateau_growth=, plateau_cov=)`.
3. **Paid SerpApi/Indeed:** built engine-selectable + config-gated; **free default (google_jobs)
   unchanged** — flip via `SERPAPI_ENGINE=indeed` only if you budget the paid engine.
4. **P5 national default = follows `remote_ok`** (which defaults True) → an API-path `enumerate_
companies` run now does a 2nd nationwide pass by default. It's additive (national+remote-tagged,
   local view unaffected) and gated by your own preference; `--no-national` = the exact old behavior.

## Needs Alex / eyeball (GUI — not unit-testable headless)

- `py gui.py`: the wizard's new **Field/industry + Career level** fields; the project bar's **+ Person**
  button + "Person — Campaign" labels + the new-person wizard flow.
- **Push the 8 commits** (held per the standing gate).
- To actually raise coverage: get a dataset (OpenJobs/jobhive), `py seed_companies.py --dataset f.csv
--industry controls_engineering [--ats greenhouse,lever,ashby] [--dry-run]`; then
  `py company_coverage.py --against <independent-list> --industry controls_engineering --record
--loop-signal` to measure.

## Guardrails honored

Token invariant intact — no new `facts_summary` field, no new `rubric_text` line (still ~94 tok/job);
all new AI is occasional company-building (cached/bounded), never per-search. Capture-recapture stays
2-independent-list (registry vs dataset/host-harvest, never the enumerator). Not fleet-safety code.

## Verification + adversarial review (all findings FIXED)

`py -m pytest -q` → green after every phase. A background adversarial Workflow review (Sonnet workers,
7 areas → per-finding adversarial verify, ~1.16M subagent tokens) at close **confirmed 9 real defects
— ALL fixed + regression-tested** (`2dc1a82`; +6 tests → **931 passed**):

1. **`models.normalize_url` (MAJOR, real data-loss):** the generic `?url=/?target=` redirect-unwrap
   fired on EVERY host → a direct ATS/apply URL carrying such a marketing param (e.g. a ZipRecruiter
   apply link) got replaced by the unrelated destination → distinct postings collapsed in dedup, one
   silently dropped from the inbox. → gated to click/redirect-looking hosts/paths.
2. **`ranker._facts_profile` (MAJOR):** no `workspace.load_config()` fallback when `cfg is None`, and
   the live GUI "Ask AI to rank" buttons call with cfg=None → the whole **1E agnostic feature never
   fired for non-tech projects** (dad-health) AND the facts cache collapsed to the shared job_key-only
   file (the very cross-person leak 1E was meant to prevent). → falls back like `build_rubric`; tech
   industry still yields no skill_terms (Alex byte-identical). This also resolves finding #5.
3. **`cc_harvest.harvest_host_index` (MAJOR):** a later-page failure discarded earlier pages and
   misreported "no hosts reachable". → first page sets reachability; later-page errors keep prior pages.
4. **`dataset_seed` (MAJOR):** bulk-seed ignored the dataset's real `name` column → two distinct boards
   sharing a slug across ATS platforms collided on the synthetic name and one was silently dropped. →
   threads the real name.
5. **`enumerate_companies` national (MAJOR):** defaulted ON via `remote_ok` (True for any project
   without a preferences.json — controls-cincinnati has none) → a silent 2nd LLM pass. → **now explicit
   `--national` opt-in** + a discoverability hint (`--no-national` removed). _(This supersedes the
   "P5 national follows remote_ok" note above — it is now opt-in.)_
6. **`gui._new_person`/`_new_project` (MAJOR):** no duplicate-slug guard → re-creating a name silently
   reactivated the existing project and the wizard OVERWROTE its profile. → guarded.
7. **`gui` project switcher (MINOR):** resolved selection by display label → identical "Person —
   Campaign" labels made one project unreachable. → index-based.
8. **`classify.is_relevant_deterministic` (MINOR):** `\b` regex missed symbol keywords (C++/.NET). →
   uses `scorer._term_pattern`.

Net: **931 passed, 1 headless-GUI skip, clean tree.** Two fixes (#2 ranker, #7/#9 GUI) are behavioral
improvements worth an eyeball in `py gui.py`; #7/#9 are GUI-only (not headless-unit-testable), the
rest have regression tests in `tests/test_review_fixes_s23.py`.
