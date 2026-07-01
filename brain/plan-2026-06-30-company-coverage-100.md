---
title: Plan — company registry to measured ~100% coverage (field-agnostic, cheap-plan-safe)
date: 2026-06-30
status: plan (NOT built)
author: Opus planner subagent
tags: [plan, coverage, discovery, agnostic, remote, capture-recapture, tokens]
---

# Plan: push the company registry to a MEASURED ~100% of relevant employers

> Field-agnostic parity (a VP Health-Informatics seeker reaches the same breadth
> as engineering), AI as a bounded/cached participant, capture-recapture as the
> "how close to 100%" instrument driving loop-until-dry. Ranking token path
> (~94 tok/job) is never touched — all AI here is occasional company-building.

## Three findings that shape it

1. **The resolver is the weak link, not the LLM.** `discover/career_link.py` reads
   robots/sitemap/homepage anchors → misses JS-SPA ATS boards (~1/10 hit). So the
   biggest win is a **deterministic bulk seed** (open MIT ATS-slug dataset) fed
   straight through the existing probe-verify gate (`scrape/ats_detect.probe_count`)
   - `merge_discovered` — sidesteps the resolver, $0.
2. **Downstream is already field-parameterized** (`get_registry(industry=)`,
   `enumerate_via_api(angles=)`, additive user-wins merge). Gaps: enumeration angles
   are eng-hardcoded (`DEFAULT_ANGLES`), there's **no `industry` config key**, and
   no relevance classification of harvested boards.
3. **Measurement primitive exists** (`coverage/registry_coverage.estimate_coverage`
   — Chapman) but is one-shot: no loop, no per-industry scoping, no history.

## Phased tasks (value/effort order)

**P1 — Deterministic bulk ATS-slug seed (MIT dataset) → probe-verify → merge** (huge jump, $0, low effort)

- New `discover/dataset_seed.py`: `load_ats_dataset(path, ats_filter=)` → `{ats_type:{slug}}`
  parsing **CSV/NDJSON via stdlib (NO pyarrow/pandas)**; map dataset ATS names → our vocab.
  `seed_from_dataset(path, industry=, probe=probe_count, max_workers=12, limit=, ...)` →
  probe-verify each slug (reuse `enumerate_companies.resolve_and_verify`'s gate, skip the
  `find_career_url` step since ats_type+slug are known) → `merge_discovered`. Live-probe =
  no hallucination/staleness possible.
- New CLI `seed_companies.py`: `--dataset --industry [--ats] [--limit] [--dry-run]`.

**P2 — Industry-derived angles + `industry` config key** (agnostic parity, 0 ranking tok)

- `config.py`: `DEFAULT_INDUSTRY = ""` (empty = today).
- `discover/enumerate.py`: keep `DEFAULT_ANGLES` as eng fallback; add
  `angles_for_industry(industry, keywords=, scope=)` → neutral size/type-spread angles
  naming the user's field; eng/empty industry → byte-identical `DEFAULT_ANGLES`.
- `enumerate_companies.py`: `_resolve_industry(arg)` (mirror `_resolve_metro`) → CLI >
  config `industry`/`keywords` > `DEFAULT_INDUSTRY`.

**P3 — Relevance classification gate (deterministic-first, AI on long tail only)**

- New `discover/classify.py`: `title_keywords_for(industry, keywords)`,
  `is_relevant_deterministic(name, sample_titles, kw) -> bool|None`,
  `classify_boards(boards, industry, keywords, ai=, cache_path=)` — keyword-match on
  already-scraped titles; AI `{relevant, subsector}` **only** on ambiguous (None),
  batched ≤10/call, cached by `(ats,slug,industry)`. Never drop a board with no title sample.
- Wire as optional filter in `seed_from_dataset` + `run_funnel` (only when `industry` passed).

**P4 — Capture-recapture LOOP + per-industry scoping + history (the measurement)**

- `coverage/registry_coverage.py`: `estimate_coverage_industry(industry, list_b, ...)`
  (restrict list A to `get_registry(industry=)`); `loop_signal(history) -> rising|plateau|dry`.
- New `coverage/registry_history.py`: append estimates to
  `cache/coverage/registry/<industry>.jsonl` (mirror `coverage/report.persist`).
- `company_coverage.py`: add `--industry`, `--record`, `--loop-signal`.
- **Two independent lists:** A = registry (industry-scoped); B = P1 dataset or a fresh
  host-level CC harvest — **NEVER** the LLM enumerator (correlated → inflates N̂).

**P5 — Remote = nationwide scope switch**

- `angles_for_industry(..., scope="metro"|"national")`: national set (national systems/
  enterprises, remote-first employers), no metro string. `enumerate_companies`/`seed_companies`
  read `hard.remote_ok` → run metro AND national passes, dedup by domain.
- **Anti-drown:** P3 relevance gate filters the national pool; `geo/filter.py` view-buckets
  keep the local inbox local (national/remote adds surface only under remote/all views);
  tag national adds `national`+`remote`.

