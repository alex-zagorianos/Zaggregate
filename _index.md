---
zag: ZAG0005
tags: [jobsearch-app, index, MOC]
created: 2026-06-13
status: active
---

# Job Search App — Project Home

> Python job-search aggregator + local match-scoring + assisted apply-queue.
> **Assisted batch, never auto-apply** — tool ranks/preps/queues, Alex clicks Submit.
> Status: **🟢 Active — built, tested (127 pass), committed + pushed (HEAD `14bdd31`).** (This `_index` is an orientation stub; the canonical brain is [[project-status]].)

---

## Core Documents

| Document                       | Purpose                                                                                       |
| ------------------------------ | --------------------------------------------------------------------------------------------- |
| [[project-status]]             | **Canonical project brain** (`brain\project-status.md`).                                      |
| [[handoff_20260614_session9]]  | **Latest session** — archive, search tightening, projects, add-companies, browser-ext verify. |
| [[handoff_20260609_session7]]  | Earlier session — throughput overhaul.                                                        |
| [[experience]]                 | Career master file (resume/cover source).                                                     |
| [[claude_code_kickoff_prompt]] | Original CC kickoff prompt.                                                                   |
| `gui.py` / `daily_run.py`      | 5-tab GUI + scheduled daily-run entry points.                                                 |

## Pipeline

Scheduled daily search (07:30 Task Scheduler) → local 0–100 match scoring (`match/scorer.py`) → deduped **Inbox** → optional Claude fit-ranking via clipboard bridge (no API key) → **Apply Queue** GUI tab with resume prompts + "Mark Applied → Next". Free no-key sources: The Muse, RemoteOK.

## Open (next session — see [[handoff_20260615_session10]] · full review [[review-2026-06-15]])

- [ ] **Run the Hermes test** to apply the 8-fix slice — `E:\ClaudeWork\hermes-test-01-jobapp\START-HERE.md` (`plan.md` for Nemotron, `claude-fallback-plan.md` to fall back to Claude). First E2E test of the local AI stack.
- [ ] **C1 LIVE data bug:** `projects/dad-health-informatics/experience.md` is Alex's file (fixed by the slice, Tasks 8–9).

- [ ] **Reload the browser extension** (chrome://extensions → reload "Job Harvester", now v1.2) before next harvest; needs LinkedIn login + `py -m scrape.browser_receiver` running.
- [ ] **Projects Phase 4** (deferred) — per-project scheduler (`daily_run --project` done; wire `setup_schedule.bat` + per-project `daily` flag).
- [ ] Run `setup_schedule.bat` once for the 07:30 task.
- [ ] Optional: company remove/edit UI, Projects Manage (rename/delete), scorer/bridge unit tests; delete root `tracker.db.bak`.

---

_Source chat: 41a289c2 (job search / LinkedIn). Full detail: `handoff_20260614_session9.md` + `brain\project-status.md`. Last updated 2026-06-14._
