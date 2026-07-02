---
zag: ZAG0005
tags: [jobsearch-app, index, MOC]
created: 2026-06-13
status: active
---

# Job Search App — Project Home

> Python job-search aggregator + local match-scoring + assisted apply-queue.
> **Assisted batch, never auto-apply** — tool ranks/preps/queues, Alex clicks Submit.
> Status: **🟢 Active — ~118 commits ahead of origin, PUSH HELD, 1744 tests.** **Session 31** (overnight 2026-07-02, Fable 5 orchestrating Opus fleet) = repo-root REORG (`ecddfa7`: 27 handoffs → `docs/handoffs/`, one-off scripts → `scripts/`, legacy quarantined) → **8 blank-slate GENERAL-USER persona tests** (SWE/RN/teacher/consultant/warehouse/remote-marketing/mecheng/data-changer; all completed find→track→completion, zero crashes; verdicts 6-7/10, 7/8 beats-manual; Adzuna = 48-100% of every metro inbox) → 4 code-verifying review lenses + 3 research reports → **improvement plan `brain/improvement-plan-2026-07-02-general-user.md`** (7 confirmed P0s: one-line `_industry_tag_match` bug zeroes careers path for multi-word industries; CareerOneStop dark in all runs; remote-only returns 0 on keyed aggregators; seniority/country-blind raw Score; Workday `wday/cxs` public API = top coverage bet). **NO app-code changes — fix wave held for Alex.** Corpus: `brain/general-user-tests-2026-07/`. See [[handoff_20260702_session31]]. **Session 30** (same day, Fable 5 + Opus subagent) = LIVE blank-canvas test runs of both profiles (controls 685-row inbox + top 10; Dad 19 supply-bound + top 10; source-mix measured: registry 85%/58%, Adzuna = all non-seeded local wins, keyless ~1%) → 3 run-caught fixes (FileCache Windows `:` filenames / Oracle tenant-slug company names / freshness log) → Guide source-setup+seeding depth → **Seed-My-Area plan HELD** (`brain/plan-2026-07-01-ai-assisted-setup-seeding.md`) → consulting taxonomy + SmartRecruiters live-validated. OPEN: cross-board company-canon dedup design. See [[handoff_20260701_session30]]. **Session 29** (Fable 5 + Opus fleet) = deep review (`brain/review-2026-07-01-deep-product-review.md`) → FULL remediation buildout (5 waves / 12 builders: 429-safe transport, resume-paste P0, Update-Inbox-now + exe `--daily` + scheduler, source-keys panel + CareerOneStop/jooble/careerjet in the daily net, job_key dedup, base_url BYO-AI unlock + MCP cycle tools, accepted/ghosted + interview rounds, APP_VERSION/applog/README, 9 ATS-wave-2 scrapers w/ UC Health+TriHealth seeded, serpapi reach probe) → adversarial review fleet (9 confirmed defects, all fixed) → **aegean-restyle MERGED** (`d8b1fcf`, Zaggregate branding). See [[handoff_20260701_session29]]. Prior status: **Session 27** (Opus) ran two live end-to-end searches (Dad health-informatics + Me controls/embedded), evaluated ranking/blast-radius/completeness, and shipped **2 fixes**: (1) **concurrency bug** — concurrent runs/GUI-switch corrupted inbox routing (hit live); fixed with a process-local project pin (`workspace.pin_active`, `daily_run` pins once). (2) **Dad's small inbox** (supply-bound, not a bug) — two-tier keywords + seeded 3 probe-verified health employers (Cincinnati Children's/Bon Secours Workday, Regard); Dad 19→23, local BI roles now rank #1(100)/#2(94). Full detail: [[handoff_20260701_session27]] + `brain\eval-2026-07-01-dad-vs-controls-runs.md`. **Session 26** (ultracode) = SCALE+ONBOARDING (BambooHR/Socrata/Rippling/WWR/WorkingNomads + jobhive bulk seeder +252 cos + `build_company_list.py` + ETag). (Orientation stub; canonical brain is [[project-status]].)

---

## Core Documents

