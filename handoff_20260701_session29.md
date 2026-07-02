# Handoff — Session 29 (2026-07-01, Fable 5 + Opus fleet) — DEEP REVIEW → FULL REMEDIATION BUILDOUT

**Task (Alex):** "broad scale overhaul" — deep review of Zaggregate vs the vision (widest
net / any user any field / bring-your-own-AI / cycle tracking), then "start an opus fleet
and make all of the changes you surfaced."

Read-me-first: `brain/review-2026-07-01-deep-product-review.md` (the plan every wave
executed against; P0–P7 + build order).

## What happened

1. **Deep review** (43-agent verified fleet): 8 dimensions + adversarial verification +
   completeness critic → the brain doc above. ~90% of critical/major claims CONFIRMED
   with file:line evidence.
2. **Build-out** (5 waves, 12 Opus worktree builders, sequential merges, suite green at
   every merge): baseline `001923d` → 65+ commits.
   - **A — foundations:** 429-safe transport (429/5xx = serve-stale-never-poison,
     404 = dead; per-ATS-host rate limiter; caching for ALL scrapers; 304→utime; cache
     GC; tiered-scrape auto-default >200 boards) · scoring precision (rescore parity,
     hard_gate salary-max/metro-variant fixes, word-START-boundary titles, symmetric
     seniority, confidence shrinkage, SEMANTIC_RANKING flag + title-veto (default OFF),
     hourly/currency/period comp, employment-type facts+gate, senior years-cap 15,
     field-aware penalty_roles, normalize_title memoized) · concurrency (atomic
     projects.json + loud RegistryCorruptError, MCP/scripts pinning, advisory lock) ·
     resume-paste P0 fix (auto-structure + lenient parser + nurse acceptance test),
     LICENSES/SUMMARY sections, wizard industry-derivation, hourly wages, full ~935-CBSA
     table, deseniorize guard, knowledge-work gate fix, DEFAULT_LOCATION=''.
   - **B — core loop + sources:** "Update my Inbox now" (pinned worker + live progress),
     frozen-exe `--daily`, Tools scheduler toggle, honest empty-state + add-search-to-
     inbox, per-source progress + Cancel + source-health summary, Ctrl+A/dismiss-all-
     shown, browser-capture toggle + extension bundled, wizard "Keep jobs coming" step ·
     "Connect job sources" panel (adzuna/usajobs/jooble/careerjet/careeronestop,
     env-then-secret), jooble+careerjet+**CareerOneStop (NLx ~3.5M jobs/day)** in
     DAILY_SOURCES, Adzuna ~19-country support, linkedin_guest genuinely opt-in,
     language guard, daily max-pages 2 (cache-shared baseline delta).
   - **C — dedup + BYO-AI:** inbox job_key coalescing (schema v6) + keyless persistence +
     freshness repost/evergreen history + cap-overflow visibility · ANTHROPIC_BASE_URL at
     all 5 AI call sites (Ollama/GLM/DSK/Kimi unlock), chunked+compact export (~215K→
     ~15-30K tokens), batch-atomic undo on every route, MCP application-cycle + resume +
     skillgap tools + compact list_inbox, per-profile fit_preference (de-Alex'd),
     opt-in auto-rank.
   - **D — cycle + lifecycle:** accepted/ghosted states, centralized applied side-effects,
     auto-ghost nudge, interview_rounds (v7) + .ics export, offer fields, per-stage note
     timeline, contacts surfaced, startup due banner + tab badge, quick_check + rolling
     backups + CSV export · APP_VERSION 1.0.0, applog framework (rotating logs),
     last_run.json + Inbox "Last updated" stamp, Report-a-problem (redacted zip),
     auto-backup post-run, sync-folder warning, test socket guard, real README.
   - **E — ATS wave 2 + feeds:** 9 new scrapers (Paylocity official / Eightfold / ADP /
     Oracle ORC / Phenom + Breezy / Pinpoint / Teamtailor / JazzHR), 6 validated LIVE;
     **UC Health (382 jobs) + TriHealth (522) probe-verified + seeded** (S27 intel was
     stale: TriHealth = Oracle not Phenom; Christ Hospital = NAS Recruitment, no clean
     endpoint, not seeded; Eaton eightfold is PCSX-gated, left as direct) · sector RSS
     (HigherEdJobs + RNJobSite live-corrected URLs, jobs.ac.uk provisional/opt-in) ·
     SerpApi reach probe (fixes capture-recapture f2=0 → the reach %% badge can finally
     certify) · TheirStack/Techmap overlap samplers (opt-in) · Techmap Kaggle seed spec.
3. **Post-build adversarial review fleet** (7 dimensions over the cumulative diff, per-
   finding verification; ran through an Anthropic 529 outage — 3 attempts):
   confirmed 4 critical + 5 major + minors. **ALL FIXED** (uncommitted at
   handoff-write time, see below):
   - job_key coalescing over-merged distinct same-title reqs on ONE board (8 UC-Health
     RN reqs → 1 row). Now CROSS-HOST ONLY (`tracker/db.py` + `_url_host`).
   - Embedded browser-receiver took the PROCESS-WIDE pin → hijacked the project
     switcher (S27 class, mirror image). Now: embedded = per-request active project +
     bind health-check; standalone `py -m` still pins.
   - URL-borne credentials (Jooble path key, Adzuna/Careerjet query params) leaked via
     HTTPError strings into app.log/last_run.json → report zip. Now: `applog.redact()`
     - logging filter + boundary scrub in search_engine + write_last_run + report zip
       scrubs file CONTENT on copy; URL-userinfo + credential-bearing base_url covered.
   - GUI project switch during a pinned Update-now run showed project B over project
     A's data → switch now refused (with dropdown snap-back) while a run is pinned
     (`workspace.pinned()`).
   - API-rank single-flight guards (both tabs); MCP set_status validates status +
     app_id existence (set_follow_up too); rescore uses effective_keywords (industry-
     only projects were getting title-blind rescores every run); repost flag decays
     (REPOST_DECAY_RUNS=5) + freshness retention eviction (120d); undo-dismiss always
     clears the dismissed marker; auto_rank_top_k=0 respected; ADP company display
     name from registry; `_clean_dead_links_done` teardown guard.
   - Regression pins: `tests/test_review_fleet_fixes.py` (10 tests).

## State at handoff-write

- Master at `7042e9f` + the review-fix pass (workspace/gui/db/applog/help/mcp/rescore/
  freshness/service/adp/careers_client/search_engine + 2 test files) **staged in the
  working tree, UNCOMMITTED** — an Anthropic API outage (529s) took down the local
  permission classifier, blocking shell (pytest/git) at the end of the session. A
  background runner keeps retrying the suite; commit + final suite verification are the
  ONLY mechanical steps left. Last full-suite green: **1713 passed** (post-E merge);
  the fix pass adds ~12 tests.
- **Push HELD** throughout (now ~75 commits ahead). Nothing pushed.
- Review-fleet gaps (API outage): the **byte-identical dimension never completed** — I
  spot-checked its enumerated items read-only instead (SEMANTIC/AUTO_RANK/LANGUAGE_GUARD
  default off; sector feeds industry-gated; careeronestop keyless-skips; page-cache
  keys include page ⇒ baseline pass spends no extra quota). **integration-seams** ran
  once (its rescore finding fixed); its verify replays 529'd.
- Deferred (recorded, low risk): partial-page board caching on mid-page transient
  (mirrors pre-existing accepted workday pattern); root handoff/script sweep (declined
  by convention); OpenAI-compat adapter (documented as future work; base_url covers
  Anthropic-compatible endpoints incl. Ollama).

## Alex-visible behavior deltas (all review-directed, flag-controlled)

1. **Reach probe default-ON when a serpapi key exists** (yours is set): ~2 google_jobs
   queries/daily-run inside the 250/mo quota; probe jobs enter the inbox (job_key dedup
   handles collisions) and the reach badge can finally certify a %%. `REACH_PROBE=0`
   or `"reach_probe": false` to disable.
2. **fit_preference now neutral by default** — the baked-in "prefers smaller companies"
   sentence is gone from ranking prompts. Add `"fit_preference": "..."` to your
   preferences to restore it.
3. **Tiered scraping now defaults ON** for your 620+-board registry (explicit
   `"tiered_scrape": false` restores O(N)-every-run).
4. Confidence shrinkage / symmetric seniority / word-boundary titles / hard_gate fixes
   / daily max-pages 2 — the reviewed precision changes.

## Needs Alex

1. **Commit the review-fix pass** if the session couldn't (`git add -A` the listed
   files; suite should read ~1725 green) — or just ask me next session.
