---
zag: ZAG0005
tags: [jobsearch-app, index, MOC]
created: 2026-06-13
status: active
---

# Job Search App — Project Home

> Python job-search aggregator + local match-scoring + assisted apply-queue.
> **Assisted batch, never auto-apply** — tool ranks/preps/queues, Alex clicks Submit.
> Status: **🟢 Active — distributable AI-native product + a measured, lift-gated coverage engine + AI re-rank round-trip. 490 tests pass; HEAD `228b013` — ✅ PUSHED to origin/master (repo confirmed private).** (This `_index` is an orientation stub; the canonical brain is [[project-status]].)

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

**Coverage engine + AI re-rank (2026-06-22, Session 13):** a **3-leg coverage benchmark** (`coverage/`) rates how completely a search finds an area's jobs (reference-proxy ∪ capture-recapture ∪ JOLTS gate), keyed by a stable `job_key`. A generic **discovery funnel** (`discover/`) + Tier-1 ATS scrapers (`scrape/`) + free aggregators (`search/`) + geo/freshness raise that score — **every source gated by a lift-test** proving it doesn't lower coverage. An **AI re-rank round-trip** (`rerank/`, `ranker.py`) exports the inbox + a versioned prompt for any AI, imports the returned scores (validated, `job_key`-joined), snapshots to `score_history`, and supports undo.

## Open (next — Alex's machine/decision only)

- [ ] **Live coverage baseline number** — the lift-gates prove improvement on fixtures; a real area measurement needs a live network run (free sources need no keys), best done interactively.
- [ ] **Build + test the exe:** `py build_package.py` → `dist/JobScout.zip`. GUI is windowed → needs a live launch (`py gui.py` also sanity-checks the merge). If the frozen exe hits an `ImportError`, add the module to `app.spec` `hiddenimports`.
- [ ] **docx title-line decision** — kept relaunch bold-concat `Company — Title`; flip to allfixes ATS-split on request.
- [ ] Optional: first-run setup wizard; WS-3 undo `batch_id` (vs second-precision ts grouping); per-project scheduler (Projects Phase 4); company remove/edit UI; delete root `tracker.db.bak`.

---

_Source chat: 41a289c2 (job search / LinkedIn). Full detail: `brain\project-status.md` §"Session 13" + `HANDOFF.md`. Last updated 2026-06-22._
