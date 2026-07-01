# Handoff — Session 28 (2026-07-01, Opus) — UI RESTYLE "Aegean" + rebrand → Zaggregate

**Task (Alex):** "improve the vibe of the app through the UI — like Hermes (agent
harness) + Anthropic's site." Then: new name/logo instead of JobScout; do the full
polish set; verify only UI changed. Terse. Alex **remote / can't live-drive** →
verified visually via headless render previews.

Read-me-first: `brain/spec-2026-07-01-ui-aegean-restyle.md` (design spec).

## Where the work lives (IMPORTANT)

All on branch **`aegean-restyle`**, worktree **`E:\ClaudeWork\ZAG0005-aegean`**, created
off `master`. **`master` + Alex's Session-27 dirty files are UNTOUCHED. 11 commits.
NOTHING merged to master, NOTHING pushed.** Main repo `E:\ClaudeWork\ZAG0005 - Job
Search App` still on `master`.

## Identity — "Aegean Paper, one sea-blue accent"

Warm paper (light) / deep-sea near-black (dark) + ONE Greek/Aegean-blue accent
(`#0d5eaf` light / `#4a9be0` dark) + editorial **serif** headlines + **mono** numerals

- 8px rhythm + hairlines + subtle **7px-rounded** controls. Full palette + rationale in
  the spec. Research came from a 5-agent Workflow (Anthropic / Hermes-Nous / dev-tool
  composite / tkinter-ceiling / current-code) — findings in the spec.

## Delivered (each verified: full suite green + a render preview)

1. **Palette + fonts** (`ui/theme.py`) — Aegean both modes; serif `FONT_H1`/`FONT_DISPLAY`
   (Georgia now — OFL Fraunces/Inter/JBMono bundling DEFERRED, native fallback ships the look);
   `FONT_NUM` mono; `SP`/`RADIUS_*` tokens.
2. **Branded top bar** (`ui/topbar.py`) — bold blue **Z zag mark** + **Zag**(blue)+**gregate**(ink)
   serif wordmark; the app's first hero. Wired in `gui.py` (`_build_topbar`/`_rebuild_topbar`,
   mirrors projectbar `before`-anchor + rebuild-on-toggle).
3. **Ctrl+K command palette** (`ui/palette.py`) — fuzzy launcher over tabs/actions; isolated overlay.
4. **Rounded ttk buttons** (`ui/chrome.py`) — Pillow 9-slice image elements; fully guarded
   (no-op if Pillow absent), idempotent per interpreter, mode-specific element names, **per-root**
   image cache. Wired via one guarded call at the end of `apply_theme`.
5. **Colored score chips** (`ui/chrome.py` + `gui.py` Inbox) — rounded green/amber/red band chip in
   a `#0` gutter, replacing the monochrome emoji dots (Tk 8.6 renders emoji mono). Only Inbox used dots.
6. **Native line icons** (`ui/icons.py`) — Windows **Segoe MDL2 Assets** glyphs (zero bundled
   assets, verified codepoints, emoji fallback); `tip_strip` info circle + `empty_state` glyph.
7. **Rebrand JobScout → Zaggregate** — app UI (wordmark, error dialog, help/privacy) + distributable
   (`build_package.py` zip/folder/README/launcher). **Kept internal `JobProgram` exe/data name**
   (renaming would orphan `%LOCALAPPDATA%\JobProgram`) and the `jobscout` MCP id.

## Method

Opus-plan → **GLM delegate** (cc-delegate) for the mechanical/safe phases (P0 palette, P1 top bar,
command palette) → Opus verify + merge. Fragile visual work (rounded buttons, chips, icons) built
**inline** + render-verified — delegating pixel-craft blind was too risky with no live eyes.
Preview harness: `scratchpad/render_preview.py` (headless Tk + `PIL.ImageGrab`, DPI-aware) → PNG.

## Audit (Alex asked: "only UI changed?") — CLEAN

Diff vs master = `ui/*`, `gui.py`, `tests/*`, `build_package.py` ONLY. **Zero app-logic files**
(scoring/scraping/DB/pipeline byte-identical). Suite **1228–1229 passed** (2–3 display-dependent
skips). Non-app-behavior touches, all transparent: hardened a **pre-existing flaky test**
(`test_db_pragmas::test_close_db_is_a_checkpoint_alias` asserted a SQLite WAL sidecar _file exists_
at 0 B; SQLite deletes it on last-connection close — my UI-tests' GC timing merely exposed it; now
accepts removed-or-0); updated `test_inbox_surfacing` for the chip design; `test_smartscreen_kit` +
`build_package` rebrand; new `test_topbar`/`test_palette`. Also fixed a real bug in my own
`chrome.py` (was caching images by `id(interp)` → id-reuse hazard → per-root cache).

## Gotchas learned (for next time)

- **cc-delegate branches off the repo's current HEAD** → to CHAIN dependent phases, work from an
  integration branch/worktree whose HEAD accumulates prior phases (that's why `aegean-restyle` exists);
  merge each green delegate branch into it before dispatching the next. No `-Sandbox` here (tkinter
  verify needs a Windows display).
- **Write tool strips literal private-use-area chars** (MDL2/emoji) → use `chr(0x…)` or `\N{NAME}`
  escapes. **Verify MDL2 codepoints against the live font** before shipping (probe → PNG) or you ship tofu.
- **Rounded ttk buttons**: `element_create` is process-wide + one-shot → guard with
  `element_names()`, name elements per-mode, keep PhotoImages alive per-root (the test suite spins many
  short-lived roots). A stray module-level image cache leaks dead interpreters + perturbs GC.
- **Tk 8.6 has no color emoji** → colored status needs images (the chips), not glyphs.

## Name decision

**Zaggregate** (Zag + aggregate; coined → IP-clear; describes the app) over Alex's **ZagRecruiter**
(too close to **ZipRecruiter** TM + "recruiter" = employer-side). Logo = bold blue zig-zag "Z".

## Needs Alex

1. **Eyeball live `py gui.py`** (both modes; hover/real-data can't be render-verified remotely) →
   then say the word to **merge `aegean-restyle` → master** (I won't push unless asked).
2. Optional next: extend chips to Top Picks / Apply Queue tables; round the input fields; **bundle the
   OFL fonts** (Fraunces/Inter/JetBrains Mono) to replace Georgia/Segoe/Consolas fallbacks; GC the
   finished `delegate/*` worktrees (`delegate-clean.ps1`).

## State left

Branch `aegean-restyle` @ `E:\ClaudeWork\ZAG0005-aegean`, 11 commits, suite green. `master` +
Session-27 dirty files untouched. `py -3.12`. Output mode: terse. Nothing merged/pushed.
