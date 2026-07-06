# Handoff — Session 39 (2026-07-06, overnight) — dead project switcher fixed + Alex's 4-lane session setup

## What Alex asked

1. "Pressing the projects tab, I am unable to switch which project I am using."
2. "Set up a fresh session for me exclusively — the original AI, software,
   controls/embedded, and Mech design projects."

## 1. Root cause — the launch pin ate every switch (S39 bug)

`webui/__main__.main()` step 2 pins the launch project for the WHOLE process
(`workspace.pin_active(active_slug())`, receiver-owns-process pattern). But
`POST /api/project` only wrote the registry: `set_active(slug)` persisted, the
pin kept `active_slug()` on the old project, the query invalidation refetched
the pinned slug, and the switcher snapped back. Silently — no toast on the
switch path. Every click Alex made _persisted_ (the registry flip-flopped
dad-health-informatics → applied-ai → mecheng across the evening) but never
went live. Reproduced with a Flask test client + simulated launch pin before
touching anything.

## 2. The fix

- **`webui/api/system.py` — `_go_live_or_pending(slug, body)`**, used by both
  the switch route and `project_create(switch:true)`: after `set_active`, an
  IDLE pin (no exclusive engine job — `runner.exclusive_active() is None`) is
  **MOVED** to the new slug, so an in-process switch goes live immediately.
  A pin owned by a genuinely in-flight run is left alone (S27 class) and
  surfaced as `pending_pinned`, exactly as before.
- **Frontend**: `SwitchProjectResponse` type (the POST never returned
  `projects[]`; old typing lied), `useSwitchProject` now toasts on
  `pending_pinned` ("takes effect once the current run finishes") and toasts
  on error — a mute-dead switcher can't happen again. Bundle rebuilt
  (`tsc -b && vite build` → webui/static, 217 vitest green).
- **Tests** (TDD, red→green):
  `test_system.py::test_project_switch_moves_idle_launch_pin` +
  `..._under_running_engine_is_pending` (runner monkeypatched);
  `test_project.py` same split for create+switch. Old under-pin tests were
  rewritten — their "any pin ⇒ pending" assumption WAS the bug.
- `webui/__main__.py` docstring notes the pin now follows in-process switches.

## 3. Ops discovery — TWO servers were sharing port 5002

Since ~23:54 last night BOTH were bound to 5002 (Windows SO_REUSEADDR lets the
second bind succeed silently):

- `python -m scrape.browser_receiver` (dev repo, real data, the launch pin) —
  what Alex's UI was actually hitting.
- `production\JobProgram\JobProgram.exe --desktop` (S38 packaging test) — with
  its OWN EMPTY data root (`production\JobProgram\data`), answering
  `project:null` whenever it won the accept race.

Both were killed; ONE clean dev receiver now runs with the fixed code
(verified live: switch software→live→applied-ai round-trip on 5002).

**Flags:**

- The production exe still contains the OLD code — repackage
  (`build_package.py`) before the next production swap to pick up the fix.
- Tech debt: no port-conflict guard at startup (second instance should fail
  loud, not share via SO_REUSEADDR — use exclusive bind / pre-bind probe).
- Tech debt: any run's `finally: unpin_active()` DESTROYS the launch pin
  (process then follows the registry cross-process again). Pin semantics
  should save/restore (inbox_health already does; companies.py/run_ingest
  don't).

## 4. Alex's session — 4 original lanes, exclusively

- `projects.json`: `active: applied-ai`; `daily: true` ONLY on **applied-ai,
  software, controls, mechdesign** (controls-cincinnati flipped OFF — the
  "controls" lane supersedes it per the setup_lanes strategy).
- `scripts/setup_schedule.py` run → per-project tasks registered:
  JobSearchDaily_mechdesign 07:30 · _controls 07:35 · _software 07:40 ·
  _applied-ai 07:45 (per-user, no admin).
- Legacy bare `\JobSearchDaily` task (7:30, `py daily_run.py` on whatever was
  active) **DELETED** — redundant + would double-run/collide with the lane
  tasks. Restore if ever needed:
  `schtasks /Create /F /SC DAILY /ST 07:30 /TN JobSearchDaily /TR "cmd.exe /c cd /d \"E:\ClaudeWork\ZAG0005 - Job Search App\" && py daily_run.py"`.
- No data was wiped (inclusion philosophy): existing inboxes on the four lanes
  stay; the 07:30–07:45 sweep brings fresh jobs. gu-_/gs-_/val-_/test-_ and
  dad projects untouched, just not daily.

## State

- Suite: webui tests + vitest green at handoff-write time; FULL
  `py -3.12 -m pytest` was launched in background — see the session close-out
  message / git commit for the final count.
- Committed locally, **PUSH HELD** per repo discipline.
- Stale memory corrected: `daily_run --project X` does NOT flip global active
  anymore (S32/L1) — per-lane tasks are safe.

## Next

- Repackage the production exe when Alex wants the fix in the frozen build.
- Wave-3 GOs (IMAP status detection + ATS autofill briefs) still pending.
- Pin-semantics save/restore + port-conflict guard — registered above as debt.
