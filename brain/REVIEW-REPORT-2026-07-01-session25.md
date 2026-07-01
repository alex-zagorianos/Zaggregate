# JobScout — Session 25: Reach Buildout (2026-07-01, Opus/ultracode, overnight autonomous)

**Mandate:** cast as wide a net as possible (Alex + dad + any-field general users); access Indeed like we
access LinkedIn; research + build ways to certify we've found 90–100% of relevant companies/jobs; improve
sorting/ranking and storage. Exhaustive research, many subagents, build a plan then execute, run overnight.

**Outcome:** 12-dimension web research → integrated plan → **21 commits, 981 → 1103 tests, full suite green,
push HELD.** Everything additive + config-gated; Alex's engineering flow verified byte-identical. Built via
parallel Sonnet builder agents on isolated worktrees (Clusters B/C/E), merged sequentially, plus inline Opus
for the coverage flagship, the semantic ranker, and quality wins. Research lives in
`brain/research-2026-07-01-reach-*.md` (+ `-SYNTHESIS.md`, the 30-item ranked plan).

---

## 1. The Indeed answer (goal: "access Indeed like LinkedIn")

There is **no free/legal self-serve API to READ Indeed listings** in 2026 — the Publisher/XML/Job-Sync
programs are all employer-side (post INTO Indeed) and the last read path died ~2020. Indeed is reached the
same way LinkedIn is: **(a) Google-for-Jobs proxies already wired** — SerpApi `google_jobs` (default) + JSearch,
which pull the _same_ upstream index (so they count as ONE source, now modeled in `coverage/independence.py`);
and **(b) the user-gated browser extension** (compliant DOM capture of the page the user opened). We did NOT
build an Indeed scraper (ToS). Landed: `serpapi_client` now warns once if `SERPAPI_ENGINE="indeed"` returns
nothing (that engine may no longer exist in SerpApi's catalog), and `SERPAPI_MONTHLY_LIMIT` bumped 100→**250**
(the real free cap). **The durable Indeed lever is registry breadth** (below) — a req in Greenhouse/Workday
syndicates to Indeed/LinkedIn/Google in 24–72h, so a bigger registry reaches those boards without scraping them.

## 2. Reach — what shipped

- **Broad-query lever** (already landed session 24) + **O\*NET-SOC agnostic reach** (this session): bundled the
  full **O\*NET 30.3 alt-titles dataset (50,990 rows)** (`data_static/onet_soc_alt_titles.tsv`, regen via
  `scripts/build_onet_alt_titles.py`); a new resolution tier in `industry_profile.resolve()` gives ANY field
  real occupation-derived synonyms out-of-the-box (deterministic exact+plural lookup — E found rapidfuzz hands
  out false-high confidence at scale and hardened against misrouting); a 23-entry BLS SOC-major-group→{Muse,
  Jobicy} source map; a related-occupation second synonym tier; and tech/remote-skewed boards (RemoteOK/
  Remotive/Himalayas/Arbeitnow/HN) auto-gate OFF for non-knowledge-work fields (plumber/nurse) — all **no-op
  for eng** (Alex byte-identical).
- **cc_harvest** now resolves the newest Common Crawl index dynamically (was pinned to a stale crawl).

## 3. Coverage certification (goal: "certify 90–100%")

The `coverage/` package was fully built but had **zero callers**. Now wired + corrected:

- **`coverage/reach.py`** — from a run's RAW multi-source results, capture-recapture over INDEPENDENT source
  families yields an honest verdict, logged + persisted every `daily_run`:
  _"Reach: seeing ~X% (95% CI Y–Z%) of the reachable universe — ~N of ~M estimated postings still unseen (from
  K independent source families, R raw → D distinct)"_, with a truthful **"cannot certify — need ≥2 independent
  families"** fallback (a single source can't reveal what it's missing).
- Correctness fixes the research caught: `jolts._series_id` ignored its args (always national) → now builds a
  real state-level series + honestly skips sub-state metros; `chao1(f1,f2)` was fed incidence counts → replaced
  with incidence **Chao2** (finite-sample correction) + jackknife1/2 cross-checks; `loglinear` got a bootstrap
  95% CI; correlated sources (SerpApi+JSearch) collapse to one family before the math (`coverage/independence.py`).
- Read the number any time: `py -m coverage.reach --project <slug>` (reads the latest persisted snapshot).

## 4. Ranking (goal: "efficiently sort/rank")

- **Local semantic similarity** (`match/semantic.py`, Model2Vec `potion-base-8M` — MIT, numpy-only, ~30MB, no
  torch): cosine between the candidate's `experience.md` profile and each job's title+description. Validated:
  a health-informatics résumé scores **0.59** vs a health-VP role, **0.12** vs a nurse role. Folded into
  `match/scorer.py` as a bounded component (`SEM_WEIGHT=12`, ~11% of score, under Huntr's <20% keyword-cap
  discipline). **OFF by default** (`SEMANTIC_RANKING` env/config) + abstains when the model/profile/text is
  absent → keyword-only score byte-identical. Enable with `SEMANTIC_RANKING=1` (+ `pip install model2vec`).

