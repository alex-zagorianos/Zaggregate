---
title: "WS-1 — Coverage Foundations + Benchmark (Design Spec)"
created: 2026-06-22
status: draft — pending spec review, then implementation plan
workstream: 1 of 3
builds_before: [[spec-2026-06-22-ws2-coverage-engine]], [[spec-2026-06-22-ws3-ai-rerank-roundtrip]]
related: [[research-2026-06-22-job-discovery-playbook]], [[spec-2026-06-22-distributable-product-design]]
---

# WS-1 — Coverage Foundations + Benchmark

## 1. Context & goal

The app (`E:\ClaudeWork\ZAG0005 - Job Search App`) finds jobs across ~10 API sources + 6 ATS
scrapers + a hardcoded company registry (`scrape/company_registry.py`) merged with a user
`companies.json`, but has **no way to rate how complete its coverage of an area
is**, and its dedup is a thin URL/`title|company` heuristic (`models.py` `identity_key`,
`normalize_url`). You asked, first, for "a rating of how well it finds all jobs in an area, as close
to 100% as possible — and tested for verification."

This workstream builds the **measurement substrate first**, on the principle _measure → improve-with-
proof → tailor_. It delivers two things that everything downstream depends on:

1. **An entity-resolution engine** that canonicalizes companies, normalizes titles to O\*NET-SOC,
   normalizes locations, and assigns each job a **stable `job_key`**. This is the load-bearing
   prerequisite for an honest coverage number, fixes the existing weak dedup, and becomes the join
   key for the WS-3 AI round-trip.
2. **A coverage-rating harness** that produces a defensible **0–100 area-coverage score** by
   triangulating three legs (reference-proxy primary, capture-recapture secondary, JOLTS sanity
   gate), persists each run, and is wrapped as a **repeatable automated regression test**.

WS-1 adds _no new sources_ — it measures the current crawler so WS-2's additions can be proven.

## 2. Decisions locked (from brainstorm)

- **Fully generic** — no Cincinnati/engineering hardcoding; area + SOC-grouping are inputs.
- **Free-first** — `cleanco` + `datasketch` + `rapidfuzz` (pip, light) for entity resolution; Census
  - BLS APIs (free keys, optional) for denominators. Splink/`dedupe`/statsmodels are **optional**
    heavy deps gated behind a capability check — never required for the frozen build.
- **Rating = three legs, never one opaque number** — composite plus CI, Chao1 ceiling, and JOLTS
  gate reported separately (see research §5).
- **O\*NET-SOC crosswalk ships as bundled static data** (public domain) so title→SOC works offline.

## 3. Non-goals (YAGNI)

- No new job sources (WS-2).
- No export/import or AI round-trip (WS-3).
- No GUI rework beyond surfacing the latest coverage score read-only.
- No Splink/R requirement — capture-recapture estimators are pure-Python (numpy only); statsmodels is
  an optional path for the ≥3-source log-linear model with a hand-rolled fallback.
- No live network calls in the regression test — it runs on cached fixtures.

## 4. Architecture

New top-level package **`coverage/`** (sibling of `search/`, `scrape/`, `match/`, `tracker/`),
plus a bundled data dir **`data_static/`** for the O\*NET-SOC crosswalk and a CBSA delineation file.

```
coverage/
  entity.py        # canonicalize_company(), normalize_title()->SOC, normalize_location(), job_key()
  resolve.py       # block (datasketch LSH) -> score (rapidfuzz) -> cluster (union-find) -> clusters
  estimators.py    # chapman(), chao1(), good_turing(), loglinear() (pure-python; statsmodels optional)
  reference.py     # reference-proxy leg: query a broad aggregator, dedup, D & N per SOC
  jolts.py         # BLS JOLTS sanity gate (optional key; degrades to "skipped")
  geography.py     # area -> CBSA -> location-variant set (Census optional; bundled crosswalk default)
  benchmark.py     # orchestrates the 3 legs -> CoverageReport; persists runs
  report.py        # CoverageReport dataclass + serialization (json) + human summary
data_static/
  onet_soc_alt_titles.tsv      # public-domain O*NET alternate-titles -> SOC code
  cbsa_delineation.csv         # CBSA -> principal cities/counties (Census, public)
```

