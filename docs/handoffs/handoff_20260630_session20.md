# Handoff — Session 20 (2026-06-30, Opus 4.8 + GLM + Sonnet) — review remediation buildout

> Deep-reviewed the app, ran a live new-user test of the built `.exe`, then fixed
> **every** review finding via a plan-mode-approved remediation delegated across GLM
> (cheap engine fixes) and Sonnet (complex seams + the delicate gui.py). **ALL
> COMMITTED LOCAL on `master`, push still HELD.**

## TL;DR

- master `eecaf3a` → **+40 commits** (now **79 ahead** of origin), tree clean.
  Suite **725 → 841 passing** (`py -m pytest -q`, ~15s; 1 display-gated skip headless).
- **The flagship find:** the shipped `.exe` crashed on first real use — `app.spec`
  never bundled `data_static/`, so the inbox's default "Local + remote" filter hit a
  missing `cbsa_delineation.csv` and the windowed exe died with "Unhandled exception
  in script". Reproduced + root-caused + fixed + **re-verified on the rebuilt exe**
  (boots on a populated inbox). Only surfaced because I tested the _frozen_ build with
  a _populated_ inbox — an empty-inbox launch passes.
- All 41 verified review findings + 2 live-test findings (Adzuna `se=` dedup,
  Add-Companies comma) + full **Scrapling** integration shipped. One MINOR deferred
  (F25, rationale below).

## Execution model (this session)

Opus authored a weak-model-proof plan per wave; **GLM** (`cc-delegate`, glm-5.2) ran the
file-disjoint engine fixes in isolated worktrees (verified green, merged `--no-ff`);
**Sonnet** builder agents (worktree-isolated) did the two complex clusters (Scrapling
fetch-seam; the gui.py UX cluster); Opus did the build-judgment + delicate-file bits
inline (data_static crit, content.js, gui stealth button, SSRF, WAL, debounce, F17,
`_extract_json`). Plan: `brain/plan-2026-06-30-review-remediation.md` (coverage map maps
every finding → wave). Delegate plans: `ZAG0001 - Local AI Stack/delegate-plans/2026063 0-*`.

## What shipped (by area)

- **Packaging / ship-blockers:** bundle `data_static/` + graceful `coverage.geography._rows`;
  `gui` `main()` crash trap + log; seed `companies.json` on first run (incl. LOCALAPPDATA
  fallback); UPX off. Rebuilt exe = 203 MB, boots on a populated inbox. **[F1 C, F27, F28, F29]**
- **Scrapers / quota:** keyword passed to workable/recruitee/rippling/personio (was dumping
  whole boards); SerpApi page>1 short-circuit (quota); Careerjet md5 id; JSON-LD url-less kept;
  The Muse pages until raw feed spent. **[F2, F3, F37, F30, F17]**
- **Match accuracy:** clearance-negation, experience-qualified `required_years`, manager→manage
  role; salary parser annualizes only on explicit hourly + skips stipend/401k; geo word-boundary
  remote + US. **[F4, F5/F10, F18, F6, F19, F20]**
- **Data lifecycle:** extras merge-not-clobber + restore extras; undo reverts the WHOLE rerank
  batch + clears Top-Picks rank (score_history `batch`, schema **v4→v5**); init_db concurrency-safe
  ADD COLUMN; Adzuna `se=` dedup; WAL checkpoint before backup. **[F7, F21, F8/F9/F23, F22, N1, F38]**
- **AI round-trip:** Top Picks now fills from the FREE clipboard pass; file-export prompt no longer
  embeds the contradictory array-JSON contract; auto-API rank route wired in the GUI. **[F15, F24, F26]**
- **New-user UX (Sonnet):** New-Project registers a "Default" project so the root inbox isn't
  orphaned; wizard pre-populates on re-run; Search-tab "Save searches"; no-keyword → Guide (no
  dead-end); long-search progressbar + friendly empty state. **[F13, F14, F31, F33, F34]**
- **Security:** tracker CSRF/Origin guard (allows loopback + extension); `safe_url` on all
  URL-open sinks + tracker.html; SSRF guard on discovery fetch; explorer via argv. **[F16, F35, F36, F40, F41]**
- **Dead links:** Indeed `?jk=` preserved in `resolveUrl` (manifest **1.4**); Ashby prune via
  board-API membership (the SPA returns 200 for pulled jobs). **[F11, F12]**
- **Scrapling (full integration, lean-exe variant — Alex's call):** lazy fetch fallback in
  `direct_scraper` (config-gated, graceful no-op); on-demand `install()` + **Tools ▸ Enable stealth
  fetching** (downloads Chromium ~300 MB on demand); app.spec bundles scrapling/playwright
  python + node driver, **NOT** the 1.4 GB browsers (would have made the exe ~1 GB). Verified a
  live `StealthyFetcher` fetch in dev. **[W8]**
- **Misc:** `_extract_json` balanced-bracket; inbox filter debounce. **[F39, F32]**

## Deferred (1, justified)

- **F25** (job_key collision on import silently scores only the first row): NOT fixed.
  `inbox_rows_by_key` has ~15 callers/tests relying on its `key→row` shape; a key collision means
  two canonically-identical postings (same company_canon|soc|loc|title_core that URL-dedup didn't
  catch). First-row-wins is acceptable — the other row keeps its local score and stays in the
  inbox (not dropped). Refactoring a 15-dependent function for a near-zero-impact edge case wasn't
  worth the risk. Revisit with a `batch_id`-style 1:1 join if it ever bites.

## Needs Alex

- **Eyeball `py gui.py`** (new Tools ▸ Enable stealth fetching; Search ▸ Save; wizard re-run
  pre-fill; New-Project shows "Default") → then **push** the 79 local commits.
- Reload the unpacked extension (manifest 1.4) for the Indeed `?jk=` fix.
- New deps in `requirements.txt`: `scrapling` (+ its tree). The exe build now bundles them; the
  ~300 MB browser download is on-demand via the Tools menu (or `scrapling install`).

## Pointers

- Deliverable test folder: `E:\ClaudeWork\JobScout-Test-Run\` (REVIEW-REPORT.md + the built exe +
  populated 4-lane `new-user-data\`). Build: `py build_package.py` → `dist\JobScout.zip` (126 MB).
- Brain: `brain/project-status.md` §"Session 20". Memory: `project-job-search`.
