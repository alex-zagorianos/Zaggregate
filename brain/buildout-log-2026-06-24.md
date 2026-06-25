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

- 2026-06-24 — Kickoff. Wrote plan + this log. Beginning Batch 0 (new backend modules).