| Document                                                | Purpose                                                                                                                                                                       |
| ------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [[project-status]]                                      | **Canonical project brain** (`brain\project-status.md`).                                                                                                                      |
| [[handoff_20260702_session31]]                          | **Latest session** — repo reorg + 8 blank-slate general-user persona tests + review/research fleet → improvement plan (7 confirmed P0s, fix wave HELD).                       |
| `brain\improvement-plan-2026-07-02-general-user.md`     | **The morning read** — P0 defects w/ file:line, quick wins, coverage/onboarding roadmaps, strategic bets (Workday cxs, CareerOneStop).                                        |
| [[handoff_20260701_session30]]                          | Live blank-canvas test runs (top-10s for controls + Dad), 3 run-caught fixes, Guide setup depth, Seed-My-Area plan HELD, consulting taxonomy + SmartRecruiters validation.    |
| [[handoff_20260701_session29]]                          | Deep review → 5-wave Opus remediation buildout → adversarial review fleet → aegean-restyle merged (Zaggregate branding).                                                      |
| [[handoff_20260701_session27]]                          | Live eval (Dad vs controls) + 2 fixes: concurrency pin, Dad-inbox supply fix (seed local Workday health systems, 19→23). See `brain\eval-2026-07-01-dad-vs-controls-runs.md`. |
| [[handoff_20260701_session26]]                          | SCALE + ONBOARDING — free sources + jobhive bulk seeder (+252) + `build_company_list.py` + ETag; 28 ahead, push held.                                                         |
| [[handoff_20260630_session21]]                          | Controls smoke test + **AI-pipeline optimization** spine (facts→gate→compact prompt, ~⅓ tokens, live in the rank buttons); local-model deferred (spec §11b).                  |
| `brain\spec-2026-06-29-ai-pipeline-optimization.md`     | Approved design for decomposing AI ranking for cheap/local models (extract/gate/score/harvest; §11b = deferred local-model work).                                             |
| [[handoff_20260630_session20]]                          | Deep review → live `.exe` new-user test → fix-ALL-findings remediation (GLM+Sonnet); Scrapling, schema v4→v5, exe-crash fix (79 commits, 725→841 tests).                      |
| [[handoff_20260625_session19]]                          | Research → company-acquisition pipeline (metro enumeration + enterprise-ATS + tiering) + remote-first-class (725 tests).                                                      |
| [[handoff_20260625_session18]]                          | Modern ttkbootstrap UI + dark-outline fix + extension full-detail capture (31 commits, 696 tests).                                                                            |
| [[handoff_20260624_session17]]                          | Dead-link fix + competitive Tier 1–3 buildout (25 commits, 682 tests).                                                                                                        |
| `brain\plan-2026-06-24-all-tiers-buildout.md`           | The all-tiers roadmap (with per-item status) + `brain\buildout-log-2026-06-24.md` decisions.                                                                                  |
| [[handoff_20260624_session16]]                          | Wire latent gaps (JSON-LD, discovery funnel, freshness) + mechanical sweep.                                                                                                   |
| [[handoff_20260622_session15]]                          | Top Picks: full-inbox AI snapshot → ranked top-X shortlist + GUI tab.                                                                                                         |
| [[handoff_20260622_session14]]                          | UI/UX pass: clean light theme, Guide/Help, dark mode, first-run Setup wizard.                                                                                                 |
| [[handoff_20260622_session12]]                          | Distributable AI-native product rebuild (exe + MCP).                                                                                                                          |
| `brain\spec-2026-06-22-distributable-product-design.md` | Approved two-channel product design spec.                                                                                                                                     |
| [[handoff_20260614_session9]]                           | Earlier session — archive, search tightening, projects, add-companies, browser-ext verify.                                                                                    |
| [[experience]]                                          | Career master file (resume/cover source).                                                                                                                                     |
| [[claude_code_kickoff_prompt]]                          | Original CC kickoff prompt.                                                                                                                                                   |
| `gui.py` / `daily_run.py`                               | 5-tab GUI + scheduled daily-run entry points.                                                                                                                                 |

## Pipeline

Wide-net search → preferences JSON hard-gate → local 0–100 match scoring (`match/scorer.py`) → deduped **Inbox** → AI fine-rank to `preferences.md` (clipboard bridge default, optional API auto) → **Apply Queue** GUI tab with resume prompts + "Mark Applied → Next". Free no-key sources: The Muse, RemoteOK.

**Two distribution channels on one engine + data folder** (2026-06-22): (1) the **EXE** with hybrid AI for non-technical friends — `py build_package.py` → `dist/JobScout.zip`; (2) the **MCP server + `find-jobs` Claude Code skill** (`mcp_server.py` + `claude-code/`) where Claude Code itself is the ranker. Friends edit `data/preferences.md` (NL profile) + `data/preferences.json` (hard filters); their own data never ships.

**Coverage engine + AI re-rank (2026-06-22, Session 13):** a **3-leg coverage benchmark** (`coverage/`) rates how completely a search finds an area's jobs (reference-proxy ∪ capture-recapture ∪ JOLTS gate), keyed by a stable `job_key`. A generic **discovery funnel** (`discover/`) + Tier-1 ATS scrapers (`scrape/`) + free aggregators (`search/`) + geo/freshness raise that score — **every source gated by a lift-test** proving it doesn't lower coverage. An **AI re-rank round-trip** (`rerank/`, `ranker.py`) exports the inbox + a versioned prompt for any AI, imports the returned scores (validated, `job_key`-joined), snapshots to `score_history`, and supports undo.

## Open (next — Alex's machine/decision only)

- [ ] **Live coverage baseline number** — the lift-gates prove improvement on fixtures; a real area measurement needs a live network run (free sources need no keys), best done interactively.
- [ ] **Push the 79 local commits** (Sessions 14–20) to `origin/master` once Alex eyeballs `py gui.py` — committed locally only. Check the new **Tools ▸ Enable stealth fetching**, **Search ▸ Save**, wizard re-run pre-fill, and that **New Project** shows a "Default" entry.
- [ ] **Reload the unpacked extension** (manifest 1.4) for the Indeed `?jk=` link fix.
- [ ] **Build + test the exe:** `py build_package.py` → `dist/JobScout.zip`. GUI is windowed → needs a live launch (`py gui.py` also sanity-checks the merge). If the frozen exe hits an `ImportError`, add the module to `app.spec` `hiddenimports`.
- [ ] **docx title-line decision** — kept relaunch bold-concat `Company — Title`; flip to allfixes ATS-split on request.
- [ ] Optional: WS-3 undo `batch_id` (vs second-precision ts grouping); per-project scheduler (Projects Phase 4); company remove/edit UI; delete root `tracker.db.bak`.

---

_Source chat: 41a289c2 (job search / LinkedIn). Full detail: `brain\project-status.md` §"Session 21"/"Session 20" + `handoff_20260630_session21.md`. Last updated 2026-06-30 (Session 21: controls smoke test + AI-pipeline optimization spine; local-model deferred; **pushed**, origin even, 841 tests — 1 uncommitted test-isolation fix to commit)._