2. Eyeball `py gui.py` (new: Update-now, scheduler toggle, source-keys panel, search
   progress/cancel, bulk triage, due banner, rounds/offer dialogs) → then **push** the
   ~75 held commits (README/CI now exist for a safer push).
3. **PII decision** (unchanged from the review): experience.md is untracked now but
   lives in pushed GitHub history — rewrite/private/accept?
4. Free key signups when you want the reach: CareerOneStop (biggest non-tech win),
   Adzuna/Jooble/Careerjet — all in Settings → Connect job sources.
5. aegean-restyle merge after live eyeball (unchanged; the branch is untouched but
   gui.py grew a LOT this session — expect a real merge, no longer trivial).
6. Optional: flip SEMANTIC_RANKING=1 after eyeballing ranked results (model2vec is
   installed; title-veto wired); AUTO_RANK=1 for wake-up-to-ranked-inbox.

## Fleet/method notes

Orchestrator = Fable 5; builders/reviewers = Opus (per Alex), 12 build agents + 20+
review/verify agents across ~5.5M subagent tokens. Worktree-per-builder with
file-ownership partitions; zero merge conflicts across 10 builder branches; suite run
at every merge point. The Workflow built-in worktree isolation fails outside a git cwd
(session runs at E:\ClaudeWork) — pre-created worktrees + path-in-prompt is the working
pattern. Anthropic 529 outage lesson: the auto-mode permission classifier (opus-4-8)
goes down WITH the API — shell dies session-wide while Read/Grep/Edit/Write keep
working; workflow agents make a serviceable retry loop.
