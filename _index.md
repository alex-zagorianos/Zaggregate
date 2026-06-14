---
zag: ZAG0005
tags: [jobsearch-app, index, MOC]
created: 2026-06-13
status: active
---

# Job Search App — Project Home

> Python job-search aggregator + local match-scoring + assisted apply-queue.
> **Assisted batch, never auto-apply** — tool ranks/preps/queues, Alex clicks Submit.
> Status: **🟢 Active — fully built; smoke-test pending.** (This `_index` is an orientation stub; the canonical brain is [[project-status]].)

---

## Core Documents

| Document                       | Purpose                                                  |
| ------------------------------ | -------------------------------------------------------- |
| [[project-status]]             | **Canonical project brain** (`brain\project-status.md`). |
| [[handoff_20260609_session7]]  | Latest session — throughput overhaul.                    |
| [[experience]]                 | Career master file (resume/cover source).                |
| [[claude_code_kickoff_prompt]] | Original CC kickoff prompt.                              |
| `gui.py` / `daily_run.py`      | 5-tab GUI + scheduled daily-run entry points.            |

## Pipeline

Scheduled daily search (07:30 Task Scheduler) → local 0–100 match scoring (`match/scorer.py`) → deduped **Inbox** → optional Claude fit-ranking via clipboard bridge (no API key) → **Apply Queue** GUI tab with resume prompts + "Mark Applied → Next". Free no-key sources: The Muse, RemoteOK.

## Open (from session7 handoff)

- [ ] **SMOKE TEST not run** (shell was down) — `py -m py_compile …`, then `py gui.py`, `py daily_run.py --max-pages 1`.
- [ ] Run `setup_schedule.bat` once (maybe as admin) for the 07:30 task.
- [ ] Two sessions uncommitted — git commit when ready.
- [ ] No tests yet for scorer / bridge parsers.
- [ ] Phase 3 LinkedIn engagement assist — to spec (human-in-the-loop only, no scraping/auto-login).

---

_Source chat: 41a289c2 (job search / LinkedIn). Full detail: `handoff_20260609_session7.md` + `brain\project-status.md`. Last updated 2026-06-13._
