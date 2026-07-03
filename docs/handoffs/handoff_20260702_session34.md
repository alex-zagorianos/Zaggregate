# Handoff — Session 34 (2026-07-02 evening, Fable 5 orchestrating) — LIVE-TEST FIXES + ONBOARDING + PRODUCTION + FIRST PUSH

Alex live-tested the extension (S33 build) in his real Chrome, then batched:
fix what testing found (auto-send "25 vs 50", edisonsmart clip failure, Track
All), onboarding polish (key links, Tools top button, extension walkthrough),
themed title bar + typography, a production/ folder with the exe, and —
explicitly — **commit everything and PUSH to GitHub**. 5 Opus builders +
review fleet. **Suite 2258 → 2312 green (0 failed — the semantic flake is
FIXED, not skipped). PUSHED to origin/master.**

## What live testing found (and the fixes)

- **Extension couldn't load at all** — manifest referenced `icons/` that never
  existed (since v1.5!). Icons generated (serif Z, Aegean blue on badge navy).
- **Auto-send double-fire**: receiver log showed each milestone POSTing twice —
  the S33 delta-clear's residual race resurrected sent batches. Fixed with a
  **sentKeys ledger** (FIFO 600, external_id-else-url): background records keys
  on send; content.js filters every jobs write against it; resurrection
  self-heals. ("25 vs 50": 47 unique rows landed of ~50 browsed — the gap was
  unhydrated virtualized cards + cross-page dupes, not loss.)
- **Degenerate captures**: a title-"T"/company-"C" row (virtualized LinkedIn
  card caught mid-hydration) and trailing-pipe artifacts — sanitized on BOTH
  sides (content.js `sanitizeField` + receiver `_sanitize_field`, min title 3).
- **edisonsmart clip failure** → the site is **Vincere** (agency ATS, hosted
  quick-job-board). NEW `scrape/vincere_scraper.py`: `POST {host}/ajax/
search-jobs` (Laravel `_token` + session dance; 419 without it), whole-board
  fetch + local keyword filter, robots-gated. Detection probes the Vincere
  fingerprint only when a clip would otherwise fall to `direct`. Live-validated:
  edisonsmart resolves → `verified_live`, 214 jobs. Plus the **browser-verified
  direct fallback**: a still-unrecognized careers page with clip evidence saves
  as `direct` + BROWSER_ONLY (honest verdict copy; ToS guard runs FIRST —
  added to clip_board itself).
- **Track All worked** (single-port /track, rows landed) — kept, plus hygiene.
- **Test leaks**: the S33 generic-harvest test wrote its Acme fixture into the
  REAL active project's inbox every suite run (isolation claimed in its
  docstring but absent) — pinned to tmp DB, leaked row purged. Also
  `wait_until_listening` test collided with any live receiver on 5002 → probes
  a guaranteed-free port now.
- **Semantic 4-test flake ROOT-CAUSED** (not skipped): model2vec
  `from_pretrained` defaults `force_download=True` → phones home even for a
  cached model → conftest's socket guard blocks it → swallowed exception
  latched `available()` False for the whole run. The mid-wave global
  `pip install pyinstaller` merely invalidated the HF-cache freshness that had
  been masking it. Fix: `_resolve_source()` resolves the snapshot
  `local_files_only=True` (offline-first, honoring the module's own "no network
  at score time" promise); transient failures no longer latch. Two consecutive
  full runs green.

## Onboarding + chrome (all merged)

- **"Get a free key →" links** everywhere keys appear (wizard, source-keys
  panel, Guide, .env.example) — every URL live-verified; USAJobs/Careerjet
  fixed to the real signup pages; SerpApi/JSearch added.
- **Tools ▾ top-bar button** (same actions as the menubar cascade, built once).
- **Extension walkthrough** in the Guide (numbered: folder → chrome://extensions
  → Developer mode → Load unpacked → pin → capture toggle → popup buttons),
  referenced from the wizard's closing step.
- **Themed Windows title bar**: `ui/titlebar.py`, DWM attrs 20 (+19 fallback) +
  35/36 caption/text colors, root + all Toplevels via a Map-hook, hard no-op
  off-Windows. Verified live both modes on build 26200.
- **Typography**: inline font tuples → theme tokens (FONT_MONO_SM,
  FONT_GUIDE_H1/H2); serif Guide headlines; mono data panes.

## Production folder

`py -3.12 build_package.py --production` → `production/` (gitignored): onedir
exe `JobProgram/JobProgram.exe` (18 MB; internal name kept — renaming orphans
%LOCALAPPDATA% data), `browser_ext/` at top level (the Load-unpacked target),
QUICKSTART.md, README/CHANGES, .env.example, seeded data/. ~101-115 MB.
Docs: `docs/BUILD.md`. Exe smoke-launched clean from the merged tree.
NOTE: rebuild after any merge — the folder is a build artifact of its commit.

## Review fleet (pre-push)

4 dimensions → adversarial verify: **0 confirmed / 1 refuted** (the refuted
SSRF scenario dies on BROWSER_ONLY gating — clipped boards never reach the
daily scraper). Its verifier exposed one real residual, fixed + tested:
`prune_companies` probed browser-only boards (guaranteed-fail streak would
eventually DELETE a user's browser-verified board) — now never probed/pruned.

## State

- **PUSHED**: master → origin/master (~225 commits, S24→S34 era). Pre-push
  scan clean (no secrets; experience.md untracked; only planted test fixtures
  match key patterns). The S29 note stands: experience.md PII remains in OLD
  pushed history — a rewrite is still Alex's call, unchanged by this push.
- Suite 2312 green. All s34 worktrees/branches pruned (only the ancient
  `ZAG0005-wt-12b-qat-t2f` remains).
- Local-only (untracked, deliberate): `.claude/` (machine-specific hooks/
  settings), `CLAUDE.md` — committed? see final commit; `production/`, `dist/`,
  `build/` gitignored.

## Needs Alex

1. **Reload the unpacked extension** (one more time — sentKeys + sanitation +
   the aggregator-guard on Capture-this-job landed after your session).
2. Re-clip edisonsmart from the popup — it should now add as a live Vincere
   board (214 jobs) and appear in careers searches for your field.
3. Relaunch the app (`production/JobProgram/JobProgram.exe` or `py gui.py`) to
   see: themed title bar, Tools ▾ top button, key links, Guide walkthrough.
4. Junk tracker rows from the pre-fix Track All test ("T"/"C", pipe-suffixed)
   are still in test-controls' tracker — delete manually or say the word.
5. GitHub now reflects everything — README/screenshots refresh is a natural
   next step if this repo goes on the resume.