Data lands under `USER_DATA_DIR` (per `config.py`): each run persists as
`USER_DATA_DIR/coverage/runs/<scope-hash>/<timestamp>.json`, plus an append-only rollup index
`USER_DATA_DIR/coverage/runs.jsonl` (one line per run for trend queries — no new DB). **`scope-hash`
is pinned:** `sha1("|".join([area, window, soc_grouping, ",".join(sorted(source_ids))]))[:12]`, so the
same scope is comparable across runs (the regression gate keys off it). Bundled static data resolves
from `DATA_DIR/data_static/` (read-only bundle), per the existing two-tier path model.

### 4.1 How it plugs into the existing code (no fork)

- `coverage/entity.job_key(job)` becomes the canonical identity. `models.py` gains a cached
  `JobResult.job_key` property delegating to it; `search_engine._deduplicate()` and the cross-run
  `seen_urls()` filter switch from `normalize_url`-only to `job_key` (URL stays the fast-path; entity
  resolution is the fallback that catches cross-source dupes). `normalize_url` is kept and reused.
- The benchmark reads jobs from a completed search run (the in-memory `list[JobResult]` from
  `search_engine.run_full_search`, or the `inbox`), so it measures the _real_ crawler output.

## 5. Components

### 5.1 `coverage/entity.py` — canonicalization & `job_key`

- `canonicalize_company(name) -> str` — `cleanco.basename` (strip Inc/LLC/Ltd/GmbH/Corp), casefold,
  unicode NFKD, collapse punctuation/whitespace; apply a small editable alias table
  (`data_static/company_aliases.json`, e.g. `optum -> unitedhealth`). Pure, deterministic.
- `normalize_title(title) -> {soc_code, soc_title, seniority}` — strip seniority tokens
  (Sr/Senior/Jr/I/II/III/Lead/Principal/Staff), `rapidfuzz` best-match the cleaned title against the
  bundled O\*NET alt-titles table; return SOC code + matched canonical title + parsed seniority.
  Confidence below a threshold → `soc_code = "00-0000"` (unmapped) but keep the cleaned title.
- `normalize_location(loc) -> {city, state, metro, is_remote}` — parse free-text/`jobLocation`;
  flag remote; map to CBSA via `geography.py`.
- `job_key(job) -> str` — **pinned contract** (the join key for WS-1 dedup, WS-2 freshness deltas,
  and WS-3 import — define once, never drift): `sha1(payload).hexdigest()[:16]`, where
  `payload = "\x1f".join([canon_company, soc_code, location_token, title_core])` with
  `location_token = "remote" if is_remote else f"{city}|{state}"` and `title_core` = the
  seniority-stripped, casefolded, whitespace-collapsed title. **Deliberately not URL-based** (URLs
  differ across sources for the same posting). Existing code uses MD5 for `identity_key`/`fit_token`;
  `job_key` is a **new, independent** SHA1 identity — `fit_token` (8-char MD5) stays only for
  back-compat fit mapping, but `job_key` is SSOT.
- **Access model:** exposed as `JobResult.job_key` via `functools.cached_property` (computed once per
  object, memoized) so every dedup/benchmark pass is O(1) after first touch.

### 5.2 `coverage/resolve.py` — clustering near-duplicates

