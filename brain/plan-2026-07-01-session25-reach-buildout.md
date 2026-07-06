# Session 25 — Exhaustive Reach Research → Plan → Build (2026-07-01, Opus/ultracode, overnight autonomous)

**Mandate (Alex, verbatim intent):** cast as WIDE a net as possible — for Alex, his dad (VP
Health Informatics), and general users of ANY field (agnostic). Specifically: (1) access **Indeed** the
way we access LinkedIn; (2) research how others do deep/exhaustive searching & scraping + ways to make ours
more efficient; (3) research ways to **certify we've found 90–100%** of relevant companies/jobs; (4) research
efficient ways to **sort/rank** and **store** what's found. "The success of this app is directly correlated
to how well it finds jobs." Build a plan, then execute it. Document as you go. Runs overnight — best judgment.

Standing gates (CLAUDE.md): terse; additive + config-gated so Alex's engineering flow stays byte-identical;
push HELD (33 commits already ahead of origin); NOT fleet-safety code → autonomous build OK; fanned-out
subagents = Sonnet tier. Free + legal + local only — NO JobSpy-style JA3/proxy mass scraping.

---

## A. Familiarization findings (what already exists — verified by code read 2026-07-01)

- **966 tests**, master **33 ahead** of origin (push held). `py -3.12`; deps incl. ttkbootstrap/rapidfuzz/
  cleanco/defusedxml/scrapling.
- **Indeed already reachable, two ways:** `search/serpapi_client.py` supports `SERPAPI_ENGINE=indeed` (BYO
  paid key, quota-tracked) AND the default `google_jobs` engine surfaces Indeed via Google-for-Jobs; the
  browser extension already captures Indeed postings by `jk` id (user-gated = the compliant path). Gap =
  it's undocumented/unsurfaced, and there's no free direct path (correct — Indeed has no open API since ~2020).
- **Reach lever landed (session 24):** `search/keyword_strategy.broad_query_keywords` — query broad field
  terms for recall, score on narrow target roles. 20× measured for Dad. No-op for eng IC titles.
- **Sources (15):** Adzuna, JSearch, USAJobs, careers(ATS), The Muse, RemoteOK, Remotive, Jobicy, Himalayas,
  HN, Arbeitnow, Jooble, Careerjet, LinkedIn-guest, SerpApi. `DAILY_SOURCES` = the free no-key subset.
- **Registry = the coverage backbone.** Discovery exists: `discover/cc_harvest.py` (Common Crawl CDX),
  `discover/dataset_seed.py` + `seed_companies.py` (jobhive-style bulk import through a probe-verify gate),
  LLM metro enumeration. Real bulk seed = Alex's data-op (needs a dataset).
- **Coverage-certification math EXISTS but is UNWIRED (the big goal-4 gap):**
  - `coverage/estimators.py` — Chapman, Chao1, Good-Turing, log-linear (statsmodels-optional).
  - `coverage/benchmark.run_benchmark(jobs, area, soc_groups)` — job-level: resolves multi-source clusters,
    uses cross-source membership as capture occasions (loglinear ≥3 sources / Chapman 2 / insufficient),
    plus Chao1 upper bound, Good-Turing c-hat, optional reference + JOLTS legs → composite %. **ZERO callers.**
  - `coverage/registry_coverage.py` — company-level capture-recapture vs an INDEPENDENT list (needs list B).
  - Blocker: `search_engine._deduplicate` DROPS cross-source membership; but `coverage/resolve.py` re-derives
    it from RAW results, which is what run_benchmark consumes → wiring is clean (feed raw results post-search).
- **Scoring:** `match/scorer.py` deterministic 0–100 (title 35 / skills 25 / salary 15 / loc 15 / recency 10,
  weight-renormalized over present components; seniority-fit adj; title-miss/exclude penalties). Optional LLM
  re-rank round-trip (`ranker.py`, `claude_bridge.py`) over a compact facts/rubric/gate pipeline (~94 tok/job).
  No semantic/embedding component yet.
- **Storage:** SQLite (`tracker/db.py`), inbox + tracker + runs beacon (per-source counts already persisted) +
  `extras` JSON for view-level metadata. Schema v5.
- **Agnostic mechanism:** `industry_profile.py` — one resolver (user/AI JSON override > ~20 seed fields >
  generic fallback) feeding keyword synonyms + source taxonomy. `match/facts.py` industry-gated.

## B. Approach

1. **Research (running):** background Workflow `jobscout-reach-research` (run wf_e1b4d4da-0b9) — 12 parallel
   Sonnet general-purpose web-research agents (Indeed, LinkedIn+legality, aggregator techniques, company
   discovery, coverage certification, ranking, dedup/ghost, storage, efficiency, stealth+legal, source
   catalog, agnostic/multi-user) → a synthesis agent producing a prioritized, file-targeted plan. Raw findings
   → `brain/research-2026-07-01-*.md`.
2. **Plan:** fold synthesis + my code-read into a decisive, ranked build list; mark each autonomous-OK vs
   needs-Alex. Documented here + a research-report doc.
