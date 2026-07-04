# Web-UI Migration Implementation Plan — S36 (2026-07-04)

> **For agentic workers:** execute ONE phase-task at a time; every task ends with the
> full suite green (`py -3.12 -m pytest`, baseline 2478) and a local commit. Never push.
> Read `CLAUDE.md` first. Builder prompts include per-task detail; this document is the
> master contract — interfaces defined here are binding across tasks.

**Goal:** Replace the tkinter/ttkbootstrap GUI tab-by-tab with a modern, sleek local web
UI (React/TS/shadcn over the existing Flask receiver on 127.0.0.1:5002), keeping the
Python engine untouched and the desktop app property intact (single PyInstaller exe, a
friend unzips and runs).

**Architecture:** One process = the app. The existing `scrape/browser_receiver.py` Flask
app gains a `webui` blueprint serving (a) built static frontend assets at `/app` and
(b) a JSON API at `/api/*` that is a re-hosting of the engine seam `mcp_server.py`
already wraps (`tracker.service`, `tracker.db`, `ranker`, `rerank`, `preferences`,
`workspace`). Long-running engine ops (daily run, search, list-building) run on
background threads through a job-runner with per-project single-flight locks, streaming
progress over SSE using the engine's existing line-sink / progress-callback contracts.
The tkinter GUI keeps working throughout; each tab retires only after its web twin is
signed off.

**Tech stack:** Backend: Flask (existing), no new Python deps required (SSE via
generator responses). Frontend: Vite + React + TypeScript, Tailwind v4, shadcn/ui
(Radix), TanStack Table + Query, dnd-kit (kanban drag-drop), cmdk (command palette),
lucide-react icons, self-hosted OFL fonts (Fraunces / Inter / JetBrains Mono — the
Aegean spec's deferred font bundling, now shipped where it's trivial).

## Global constraints (binding for every task)

- Python via `py -3.12` only. Suite green at every commit (`py -3.12 -m pytest`; 2478 baseline, grows).
- **PUSH HELD** — commit locally freely, never push.
- **127.0.0.1 only.** No `0.0.0.0`, ever (documented security decision, browser_receiver.py L40-42).
- Mutating `/api/*` routes MUST pass the receiver's `_origin_allowed()` gate (loopback + `chrome-extension://`), same as `/clip|/harvest|/track`.
- API keys/secrets never leave the server: GET endpoints return masked values only; `_call_prompt_via_api`-style Anthropic calls happen server-side.
- **Never two project-touching processes at once.** The web server runs single-process; project-touching mutations serialize behind the job-runner lock; per-request project resolution (the `/harvest` pattern), never a process-wide pin from a request handler.
- **Inclusion over precision** (repo CLAUDE.md): the web Inbox may never hard-hide loosely-related rows; dismiss/status/view-mode are the only drop mechanisms.
- **Scoring parity:** no task touches `match/`, `ranker.py`, `preferences.hard_gate`, or rescore levers. If a task ever must, it requires the byte-identical eng-parity harness before landing.
- Existing test conventions: Flask `test_client()` (no live sockets — conftest autouse socket guard), tk tests skip headless via `tk.TclError → pytest.skip`.
- PyInstaller: any new first-party package with lazy imports goes into app.spec's `collect_submodules` tuple; any new data files (static assets) into `datas`; runtime path resolution must be `sys._MEIPASS`-aware with a dev fallback.
- Frontend build output (`webui/static/`) is COMMITTED so source users without Node still get the web UI; `webui/frontend/node_modules/` is gitignored.
- Conventional commits (`feat(webui): …`, `test(webui): …`), one logical change per commit.

## Visual identity — "Aegean Paper", web edition

Source of truth: `ui/theme.py` `_LIGHT`/`_DARK` (17 named colors each) + spacing
`SP=(4,8,12,16,24,32)` + `RADIUS_BTN=7`/`RADIUS_CHIP=6` + `STATUS_BADGE` (9 status
colors per mode) + score bands (≥70 good / ≥45 mid / else low). These are generated
into CSS custom properties by `scripts/gen_web_tokens.py` (Task 0c-1) — the tk app and
web app share one palette during the transition; a palette change in theme.py + a
regen keeps them in sync.

Identity rules for all frontend work (from `brain/spec-2026-07-01-ui-aegean-restyle.md`):
paper/near-black base, ONE accent (Aegean blue `#0d5eaf` light / `#4a9be0` dark),
editorial serif headlines (Fraunces), Inter body, JetBrains Mono for numerals only,
8px spacing grid, hairline borders, 7px-rounded controls, square table corners.
Light `WINDOW #f4f3ee / SURFACE #fcfbf8 / INK #16191f`; dark `WINDOW #13171d /
SURFACE #1c222b / INK #e7eaef`. Dark mode = `data-theme="dark"` attribute toggling the
custom-property set. The topbar wordmark (**Zag** in accent + **gregate** in ink, serif,
zigzag Z mark) is the brand hero — reproduce as inline SVG + styled text.

