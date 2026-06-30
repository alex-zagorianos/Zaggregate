# Handoff — Session 16 (2026-06-24, Opus 4.8, ultracode) — wire the latent gaps + mechanical-debt sweep

> A familiarize → fix pass. A fresh 9-reader subsystem audit (parallel Workflow +
> live-suite verify) surfaced latent gaps the per-session handoffs never recorded;
> this session wired/fixed them. Built this session, **committed LOCAL, push still
> HELD** (rides the Session 14/15 eyeball hold). Output mode: TERSE.

## TL;DR

- master `6bf3722` → **+5 commits** (`00f97f0`, `db82cb2`, `5350056`, `b328f00`, `e14d52e`),
  now **11 ahead** of `origin/master`, tree clean. **553 → 572 tests** (`py -m pytest -q`, ~7s).
- Three behavior-changing wire-ups (all confirmed via `AskUserQuestion`) + two cleanups +
  one **GLM-delegated** mechanical bundle. +19 tests, every wire-up additive / lift-safe.
- **Push still held** — same gate as S14/15: eyeball `py gui.py` then push the 11 commits.

## What shipped

1. **JSON-LD wired** (`00f97f0`) — `scrape/jsonld_scraper` was implemented but _orphaned_. Now
   `direct_scraper` folds same-page schema.org/JobPosting JSON-LD into its results (deduped by
   `identity_key` — strictly additive, can't lower coverage); new **`jsonld` ats_type**; shared
   `_fetch_html` keeps the negative-failure cache. (`tests/scrape/test_jsonld_merge.py`, +3)
2. **Discovery funnel unified** (`db82cb2`) — `discover/` had CDX harvest + careers-link + registry
   merge built but only the Brave discoverer was wired in. New **`discover/funnel.run_funnel`**
   combines the CDX + per-domain legs → `merge_discovered` (user-wins, additive-only), reachable as
   `py -m search.cli --discover [--discover-domains acme.com,…] [--discover-limit N]`. Maintenance
   command (hits Common Crawl on demand), mirrors `--prune-companies`. (`tests/discover/test_funnel.py`, +4)
3. **Freshness deltas surfaced** (`5350056`) — `search/freshness` existed but was never called.
   `daily_run` now marks `JobResult.is_new` against a **project-scoped baseline** (`daily:<slug>`;
   manual GUI/CLI searches don't move it), stamps new inbox rows' `extras.new_batch` (schema-free,
   latest-batch-wins like Top Picks), and the GUI gains a **"New only"** Inbox filter. `is_new` is
   transient; `inbox_add_many(new_batch=…)` is opt-in (back-compat). (`tests/test_freshness_wiring.py`, +4)
4. **normalize_url deduped** (`5350056`, same commit) — `tracker/db.normalize_url` was a parity copy
   of `models.normalize_url`; now imported from `models` (verified byte-identical for all inputs, so
   the inbox `norm_url` UNIQUE key is unchanged). Removed the now-unused `urllib.parse` import + local
   `_TRACKING_PARAMS`.
5. **GLM-delegated mechanical bundle** (`b328f00`) — Opus-planned (fully-inlined weak-model-proof plan),
   executed by **cc-delegate → glm-5.2** (green, 19 turns, $0.65), Opus-verified + transferred (files
   disjoint from the inline work):
   - `match/scorer`: `exclude_keywords` now match on **word boundaries** (was substring — "ai"⊂"maintain",
     "remote"⊂"remotely") via the existing `_term_pattern`; size-modifier docstring → its 4 bands.
   - `claude_bridge.to_clipboard`: **cross-platform** (clip / pbcopy / xclip→xsel) so the distributable's
     clipboard bridge works off Windows.
   - `config.ANTHROPIC_MODEL`: **env-overridable** (`os.getenv`), was hardcoded.
   - `requirements.txt` + `app.spec`: dropped **vestigial `datasketch`** (never imported); hardened
     `hiddenimports` via **`collect_submodules`** over the first-party packages (frozen-exe ImportError
     guard for lazily-imported app modules).
   - (`tests/test_exclude_keyword_boundary.py` +3, `test_clipboard_crossplatform.py` +4, `test_config_model_override.py` +1)

`e14d52e` = brain/index docs. **Doc-undercount corrected:** MCP exposes **8** tools (… +
`export_inbox`/`import_scores`), size modifier has **4** bands — both were under-stated in the brain
(no code error).

## Git — 5 local commits, push HELD

```
e14d52e docs: Session 16 — wire latent gaps + mechanical sweep
b328f00 fix: exclude-keyword word boundary, x-platform clipboard, model env, packaging  (GLM)
5350056 feat(freshness): surface jobs new since last run + dedupe normalize_url
db82cb2 feat(discover): unify the discovery funnel behind `cli --discover`
00f97f0 feat(scrape): wire orphaned JSON-LD scraper as an additive fallback
```

On top of `6bf3722` (S15). 11 commits ahead of `origin/master` total (S14/15's 6 + these 5).
Repo private (`git@github.com:alex-zagorianos/Job-Program.git`).

## Build mechanics (durable note)

cc-delegate **worked cleanly this session — no z.ai cap** (contrast Sessions 13–15 where the GLM
executor kept hitting the 5-hour cap / false-green). The reliable recipe held: fully-inlined plan
(exact current code + replacement, "don't read other files"), file-disjoint from the inline clusters,
scoped `Verify: py -m pytest -q`, green → confirming verify → transfer. Worktree GC'd via
`delegate-clean -Apply`. See [[delegate-buildout]].

## 🟡 Needs Alex (machine / decision only)

1. **Eyeball `py gui.py`** — light + dark, Top Picks, and the new **"New only"** Inbox filter — then
   `git push` the 11 local commits.
2. `--discover` grows `companies.json` from Common Crawl on demand — run it when you want fresh boards
   (not in the daily path).
3. Carry-overs unchanged: `py build_package.py` exe build + manual GUI launch; live coverage baseline
   (network run); docx title-line decision.

## Pointers

- Brain: `brain/project-status.md` §"Session 16" + `## Git`. `_index.md` status + handoff pointer.
  Memory: `project-job-search` (Session 16 paragraph).
- The freshness baseline lives under `USER_DATA_DIR/freshness/daily_<slug>.json` (gitignored data dir).
- Audit that surfaced these: 9 parallel subsystem readers + live verify (drift-checked vs the brain).
