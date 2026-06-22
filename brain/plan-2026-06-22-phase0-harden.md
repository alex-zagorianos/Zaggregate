# Phase 0 — Harden the Tool (Integration Runbook)

> **For agentic workers:** This is an integration/merge runbook, not a TDD feature plan. Steps are
> ordered operations with verification gates. Execute INLINE (delicate conflict resolution — not
> parallelizable). Steps use checkbox (`- [ ]`) syntax.

**Goal:** Land the verified `claude-allfixes` hardening (290 tests) onto `master` cleanly, preserving
the uncommitted relaunch work and the unique T4 status-history feature, and prune dead branches.

**Architecture:** Work on branch `harden/phase0` (off `master @ e0ec05e`). Commit relaunch work →
3-way merge `claude-allfixes` → resolve 3 resume conflicts → fold T4 → verify ≥290 → fast-forward
`master` → push (gated on repo-private confirm).

**Tech Stack:** git, Python 3.12 (`py`), pytest.

## Global Constraints

- Python command is `py` (not `python`); no venv, global packages.
- NEVER `--no-verify` / `--no-gpg-sign`; never change git config without asking.
- Commit message trailers: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` +
  `Claude-Session: https://claude.ai/code/session_01VxXHutqNNuiRwAYkvLps6i`.
- **PUSH IS GATED:** do NOT push until Alex confirms `alex-zagorianos/Job-Program` is PRIVATE (PII in
  `experience.md`). All steps before push are local + reversible.
- Test gate after merge: `py -m pytest -q` ≥ 290 passing.

---

## Step 1 — Pre-flight

- [ ] Confirm on `harden/phase0`, spec committed (`f5617a4`), relaunch work present & uncommitted.
- [ ] Baseline: `py -m pytest -q` → 140 passing on this tree.
- [ ] **Ask Alex to confirm the GitHub repo is private** (blocks Step 10 push only; proceed with 2–9).

## Step 2 — Commit the relaunch work (resume engine + registry)

The uncommitted edits are one coherent resume-engine upgrade + a registry expansion.

- [ ] `git add experience.md resume/generator.py resume/experience_parser.py resume/docx_builder.py`
- [ ] Commit: `feat(resume): projects + headline sections and ATS-tuned docx styling`
- [ ] `git add companies.json` → commit: `feat(companies): expand careers registry (+~175 boards)`
- [ ] `git add brain/project-status.md` → commit: `docs(brain): session 11 status note`

## Step 3 — Untracked scaffolding hygiene

- [ ] `.gitignore` += `candidates.json`, `verify_and_add.py`, `flatten_candidates.py` (one-shot/intermediate).
- [ ] Move reusable tools to `scripts/`: `setup_lanes.py`, `summarize_lanes.py`, `generate_shortlist.py`;
      `git add scripts/ .gitignore` → commit: `chore: stash one-shot scaffolding; keep reusable lane scripts`.
- [ ] `job search/` folder → rename to `planning/` (space-in-path footgun) and `handoff_20260615_session11.md`:
      commit both (`docs: planning notes + session 11 handoff`) — matches in-repo handoff convention.

## Step 4 — Merge claude-allfixes

- [ ] `git merge claude-allfixes` — expect conflicts ONLY in the 3 resume files; 56 others apply clean.
- [ ] `git status` → confirm conflicts limited to `resume/{experience_parser,generator,docx_builder}.py`.

## Step 5 — Resolve the 3 resume conflicts (re-apply intent, not just text)

- [ ] **`resume/experience_parser.py`** — take allfixes's SSOT structure, then re-add projects:
      add `"projects": "PROJECTS"` to `EXPERIENCE_SECTIONS` and `"projects": "Projects"` to `CORPUS_LABELS`.
- [ ] **`resume/generator.py`** — take allfixes's `corpus = experience_corpus(experience)` + import;
      KEEP relaunch's `RESUME_TOOL` schema + `_INSTRUCTIONS` verbatim; drop the inline `### Projects`
      line (now delivered via `CORPUS_LABELS`).
- [ ] **`resume/docx_builder.py`** — base on relaunch (newer, fuller ATS overhaul); cherry-pick
      allfixes's `_split_cover_letter` (RESUME-4) into `build_cover_letter_docx`. **Default decision:**
      keep relaunch's bold title-concat (deliberate ATS-styling choice); note for Alex to revisit vs
      allfixes's title-on-own-line.
- [ ] `git add` the 3 files; do NOT commit yet (verify first).

## Step 6 — Verify the merge

- [ ] `py -m pytest -q` → expect ≥ 290 passing (allfixes's RESUME-1/4/6 tests must still pass with the
      projects re-add). Fix any regression before committing.
- [ ] `git commit` the merge (default merge message + trailers).

## Step 7 — Fold T4 status-history (the one unique delegate feature)

Source: worktree `…__delegates/delegate-20260617-194221-9d6dd2/wt` (uncommitted; 0 commits). Adds a
`status_history` table + transition logging in `update_job` (absent from allfixes).

- [ ] Capture the diff: `git -C "…/delegate-20260617-194221-9d6dd2/wt" diff` (+ list untracked test).
- [ ] Re-apply onto `harden/phase0`: add the `status_history` table/CREATE + `user_version` bump, and
      the old→new logging inside the POST-merge `update_job` (allfixes rewrote `tracker/db.py` — port
      the hunk by intent, don't patch blindly). Bring its test file.
- [ ] `py -m pytest -q` green → commit: `feat(tracker): status_history transition log (folds delegate T4)`.

## Step 8 — Remaining-open critical not in allfixes: C1 recurrence guard

allfixes did NOT close the C1 recurrence path (`gui._new_project` auto-copies the active resume; no
contact-name warning).

- [ ] Make GUI new-project resume-copy OPT-IN (don't default-copy the active resume into a fresh campaign).
- [ ] Add a parse/startup warning when `experience.md` `contact_name()` ≠ the project owner.
- [ ] Add/extend a test for the opt-in default; `py -m pytest -q` green → commit:
      `fix(gui): C1 — opt-in resume copy + owner-mismatch warning`.

## Step 9 — Prune superseded branches + worktrees

6 delegate branches are superseded by allfixes (T1/T2/T3 + 3×FEEDS-1); each is a worktree with 0 commits.

- [ ] For each of the 6 (NOT the T4 one — already folded): `git worktree remove --force <wt>` then
      `git branch -D <branch>`.
- [ ] Remove the now-merged `claude-allfixes` worktree (`E:/ClaudeWork/zag0005-allfixes`) +
      `git worktree prune`. Keep the `claude-allfixes` branch ref until master is updated + pushed.
- [ ] `git worktree list` → only the main worktree remains.

## Step 10 — Land on master + push (GATED)

- [ ] `git switch master` → `git merge --ff-only harden/phase0` (master is exactly base, so this FFs).
- [ ] `py -m pytest -q` on master → ≥ 290.
- [ ] **GATE:** only if Alex confirmed repo PRIVATE → `git push origin master`.
- [ ] Post-push: delete the merged `claude-allfixes` branch; leave `origin/main` orphan alone (Alex
      decides rename/retire separately — unrelated history, do NOT merge).

## Done criteria

`master` fast-forwarded, `py -m pytest -q` ≥ 290, only the main worktree remains, relaunch + T4 + C1
guard preserved, working tree clean. Then Phase 1 (data folder + preferences) gets its own TDD plan.
