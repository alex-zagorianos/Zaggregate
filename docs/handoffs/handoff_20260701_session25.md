# Handoff — Session 25 (2026-07-01, Opus 4.8 / ultracode, overnight autonomous)

**Task (Alex):** cast as wide a net as possible for Alex + dad + any-field general users; access Indeed like we
access LinkedIn; research + build ways to **certify we've found 90–100%** of relevant companies/jobs; improve
**sorting/ranking** and **storage**; exhaustive research w/ many subagents; build a plan then execute; run
overnight, best judgment. **Agnostic use case preferred.**

## What happened

12-dimension web-research fan-out (Workflow + agents, ~2.5M tokens) → integrated 30-item plan → built the
autonomous-safe, high-value items across parallel Sonnet worktree builders (Clusters B/C/E) + inline Opus
(coverage flagship, semantic ranker, quality wins) → **6-dimension adversarial self-review (8 defects, all
fixed)**. **22 commits, 981 → 1111 tests, full suite green. PUSH HELD** (master now **55 ahead** of origin).

**Read-me-first:** `brain/REVIEW-REPORT-2026-07-01-session25.md` (full changelog + §7 ranked "Needs Alex").
Research: `brain/research-2026-07-01-reach-*.md` + `...-SYNTHESIS.md`. Plan/log:
`brain/plan-2026-07-01-session25-reach-buildout.md`.

## Shipped (all additive, config-gated, Alex byte-identical)

- **Coverage certification (goal 3):** `coverage/reach.py` — every `daily_run` logs + persists an honest
  _"seeing ~X% (95% CI Y–Z%) of the reachable universe, ~N unseen, K independent source families"_ from the
  run's raw multi-source overlap (capture-recapture), with a truthful "cannot certify (need ≥2 independent
  families / no overlap)" fallback. Fixed the estimator bugs the research + review caught (jolts series,
  chao1→chao2, bootstrap CI, correlated-source collapse `coverage/independence.py`, zero-overlap false-100%,
  Chapman negative-CI crash). CLI: `py -m coverage.reach --project <slug>`.
- **Indeed (goal 1):** confirmed there's no free/legal read API — reach it via the already-wired Google-Jobs
  proxies (SerpApi `google_jobs` + JSearch = ONE meta-source) + the user-gated extension. `serpapi` warns once
  if `SERPAPI_ENGINE="indeed"` returns nothing; `SERPAPI_MONTHLY_LIMIT` 100→250. No Indeed scraper (ToS).
- **Agnostic reach (goal: any field):** bundled the full **O\*NET 30.3 alt-titles (50,990 rows)** +
  `industry_profile` O*NET-SOC resolution tier + 23-group SOC→{Muse,Jobicy} map + related-occupation synonym
  tier + auto-gating of tech/remote boards for non-knowledge-work fields. **Eng path unchanged.**
- **Ranking (goal 4a):** `match/semantic.py` local Model2Vec similarity folded into the scorer (SEM_WEIGHT=12,
  **OFF by default** via `SEMANTIC_RANKING`, byte-identical when off). `pip install model2vec` to use.
- **Storage (goal 4b):** WAL pragmas + checkpoint-on-exit, **FTS5 inbox search** (`inbox_search()`, LIKE
  fallback), `applications.norm_url` index + `urls_not_seen()` anti-join. Schema v4→v5, backward-compatible.
- **Quality:** schema.org `validThrough` captured → `match/ghost` strongest stale signal (now persisted to
  inbox extras + read live); stealth-fetch legal guards (registry allowlist + per-host rate-limit + robots +
  post-redirect re-vet); cc_harvest resolves the newest Common Crawl index dynamically.

## Needs Alex (see REVIEW-REPORT §7 for the full ranked list + why)

1. **Eyeball `py gui.py`** then **push the 55 commits** (33 pre-session + 22 this session).
2. Biggest un-built reach levers (documented, ready): **BambooHR ATS client** (#1 non-tech; endpoint 403s
   flaky headless — validate with a real customer slug), **US municipal Socrata**, and a **bulk registry seed**
   (jobhive/OpenJobs → `seed_companies.py`) — the single biggest raw-reach move.
3. Decisions deferred on purpose: **BM25** skill/title scoring (changes existing scores → not byte-identical,
   wants your call/a flag); a **Reach dashboard** GUI badge (backend ready); Census CBP macro gate (needs a key);
   ETag conditional-GET for GH/Lever/Ashby (efficiency). Live smoke: SerpApi `indeed` engine (needs your key).

## Env notes

- `py -3.12` (NOT python/uv). Installed this session: **`model2vec`** (pulled numpy→2.5.0; suite green on it).
  `scrapling` pinned `==0.4.9` (not importable in this env — re-verify on a real install).
- Nothing here is fleet-safety code; everything additive + reversible; push held per your standing gate.
- Stale worktree `E:\ClaudeWork\ZAG0005-wt-12b-qat-t2f` is a prior-session leftover (not mine) — left as-is.