`resolve(jobs) -> list[Cluster]`: (1) **block** with `datasketch` MinHashLSH over shingled
`canon_company + soc + norm_location + title` (Jaccard threshold ~0.5) — cheap exact-block fallback
`(canon_company, soc, norm_location)` when datasketch is unavailable; (2) **score** candidate pairs
within a block with `rapidfuzz` (`token_set_ratio` on title, `WRatio` on company, plus
location/salary/date-proximity bonuses) → match if combined ≥ threshold; (3) **cluster** matched
pairs via union-find/connected-components; each cluster → one canonical job (best-fielded member) +
the set of source job_keys it absorbed. Deterministic given the same input + thresholds.

### 5.3 `coverage/estimators.py` — capture-recapture (pure Python)

- `chapman(n1, n2, m) -> (N_hat, var, ci95)` — bias-corrected Lincoln-Petersen.
- `chao1(f1, f2, s_obs) -> N_hat` — bias-corrected lower bound on the universe.
- `good_turing(f1, n) -> C_hat` — completeness estimate.
- `loglinear(source_membership_matrix) -> N_hat` — ≥3-source Poisson GLM with pairwise interactions
  via statsmodels **if importable**, else fall back to averaged pairwise Chapman across source pairs.
- All operate on the **deduped** clusters: a source "captures" a cluster if any of its job_keys is in
  it. `f1`/`f2` = clusters seen by exactly 1 / exactly 2 sources.

### 5.4 `coverage/reference.py` — reference-proxy leg (primary)

`reference_coverage(area, soc_groups, our_clusters, provider) -> {D_g, N_g, cov_proxy_g, weighted}`.
Default provider = an aggregator the app already has (Adzuna; JSearch/SerpApi if a key is present),
queried for the same area+occupation, **run through the same `resolve()`** to get a deduped `D`.
`N` = our clusters that match a reference cluster. Per-SOC; `employment_share_g` weights come from
`jolts.py`/Census or a uniform fallback. Honors source rate limits + 24h cache (reuse
`search/http_util.py` — `FileCache`/`cache_key`/`RateLimiter`; `base_client.py` is abstract-only).
**Uses published aggregate counts where available** before falling
back to enumerating cards (lower ToS risk, research §5b).

### 5.5 `coverage/jolts.py` — macro sanity gate

`jolts_gate(area, naics, our_count) -> {expected_openings, ratio, verdict}` using BLS JOLTS API v2
(free key in `secrets/`). Finest matching geography (national/state). Returns pass/fail/skip
(skip when no key or no matching series). **Not folded into the composite** — reported separately.

### 5.6 `coverage/benchmark.py` + `report.py` — orchestration

`run_benchmark(jobs, area, soc_groups, *, provider=None) -> CoverageReport`:

1. `resolve(jobs)` → clusters + per-source membership (record dedup metadata).
2. Leg 2 capture-recapture (`estimators`) → `cov_CR` + CI, `cov_upper` (Chao1), `C_hat`.
3. Leg 1 reference-proxy (`reference`) → `cov_proxy_weighted` (if provider available; else null).
4. Leg 3 JOLTS gate (if key).
5. Composite `CoverageScore = 100·(0.5·cov_CR + 0.3·cov_proxy_weighted + 0.2·C_hat)` — weights
   renormalize over whichever legs are present.
6. Persist `CoverageReport` JSON to `USER_DATA_DIR/coverage/runs/...` + append to rollup index.

`CoverageReport` carries: scope (area, window, soc-grouping, source list), composite score, every
leg's components, `cov_CR` CI, Chao1 ceiling, JOLTS verdict, dedup F1 (when a labeled set exists),
per-SOC table, and the cluster/source counts. `report.human_summary()` renders the terse readout.

## 6. Data flow (one rating)

`run_full_search` (or inbox load) → `list[JobResult]` → `resolve()` → clusters → 3 legs →
`CoverageReport` → persist + (optional) print/GUI badge. No writes outside `USER_DATA_DIR`.

## 7. Error handling & edge cases

- Missing optional deps (`datasketch`/`statsmodels`/`splink`): capability-probe at import; fall back
  to exact-block / pairwise-Chapman; record which path ran in the report. Never crash.
