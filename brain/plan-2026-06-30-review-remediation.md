---
title: Review Remediation + Scrapling Integration — implementation plan
date: 2026-06-30
status: EXECUTED 2026-06-30 (all waves merged; suite 725→841). F25 deferred (see handoff). push HELD.
execution: GLM (cc-delegate) for engine fixes + Sonnet agents for Scrapling seam & gui.py; Opus inline for delicate/build bits
tags: [plan, fixes, packaging, scraper, security, scrapling]
---

# Plan — fix all review findings + full Scrapling integration

Source of findings: the 2026-06-30 deep review (41 verified) + the live new-user exe
test (2 new) + `brain/scraping-sources.md` (Scrapling). Every finding below is mapped to a
wave with a concrete change + a test. **Execution = GLM executor** in an isolated worktree;
specs are written weak-model-proof (exact file, exact change, exact test). Opus verifies each
wave (full suite + targeted checks) and escalates anything GLM can't land.

**Global rules for the executor**

- TDD where practical: add/adjust the test in the same commit as the fix; `py -m pytest -q`
  must stay green (baseline **754 passed**).
- Conventional commits, one per wave (or per finding for the big ones). No `--no-verify`.
- Do NOT change the 0–100 scorer math (findings are about parsers/gates/IO, not the rubric).
- View-level signals stay view-level (never folded into the 0–100 score) — the project precedent.
- Windows/cp1252: keep all new print/log output ASCII-safe.

