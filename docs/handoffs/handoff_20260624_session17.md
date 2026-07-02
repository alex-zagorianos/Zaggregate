# Handoff — Session 17 (2026-06-24, cheap-backend, autonomous) — competitive buildout

> Beta-test session that turned into a large autonomous build. Started by fixing
> "dead links" Alex saw in the AI-lane inbox, then ran a market-research workflow,
> then **built out the Tier 1–3 roadmap** from that research. Built across inline
> work + delegated parallel worktree agents. **ALL COMMITTED LOCAL, push still
> HELD** (rides the S14/15 eyeball-hold). Output mode: TERSE.

## TL;DR

- master `fe96b71` → **+25 commits** (now **25 ahead** of `origin/master`), tree clean.
  **Suite 572 → 682** (`py -m pytest -q`). GUI launches clean.
- **Dead-link root cause + fix** (`586ac45`): Greenhouse `absolute_url` often points at a
  company JS careers SPA that never renders the job. Build the **server-rendered hosted URL**
  (`job-boards.greenhouse.io/embed/job_app?for=slug&token=id`) from slug+id instead; add an
  inbox **liveness prune** (`--prune-inbox` + GUI button) that removes 404s; repair script fixed
  914 existing rows across all projects (browser-verified: Nuro/Tulip links now render).
- **Market research** (workflow, 12 agents): no product ships JobScout's exact 6-leg combo;
  closest = Swiss Job Hunter (OSS, 4/6). Full landscape + 41 mined features → `_jobscout_features
_digest.md` (at `E:\ClaudeWork\`) + the plan below.
- **Built the roadmap** — see status table.

## Plan + decisions

- Plan (all tiers): `brain/plan-2026-06-24-all-tiers-buildout.md`
- Decisions + open questions log: `brain/buildout-log-2026-06-24.md` (D1–D9, Q1–Q3)

## What shipped (by item)

|           | Feature                                                                                     | Commit theme                  |
| --------- | ------------------------------------------------------------------------------------------- | ----------------------------- |
| **T1.1**  | Clean-dead-links button (threaded) + opt-in daily prune                                     | feat(inbox) surfacing / daily |
| **T1.2**  | "Why this matches" + structured scorecard in detail pane (`scorer.score_breakdown`)         | feat(inbox)                   |
| **T1.3**  | Colored score/fit cells (`theme.score_glyph`)                                               | feat(inbox)                   |
| **T1.4**  | Empty states (empty vs filtered-to-zero)                                                    | feat(inbox)                   |
| **T1.5**  | Tools ▸ Due — follow-ups & deadlines (`db.followups_due`)                                   | feat(gui) Tools               |
| **T1.6**  | Tools ▸ Connect-your-AI key box (`config.read/write_secret`, `ui.settings`)                 | feat(gui) Tools               |
| **T1.7**  | Help ▸ Privacy — what leaves this computer                                                  | feat(gui) Tools               |
| **T2.8**  | Tools ▸ Application funnel (`tracker/analytics.py`)                                         | feat(gui) Tools               |
| **T2.9**  | Ghost/staleness advisory + Hide-stale filter (`match/ghost.py`)                             | feat(inbox)                   |
| **T2.10** | Skill-gap "job also wants" (`match/skillgap.py`)                                            | feat(inbox)                   |
| **T2.11** | SmartScreen survival kit in `build_package.py` (FIRST-RUN.txt + launch.bat + signtool stub) | feat (Batch 2)                |
| **T2.12** | First-search offer when Setup finishes                                                      | feat(onboarding)              |
| **T3.14** | Comp normalizer + "Meets pay floor" filter (`match/comp.py`)                                | feat(gui)                     |
| **T3.18** | Contacts/referral CRM (`contacts` table, SCHEMA_VERSION 3→4) + Tools ▸ Contacts             | feat (Batch 2) / feat(gui)    |
| **T3.22** | Opt-in daily Common-Crawl discovery refresh                                                 | feat(daily)                   |
| **T3.23** | T/D/O shortcut hints on Inbox buttons                                                       | feat(inbox)                   |
| **T3.24** | File ▸ Back up / Restore my data                                                            | feat(data)                    |
| **T3.25** | Confidence indicator — folded into the T1.2 scorecard                                       | (in T1.2)                     |

**Engine modules built in parallel via delegated worktree agents** (TDD, reviewed, merged):
`match/ghost.py`, `match/skillgap.py`, `tracker/analytics.py` (Batch 0); `build_package.py` kit,
`match/comp.py`, `contacts` (Batch 2). Plus inline helpers in `scorer`/`theme`/`db`/`config`/
`ui.settings`/`resume.service`.

## 🟡 NOT built (remaining roadmap — specced in the plan)

- **T2.13** browser-ext capture-on-submit — needs the localhost receiver + extension JS; partial
  only, opt-in; left for a focused pass.
- **T3.15** age/repost display (ghost staleness covers most of it), **T3.16** size/funding facets,
  **T3.17** `job_key` dedup (held back from delegation — subtle; do inline + characterization
  test), **T3.19** filter presets, **T3.20** review-mode card, **T3.21** onboarding checklist,
  **T3.27** tunable weights (**see Q2 — your call**), **T3.28** opt-in auto-update.
- **Deferred (decision D2):** full web/Tauri reskin; Gmail-OAuth email auto-status.

## Open questions for Alex (logged, proceeding with defaults)

- **Q1** (carry-over): docx title-line (bold-concat vs ATS-split).
- **Q2:** expose tunable scoring weights to users? (default: behind "Advanced", tuned defaults)
- **Q3:** daily auto-prune defaults **off** (re-probes every link each run). On by default?

## Needs Alex (machine/decision only)

1. **Eyeball `py gui.py`** — Inbox (color cells, scorecard detail, Hide-stale/Meets-pay-floor/New
   filters, Clean dead links, empty states), **Tools menu** (Due / Funnel / Contacts / Connect-AI),
   **Help ▸ Privacy**, **File ▸ Back up/Restore**. Then **`git push`** the 25 local commits.
2. Carry-overs: `py build_package.py` exe build (now ships the SmartScreen kit); live coverage
   baseline.

## Pointers

- Brain: `brain/project-status.md` §"Session 17". Plan + log in `brain/`. Memory: `project-job-search`.
- Build mechanics: delegated parallel modules via Workflow worktree agents (orphan-root quirk →
  copy changed files, don't git-merge; diff-reviewed the 2 edited existing files before trusting).
  gui.py wiring done inline (single delicate 2.4k-line file → no parallelism, serialized).
