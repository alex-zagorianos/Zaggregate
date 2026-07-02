# S32 — Local-scorer honesty for the no-AI user (design)

Builder worktree `s32/scoring` (baseline master@414bb03). Implements the 5 items the
raw local `Score` misleads a keyless user on, per
`brain/improvement-plan-2026-07-02-general-user.md` P0-3 + QW-2/QW-3 and
`brain/general-user-tests-2026-07/review-ranking.md` #1–#6.

Root cause (both docs): the correct seniority/restriction logic lives in `match/facts.py`
(the AI-batch path) and is NOT wired into the local title score or the `preferences.hard_gate`.

## Guiding constraint: gated, prove-byte-identical

Every default-behavior change reported explicitly. Where a change is gated on config
(`seniority_target` present, non-US region token present, etc.), an ungated profile must
score byte-identical. Regression tests assert this on representative fixtures.

## Item 1 — Seniority-aware local score + gate (P0-3, review #1/#3)

- `match/facts.py`: extend detectors so they cover the plan's full marker set:
  - `_ROMAN` currently matches only I/II/III and needs a trailing boundary → add `IV`
    (and keep III→senior; map IV→senior tier too). New `_ROMAN_MAP` entry.
  - `_YEARS_EXP` misses bare "8+ YOE" / "years of experience" (needs an experience
    qualifier nearby). Add a `YOE`/`years of experience` alternative.
  - These are additive: existing outputs for already-detected strings unchanged.
- `match/scorer.py`: NEW module constant `_SENIORITY_TARGET_ORD` mapping the config's
  `seniority_target` strings (`intern/entry/mid/senior/senior-exec/…`) to the same
  ordinal scale as `_LEVEL_ORD`. NEW helper `_seniority_target_adj(title, desc,
target_ord, years_cap)` returning a bounded negative nudge (0..−12) when the posting's
  detected level (or required years) EXCEEDS the target — mirrors the exec branch for the
  below-target IC case. **Only engages when `seniority_target` is explicitly set**
  (`target_ord is not None`); a profile without `seniority_target` passes `None` →
  returns 0 → byte-identical.
- Thread a new `seniority_target=` + `years_cap=` kwarg (both `Optional`, default `None`)
  through `score_job`/`score_jobs`. `score_jobs` reads them once; all 5 callers pass
  `cfg.get("seniority_target")` / `cfg.get("years_cap")`.
- Nudge magnitude: senior/lead (1 tier over) −8, manager (2 over) −10, director+ −12;
  required-years over cap adds −4 (bounded total −12). Never hides — a downrank, not a drop.
- Respect existing exclude behavior: applied AFTER the existing `_seniority_fit_adj`
  (exec branch) and independent of the opt-in `seniority_exclude` blocklist.

## Item 2 — Country-blind remote (QW-2, review #2)

- `search/search_engine.py` `_location_score`: NEW `_NON_US_REMOTE_RE` (conservative:
  `czech|czechia|emea|latam|\buk\b|united kingdom|\beu\b|europe|canada|australia|india|
germany|mexico|brazil|apac|…`, word-bounded). When a job location contains "remote"
  AND a non-US region token AND the target is a US metro AND no US signal in the string,
  return reduced credit (1 instead of 3) instead of full marks.
- Config escape hatch: a new optional param `remote_regions_ok` (default `False`) — when
  the user genuinely can work in those regions, the cap is skipped (full marks restored).
  Threaded from `preferences.json` `remote_regions_ok` alongside `remote_ok`.
- Default behavior change: a US-target search with a non-US-only remote row now gets
  `loc 33%` not `loc 100%`. A plain "Remote" (no region token) is UNCHANGED (still 3).
- Also feed a label-derived restriction: extend `facts._detect_restriction` inputs via a
  new `_detect_restriction_label` so `gate._FOREIGN_RESTRICTION` can catch a bare
  "Remote - Czechia" label (closes the AI-gate hole too) — additive, only fires on the
  label regex, default off for US labels.

## Item 3 — Sub-floor salary in JD body (QW-3, review #5)

- Normalization already exists: `salary_from_text`/`parse_comp` annualize monthly/hourly
  (verified: `US$1,500 per Month → 18000`). The gate just never reads the body.
- `preferences.hard_gate`: when a job's API salary fields are BOTH empty, run
  `parse_comp(description)` and gate on the annualized floor — DROP only on a _confident_
  sub-floor parse (a single clearly-periodized figure or a full range whose top is below
  floor). Ambiguous/None parse → kept (wide net preserved).
- Default behavior change: a $90k-floor gate now drops a body-only "$1,500/month" row.
  Rows with no body comp signal, or comp at/above floor, are unchanged.

## Item 4 — Location-label distrust (review #6)

- `preferences.hard_gate` (or a scorer note): smallest robust version — when the stamped
  `job.location` is a bare echo of a query metro AND the description body names a
  _different_ US state, downgrade location credit / flag. Implement as a scorer-side
  location-credit cap keyed on a body-vs-label state contradiction (never hard-drop).
- Conservative: only fires when BOTH a label state and a _different_ body state are
  confidently extracted (first `City, ST` in body). Default (no body, or agreeing states)
  unchanged.

## Item 5 — Title-family disambiguation (review #4)

- review-ranking.md §4 sketch: optional per-profile `title_context_required` list. When
  set, cap title credit for an ambiguous head term unless a context token co-occurs in
  title/description. Reuse `industry_profile` consulting `title_terms` as the context set.
- Strictly opt-in (default empty → byte-identical). Threaded as `title_context_required=`.

## Test plan

- `tests/test_scorer_seniority_target.py` — item 1 nudge + byte-identity when unset.
- `tests/test_location_remote_country.py` — item 2 cap + escape hatch + plain-remote unchanged.
- `tests/test_gate_salary_body.py` — item 3 sub-floor body drop + safe-keep.
- `tests/test_location_label_distrust.py` — item 4 contradiction downrank.
- `tests/test_title_context.py` — item 5 opt-in cap + default byte-identity.
- `tests/test_facts_seniority_markers.py` — IV / YOE detector extensions.
- Full suite must stay green (baseline 1744 passed / 1 skipped).