## 5. Storage (goal: "efficiently store")

`tracker/db.py`, schema v4→v5, additive/backward-compatible: completed the WAL pragma set
(`synchronous=NORMAL`, `temp_store=MEMORY`, bounded `mmap_size`) + `wal_checkpoint(TRUNCATE)` on clean exit;
an **external-content FTS5 index over the inbox** (`inbox_search()`, LIKE fallback on FTS5-less builds) so a
non-technical user (dad) can search a growing inbox; `applications.norm_url` + indexes + a `urls_not_seen()`
SQL anti-join so the tracked/dismissed check scales with the batch, not the table.

## 6. Quality wins

- **Ghost/expired filtering:** the JSON-LD scraper discarded schema.org `validThrough`; now captured onto
  `JobResult.valid_through` and used by `match/ghost` as the strongest (publisher-attested) stale signal.
- Stealth-fetch **legal guards**: registry/same-host allowlist + per-host rate limit + robots.txt fail-open
  check before any browser escalation (never for arbitrary/authenticated URLs).

---

## 7. Needs Alex (ranked recommendations — researched, NOT built, with why)

1. **Push the 54 held commits** (33 pre-session + 21 this session), after eyeballing `py gui.py`.
2. **BambooHR ATS client** (S, HIGH non-tech reach) — `{co}.bamboohr.com/careers/list` public JSON, ~30k SMB
   employers (dental/local-mfg/nonprofit/retail = the non-tech local jobs we under-reach). **Not built tonight:**
   the endpoint 403s intermittently headless (anti-bot on many subdomains, contradicting the research), so it
   needs a real customer slug to validate the JSON shape + a decision on routing it through the stealth fetcher.
   Slots into the existing `scrape/*_scraper.py` + `ats_detect` + `cc_harvest` infra. See source-catalog research.
3. **US municipal Socrata client** (M, HIGH non-tech gov reach) — one reusable SODA client, config per city
   (NYC `data.cityofnewyork.us/resource/kpav-sd4t.json` first). Archetypal non-tech local jobs.
4. **BM25 for skill/title scoring** (S) — replaces unweighted term-counting so rare high-signal skills outweigh
   common ones. **Deferred deliberately:** it changes existing scores (NOT byte-identical) → wants your eyeball,
   or gate it behind a flag. `match/scorer.py` `_skill_score`/`_title_score` (`rank_bm25`/`bm25s`, dep-light).
5. **Reach dashboard tab** (M) — surface `coverage/reach.py`'s persisted snapshot as a CI-banded GUI badge
   ("seeing ~X%…"), the user-facing form of goal 3. Backend + number already exist.
6. **Bulk registry seed** — the biggest raw-reach lever (per sessions 19/22/23): get a dataset (jobhive 86K /
   OpenJobs) → `py seed_companies.py --dataset f.csv --industry <field>`; then `py company_coverage.py --record`.
7. **Census County Business Patterns** company-level macro gate (M) — free key; complements the job-level
   JOLTS gate (establishment counts by county/NAICS). Additive/skip-without-key like jolts.
8. **validThrough → inbox extras** (S) — thread `valid_through` into inbox extras + surface in the GUI ghost
   check (needs a small `gui.py` + `tracker/db` touch). The scraper-time signal already works.
9. **ETag/If-Modified-Since conditional GET** for Greenhouse/Lever/Ashby (S) — research verified live 304s
   → skip multi-MB re-downloads on unchanged boards; keeps a large registry's daily run cheap.
10. Live smoke tests you must run (have the keys/data): SerpApi `indeed` engine; O*NET regen already succeeded.

Nothing here is fleet-safety code; everything is additive and reversible. Push is held per your standing gate.

---

## 8. Self-review (ran before finalizing)

A 6-dimension adversarial review workflow (14 agents, per-finding verification) ran over this session's
diff (`e8045a8..HEAD`): coverage math, byte-identical invariant, stealth/legal, storage migration,
cross-cluster integration, O*NET agnostic. It surfaced **8 confirmed defects (0 uncertain)** — all fixed and
regression-tested in commit `68739e6` (1103→1111 tests). The two most important were in the new coverage code:
a **false "100% certified"** when 3+ source families had zero overlap (loglinear degenerates to n_distinct),
and a **crash** when a Chapman CI lower bound went negative (None slipped into the % formatter, and daily_run's
best-effort guard silently swallowed the otherwise-valid estimate). Also fixed: a stealth-fetch post-redirect
host-revet gap, an unchunked SQL-variable overflow in `urls_not_seen`, the dead `valid_through` signal (now
persisted to inbox extras + read by ghost), an eng-industry SOC-persist that broke byte-identical, and two
minor issues (chao2 degenerate value, serpapi warn-once race). Full suite green after fixes.