3. **Build:** implement the autonomous-OK, additive, config-gated, free+legal, high-(impact/effort) items via
   TDD (Sonnet builder agents on file-disjoint worktrees for engine modules; inline for delicate/serial files);
   full suite green per step; commit locally; **push HELD**.
4. **Review + document + handoff.**

### Preliminary build candidates already identified (pre-research; will re-rank after synthesis)

- **Wire job-level coverage certification** (goal 4): call `run_benchmark` on each real run's raw multi-source
  results; persist + surface a "seeing ~X% (95% CI) of the reachable universe" number. Additive, math exists.
- **Surface/strengthen the Indeed paths** (goal 1): document `SERPAPI_ENGINE=indeed`, ensure the browser-ext
  Indeed capture is robust; keep the free google_jobs default. No new scraping.
- **Source-catalog gaps** (goal: reach): add any free+legal sources the catalog research surfaces (candidates:
  We Work Remotely, Findwork, Reed, etc.), each gated by a coverage-lift test.
- **Registry acquisition** (goal: reach): make the CC-harvest / dataset-seed path a one-command, documented op;
  possibly bundle a starter agnostic slug set.
- **Ranking** (goal 4b): evaluate a light, exe-friendly semantic-similarity component (TF-IDF/BM25 or a small
  local embedding) as an additive scorer signal — pending research on distributable footprint.
- **Efficiency** (goal 2): conditional/delta fetch (ETag/If-Modified-Since, ATS updated-at cursors) so a large
  registry stays fast; extend the existing tiering.
- **Agnostic** (goal: any field): O*NET/SOC-derived synonym map so a new field gets broad reach out-of-the-box.

## C. Research outcome (complete)

12 dimensions researched (Workflow `wf_e1b4d4da-0b9` = 10 + 2 re-run as background agents),
persisted to `brain/research-2026-07-01-reach-*.md` + `...-SYNTHESIS.md` (30-item prioritized plan).
Headline findings:

- **Indeed:** no free/legal self-serve consumption API exists (Publisher/XML all employer-side, died ~2020).
  Reach it the way we reach LinkedIn: Google-for-Jobs proxies already wired (SerpApi `google_jobs` + JSearch —
  treat as ONE meta-source) + the user-gated browser extension. SerpApi's standalone `indeed` engine may not
  exist in the current catalog → add an empty-result warning. Do NOT integrate an Indeed scraper (ToS).
- **Reach lever = registry breadth** (ATS syndication: a Greenhouse/Workday req flows to LinkedIn/Indeed/Google
  in 24–72h), grown via Common Crawl + MIT datasets (jobhive 86K, OpenJobs) + O*NET-agnostic field mapping.
- **Certify coverage:** wire the existing-but-inert `coverage/` package; fix jolts `_series_id`, chao1→chao2,
  add CIs + correlated-source grouping; surface a CI-banded "seeing ~X%… ~N unseen" badge.
- **Ranking:** keep the deterministic scorer; add a small local Model2Vec semantic component (numpy-only) +
  BM25 for skills/title. No RRF, no LambdaMART (no training data).
- **Storage:** stay on SQLite; add WAL pragmas + FTS5 + companies index. No DuckDB/vector-DB (packaging risk).
- **Non-tech sources:** almost no open APIs → best adds are SMB ATS (BambooHR/Breezy) + US municipal Socrata;
  cheapest gain = query existing aggregators harder.

## D. Execution log (this session)

Push HELD throughout; master was 33 ahead → growing. Full suite green after every commit.

- ✅ **Cluster A — coverage certification** (`59ade47`, 966→981): `coverage/reach.py` capstone wired into
  daily_run (honest "seeing ~X% (95% CI), ~N unseen, K independent families" + "cannot certify" fallback);
  fixed jolts `_series_id` (state series + sub-state skip), chao1→chao2 (+jackknife), loglinear bootstrap CI,
  correlated-source collapse (`coverage/independence.py`). `SearchEngine.last_raw_results` exposes membership.
- ✅ **cc_harvest dynamic crawl** (`f…`): resolve newest Common Crawl index via collinfo.json (was pinned
  to stale CC-MAIN-2025-05), graceful fallback.
- ✅ **validThrough ghost signal**: capture schema.org validThrough (was discarded) → `JobResult.valid_through`
  - `match.ghost` strongest stale signal (publisher-attested expiry). Inbox-extras threading = cluster F.
- ✅ **match/semantic.py** (inert): local Model2Vec (potion-base-8M) similarity, gated OFF by default; validated
  (health résumé 0.59 vs health-VP, 0.12 vs nurse). Scorer integration = cluster D post-merge.
- 🔄 **Clusters B/C/E** building in parallel on worktrees (Sonnet builders): B=Indeed/sources/stealth-legal,
  C=storage (WAL/FTS5/index), E=agnostic O*NET/SOC. Merge sequentially → then D inline → then F.
- ⏭ Deferred to Alex (from synthesis §gaps): live SerpApi `indeed` smoke test + Census CBP/O*NET/dataset ops
  (keys/data), the GUI coverage badge (#19) + browser-ext hardening (#16), linkage-error audit (#29).
