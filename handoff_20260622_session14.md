# Handoff — Session 14 (2026-06-22, Opus 4.8, ultracode)

> A **UI/UX + non-technical-onboarding pass**: crisp clean-light look, in-app Guide/Help,
> per-tab tips, relabeled AI controls, and a first-run Setup wizard. **Committed LOCAL,
> push HELD** (awaiting Alex's eyeball on the look). Output mode: TERSE.

## TL;DR

- New `ui/` package (`theme.py` / `help.py` / `setup_wizard.py`) + heavy `gui.py` integration; `workspace.py`/`preferences.py`/`build_package.py` touched.
- Tests **490 → 510** (`py -m pytest -q`, ~7s; 1 display-guarded skip when headless). Live wizard-walk + full-App construct smokes pass.
- Built **inline** (concentrated in one file + a new package; visual/taste work; prior delegate runs hit the z.ai cap).
- **NOT pushed.** Last pushed HEAD = `228b013`; the UI/UX commit sits on top, local only.

## What shipped

**4 confirmed decisions** (AskUserQuestion): clean light & modern theme · all four help surfaces · relabel (not hide) the AI controls · build a first-run Setup wizard.

- **`ui/theme.py`** — real ttk theme on `clam`: one accent `#3b5bdb`, white surfaces, zebra tables, flat notebook tabs, focus rings. Factories: `apply_theme`, `btn(kind=accent/ghost/success/danger)`, `header_bar`, `tip_strip`, `zebra`/`row_tag`, `Tooltip`/`tip`. Palette repointed in `gui.py` (`DARK=INK`, `BG=WINDOW`, …).
- **`ui/help.py`** — scrollable **Guide** tab from a `GUIDE` list (Welcome → 3 steps → what each tab does → how AI ranking works → Tips/FAQ); Help-menu dialogs (Quick Start / What do the tabs do? / About); `open_data_folder()` reveals `config.USER_DATA_DIR`.
- **`ui/setup_wizard.py`** — first-run wizard. Pure `build_preferences(answers)→{hard,profile_md}` + `_search_config`; `apply()` writes prefs + search config + (if given) `experience.md`, then sets `.onboarded`. 4 screens (welcome / roles+about / where+remote+salary / resume). `maybe_run` (first-run only) / `run` (Help menu, forced).
- **`gui.py`** — `theme.apply_theme(self)`; **menu bar** (File: New Project / Open data folder / Exit · Help: Quick Start / Open the Guide / What do the tabs do? / Run Setup Wizard / Open data folder / About); 6th **❓ Guide** tab; per-tab tip strips; every `tk.Button`→`theme.btn`; zebra-striped Inbox/Search/Queue/Tracker; recolored detail panes + dialogs; first-run wizard auto-launch (`after(120, …)`).
- **Relabeled AI controls** (Inbox + Apply Queue), tooltips on each: Copy Fit Prompt→**"Ask AI to rank these"**, Paste→**"Paste AI ranking"**, Import→**"Load AI results"**, Undo→**"Undo AI ranking"**; merge dropdown shows **"Replace it / Keep the old one / Only fill blanks"** (display→value map feeds `_import_scores` unchanged).

## Adversarial self-review → all 9 findings fixed

5-dimension Workflow (integration / contract / UX / regressions / packaging) → per-finding verify → synthesis. 9 verified real (1 major, 8 minor):

1. **[MAJOR] Wizard never collected the "about" narrative** — the highest-value AI-ranking input, and the generated `preferences.md` literally told the user to write it. Added an optional multi-line box on the roles step; `_cache_step` now caches both about + resume by widget-existence; `_collect()` returns it.
2. **Project-aware preferences (architectural fix)** — `apply()` wrote prefs to the ROOT while config/resume went per-project ⇒ re-running the wizard after creating a project desynced them; `ranker`/`rerank` call `preferences.load()` bare ⇒ same latent **read-side** desync. Added `workspace.preferences_paths(slug)`; routed `apply()` **and** `preferences.load()` through it. No-project common case is byte-identical to before (root).
3. Wizard "Step N of 4" vs "three steps" copy → counter excludes the welcome intro → "Step 1–3 of 3" (subtitle softened too).
4. Skip had no warning → `_on_skip` now confirms (not `_on_close`, so the window still closes freely).
5. Skip/close stranded a new user on an empty Search tab → `_after_setup` now lands on the **Guide** either way (rebuild only on apply).
6. Merge label "if a job is already scored:" → **"if a job already has a Fit grade:"** (Score vs Fit ambiguity).
7. Guide never defined **Fit vs Score** → added an explainer line.
8. Guide overpromised the Inbox "fills automatically" → added a **day-one "starts empty, run a Search first"** note + qualified step 1.
9. README pointed at `JobProgram\data\…` (wrong on read-only installs) + named the stale "Copy fit prompt" button → rewritten to defer to **Help → Open my data folder** and the new button name.

## Tests added (+20 since S13 → 510)

- `tests/ui/` (14, from the build): `test_theme.py` / `test_help.py` / `test_setup_wizard.py`.
- This turn (+6): `test_workspace.py` (`preferences_paths` root + project), `test_preferences.py` (`load()` default follows active project), `test_setup_wizard.py` (about narrative roundtrip; **project-colocation end-to-end** — nothing stranded at root), `test_help.py` (Fit-vs-Score + "starts empty").

## 🟡 Needs Alex (machine / decision only)

1. **Eyeball the look, then push.** The S14 commit is local; `_after_setup`/theme/wizard are visual — a live `py gui.py` is the real check. To see the first-run wizard on a throwaway dir without touching real prefs: `JOBPROGRAM_DATA=<temp> py gui.py`.
2. Carry-over: build the exe (`py build_package.py`); docx title-line decision; WS-3 `batch_id`; per-project scheduler; company remove/edit UI; delete `tracker.db.bak`.

## Follow-up (same session) — dark mode + deepened AI guide

Two more asks, same inline build + adversarial review. **Second local commit on top of `a716f3f`; still unpushed.**

- **Light/Dark switch.** `theme.py`: `_LIGHT`/`_DARK` palettes + `set_mode`/`current_mode`/`toggle_mode` rewrite the module color names; `apply_theme(root, mode=None)` restyles ttk live. New `ui/settings.py` persists the choice (`USER_DATA_DIR/ui_settings.json`, gitignored). gui.py: **View → Dark mode** → `_set_theme()` persists + restyles ttk + `_sync_palette_aliases()` (re-points the legacy `BG/WHITE/INK…` aliases captured at import) + reconfigures root + rebuilds project bar (grouped `self._projbar`, `before=self._nb`) + tabs (`_rebuild_tabs(select_index=…)` keeps the tab). Tracker badges theme-aware (`theme.STATUS_BADGE`); tooltips use `TOOLTIP_BG/FG`. Saved mode applied at startup.
- **Deepened "use it with AI" guide.** help.py GUIDE: "Working with AI — the heart of this app" + "Getting the most out of AI" (Score-vs-Fit, the free clipboard round-trip step-by-step, Export/Load files, rich-profile tips, model/iterate, trust-but-verify/privacy) + new Help → "Getting the most from AI" dialog (`show_ai_help`).
- **Review found + I fixed:** every un-themed `tk.Text` (PasteDialog/ResumeTab/JobDialog notes/AddCompanies) → `bg=SURFACE/fg=INK/insertbackground=INK`; InboxTab filter Source/Size/Find labels + "Unscored only" checkbutton were missing `fg` (black-on-dark) → themed; transient status hex (`#e65100/#2e7d32/#666/#888`) → `theme.WARN/SUCCESS/MUTED`. **Accuracy fix:** AI help wrongly claimed an API key auto-ranks the inbox/daily run — but `rank_via_api` is only reached via `ranker.rank()`, which neither the GUI nor `daily_run` calls. Reworded: the key powers AI **resume/cover generation**; ranking is the free clipboard/file bridge.
- Review note: the Workflow hit the shared z.ai/Anthropic **session cap** mid-run (synthesis + some verifiers cut off) — it still returned 4 verified findings; I completed the color sweep + accuracy check by hand.
- **Tests:** +13 → **522** (`py -m pytest -q`). Live dark-switch smoke green.

## Pointers

- Canonical brain: `brain/project-status.md` (Session 14 + "Session 14 cont." + `## Git` updated).
- `_index.md` status line + Core Documents + Open list updated.
- Memory: `project-job-search`.
- `app.spec` unchanged — the `ui` package is imported at `gui.py` top level, so PyInstaller bundles it automatically.
