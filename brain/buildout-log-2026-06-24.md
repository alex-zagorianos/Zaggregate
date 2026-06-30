# Buildout Log — 2026-06-24 (all-tiers, autonomous)

Running log of decisions, progress, and **questions for Alex** (he stepped away; I proceed
with a logged default and he answers on return). Companion to
`plan-2026-06-24-all-tiers-buildout.md`.

---

## Standing defaults I chose (would have asked)

> **D1 — Commit cadence / push.** Commit each _verified_ feature/cluster locally on `master`;
> **do NOT push** (continues the Session 14–16 eyeball-hold). Suite must be green before each
> commit. → Default: **local commits, push held.**

> **D2 — Scope of "all tiers".** Build everything in the competitive roadmap **except** the two
> items the analysis itself marked not-now: the **full web/Tauri reskin** (freezes feature work,
> breaks the layperson-distributable property) and **Gmail-OAuth email auto-status** (heavy
> OAuth for an EXE). Both are specced in the plan as deferred, not built. → Default: **build all
> except reskin + email-OAuth.**

> **D3 — Code-signing cert.** I can't buy/validate an OV cert. The SmartScreen item ships the
> **free coaching layer** (FIRST-RUN.txt + "Unblock" steps + launch.bat); the `signtool` step is
> left as a documented, commented stub in `build_package.py` for Alex. → Default: **coaching layer
> now, signing stub for Alex.**

> **D4 — API key storage.** In-app API-key box writes plaintext to `config.SECRETS_DIR/<name>`
> (mirrors the existing SerpApi pattern), `.gitignored`, with a "stays on this computer" note.
> Acceptable for a single-user local app. → Default: **plaintext in SECRETS_DIR, gitignored.**

> **D5 — New DB surface.** Features needing schema (contacts CRM) use the existing in-place
> `ALTER` + `.bak` upgrade pattern and bump `SCHEMA_VERSION`. Everything else stays schema-free
> via the `extras` JSON convention (like Top Picks / freshness). → Default: **bump only where a
> real table is needed (contacts); extras elsewhere.**

> **D6 — Semantic embedding re-rank.** torch/sentence-transformers are too heavy for the EXE
> (breaks "distributable to dad"). Ship the **numpy char-ngram/TF-IDF pseudo-embedding** variant,
> **off by default**, as a separate optional signal that never changes the honest 0–100 score.
> Never bundle torch. → Default: **numpy pseudo-embedding, optional, off by default.** (Low
> priority; built last or left specced if time-bound.)

> **D7 — Score stays honest.** Every new signal (ghost-likelihood, location, semantic, freshness)
> is a **view-level badge/filter/sort**, never folded into the deterministic 0–100 score — the
> `jobscout-location-filter-design` precedent. → Default: **filter/label, never rescore.**

> **D8 — Delegation mechanism.** Parallelize **new, file-disjoint modules** via Workflow
> subagents; do **shared-file integration** (`gui.py`, `theme.py`, `scorer`, `db`, `settings`,
> `help`, `daily_run`, `config`) **inline + serialized** to avoid god-file merge conflicts.
> Mechanical bundles may go to `cc-delegate → glm`. Every delegated unit is verified (full suite)
> before commit. → Default: **parallel for new modules, serial inline for shared files.**

> **D9 — Verification gate.** No cluster is committed unless `py -m pytest -q` is fully green and
> new behavior has a test. New sources/scorers get a lift-style gate per repo convention.

---

## Open questions parked for Alex

- **Q1:** docx title-line decision is still open from Session 12 (bold-concat vs ATS-split) —
  untouched by this buildout; still yours to call.
- **Q2:** Tunable scoring weights (T3.27) is a power-user footgun. Built behind an "Advanced"
  affordance, defaulting to the tuned 35/25/15/15/10. Confirm you want it user-exposed at all.
- (Append more here as they arise.)

---

## Progress (newest first)

- 2026-06-24 — Kickoff. Wrote plan + this log.
- 2026-06-24 — **Dead-link fixes committed** (`586ac45`): server-rendered Greenhouse URLs +
  inbox liveness prune + repair script. Suite 586.
