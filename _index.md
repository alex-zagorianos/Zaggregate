---
zag: ZAG0005
tags: [jobsearch-app, index, MOC]
created: 2026-06-13
status: active
---

# Job Search App — Project Home

> Python job-search aggregator + local match-scoring + assisted apply-queue.
> **Assisted batch, never auto-apply** — tool ranks/preps/queues, Alex clicks Submit.
> Status: **🟢 Active — hardened + rebuilt as a distributable AI-native product. 322 tests pass; HEAD `6e1ac37`, 19 commits ahead — 🟡 PUSH HELD (confirm repo private first).** (This `_index` is an orientation stub; the canonical brain is [[project-status]].)

---

## Core Documents

| Document                                                | Purpose                                                                                    |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| [[project-status]]                                      | **Canonical project brain** (`brain\project-status.md`).                                   |
| [[handoff_20260622_session12]]                          | **Latest session** — hardened + rebuilt as a distributable AI-native product (exe + MCP).  |
| `brain\spec-2026-06-22-distributable-product-design.md` | Approved two-channel product design spec.                                                  |
| [[handoff_20260614_session9]]                           | Earlier session — archive, search tightening, projects, add-companies, browser-ext verify. |
| [[experience]]                                          | Career master file (resume/cover source).                                                  |
| [[claude_code_kickoff_prompt]]                          | Original CC kickoff prompt.                                                                |
| `gui.py` / `daily_run.py`                               | 5-tab GUI + scheduled daily-run entry points.                                              |

## Pipeline

Wide-net search → preferences JSON hard-gate → local 0–100 match scoring (`match/scorer.py`) → deduped **Inbox** → AI fine-rank to `preferences.md` (clipboard bridge default, optional API auto) → **Apply Queue** GUI tab with resume prompts + "Mark Applied → Next". Free no-key sources: The Muse, RemoteOK.

**Two distribution channels on one engine + data folder** (2026-06-22): (1) the **EXE** with hybrid AI for non-technical friends — `py build_package.py` → `dist/JobScout.zip`; (2) the **MCP server + `find-jobs` Claude Code skill** (`mcp_server.py` + `claude-code/`) where Claude Code itself is the ranker. Friends edit `data/preferences.md` (NL profile) + `data/preferences.json` (hard filters); their own data never ships.

## Open (next — Alex's machine/decision only; see [[handoff_20260622_session12]])

- [ ] **Confirm GitHub `alex-zagorianos/Job-Program` is PRIVATE → then push the 19 commits.** Push is HELD because `experience.md` PII is already on origin.
- [ ] **Build + test the exe:** `py build_package.py` → `dist/JobScout.zip`. GUI is windowed → needs a live launch (`py gui.py` also sanity-checks the merge). If the frozen exe hits an `ImportError`, add the module to `app.spec` `hiddenimports`.
- [ ] **docx title-line decision** — kept relaunch bold-concat `Company — Title`; flip to allfixes ATS-split on request.
- [ ] Optional: first-run setup wizard; per-project scheduler (Projects Phase 4); company remove/edit UI; delete root `tracker.db.bak`.

---

_Source chat: 41a289c2 (job search / LinkedIn). Full detail: `handoff_20260622_session12.md` + `brain\project-status.md`. Last updated 2026-06-22._
