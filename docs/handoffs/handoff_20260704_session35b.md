# Handoff — Session 35b (2026-07-04, Fable 5 ultracode) — FIX-ALL + MODULARIZE + FULL-SCALE VALIDATION

Continuation of S35 (same conversation). Alex's directives, in order:

1. "fix all other findings that need it" → every remaining confirmed S35 finding.
2. "consider making it multiple files instead of one monolith" → gui.py + cli.py split.
3. "once all is done do a full scale test of multiple profiles and other methods to
   make sure the refactoring didn't break anything."
4. Language question → answered: engine stays Python; UI successor = local web UI
   over the Flask receiver (roadmap; see KNOWN_ISSUES).

## Wave 1 — 3 Sonnet builders in worktrees (all merged, suite green per merge)

- **s35/ranking**: #28 `_EXEC_RE` exec-intent split (Product/Account/Community
  Manager no longer flip exec; Engineering Manager → allow_management + senior,
  not senior-exec), #37 SOC-11 penalty exemption (the only REAL collision — 33/35/
  43/51/53 audited and correctly NOT mapped), #31 SOC 33/51 Muse routing (45 has no
  defensible category), #38 skills-chip honesty (score was already renormalized;
  the notes token now omits "skills n%" when no data). **Eng parity: 25-job harness
  byte-identical** (only no-description rows' notes drop the misleading chip).
- **s35/sources**: keyless-skip surfaced on ALL entry points (CLI summary lines,
  GUI progress "skipped — needs a free key", MCP `skipped_keyless` payload); US-only
  sources (USAJobs/CareerOneStop) skip for non-US users; jobs.ac.uk in DAILY_SOURCES
  w/ location-aware activation; careerjet/jooble country routing; Adzuna cache-key
  schema-versioned. US byte-identical proven per change.
- **s35/resilience**: sector-feed parse errors RAISE + skip cache write (no more
  cached-empty); CareersClient per-run failure summary; Brave discovery failures
  warn_once; build_clients per-source ctor guard (one bad source can't zero the
  run); CareersClient per-run fetch memo (N fetches for 3 keywords, not 3N;
  workday/smartrecruiters excluded deliberately); discovery TTL 168h + in-run memo;
  cache GC in finally; icims/taleo/successfactors added to discovery hosts (UKG/
  Paycom etc. deliberately NOT — no scraper); inbox-harvest negative-cache 336h.
  Plausible "double baseline pass" investigated → real but cache-absorbed, serves
  the freshness delta — left alone.
- Merge conflict (sources × resilience in search/cli.py, 4 regions) hand-resolved:
  resilience's outer-try structure + sources' country deltas; both branches' test
  suites green on the resolved file.

## Wave 2 — modularization (Alex: "multiple files instead of one monolith")

- **gui.py 5,303 → 1,834 lines**: 10 new ui/ modules (tab_inbox 1357, tab_search
  557, companies_dialogs 496, job_dialog 367, tab_tracker 274, tab_resume 160,
  tab_toppicks 156, common 164, ai_setup_dialog 100, paste_dialog 41). Pure moves;
  compat re-export block keeps every `gui.X` name working; mutable palette state
  centralized in ui/common.py with attribute-access discipline; one test patch
  target updated; `run_daily_ingest` late-import preserves test patching.
- **search/cli.py 816 → 610**: build_clients dispatch → `search/source_registry.py`
  (BuildContext + one function per source). Log strings byte-verified. Adding a
  source is now one function + one dict entry.

## Review fleet over the cumulative diff (4 dims, adversarial verify)

Merge-resolution, pure-move fidelity, cross-branch interactions: **zero findings**.
One CONFIRMED: `applog._WARNED_ONCE` cross-test pollution (b2_source_keys warms
'careerjet:no-affid' → tests/search/test_careerjet.py's WARNING assertion fails
under -k/--lf orders; masked by default collection order). Fixed with an autouse
conftest fixture resetting warn-once + discoverer run-memo (`979397d`); repro
pairs verified in the previously-failing order.

## Full-scale validation (Alex's ask #3) — ALL PASS

- **5 blank-slate profiles through the real daily_run** (sequential, max-pages 1):
  eng Cincinnati 2255 raw/280 inboxed · nurse Columbus 507/136 · warehouse
  Louisville 282/53 · **London-UK 555/304** · remote 784/125. No tracebacks, exit 0,
  keyless-skips surfaced everywhere, US-only skips fired exactly on the UK lane.
- **Live catch the unit tests couldn't make**: UK lane's Adzuna returned 0 —
  /gb/ routing was right but `where="London, United Kingdom"` breaks Adzuna's
  geocoder ('London'=231, w/ country=0). Fixed: strip the tail when it names the
  routed country (`config.location_country_tail`; US "City, ST" never matches →
  byte-identical, tested). Re-run: **Adzuna gb = 295 rows, top source for the UK
  user** (was 0). jobs.ac.uk 404 = provisional endpoint (KNOWN_ISSUES) but
  correctly SURFACED in last_run errors[] — the new resilience machinery working.
- **GUI**: compat surface all 29 names; import clean. **Parity**: byte-identical
  through both refactors. **Receiver live process**: OPTIONS 200 / foreign-origin
  403 / oversized 413 (new body cap live). **Production**: exe REBUILT with the
  new module layout + clean 12s launch (PyInstaller follows ui/ imports).

## State

- master `+42` commits over pushed `6be40b9`. **PUSH HELD.**
- Final suite: **2478 passed / 0 failed** (S35 baseline was 2311).
- Worktrees pruned; only pre-existing ZAG0005-wt-12b-qat-t2f remains.
- 5 `val-*` validation projects kept in projects/ (disposable, like gu-_/gs-_).
- KNOWN_ISSUES.md updated: most items moved to "fixed"; remaining = #4 blue-collar
  registry (waits), jobs.ac.uk endpoint, sector-feed breadth, non-US metro table,
  zero-key floor test, tkinter→web-UI roadmap.

## Needs Alex

1. Say "push" (42 commits held).
2. Next session (his words): **seeded-company-list buildout**.
3. Carried: reload extension, re-clip edisonsmart, junk tracker rows,
   CareerOneStop key, experience.md PII-history decision; delete val-_/gu-_/gs-*
   test projects when ready.