**P6 — Host-level Common-Crawl upgrade + enterprise-ATS bulk (completeness ceiling)**

- `discover/cc_harvest.py`: `harvest_host_index(...)` using cc-index host-level columnar
  (`url_host_registered_domain`) — far more complete than per-URL CDX; keep CDX as fallback,
  gate behind a flag. (Also fixes today's ashby CDX 400.)
- Add enterprise ATS hosts (`.myworkdayjobs.com`, `.icims.com`, `.taleo.net`, `*.sapsf.*`)
  to harvest host-lists — where health systems live. Detection + probe already exist; no new scraper.

## AI invocation + token budget (ranking path untouched)

| Step                                                                                     | Trigger                             | Shape                                        | Budget                | Cheapness                            |
| ---------------------------------------------------------------------------------------- | ----------------------------------- | -------------------------------------------- | --------------------- | ------------------------------------ |
| P2 angles                                                                                | per (metro,industry), company-build | 4–5 prompts ~132 in + ~900 out               | ~5k one-time          | cached; bridge/Haiku                 |
| P3 classify                                                                              | ambiguous boards only               | `{relevant,subsector}` ≤10/call, titles only | ~0.3–0.5k / 10 boards | deterministic-first; permanent cache |
| P5 national seed                                                                         | remote_ok, long tail                | national angle-set                           | ~5k one-time/industry | same cache/gate                      |
| Deterministic-first ($0): bulk seed, probe-verify, dedup, merge, capture-recapture math, |
| host harvest, keyword relevance. Re-run w/ no new ambiguous boards = all cache hits.     |

## New-dependency decisions

- **No pyarrow/pandas** (keep .exe lean; past crash from bundling gaps). Importer parses
  CSV/NDJSON via stdlib; user does a one-time offline parquet→csv conversion (documented).
- CC host index uses existing `requests` session — no new dep.
- **License:** jobhive (MIT) + OpenJobs (MIT) safe to ship. **Feashliaa = CC BY-NC**
  (personal-use only) → local file only, never in a distributable. PDL = CC BY 4.0 (attribute).

## Files

New: `discover/dataset_seed.py`, `discover/classify.py`, `coverage/registry_history.py`,
`seed_companies.py`. Modified: `discover/enumerate.py`, `discover/funnel.py`,
`discover/cc_harvest.py`, `coverage/registry_coverage.py`, `company_coverage.py`,
`enumerate_companies.py`, `config.py`. Tests: `tests/discover/test_dataset_seed.py`,
`tests/discover/test_classify.py`, `tests/coverage/test_registry_loop.py`, extend
`tests/coverage/test_registry_coverage.py`. Untouched (safe): save_companies/merge_discovered,
match/facts, match/rubric, claude_bridge ranking.

## Risks

- Bulk import bloats registry with off-industry boards → P3 gate + `get_registry(industry=)`
  filter + tiering; all adds live-probed.
- Probe cost on a large dataset → `--limit`, threaded, cached, maintenance-only.
- Capture-recapture independence violated → hard-code B to dataset/host-harvest; refuse enumerator.
- National drowning local → relevance gate + geo view-buckets + tags.
- License leakage → NC datasets local-only; MIT/CC-BY only in shipped seed.
- Regressing Alex's eng flow → empty/eng industry = byte-identical angles; all new steps additive/off.

## Verification

Unit: dataset parse + ATS map + bad-row drop; classify keep/drop/ambiguous + cache-hit-no-call;
industry-scoped estimate; loop_signal transitions; angles eng-fallback byte-identical + national
omits metro. Integration (mocked): seed end-to-end verified count + lift-only merge (mirror
test_discovery_lift). Manual: `seed_companies.py --dry-run`; `company_coverage.py --industry ...
--record` twice around a round → `--loop-signal` rising→plateau. Rollback: git revert; companies.json
append-only so revert leaves a larger-but-valid registry.

## Open questions

1. Canonical bulk dataset: **jobhive** (MIT ~86k/47 ATS) vs **OpenJobs** (MIT, has
   `industry_category` → lets P3 skip AI on many boards). Recommend OpenJobs primary if ATS/slug clean.
2. `loop_signal` thresholds: propose plateau = union growth <2% over 2 rounds AND coverage ≥85%. Confirm.
3. Tag bulk adds with resolved `industry` (so `get_registry(industry=)` filters immediately) vs
   generic `["discovered"]`. Recommend industry tag when known.

## Could not verify

- Exact jobhive/OpenJobs parquet column names / ATS vocab / industry-column cleanliness (finalize
  importer map against the real file; keep it configurable).
- cc-index host-level endpoint shape for the current crawl (`CC-MAIN-2025-05` hardcoded) — confirm before P6.
- Whether the frozen .exe bundles `discover/` + new CLIs for a stranger's first run (dev env fine).

## Out of scope

Local-model classify/score (deferred; `ai=` seam is local-swap-ready), scorer math / ranking
token path, GUI coverage-trend widget, in-app parquet conversion, GOAL-2 multi-person.