Quality bar: this must read as a designed product, not a Bootstrap admin panel —
generous whitespace, typographic hierarchy, subtle motion (150–200ms ease), empty
states with guidance, keyboard-first affordances (Ctrl+K palette, `t/d/o` triage keys
preserved from the tk app).

## File map

```
webui/
  __init__.py          # register_webui(app) — blueprint factory, static resolution
  paths.py             # static_dir(): _MEIPASS-aware resolution w/ dev fallback
  security.py          # origin gate shared w/ receiver (import, don't duplicate)
  serializers.py       # row/JobResult → JSON dict shaping (dates, extras, masking)
  jobs.py              # JobRunner: id→{status,lines,result,error}, locks, SSE drain
  api/
    __init__.py        # blueprint assembly
    system.py          # /api/status, /api/project (GET list+active, POST switch)
    inbox.py           # inbox list/filters/track/dismiss/fit/export/import/undo
    toppicks.py        # /api/toppicks
    applications.py    # tracker CRUD, statuses, rounds, notes, contacts, funnel
    settings.py        # source keys (masked), theme, location-mode, key tests
    prefs.py           # preferences load/save
    runs.py            # daily run + search jobs: POST start, GET status, SSE events
    resume.py          # prompt build, paste→DOCX, file downloads
    onboarding.py      # wizard state + step submission (Phase 5)
  static/              # built frontend (committed)
  frontend/            # Vite app (React TS)
    src/
      tokens.css       # GENERATED — do not hand-edit
      api/client.ts    # typed fetch client
      components/…     # shadcn/ui + app components
      tabs/…           # one folder per tab
scripts/gen_web_tokens.py   # theme.py → tokens.css
tests/webui/…               # Flask test_client API tests, one file per api module
```

Registration point: `scrape/browser_receiver.py` calls `register_webui(app)` guarded by
try/except ImportError (receiver stays functional standalone if webui absent).
`gui.py` gains no coupling; the eventual launcher (Phase 5) is
`py -m webui` / exe flag `--web` → start receiver+webui, open default browser at
`http://127.0.0.1:5002/app`.

## API contract (Phase 0b establishes; later phases extend)

All responses `{"ok": true, ...}` or `{"ok": false, "error": str}` + proper HTTP codes.
Mutating routes: origin-gated, JSON bodies, 8MB cap inherited.

