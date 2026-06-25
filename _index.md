---
zag: ZAG0005
tags: [jobsearch-app, index, MOC]
created: 2026-06-13
status: active
---

# Job Search App — Project Home

> Python job-search aggregator + local match-scoring + assisted apply-queue.
> **Assisted batch, never auto-apply** — tool ranks/preps/queues, Alex clicks Submit.
> Status: **🟢 Active — **Session 17** fixed the AI-lane "dead links" (server-rendered Greenhouse URLs + inbox liveness prune) and built out the competitive Tier 1–3 roadmap from a 12-agent market-research workflow: structured scorecard + colored cells + ghost/skill-gap/comp signals in the Inbox, a Tools menu (Due / Funnel / Contacts / Connect-AI), Help▸Privacy, File▸Backup-Restore, SmartScreen kit, contacts CRM (schema v4). New signals are all view-level — the 0-100 score is unchanged. **682 tests; 25 commits LOCAL, not pushed (repo private)** — pending Alex's `py gui.py` eyeball. Remaining roadmap (browser-ext capture, dedup, presets, review-mode, tunable weights, auto-update) specced in `brain\plan-2026-06-24-all-tiers-buildout.md`.** (Orientation stub; canonical brain is [[project-status]].)

---

## Core Documents

| Document                                                | Purpose                                                                                      |
| ------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| [[project-status]]                                      | **Canonical project brain** (`brain\project-status.md`).                                     |
| [[handoff_20260624_session17]]                          | **Latest session** — dead-link fix + competitive Tier 1–3 buildout (25 commits, 682 tests).  |
| `brain\plan-2026-06-24-all-tiers-buildout.md`           | The all-tiers roadmap (with per-item status) + `brain\buildout-log-2026-06-24.md` decisions. |
| [[handoff_20260624_session16]]                          | Wire latent gaps (JSON-LD, discovery funnel, freshness) + mechanical sweep.                  |
| [[handoff_20260622_session15]]                          | Top Picks: full-inbox AI snapshot → ranked top-X shortlist + GUI tab.                        |
| [[handoff_20260622_session14]]                          | UI/UX pass: clean light theme, Guide/Help, dark mode, first-run Setup wizard.                |
| [[handoff_20260622_session12]]                          | Distributable AI-native product rebuild (exe + MCP).                                         |
| `brain\spec-2026-06-22-distributable-product-design.md` | Approved two-channel product design spec.                                                    |
| [[handoff_20260614_session9]]                           | Earlier session — archive, search tightening, projects, add-companies, browser-ext verify.   |
| [[experience]]                                          | Career master file (resume/cover source).                                                    |
| [[claude_code_kickoff_prompt]]                          | Original CC kickoff prompt.                                                                  |
| `gui.py` / `daily_run.py`                               | 5-tab GUI + scheduled daily-run entry points.                                                |

## Pipeline

Wide-net search → preferences JSON hard-gate → local 0–100 match scoring (`match/scorer.py`) → deduped **Inbox** → AI fine-rank to `preferences.md` (clipboard bridge default, optional API auto) → **Apply Queue** GUI tab with resume prompts + "Mark Applied → Next". Free no-key sources: The Muse, RemoteOK.

**Two distribution channels on one engine + data folder** (2026-06-22): (1) the **EXE** with hybrid AI for non-technical friends — `py build_package.py` → `dist/JobScout.zip`; (2) the **MCP server + `find-jobs` Claude Code skill** (`mcp_server.py` + `claude-code/`) where Claude Code itself is the ranker. Friends edit `data/preferences.md` (NL profile) + `data/preferences.json` (hard filters); their own data never ships.

**Coverage engine + AI re-rank (2026-06-22, Session 13):** a **3-leg coverage benchmark** (`coverage/`) rates how completely a search finds an area's jobs (reference-proxy ∪ capture-recapture ∪ JOLTS gate), keyed by a stable `job_key`. A generic **discovery funnel** (`discover/`) + Tier-1 ATS scrapers (`scrape/`) + free aggregators (`search/`) + geo/freshness raise that score — **every source gated by a lift-test** proving it doesn't lower coverage. An **AI re-rank round-trip** (`rerank/`, `ranker.py`) exports the inbox + a versioned prompt for any AI, imports the returned scores (validated, `job_key`-joined), snapshots to `score_history`, and supports undo.

## Open (next — Alex's machine/decision only)

- [ ] **Live coverage baseline number** — the lift-gates prove improvement on fixtures; a real area measurement needs a live network run (free sources need no keys), best done interactively.
- [ ] **Push the 5 local commits** (Session 14 UI/UX + dark mode + AI guide; Session 15 location filter + Top Picks) to `origin/master` once Alex eyeballs `py gui.py` — committed locally only. Check both light & dark, and the new **Top Picks** tab.
- [ ] **Build + test the exe:** `py build_package.py` → `dist/JobScout.zip`. GUI is windowed → needs a live launch (`py gui.py` also sanity-checks the merge). If the frozen exe hits an `ImportError`, add the module to `app.spec` `hiddenimports`.
- [ ] **docx title-line decision** — kept relaunch bold-concat `Company — Title`; flip to allfixes ATS-split on request.
- [ ] Optional: WS-3 undo `batch_id` (vs second-precision ts grouping); per-project scheduler (Projects Phase 4); company remove/edit UI; delete root `tracker.db.bak`.

---

_Source chat: 41a289c2 (job search / LinkedIn). Full detail: `brain\project-status.md` §"Session 15" + latest handoff. Last updated 2026-06-22._
