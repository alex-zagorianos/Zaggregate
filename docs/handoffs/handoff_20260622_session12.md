# Handoff — Session 12 (2026-06-22, Opus 4.8, ultracode)

> Hardened the app, then rebuilt it as a **distributable AI-native product** with two
> channels on one engine + data folder. **ALL LOCAL — push HELD.** Output mode: TERSE.

## TL;DR

- master `e0ec05e` → **`6e1ac37`, 19 commits ahead of `origin/master`** — **PUSH HELD** (Alex chose "keep local" until he confirms GitHub `alex-zagorianos/Job-Program` is PRIVATE; `experience.md` PII is already on origin).
- Tests **140 → 322** (`py -m pytest -q`, ~3s). Tree clean; only `master` remains (all delegate/allfixes branches + worktrees pruned).
- Flow: brainstorming → spec → writing-plans → 5 phases, all landed.

## What shipped (5 phases)

**Spec:** `brain/spec-2026-06-22-distributable-product-design.md` — two channels on ONE engine + data folder. Plans: `brain/plan-2026-06-22-phase{0,1,2}-*.md` (P3/P4 inline).

- **P0 Harden** — committed the 2026-06-19 relaunch work; **merged `claude-allfixes`** (290-test backlog; 3 resume conflicts resolved → relaunch ATS docx base + allfixes SSOT parser/generator + re-added Projects); folded delegate **T4 `status_history`** (SCHEMA_VERSION 1→2); **C1 recurrence guard** (new-project resume copy opt-in, default NO); untracked `config_dad.json`/`user_config.json`; deleted dead `resume/app.py`; pruned 8 worktrees.
- **P1 Data folder + prefs** — `config.USER_DATA_DIR` (`JOBPROGRAM_DATA` env › `./data` frozen › repo-root in dev = unchanged); `workspace.BASE_DIR` roots there (fixes frozen `_MEIPASS` write); new `preferences.py` (NL `preferences.md` + `preferences.json` hard-gate {salary_min/locations/remote_ok/work_auth/dealbreakers/seniority_exclude} + legacy migration); `userdata.scaffold()`/`bootstrap()` + `data_templates/` neutral seeds.
- **P2 AI ranking** — new `ranker.py` anchors the fit prompt to `preferences.md` + experience summary; `rank_via_api` (key from env or `secrets/anthropic_key`); `gate` = hard-filter. Wired into the service (InboxTab + ApplyQueueTab) + `daily_run` hard-gate. **Fixed a latent post-merge crash:** ApplyQueueTab called list-returning `parse_fit_response` with the old `.items()` dict API → rerouted through `tracker_service`.
- **P3 Packaging** — `bootstrap()` self-seed wired into gui + daily_run startup; `app.spec` PII-clean (drops `experience.md`/`user_config.json`; bundles `data_templates/` + `companies.json`); `build_package.py` → `dist/JobScout.zip` (app + seeded `data/` next to exe + README); `preferences.{md,json}` gitignored.
- **P4 Claude Code channel** — `mcp_server.py`: 6 stdio tools via official `mcp` SDK `FastMCP` (`get_preferences`/`search_jobs`/`list_inbox`/`set_fit_scores`/`track_job`/`dismiss_job`; CC is the ranker, no AI in server) + `claude-code/` (`.mcp.json` + `find-jobs` skill + README) + `requirements-mcp.txt` (kept out of the exe build).

## 🟡 Needs Alex (machine / decision only)

1. **Confirm repo PRIVATE → push the 19 commits.** (Hold reason: `experience.md` PII on origin.)
2. **Build + test the exe:** `py build_package.py` → `dist/JobScout.zip`. GUI is windowed → needs a live launch (`py gui.py` also sanity-checks the merge). The pyinstaller run was NOT executed here. Watch for an `ImportError` on a lazily-imported scraper/feed client → add it to `app.spec` `hiddenimports` (currently `anthropic, docx, bs4`).
3. **docx title-line:** kept relaunch bold-concat `Company — Title` (flip to allfixes ATS title-on-own-line on request).
4. Optional: first-run setup wizard.

## Pointers

- Canonical brain: `brain/project-status.md` (Session 12 + `## Git` updated this session).
- Global handoff: `E:\ClaudeWork\HANDOFF.md` (2026-06-22 entry).
- Memory: `project-job-search` (roadmap marked ALL 5 PHASES COMPLETE).