Legend: **[F#]** = review finding number; **[N#]** = new finding from the live test.

---

## Wave 0 — Ship-blockers (the exe must work for a real user)

0.1 **[F1][CRIT] Bundle `data_static/` + degrade gracefully.**

- `app.spec`: add `('data_static', 'data_static')` to `datas`.
- `coverage/geography.py::_rows()`: wrap the file open in `try/except OSError: return []` so a
  missing/぀corrupt data file yields an empty CBSA table (filter falls back to substring-only)
  instead of crashing the inbox. Same defensive read for `company_aliases.json` /
  `onet_soc_alt_titles.tsv` consumers if they assume presence.
- Test: `tests/test_geography_missing_data.py` — monkeypatch `coverage._paths.DATA_STATIC` to a
  nonexistent dir, assert `metro_variants("Cincinnati")` and `geo.filter.location_visible(...)`
  return without raising. (This is the exact crash I reproduced.)

0.2 **[F27] Startup error trap around `App().mainloop()`.**

- `gui.py` `__main__`: wrap `App().mainloop()` in `try/except Exception`; on failure write the
  traceback to `config.OUTPUT_DIR/gui_error.log` and show a `messagebox.showerror`, then exit 1.
  Closes the gap where a _construction-time_ exception dies as the raw PyInstaller
  "Unhandled exception in script" box (what the user saw).
- Test: import-level smoke that the wrapper exists + a unit test that the handler writes a log
  given a forced exception (factor the body into `_run_gui()` so it's testable headless).

0.3 **[F28][N-pkg] Seed `companies.json` on first run (all install shapes).**

- `userdata.py`: add `companies.json` to the scaffold — copy from the bundle
  (`config.DATA_DIR/companies.json`) into `USER_DATA_DIR` if missing. Fixes the LOCALAPPDATA
  fallback install AND any CLI/dev first-run that today gets only the tiny hardcoded REGISTRY.
- Test: extend `tests/test_userdata*.py` — fresh temp `USER_DATA_DIR` + a bundle with
  `companies.json` → bootstrap copies it; idempotent on second call.

0.4 **[F29] UPX safety.**

- `app.spec`: set `upx=False` (simplest, safest) OR keep `upx=True` with
  `upx_exclude=['vcruntime140.dll','python3*.dll','_tkinter*','tcl*','tk*','*PIL*']`. Default to
  `upx=False` to avoid AV/SmartScreen false positives that undercut the unsigned-exe first-run kit.
- Verify: `py build_package.py` produces a launchable exe (manual smoke after the wave).

**Wave 0 verify:** rebuild `dist/JobScout.zip`; launch the exe against a POPULATED inbox; confirm
window title is "Job Search Tools — …" (not the crash dialog). This is the acceptance gate I used.

---

## Wave 1 — Scraper correctness & quota

1.1 **[F2][MAJOR] 4 ATS scrapers fetch the whole board unfiltered.**

- `scrape/careers_client.py:173-180`: pass `keyword=keyword` to `scrape_workable/recruitee/
rippling/personio`. Extend each `fetch()` (`scrape/workable_scraper.py`,
  `recruitee_scraper.py`, `rippling_scraper.py`, `personio_scraper.py`) to accept
  `cache_dir=None, cache_enabled=False` and route through the shared `read_cache/mark_failed/
write_cache` helpers like greenhouse/lever (negative-failure cache + per-keyword caching).
- Update `tests/scrape/test_careers_dispatch.py` (it currently codifies the buggy `lambda slug:`
  signature) to assert the keyword IS passed; keep `test_scraper_deep_match.py` green.

1.2 **[F3][MAJOR] SerpApi pagination.**

- `search/serpapi_client.py`: capture `serpapi_pagination.next_page_token` and send it on the
  next page (or compute `start=(page-1)*results_per_page`). If multi-page is undesired, return
  `{"jobs_results": []}` for `page>1` so no quota is spent and no dupes are produced. Mirror
  `jsearch_client.py`.
- Test: `tests/search/test_serpapi_pagination.py` — mock the HTTP layer; assert page 2 either
  sends the token or short-circuits to empty (no second quota increment).

1.3 **[F17][MINOR] TheMuse keyword-blind paging.**

- `search/themuse_client.py` / `search/search_engine.py:124-139`: have the client signal raw
  end-of-feed (e.g., return a sentinel / set an attribute) distinct from "0 client-side matches"
  so a keyword isn't abandoned after page 1. Test the paging continues until the raw feed ends.

1.4 **[F30][MINOR] JSON-LD postings with no `url` dropped silently.**

- `scrape/jsonld_scraper.py:92-95`: fall back to the page URL (or synthesize a
  `title|company` identity) and emit a debug count of url-less entries instead of dropping.
- Test: a JSON-LD fixture with a url-less posting is ingested (not dropped).

1.5 **[F37][NIT] Careerjet non-deterministic `job_id`.**

- `search/careerjet_client.py:49`: replace `hash()` with `hashlib.md5(...)` like the other clients.
- Test: same input → same id across "runs" (call twice).

---

## Wave 2 — Match / gate accuracy (stop burying good jobs)

2.1 **[F4][MAJOR] Clearance gate fires on negated phrasing.**

- `match/facts.py` clearance detection: suppress a match when preceded by a negator
  ("no", "not", "without", "ability to obtain", "able to obtain", "eligible to obtain") within
  ~40 chars; or accept only affirmative forms ("must have/hold/possess", "active … clearance",
  "requires … clearance"). Used at `gate.py:34-35`.
- Test: "No security clearance required" / "ability to obtain a clearance" → NOT clearance;
  "Active TS/SCI clearance required" → clearance.

2.2 **[F5][F10][MAJOR] `required_years` grabs company-tenure / marketing numbers.**

- `match/facts.py` `_detect_required_years`: require an experience qualifier near the number
  ("experience", "exp", "yrs of", "years of experience", "minimum", "at least"); ignore matches
  near "in business", "founded", "established", "since". Only let the gate DROP on a high
  threshold (≥10, matching the prompt's own scale) at `gate.py:49-52`.
- Make gate auto-drops reviewable (see 3.x: don't write them with a `source` the undo can't
  restore, or surface them so a user can recover) — coordinate with `service.mark_inbox_gated`.
- Test: "over 25 years in business" → required_years None/0; "requires 8+ years of experience"
  → 8 and gated.

2.3 **[F6][MAJOR] `salary_from_text` records stray dollar amounts.**

- `match/scorer.py:145-192`: prefer a two-endpoint range; accept a lone `$value` only when a
  pay-context word is nearby ("salary","compensation","base","/yr","per year","annually","$/hr",
  "hourly","range"); only annualize on an explicit hourly token. Reject obvious non-salary
  ("stipend","gift card","life insurance","$ up to … reimbursement"). Don't return on the FIRST
  `$`-hit; scan for the best candidate.
- Test: "$75 monthly stipend" → no salary; "$120,000–$140,000" → (120000,140000);
  "$60/hr" → annualized ~124800.

2.4 **[F18][MINOR] People-management drop under-triggers.**

- `match/facts.py` `_detect_role_type`: drop on manager/director **seniority** alone, or add a
  downrank flag, so a manager-titled technical role doesn't resolve to generic "build" and skip
  the gate. Test a "Engineering Manager" posting flags people-management.

2.5 **[F19][F20][MINOR] geo remote false positives + US substring bug.**

- `geo/filter.py`: word-boundary match for "remote" so "Remote Sensing/Monitoring" titles aren't
  treated as remote; drop "remote" from `_US_OK` and use word-boundary tokens for "us"/country
  matches so "australia"/"belarus" don't pass the US gate. (Both currently latent —
  `filter_to_metro` unused — but fix for correctness + the future path.)
- Test: "Remote Sensing Engineer, Dayton OH" → not remote; "Remote — Australia" → not US-ok.

---

## Wave 3 — Data lifecycle & dedup

3.1 **[F7][MAJOR] File-import re-rank clobbers extras.**

- `tracker/service.py:apply_rerank_scores`: replace `inbox_set_extras` (overwrite) with a
  `json.loads` + `inbox_merge_extras` (key-preserving, non-dict guard), mirroring the MCP path.
  Preserves `new_batch` (freshness) and `browse` (extension) metadata.
- Test: a row with existing `extras.browse` keeps it after an import that sets `rank`.

3.2 **[F8][F9][F23][MAJOR/MINOR] Undo-last-rerank only reverts the last second.**

- `tracker/db.py`: add a `batch` column to `score_history` (SCHEMA_VERSION bump + additive ALTER
  migration). `service.apply_rerank_scores` / `score_inbox_from_reply` stamp ONE `batch` id per
  call; `inbox_undo_last_rerank` groups by `batch` (not `MAX(ts)`), reverts `fit` AND clears the
  `rank`/`rec_batch` extras for the batch so Top Picks stops showing the undone shortlist.
- Test: a multi-row batch written across >1 wall-clock second fully reverts in one undo, and
  `top_picks()` is empty afterward.

3.3 **[F21][MINOR] Undo-dismiss loses extras.**

- `tracker/service.py:_INBOX_RESTORE_COLS`: add `"extras"` so a restored inbox row keeps
  new_batch/rank/tags/browse. Test round-trip dismiss→restore preserves extras.

3.4 **[F22][MINOR] init_db migration concurrency.**

- `tracker/db.py`: wrap each ALTER-if-missing column probe in `try/except` for
  "duplicate column name" (or `BEGIN IMMEDIATE` before probing). Test: simulate the stale-probe
  race (probe says missing, ALTER raises) → init_db still succeeds.

3.5 **[F25][MINOR] job_key collision silently skips a row on import.**

- `tracker/service.py:inbox_rows_by_key` + `rerank/import_.py`: make the join 1:1 (don't
  `setdefault`-collapse), or report leftovers so the second colliding row is scored or surfaced,
  honoring the "never drops matches" promise. Test a 2-row collision both get scored/reported.

3.6 **[N1][MINOR] Adzuna `se=` token defeats dedup (same job inboxed twice).**

- `models.normalize_url`: also strip volatile tracking params (`se`, and for
  `adzuna.com/land/ad/<id>` collapse to the ad id; keep the stable `v` only if needed). Verified
  live: `…/land/ad/5776175260?se=A…` and `?se=B…` (same `v`) currently produce 2 inbox rows.
- Test: the two real Adzuna URLs normalize equal; assert no regression on the existing
  normalize_url cases (it's the inbox UNIQUE key).

---

## Wave 4 — AI round-trip & Top Picks

4.1 **[F15][MAJOR] Top Picks never fills from the free clipboard workflow.**

- The Guide's `score_inbox_from_reply` writes only `fit`; `top_picks()` needs `rank≥1`.
  Fix: on the clipboard scoring path, after writing fits, derive `rank`/`rec_batch` from the
  returned Fit ordering (best-first) via `service.rank_patch` + `inbox_merge_extras`, so the
  headline Top Picks tab populates. (Confirmed in my round-trip: I had to set ranks manually.)
- Test: `score_inbox_from_reply` on N rows → `top_picks()` returns them ranked by fit.

4.2 **[F24][MINOR] File-export prompt embeds the contradictory bridge JSON contract.**

- `rerank/schema.py:80-113`: stop embedding `_FIT_INSTRUCTIONS` ("ONLY a JSON array
  {i,token,fit,…}") under the CSV/job_key contract. Extract ONLY the scoring _scale_ into a
  shared constant and reference that. Test the export prompt no longer contains the array-JSON
  instruction and the CSV round-trip still imports.

4.3 **[F26][MINOR] "Auto" API route never wired / Settings over-promises.**

- `gui.py` `_copy_fit_prompt` (and the rank action): branch on `ranker.has_api_key()` → call
  `ApiRanker.rank()` (auto) when a key exists, else the clipboard bridge. Update the Settings/Help
  wording to match reality. Test the branch selects api vs bridge by key presence (mock the api).

---

## Wave 5 — New-user UX

5.1 **[F31][F14][MAJOR/MINOR] Multi-lane setup + persisted Search config.**

- `ui/setup_wizard.py`: add an optional "set up multiple search lanes" step (or a clear path)
  that creates one project per lane via `workspace.create_project` with per-lane keywords; OR at
  minimum a "Save these searches" button on the Search tab that calls `workspace.save_config`
  (today Search-tab keyword edits are never persisted). Add a small per-project config editor in
  New Project.
- Re-running the wizard must PRE-POPULATE from existing `preferences`/config and merge-on-apply
  (don't blank-overwrite location/salary/remote/roles/About). [F14]
- Tests (`tests/ui/`): build_preferences/_search_config round-trip; re-run prepopulates; multi-
  lane creation registers N projects.

5.2 **[F13][MAJOR] First "New Project" orphans the root campaign.**

- `workspace.py` / `gui.py:_new_project`: on the FIRST `create_project`, migrate the existing
  root inbox/config/experience into a registered "Default" project (so it stays reachable in the
  switcher), and fix the dead resume-copy prompt (`active_slug()` None guard).
- Test: with a root inbox present, first create_project yields TWO registered projects (Default +
  new) and the root inbox is reachable under Default.

5.3 **[F33][MINOR] "Find your first jobs now?" dead-ends.**

- `gui.py:2538-2549`: guard on keywords-present; if none, fall through to `_open_guide()` instead
  of the "Keywords needed" popup + return.

5.4 **[F34][MINOR] Long-search feedback + empty states.**

- `gui.py:1884-1942`: show an indeterminate progressbar during the 30–60s scrape; friendly
  empty-state on 0 results; remove/reword the dead `.env` "no sources" message.

5.5 **[N2][MINOR] Add-Companies "Name, URL" comma format silently fails.**

- `scrape/ats_detect.py:parse_line`: accept comma OR `|` as the name/URL separator (and a bare
  URL). Today "Vertical Aerospace, https://boards.greenhouse.io/verticalaerospace" → junk
  `direct`/empty. Test the comma form parses to greenhouse/verticalaerospace.

---

## Wave 6 — Security

6.1 **[F16][MAJOR] Tracker write endpoints have no CSRF/Origin defense.**

- `tracker/app.py`: add an Origin/Referer allowlist check (localhost only) that returns 403
  BEFORE any mutating handler (`/delete`, `/api/add`, status changes), mirroring
  `browser_receiver.py:87`. Optionally flask-wtf CSRF for form posts. Test a cross-origin POST is
  rejected; same-origin passes.

6.2 **[F35][F36][MINOR] Unvalidated URL open sinks + tracker.html href.**

- Route all six `webbrowser.open`/`os.startfile` sinks in `gui.py` through an http(s)-only helper
  (the existing-but-unused `safe_url`); validate scheme at the write boundary too. Register +
  use a `safe_url` Jinja filter in `tracker/templates/tracker.html:180`. Test javascript:/file:/
  UNC URLs are refused.

6.3 **[F40][NIT] SSRF in discovery probe.**

- `discover/career_link.py`: http(s)-only; reject loopback/link-local/private IPs; bound
  redirects. Test a `http://127.0.0.1`/`http://169.254.x` domain is refused.

6.4 **[F41][NIT] `explorer` via string-form Popen.**

- `gui.py:643`: use the argv-list form wrapped in try/except, consistent with the rest.

---

## Wave 7 — Dead-link robustness

7.1 **[F11][MAJOR] Indeed query-strip destroys job identity.**

- `browser_ext/content.js:328-334,373,495`: rebuild a per-job URL from the captured
  `external_id` (Indeed `?jk=`, LinkedIn `/jobs/view/<id>`) instead of dropping the query.
  `normalize_url` already keeps `jk`, so the fix is entirely in content.js. Bump manifest version.
- Verify via the node simulation harness already used for the extension; update `selector_check.js`
  notes if needed.

7.2 **[F12][MAJOR] Ashby dead postings never pruned.**

- `scrape/inbox_health.py`: probe Ashby via `api.ashbyhq.com/posting-api/job-board/{org}`
  membership (the SPA page returns 200 for any path). Until membership can be checked, return
  `None` (don't claim to prune) and fix the test that mocks a 404 reality never sends.
- Test: a pulled Ashby posting (absent from the board API) is detected dead; a live one is kept.

---

## Wave 8 — Scrapling FULL integration (incl. exe) ⚠ largest / riskiest

Per `brain/scraping-sources.md` + your decision to bundle browsers into the distributable.

8.1 **Dependency + install.**

- Add `scrapling[fetchers]` to `requirements.txt`. Document `scrapling install` (pulls Chromium +
  Camoufox) in README/build steps. Confirm the v0.4.9 fetcher API
  (`Fetcher`/`DynamicFetcher`/`StealthyFetcher`, method/param names) against the installed package
  before wiring (the notes flag the API has shifted).

8.2 **Fetch fallback seam (backstop, not default; lazy import).**

- New `scrape/stealth_fetch.py`: `fetch_html(url, *, level="auto") -> str|None` that lazily
  imports Scrapling and escalates Fetcher → DynamicFetcher → StealthyFetcher only on
  empty/JS-only HTML or 403/anti-bot. Returns rendered HTML for the existing BS4/JSON-LD path.
- Wire as a FALLBACK in `scrape/direct_scraper.py:_fetch_html()` (after the `requests` attempt
  fails/returns empty), and the same pattern in `scrape/workday_scraper.py` and
  `search/linkedin_guest_client.py`. Respect the negative-failure cache (`mark_failed`) so dead
  URLs aren't browser-retried every run. Gate behind a config flag `SCRAPLING_FALLBACK`
  (default on if installed, graceful no-op if the package/browsers are absent).
- Tests (mock Scrapling — never launch a real browser in CI): fallback triggers only on
  empty/403; lazy import (not imported on the happy path); mark_failed respected; absent-package
  path is a clean no-op.

8.3 **Bundle the browsers into the .exe.**

- `app.spec`: collect Scrapling + Playwright/Camoufox browser binaries as `datas`
  (`collect_data_files` for the playwright/camoufox browser dirs) and add hidden imports
  (`scrapling`, `scrapling.fetchers`, `playwright`, `camoufox`). At runtime set
  `PLAYWRIGHT_BROWSERS_PATH` / the Camoufox path to the bundled location when frozen (small
  shim in `config.py` or a runtime hook). **Expect a large exe (~500MB+)** and longer build;
  test the frozen build can actually launch a fetch on a known JS page.
- Verify: rebuild; confirm exe size + that `stealth_fetch.fetch_html` works from the frozen exe
  on a JS-rendered test page. **If frozen-browser bundling proves infeasible in v0.4.9**, fall
  back to: ship lean + a one-click "Enable stealth fetching" button that runs `scrapling install`
  into the user data dir (escalate to Alex with the finding rather than shipping a broken 500MB exe).
- Update `brain/scraping-sources.md` Status: CANDIDATE → INTEGRATED (with the realized API + the
  exe-bundling approach + any caveats found).

---

## Wave 9 — Performance & remaining nits

9.1 **[F32][MINOR/opt] Inbox debounce + incremental row update.**

- `gui.py`: debounce filter `<KeyRelease>` via `after()` (cancel-and-reschedule); on
  Track/Dismiss remove just the one row from the tree instead of full delete+reinsert + re-query.
  Test the debounce coalesces rapid keystrokes (logic-level).

9.2 **[F38][NIT] WAL-safe pre-migration backup.**

- `tracker/db.py:78-84`: `PRAGMA wal_checkpoint(TRUNCATE)` before `copy2`, or use
  `sqlite3 Connection.backup`. Test the backup includes committed WAL data.

9.3 **[F39][NIT] `_extract_json` balanced-bracket scan.**

- `claude_bridge.py:61-93`: add a balanced-bracket scan with the current first/last heuristic as
  fallback. Test a reply whose prose contains stray `[`/`{` still parses.

---

## Coverage map (every finding accounted for)

F1→0.1 · F2→1.1 · F3→1.2 · F4→2.1 · F5/F10→2.2 · F6→2.3 · F7→3.1 · F8/F9→3.2 · F11→7.1 ·
F12→7.2 · F13→5.2 · F14→5.1 · F15→4.1 · F16→6.1 · F17→1.3 · F18→2.4 · F19/F20→2.5 · F21→3.3 ·
F22→3.4 · F23→3.2 · F24→4.2 · F25→3.5 · F26→4.3 · F27→0.2 · F28→0.3 · F29→0.4 · F30→1.4 ·
F31→5.1 · F32→9.1 · F33→5.3 · F34→5.4 · F35/F36→6.2 · F37→1.5 · F38→9.2 · F39→9.3 · F40→6.3 ·
F41→6.4 · N1→3.6 · N2→5.5 · Scrapling→Wave 8.

## Sequencing & delivery

1. **Wave 0 first** (ship-blockers) → rebuild + manual exe smoke (acceptance gate).
2. Waves 1–7, 9 in parallel-ish file-disjoint commits via the GLM executor (each with its test).
3. **Wave 8 last** (largest/riskiest; may need an Opus escalation for frozen-browser bundling).
4. Opus verifies each wave (full suite + the wave's targeted checks), merges, re-runs suite on
   master. Final: rebuild `dist/JobScout.zip`, populated-inbox exe smoke, summary handoff.
5. Push is a separate explicit step (repo already 39+ commits ahead) — not part of this plan.

## Risks / escalation triggers (GLM → Opus)

- Wave 2 (gate/parser regex) and Wave 3.2 (score_history schema + undo grouping) are subtle —
  verify against real fixtures; escalate if the suite can't prove correctness.
- Wave 6.1 (CSRF) — don't break the legitimate browser-extension origin flow.
- Wave 8.3 (browsers in the exe) — the single most likely to need Opus; honor the lean+installer
  fallback rather than shipping a broken giant exe.
