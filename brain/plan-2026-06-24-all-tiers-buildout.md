# Plan — All-Tiers Buildout (2026-06-24)

Build out the full competitive-analysis roadmap (Tiers 1–3) from the 2026 market research
(`brain/` workflow output; full feature digest at `E:\ClaudeWork\_jobscout_features_digest.md`).
Autonomous run; decisions logged in `buildout-log-2026-06-24.md`.

**Invariants (all features):** local-first / private · no required API key (clipboard bridge
stays the default) · **never auto-apply** · honest 0–100 score (new signals are
view-level, never rescored) · additive/back-compat · tkinter-feasible · every change tested ·
suite green before commit. Python cmd: `py`. Active project: `applied-ai`.

## Architecture strategy

`gui.py` (2,463 lines) is touched by almost every UI feature → the merge bottleneck. So:

- **Parallelize NEW, file-disjoint modules** (new files don't conflict): `match/ghost.py`,
  `tracker/analytics.py`, `match/skillgap.py`, `match/comp.py`, contacts DB layer, etc. — built
  by delegated workflow agents, each TDD'd.
- **Serialize SHARED-file edits** inline: `gui.py`, `ui/theme.py`, `match/scorer.py`,
  `tracker/db.py`, `ui/settings.py`, `ui/help.py`, `daily_run.py`, `config.py`. One coherent pass
  per batch; I keep control.
- **Verify (full suite) + commit per cluster.** Never leave master broken.

## Build order (batches)

- **Batch 0 — engine modules (parallel):** scorer structured-breakdown return; `match/ghost.py`;
  `tracker/analytics.py`; `match/skillgap.py`; `match/comp.py`; `tracker/db` followups_due query;
  inbox_health restore/daily helper. All new/disjoint → delegate in parallel. (Unblocks the GUI.)
- **Batch 1 — Tier 1 GUI + plumbing (serial inline):** T1.1–T1.7.
- **Batch 2 — Tier 2 (mixed):** T2.8–T2.13.
- **Batch 3 — Tier 3 (mixed):** T3.14–T3.28.
- Each Tier closes with: full suite green, brain/index update, commit.

---

## Tier 1 — high-impact / low-effort (surface what exists)

### T1.1 Dead-link prune → daily run + GUI button + undo

- **Files:** `daily_run.py` (call `inbox_health.prune_inbox` after freshness, logged count),
  `scrape/inbox_health.py` (add `dry_run` already there; add soft "link unverified" mark for
  un-probeable), `gui.py` InboxTab ("Clean dead links (preview)" → dry-run → confirm → prune),
  `tests/`.
- **Approach:** reuse the prune built this session. GUI button runs `prune_inbox(dry_run=True)`,
  shows count, confirms, then real prune. daily_run gets a capped/threaded pass.
- **Tests:** daily_run calls prune (monkeypatched); GUI action wiring (headless-guarded).

### T1.2 "Why this matches you" + structured score breakdown

- **Files:** `match/scorer.py` (return a structured breakdown dict alongside the `notes` string —
  `score_breakdown(job) -> {title,skills,salary,location,recency,penalties,confidence}`),
  `claude_bridge.py` (keep `flags` separate from `rationale` in the surfaced data),
  `gui.py` detail pane (InboxTab/SearchTab/TopPicksTab), `tests/`.
- **Approach:** pure presentation of data already produced; scorer gains a dict return (string
  kept for CSV/back-compat). Detail pane renders full `why`, red-flag chips, and the breakdown.
- **Tests:** `score_breakdown` returns correct components/confidence; flags parsed separately.

### T1.3 Score/Fit color bands in tables

- **Files:** `ui/theme.py` (band→color map + `score_band(n)` helper, dark-aware),
  `gui.py` (`_render` tags rows/Score cell; Inbox/Search/TopPicks), `tests/`.
- **Approach:** Treeview per-row `tag_configure(foreground=)` + leading ● glyph in Score column
  (ttk can't bg a single cell). Compose with existing zebra tags.
- **Tests:** `score_band` thresholds (≥70 green / 45–69 amber / <45 grey); theme has both modes.

### T1.4 Real empty states

- **Files:** `ui/theme.py` (`empty_state(parent, text, button_text, command)` factory),
  `gui.py` (Inbox/Search/ApplyQueue/Tracker; distinguish "no data" vs "filtered to zero"),
  `tests/`.
- **Approach:** generalize TopPicksTab's existing empty-label pattern.
- **Tests:** factory builds; band between empty vs filtered-empty chosen correctly (logic helper).

### T1.5 Follow-up & deadline reminder queue

- **Files:** `tracker/db.py` (`followups_due(within_days, include_deadlines) -> rows`; generalize
  `count_followups_due`), `gui.py` (a "Due" view/dialog: urgency sort, open / mark-contacted /
  snooze +7d), `tests/`.
- **Tests:** `followups_due` returns the right rows by date/status; snooze updates `follow_up_date`.

### T1.6 In-app API-key entry (Settings → "Connect your AI")

- **Files:** `ui/settings.py` (get/set key → `config.SECRETS_DIR/<name>`), `config.py` (shared
  resolver `resolve_secret(name)`), `search/serpapi_client.py` + `ranker.py` + `resume/service.py`
  (consult the resolver; `api_available()` honors it), `gui.py` (masked Settings dialog + "Test
  key" + "you don't need this" note), `tests/`.
- **Tests:** resolver reads env → SECRETS_DIR file → none; `api_available()` flips on a written
  key; masked write/read round-trip.

### T1.7 "What leaves this computer" privacy panel

- **Files:** `ui/help.py` (`PRIVACY` content built from the enumerated sources in `config.py`;
  plain-English egress list), `gui.py` (Help menu entry), `tests/`.
- **Approach:** static, accurate, source-by-source list (kept in sync with config). Optional later:
  a local egress log.
- **Tests:** privacy content names every active network source; no false "nothing leaves" claim.

---

## Tier 2 — high-impact / medium-effort

### T2.8 Funnel & response-rate analytics (Huntr-style, local)

- **Files:** `tracker/analytics.py` (NEW — read `status_history` + `applications`: stage counts,
  conversion %, response rate, median time-to-response/rejection, per-source/per-lane breakdown),
  `gui.py` (Stats sub-view on Tracker or a dialog: count cards + a Treeview table, NO charting
  lib), `mcp_server.py` (`funnel_stats` tool), `tests/`.
- **Tests:** analytics math on a seeded status_history (conversions, medians, low-n labeling).

### T2.9 Ghost / stale-job likelihood (offline) + badge

- **Files:** `match/ghost.py` (NEW — pure logic: posting-age + repost-count + missing-salary +
  aggregator-only-not-on-careers-board + evergreen-title → 0–100 ghost score, abstains on unknown),
  `search/freshness.py` (a `seen_count`/`first_seen` rolling helper for repost detection),
  `gui.py` (badge next to score + "Hide stale" filter), `tests/` (+ lift-style abstention test).
- **Approach:** soft badge/sort only (D7). Extras key like Top Picks (schema-free).
- **Tests:** ghost score rises with age/repost/missing-salary; neutral/abstain on unknown data.

### T2.10 Skill-gap "you have / job wants" panel

- **Files:** `match/skillgap.py` (NEW or extend `scorer`: return matched terms + salient JD terms
  not in the user's skills; stoplist), `resume/generator.py` (accept "emphasize these" missing
  terms), `gui.py` (two-column panel on job detail), `tests/`.
- **Tests:** matched/missing extraction with a stoplist; resume prompt includes missing terms.

### T2.11 SmartScreen / Defender survival kit (distributable)

- **Files:** `build_package.py` (FIRST-RUN.txt + README coaching + `launch.bat`; commented
  `signtool` stub — D3), `tests/` (package contents assertion where feasible).
- **Tests:** built package includes FIRST-RUN.txt + launch.bat; README has Unblock copy.

### T2.12 Onboarding success + first-run "find my first jobs"

- **Files:** `ui/setup_wizard.py` (confirmation screen + `on_finish` search hook),
  `gui.py` (`_after_setup` fires the existing Search path; lands on populated Inbox/Search),
  `tests/`.
- **Tests:** wizard finish triggers the on_finish callback with the entered config.

### T2.13 Browser-extension capture-on-submit (opt-in)

- **Files:** `browser_ext/content.js` + `popup.js` ("Mark Applied" → POST to receiver),
  `scrape/browser_receiver.py` (`/applied` → `db.add_job(status='applied', date_applied, JD)`),
  opt-in toggle in settings, `tests/` (receiver route).
- **Note:** extension JS is hard to unit-test; test the receiver route. Selector-rot caveat. May
  land partial; flagged in log.

---

## Tier 3 — fill-out & polish

- **T3.14 Comp transparency column.** Extract salary parsing from `scorer._SALARY_RE` into
  `match/comp.py`; normalize JSON-LD/Adzuna/description ranges onto `JobResult.salary_min/max`;
  GUI comp column + "meets my floor" filter. Tests.
- **T3.15 Posting-age + reposted freshness display.** Age column + "reposted N×" from
  `freshness` history (overlaps T2.9 plumbing). Tests.
- **T3.16 Company size/funding facets.** Inbox facets from `board_count` bands + registry
  `industries`; persist to `ui_settings.json`. Tests.
- **T3.17 Stronger `job_key` dedup.** Fold `_deduplicate` by `job_key` (keep URL-distinctness);
  characterization test first + coverage lift-gate.
- **T3.18 Contacts / referral CRM.** `contacts` table (SCHEMA_VERSION bump, D5); JobDialog
  subpanel + "has contact" badge. Manual capture only (no LinkedIn scrape). Tests.
- **T3.19 Saved filter presets / quick-filter chips.** Save/load the Inbox filter vars via
  `ui/settings.py`; preset chips + built-ins. Tests.
- **T3.20 Review-mode card triage.** One-job card view reusing t/d/o + advance logic. Tests.
- **T3.21 Onboarding checklist on Guide.** Live checklist (prefs set ✓ / searched ✓ / tracked ✓ /
  resume ✓ / daily ◻) with per-row "Do this". Tests.
- **T3.22 Periodic CDX discovery refresh.** Weekly cadence call to `discover.funnel.run_funnel`
  from `daily_run` (additive, throttled). Tests.
- **T3.23 Keyboard-shortcut hints.** Append "(T/D/O)" to labels + a footer legend on Inbox/Top
  Picks. Tiny.
- **T3.24 Backup / restore data folder.** Help → zip/unzip `USER_DATA_DIR` (exclude/ warn on
  secrets). Tests.
- **T3.25 Confidence indicator on score.** Expose scorer `present/5`; plain-English "limited info"
  badge (folds into the T1.2 detail pane). Tests.
- **T3.26 Company grouping/collapse (optional).** Treeview parent/child mode toggle. Lower prio.
- **T3.27 Tunable scoring weights (advanced).** Weights from config (per-profile like
  exclude_titles); Advanced settings + rescore preview. Footgun-guarded, default tuned. **See Q2.**
- **T3.28 Auto-update check (opt-in).** Help → ping a GitHub Releases JSON; disclosed in the
  privacy panel; off by default. Needs Alex's release discipline. Tests.

### Deferred (specced, NOT built — D2)

- **Full web/Tauri reskin** — capture polish via tkinter (bands/chips/cards/empty states) first.
- **Email-derived auto-status (Gmail OAuth)** — too heavy for the EXE; interim = paste an email
  into the AI bridge.
- **JobSpy wrapper** (optional consumer-board source) — only if maintenance pain warrants; build
  behind try/except import + lift-gate. (Low priority; build if time remains.)
- **Semantic embedding re-rank** (D6) — numpy pseudo-embedding, optional, off by default; last.

## Success criteria

- Suite green throughout (start: 586); each feature adds tests.
- Every Tier 1–2 feature landed, committed locally (push held), brain + index updated.
- Tier 3 landed as far as the unattended run reliably allows; remainder left clearly specced here
  with status in the buildout log.
- No regression to the honest score, the no-auto-apply spine, or the local-first/private model.

## Risks

- `gui.py` god-file → serialized edits (mitigated by strategy above).
- Delegated agents on a constrained backend → verify everything; fall back to inline.
- Long unattended run → commit per verified cluster so progress is durable; log blockers.
