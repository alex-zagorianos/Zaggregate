# Handoff — 2026-07-05 Session 38 (evening; chrome + queue buildout + tech-debt sweep)

Alex, testing live: (1) "top windows bar is still white with the python logo…
use the Z or have that tab be built in… plan how to fix this and then fix it.
Also begin working on all of the fixes/implementations that we discussed in
previous sessions." (2) "don't really care about international… focus on US."
(3) "I want a thorough comb through front end and backend to get rid of
techdebt too."

**Everything shipped and verified. Suite 3,218 passed / 0 failed (2 flaky
environmental no-display skips); vitest 217/22 files; tsc + vite build clean;
exe rebuilt at 91.8MB (was ~141MB) + frozen web smoke all-green. 15 commits
tonight, PUSH HELD (~38 total ahead).**

## 1. Desktop chrome (the title-bar ask)

- `webui/native_win.py` (new, pure ctypes, tk-free): WM_SETICON Z icon +
  DWM immersive-dark + Win11 caption/text colors painted with the app's own
  Aegean Paper/Night background — the native bar blends into the page.
  AppUserModelID so dev runs get their own taskbar identity.
- Z mark: `scripts/make_icon.py` → `data_static/zaggregate.ico` (committed)
  - matching `favicon.svg`; `app.spec` `icon=` so Explorer shows it.
- Live theme sync: pywebview `js_api` ThemeBridge; `theme.tsx` calls
  `window.pywebview.api.set_theme` on every theme apply (no-op in browser).
- Verified live: WM_GETICON returns both icon handles on the running window.

## 2. Previous-session queue — ALL BUILT (wave 1 + 2 + 3)

- **get_conn() redesign** (orchestrator-built): thread-cached connections
  (53x faster/call measured), nested-transaction calls get fresh handles
  (pre-S38 semantics preserved), thread-ident registry with dead-thread
  sweeping, `close_all_connections()` seam → release_for_restore/close_db
  drop Windows locks deterministically; atexit = close_db. 8 tests.
- **URL-synced Inbox filters**: `useUrlSyncedState` + fail-open codec;
  refresh/back keep the view; defaults omitted from the URL.
- **Metro CBSA gap**: "Minneapolis, MN" now matches its own hyphenated
  multi-city CBSA title (additive arm; city AND state must match).
- **Breadth floors**: tests pin 18 keyless sources + companies.json ≥ 400.
- **jobs.ac.uk RETIRED**: upstream deleted its entire /feeds tree (verified
  live) — search() short-circuits, one-line note, parser kept for revival.
- **Windows toast** (opt-in, default OFF): `notify_win.py` ctypes
  Shell_NotifyIconW after daily runs with new score≥80 rows; toggle in web
  settings menu; origin-gated PUT /api/settings/notify. Orchestrator fixed a
  real Win64 bug live-smoke found (WNDPROC needed pointer-sized LRESULT).
- **NSPE sector source** (new, keyless): careers.nspe.org RSS w/ server-side
  keyword filter; self-gates onto mech/manufacturing/industrial profiles
  (higheredjobs pattern); live-verified 31 items parsed. ASME/IEEE/SAE/iHire
  rejected in research (no feeds / Cloudflare).
- **Wave-3 designs awaiting Alex GO**: `brain/design-2026-07-05-imap-status-
detection.md` + `…-ats-autofill-assist.md` (both privacy-sensitive).

## 3. US-first directive

Non-US metro table + further international source work DROPPED from the
backlog. Existing international support stays (tested, self-gating). Sweep
audit: arbeitnow documented-as-is (cached per-cycle, carries remote rows);
language guard now arms from the ACTIVE project's country, not just env.

## 4. Tech-debt sweep (the "thorough comb")

`brain/techdebt-register-2026-07-05.md` = 39 findings, 8 read-only fleet
dimensions + adversarial verify (NOTE: the workflow's verdict-join broke on
paraphrased titles — orchestrator hand-verified everything acted on; two
finder errors caught: test_application_cycle.py tests LIVE contracts, and
legacy/ is gitignored PERSONAL data — left alone).

- **D1**: report.html's per-job link pointed at the retired :5001 tracker
  (broken since S36) → now "Open in Zaggregate" deep-links the web Inbox
  pre-filtered to the company. tracker/app.py + template + CSRF tests
  DELETED; PORT_TRACKER/PORT_RESUME gone; stale docs fixed.
- **D2 (frontend)**: per-tab React.lazy code-splitting — main chunk 821KB →
  495KB + 9 on-demand chunks (SourcesTab stays folded: onboarding imports it
  statically); useQueryGuard replaces the copy-pasted guard in 10 files;
  @dnd-kit/sortable removed; dead eslint-disable directives gone.
- **D3 (backend)**: shared `scrape/html_text.py` stripper replaces 13
  byte-identical copies (PARITY-PROOFED per file; vincere/careeronestop/
  single_feed differ and were left + pinned); `dateparse.py` dedups the ISO
  loop from freshness/search_engine/ghost; onboarding salary-parse reuses
  parse_salary_input (new _detailed seam); db.py _current_status helper;
  import_ai "never a 500" guard now real; companies-dialog worker guarded;
  webui tests: zero real sleeps (shared wait_until); ~41 new tests.
- **D4 (packaging)**: exe excludes the unreachable numpy/HF chain →
  91.8MB (was ~141MB); spec prints absent optional packages instead of
  silently shrinking; pyinstaller pin 6.21.0; certifi declared.
- **Deferred (registered, next debt session)**: pyproject packaging root-fix
  (#12) · tracker/db.py split (#13) · search→ui layering (#14) · tab_inbox
  split (#16) · gui.py lazy-tk imports (#25) · conftest tmp_db consolidation
  (#28) · SourcesTab chunk split.

## Needs Alex

1. **Swap the running window**: production\ still runs the pre-chrome-queue
   build from 21:59; dist\ has the final 91.8MB build (smoke-green). Say the
   word (or close the window) → mirror + relaunch.
2. Wave-3 GOs: IMAP status detection + ATS autofill (briefs in brain/).
3. Push (~38 commits held) · LICENSE · free API keys (Jooble = 500-request
   starter bucket, see S38 chat — worth claiming, not load-bearing).
4. Pending decisions that survived the sweep: tk-tab retirement · exe
   default --desktop · Discover keep/remove.

## Gotchas learned tonight

- PS 5.1 here-strings in the PowerShell tool intermittently mis-parse
  multi-line `git commit -m @'…'@` → use Bash + `git commit -F <file>`.
- robocopy with default retry (/R:1000000) hangs forever on a locked file —
  always pass /R:2 /W:2; a "FAILED" on a hash-identical runtime DLL is
  cosmetic.
- pywebview WNDPROC callbacks MUST use pointer-sized LRESULT/LPARAM
  (wintypes.LPARAM) — c_int defaults overflow on Win64 and only live smoke
  catches it (stubbed tests can't).
- sqlite3.Connection is NOT weak-referenceable — registry keyed by thread
  ident + weakref-to-thread instead of WeakSet.
- Workflow verify stages must echo finding titles VERBATIM for verdict
  joins — or join on index, not title.