- 2026-06-24 — **Batch 0 (engine layer) DONE + committed** (`6b56ed1`). 3 new modules built in
  PARALLEL via delegated worktree agents (TDD, reviewed): `match/ghost.py`, `match/skillgap.py`,
  `tracker/analytics.py`. Plus inline helpers: `scorer.score_breakdown`, `theme.score_band`/
  `score_glyph`/`band_color`/`empty_state`, `tracker.followups_due`, `config.read_secret`/
  `write_secret`, `ui.settings` api-key API, `resume.api_available` honors pasted key. **+53 tests,
  suite 639 green.** Worktrees cleaned. master 15 ahead.
  - **Decision D8 refinement:** GUI wiring (gui.py, 2,463 lines) done **inline**, not delegated —
    a single delicate file offers no parallelism and high merge risk; the parallelizable engine
    modules were the real delegation win (done). Reverting to delegation for any _new_ disjoint
    file batches (comp, SmartScreen kit, etc.).
- 2026-06-24 — Beginning Tier-1 GUI wiring inline.
- 2026-06-24 — **Tier 1 COMPLETE + key Tier 2 surfacing.** Commits on master (push HELD):
  - `feat(inbox)` surfacing: **T1.2** score-breakdown + **T1.3** color bands +
    **T2.9** ghost/Hide-stale + **T2.10** skill-gap in the detail pane; **T1.1** Clean-dead-links
    button (threaded) + opt-in daily prune.
  - `feat(gui)` Tools menu: **T1.5** Due queue, **T2.8** funnel analytics, **T1.6** API-key
    Settings; **T1.7** privacy panel (Help).
  - `feat(inbox)` **T1.4** empty states (empty vs filtered-to-zero).
  - `feat(onboarding)` **T2.12** first-search offer on Setup finish.
  - Suite **586 → 648**. master now **19 ahead** of origin.
- 2026-06-24 — **Batch 2 delegated** (parallel worktrees): **T2.11** SmartScreen kit,
  **T3.14** comp module, **T3.18** contacts CRM. (Awaiting completion → review + merge.)

### Status by item

- **DONE:** T1.1 T1.2 T1.3 T1.4 T1.5 T1.6 T1.7 · T2.8 T2.9 T2.10 T2.12 · (engine: ghost,
  skillgap, analytics, score_breakdown, followups_due, secrets/api-key).
- **IN FLIGHT (Batch 2):** T2.11 (SmartScreen), T3.14 (comp), T3.18 (contacts).
- **PENDING (specced in plan):** T2.13 browser-ext capture (hard, partial-only), T3.15 age/repost
  display, T3.16 size/funding facets, T3.17 job_key dedup (held back from delegation — subtle;
  do inline/careful), T3.19 filter presets, T3.20 review-mode card, T3.21 onboarding checklist,
  T3.22 CDX refresh, T3.23 shortcut hints, T3.24 backup/restore, T3.25 confidence badge (folded
  into T1.2), T3.27 tunable weights (see Q2), T3.28 auto-update. Deferred per D2: web reskin,
  email-OAuth.

### New questions for Alex

- **Q3:** daily auto-prune (`prune_inbox_daily`) defaults **off** (re-probes every link each run,
  ~minutes). The GUI "Clean dead links" button + `--prune-inbox` cover it. Want it on by default?

## FINAL STATUS (Session 17 close)

- **Shipped:** all Tier 1 (T1.1–T1.7) · Tier 2 T2.8/T2.9/T2.10/T2.11/T2.12 · Tier 3
  T3.14/T3.18/T3.22/T3.23/T3.24 (T3.25 folded into T1.2). 572 → **682 tests**, **25 commits local**.
- **Batch 2 merge note:** orphan-root worktrees → copied changed files + diff-reviewed the 2 edited
  existing files (build_package.py purely additive; db.py only SCHEMA_VERSION 3→4 + contacts, earlier
  additions intact).
- **Remaining (specced, not built):** T2.13 browser-ext capture · T3.15 age/repost display · T3.16
  size facets · T3.17 job_key dedup (held: subtle — do inline + characterization test) · T3.19 filter
  presets · T3.20 review-mode card · T3.21 onboarding checklist · T3.27 tunable weights (**Q2**) ·
  T3.28 auto-update. **Deferred (D2):** web reskin, email-OAuth.
- **Needs Alex:** eyeball `py gui.py` → `git push` the 25 commits; answer Q1/Q2/Q3; `py
build_package.py` exe build (now ships the SmartScreen kit).