- No reference key: Leg 1 = null, composite renormalizes over Legs 2 (+ C_hat); clearly labeled.
- No JOLTS key / no matching series: gate = "skipped".
- Sparse data (`f2 == 0`): Chao1 uses the `+f1(f1-1)/(2(f2+1))` form; guard div-by-zero.
- Single source: capture-recapture undefined → composite falls back to proxy-only or returns
  "insufficient sources" with a clear message.
- O\*NET match below confidence → unmapped SOC bucket; coverage still computed on mapped + unmapped.

## 8. Testing strategy (this IS the deliverable's verification)

- **Unit:** `canonicalize_company` (Inc/LLC/alias/unicode cases); `normalize_title` → known SOC codes;
  `job_key` stability + cross-source collision (same posting from Greenhouse + Adzuna → same key);
  `chapman`/`chao1`/`good_turing` against textbook worked examples (assert exact numbers); composite
  renormalization when legs are missing.
- **Entity-resolution accuracy:** a committed **labeled fixture** (`tests/fixtures/coverage/labeled_pairs.jsonl`,
  ~200 hand-labeled same/different job pairs drawn from real multi-source captures) → assert dedup
  **precision/recall/F1 ≥ baseline thresholds** (e.g. F1 ≥ 0.85). This is the gold check the user asked
  for ("tested for verification").
- **Benchmark integration:** a committed **cached multi-source fixture** for one test area →
  `run_benchmark` produces a stable `CoverageReport`; assert score within a tolerance band and that
  all expected legs populate.
- **Regression gate test:** re-running the benchmark on the fixture must not drop dedup F1 below the
  floor nor regress CoverageScore beyond tolerance vs a committed `baseline.json` — this is what WS-2
  re-runs after each source addition to _prove_ lift.
- Keep the suite green; add ~30–40 tests here. (Current suite ≈ 269 test functions across 39 files —
  recount at build time; don't hard-code a target number.)

## 9. Risks

- **R1 — O\*NET crosswalk size/licensing.** O\*NET is public domain; ship only the alt-titles + SOC
  columns to keep the bundle small. Mitigation: trim to the columns used; document the O\*NET version.
- **R2 — capture-recapture overstates coverage** when sources scrape each other (positive dependence).
  Mitigation (research §5c): always report Chao1 _ceiling_ + CI; weight CR at 0.5 not 1.0; surface the
  dependence caveat in the report.
- **R3 — reference proxy is biased/segment-skewed.** Mitigation: per-SOC + employment-share weighting;
  label `D` as a biased lower proxy; never present proxy alone.
- **R4 — PyInstaller hiddenimports** for `rapidfuzz` (C-ext) / `datasketch`. Mitigation: add to
  `app.spec` hiddenimports; CI build-smoke (WS deferred to packaging, but note the dep now).
- **R5 — entity resolution changes existing dedup behavior.** Mitigation: keep `normalize_url` as the
  fast path; `job_key` only _adds_ cross-source collapsing; characterization-test the current dedup
  before swapping so behavior changes are intentional.

## 10. Done criteria

- `coverage/` package + bundled static data committed; `job_key` wired into dedup behind the URL
  fast-path.
- `run_benchmark` produces a `CoverageReport` (3 legs + composite + CI + ceiling + JOLTS) for a test
  area and persists it under `USER_DATA_DIR/coverage/`.
- Labeled-pair dedup F1 ≥ 0.85 and the regression-gate test pass on committed fixtures.
- A **baseline coverage number for the current crawler** is recorded (the "before" figure WS-2 must
  beat). Tests green (current suite + ~30–40 new).
- **Bundled static data is sourced before planning:** `onet_soc_alt_titles.tsv` (O\*NET, public
  domain — pin version) and `cbsa_delineation.csv` (Census, public) do not exist yet; acquiring +
  license-checking + format-validating them is an explicit early task in the plan, not an assumption.