- `GET /api/status` → `{ok, version, project, theme}`
- `GET /api/project` → `{active, projects:[{slug,name,person,daily}]}`; `POST /api/project {slug}` → switch (`workspace.set_active`)
- `GET /api/toppicks?limit=N` → `{rows:[serialized inbox rows w/ rank]}` (tracker.service.top_picks)
- `POST /api/inbox/<id>/track` → `{app_id}`; `POST /api/inbox/<id>/dismiss` → `{ok}`
- `GET /api/settings/keys` → `[{source, label, fields:[{name, set, masked}], get_key_url}]`; `PUT /api/settings/keys/<source>` `{field:value…}`; `POST /api/settings/keys/<source>/test` → live probe result (reuse ui/source_keys.py probe logic, moved server-side)
- `GET/PUT /api/settings/theme` `{mode: light|dark}`
- Jobs: `POST /api/runs/daily` → `{job_id}` (409 `{running_job_id}` if that project already has one); `GET /api/jobs/<id>` → `{status: running|done|failed, lines_tail, result}`; `GET /api/jobs/<id>/events` → SSE stream (`event: line|done|error`)
- Phase 2+: `/api/applications*` mirroring `tracker/db.py` CRUD (statuses list served from `db.STATUSES`), kanban move = `POST /api/applications/<id>/status`
- Phase 3+: `GET /api/inbox?min_score=&sources=&size=&location_mode=&pay_floor=&q=&new_only=&unscored_only=&hide_stale=` (server-side filtering mirroring InboxTab's classifier helpers), export/import, fit-scores batch, undo
- Phase 4+: `POST /api/search` (job w/ per-source SSE progress events reusing `SearchEngine.run_full_search(progress=cb, cancel=Event)`), `POST /api/jobs/<id>/cancel`; resume endpoints wrapping `resume/service.py` with DOCX downloads via `send_file`

## Phases (task tracker #2–#12 mirrors this)

**Phase 0a — extract Apply Queue (pre-req hygiene).** Pure move of `ApplyQueueTab`
(gui.py L148–635) → `ui/tab_queue.py`, S35b split pattern (compat re-export, palette
discipline, late imports preserved). Exit: suite green, `gui.ApplyQueueTab` importable.

**Phase 0b — backend foundation.** `webui/` package per file map: blueprint, static
serving, serializers, JobRunner, system/toppicks/settings-theme routes + SSE plumbing,
`tests/webui/` covering: status, project list/switch, origin-gate 403 on mutating
routes, toppicks shape, job lifecycle (fake job fn), SSE event framing, 409
single-flight. Exit: suite green with ~25+ new tests; receiver unaffected (existing
receiver tests untouched).

**Phase 0c — frontend scaffold.** `scripts/gen_web_tokens.py` + generated tokens.css;
Vite/React/TS/Tailwind/shadcn scaffold; app shell: topbar wordmark, tab nav, dark-mode
toggle, Ctrl+K palette (cmdk, commands stubbed), API client, error/empty-state
primitives; build wired to output `webui/static/`; `npm run build` clean;
`/app` serves the shell from Flask. Exit: shell renders both themes, typecheck+build
clean, committed static assets.

**Phase 0d — packaging.** app.spec: `webui` in `collect_submodules` tuple + static in
`datas`; `webui/paths.py` `_MEIPASS` resolution test; `build_package.py` unchanged
mechanics verified; rebuild exe; smoke: frozen exe with receiver toggled serves
`/app` + `/api/status`. Exit: documented smoke pass.

**Phase 1 — pilot: Top Picks + Connect Job Sources.** Full vertical slice. Top Picks:
ranked read-only table (TanStack), Show-top-N, Track/Dismiss/Open w/ optimistic
updates + toasts, empty state pointing at Inbox export flow. Sources: data-driven
form for the 5 keyed sources, save/live-test/instant feedback, get-a-key links,
masked persisted values, Adzuna paste-splitter (port the tested regex). Exit: behavior
parity vs tk twins verified side-by-side; API tests + component logic tests green.

**Phase 2 — Tracker + Kanban + JobDialog.** Applications API (full CRUD surface incl.
rounds/notes/contacts/funnel); tracker table w/ status chips + archive view; kanban
with dnd-kit drag-drop (+ Move menu preserved for keyboard/a11y); job editor sheet w/
conditional offer fields, rounds sub-CRUD, timeline, `.ics` download. Exit: every
tracker/kanban tk action reproducible on web; suite green.

**Phase 3 — Inbox (flagship).** Inbox API w/ server-side filters; daily-run job w/
live SSE console; triage (t/d/o keys, bulk dismiss + undo), detail pane (fit
rationale, score breakdown, ghost/stale, ATS hint), AI export/import UI, keyless +
reach badges, demo banner. Inclusion-over-precision enforced. Exit: parity on all
InboxTab affordances that survive design review; suite green.

**Phase 4 — Search + Apply Queue + Resume.** Search w/ per-source streaming progress,
cancel, source-health detail; Apply Queue flows (prompt copy, paste→DOCX, batch-of-5,
API generate, mark-applied auto-advance); Resume tab w/ downloads replacing explorer
reveals. Exit: parity; suite green.

**Phase 5 — onboarding + dialogs + consolidation.** Wizard (7 steps, reuse
`setup_wizard.py`/`ai_setup.py` pure validators server-side), AI-setup, Add
Companies/Build My List (SSE log streams), Seed My Area, Guide static page,
backup/restore via download/upload; **retire `tracker/app.py` (:5001)** — routes fold
into :5002, `browser_ext/popup.js` `TRACKER_URL` updated, `run_servers.bat` updated;
launcher `--web` + browser-open. Exit: tk GUI optional; single server; ext regression
tests green.

**Deep testing (task #11).** Written plan first, then execution: full suite;
API-contract sweep (every route × auth/origin/error paths); frontend typecheck +
build + component tests; frozen-exe functional pass; scoring-parity spot-check
(no drift expected — assert byte-identical daily-run scoring vs pre-migration
baseline on the eng profile harness); performance sanity (inbox with 2k rows).

**Scenario testing (task #12).** Written plan first, then execution: blank-slate
personas (eng/nurse/UK/remote, mirroring S35b's validation lanes) driven start-to-
finish through the WEB UI/API — onboard → connect keys → seed → daily run → triage →
track → kanban advance → resume gen; plus returning-user and project-switch
scenarios. Deliverable: findings report (errors / inefficiencies / improvement areas)
in brain/, fixes triaged.

## Review protocol (every phase)

1. Builder agent(s) implement (worktree if parallel writers; direct-in-repo when serial).
2. Reviewer agent (fresh context) reviews the diff for: correctness vs this contract,
   security (origin gate, secret masking, path traversal on downloads), the global
   constraints above, and design-quality on frontend work.
3. Orchestrator verifies independently: run suite, run build, exercise key routes via
   test_client, eyeball rendered UI via preview screenshots where possible.
4. Confirmed findings → fix builder → re-verify. Only then next phase.

## Risks / gotchas carried from recon

- PyInstaller lazy-import blind spot (app.spec `collect_submodules`) — silent frozen-only ImportError; Phase 0d smoke exists to catch this early.
- `tracker/app.py` runs `init_db()` at import time — do NOT import it from webui; its retirement (Phase 5) removes the hazard.
- `rescore_inbox.py` opens raw sqlite without WAL pragmas — don't call it from a request thread; only via the job runner (which serializes).
- `applog._WARNED_ONCE` / `discoverer._RUN_QUERY_MEMO` are per-run process globals — job runner must reset per run exactly like `daily_run.main()` does, and never run two engine jobs concurrently in-process.
- Windows: dev-mode `npm` calls are fine; never shell `explorer` from server code — all file handoffs are HTTP downloads.
- graphify graph is stale for `ui/` (pre-split monolith): builders must trust files over the graph there; run `graphify update .` after big landings.
