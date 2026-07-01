# Session 26 round-3 — jobhive seeder + ETag: adversarial review (2026-07-01, Opus/ultracode)

Diff reviewed: `7456a04..HEAD` (streaming jobhive bulk seeder + wiring, ETag/conditional-GET for
greenhouse+lever, and the +252-company seed run). Focused 3-dimension review (6 agents,
per-finding adversarial verification, Sonnet) → **3 confirmed findings (0 dismissed): 1 critical,
2 major.** All fixed + regression-tested; full suite green.

## Findings + fixes

1. **CRITICAL — ETag re-served dead boards forever** (`scrape/cache_helpers.py`
   `conditional_get_json`). The error fallback treated a permanent HTTP error (404/410/500 — a
   removed/renamed board) the same as a transient network blip: it returned the stale cached body,
   so the scraper saw `data != None`, never called `mark_failed`, and re-served the zombie board's
   jobs on every run (also defeating the failed-cache backoff + the ETag efficiency goal). This was
   a regression from the migration (pre-diff, any HTTPError → `mark_failed` + `[]`). **Fix:** a
   server HTTP-status error now returns `(None, False)` (→ scraper marks it failed, matching
   pre-diff); only a true network exception keeps the stale-better-than-nothing fallback. Both
   paths regression-tested.

2. **MAJOR — `_looks_junk` dropped real long-name employers** (`discover/jobhive_seed.py`). The
   `len > 30` rule silently excluded legitimate boards like `lawrencelivermorenationallaboratory`
   and `johnsonandjohnsoninnovativemedicine` (national labs, universities, hospital systems,
   full-legal-name corporates) — exactly the large/health employers we want, with no log. **Fix:**
   dropped the length-only rule; junk = a long hex hash OR a long _digit-heavy_ string. Real
   concatenated org names now pass. (The already-written seed missed some of these — a reach gap,
   not a correctness error; the fix makes future/onboarding seeds correct.)

3. **MAJOR — `keywords_for_industry` re-polluted for generic fields** (`discover/jobhive_seed.py`).
   The `specific or out` fallback handed back purely generic tokens when a field had no synonyms and
   its own tokens were all generic (e.g. "general manager" → `['general','manager']`) — so a
   `--jobhive` run for such a field matched ~any company, defeating the precision filter. **Fix:**
   `keywords_for_industry` now returns `[]` for an all-generic field (no loose fallback); both
   callers (`build_company_list._jobhive_stage` + the CLI) skip an empty-keyword field with a clear
   message instead of seeding on generics.

## Note

The +252-company seed was written before fixes 2/3 — but that run used _curated multi-word_
keywords (not the generic fallback), so fix 3 didn't affect it; fix 2 means it under-captured some
long-name orgs (a reach gap only). Health-informatics stayed thin (13) because health systems live
on Workday/NEOGOV, not jobhive's tech-ATS slices — the real municipal/health channel is a future
lever, not a bug. Suite after fixes: full green (see commit).
