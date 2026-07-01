# Spec — "Aegean" UI restyle (make JobScout less bland)

2026-07-01 · Opus + 5-agent research fleet (`wf_9c2b4fe5-8c5`). Goal: give the
tkinter GUI a distinctive, intentional visual identity inspired by Anthropic's
warm-editorial site + the Hermes (Nous) agent-harness poster look + modern
dev-tool restraint (Linear/Raycast/Vercel). **Plan only — awaiting build approval.**

## Locked decisions (Alex, via the taste forks)

| Fork             | Choice                                                                                    |
| ---------------- | ----------------------------------------------------------------------------------------- |
| **Accent**       | **Greek / Aegean blue** (not Anthropic clay) — blue-and-white island identity             |
| **Corners**      | **Hybrid** — buttons/inputs subtly rounded (~7px), tables/panels stay squared             |
| **Ambition**     | **Full P0–P3** — foundations + chrome + rounded components + command palette + line icons |
| **Default mode** | **Keep current** (whatever `uisettings.get_theme()` loads); both palettes reskinned       |

## The identity — "Aegean Paper, one sea-blue accent"

What all three references share (and the actual cure for "bland"): **paper/near-black
base · exactly ONE confident accent · an editorial serif for headlines · mono
reserved for numbers/code · generous 8px whitespace · hairline borders instead of
bevels.** We keep the warm-paper base (whitewashed walls) and make the one accent a
saturated **Greek-flag blue** — deliberately NOT pale "AI-blue"; identity comes from
saturation + serif headlines + a rare terracotta/olive secondary (island rooftops),
never a rainbow of chrome colors.

### Why this is cheap to do

Styling is ~100% centralized in `ui/theme.py`. `gui.py` has **zero raw hex**, only
**5 inline font tuples** (`gui.py:187,247,563,567,599`) + **13 emoji/glyph literals**.
Only other strays: `ui/help.py:345,347` (2 font tuples). Editing the `_LIGHT`/`_DARK`
dicts + `FONT_*` tuples reskins ~95% of the app on its own. `tracker/app.py` (dead
Flask tracker) is OUT of scope.

## Palette

### LIGHT — "Aegean Paper"

```
WINDOW  #f4f3ee   whitewashed paper (app background)
SURFACE #fcfbf8   cards / tables / headers
ALT     #eae8e0   zebra rows / table headings / subtle fill
INK     #16191f   primary text (near-black, faint cool)
MUTED   #565d68   secondary text
FAINT   #8b909a   hints / disabled text
BORDER  #dcdad0   hairlines / separators (soft warm-gray)
ACCENT        #0d5eaf   Aegean / Greek-flag blue — THE one accent
ACCENT_DK     #0a4a8c   hover / pressed
ACCENT_FG     #ffffff
ACCENT_TINT   #e3edf9   selected row / soft blue fill
ACCENT_DIM    #a7c4e6   disabled accent
ACCENT_FG_DIM #eaf1fb
SUCCESS #3f8f5b  SUCCESS_DK #35784c  SUCCESS_DIM #b3ccb9   (olive-leaning green)
DANGER  #c14a34  DANGER_DK  #a63d2a                        (terracotta red)
WARN    #cf8a3c                                            (ochre / rooftop)
TOOLTIP_BG #16191f  TOOLTIP_FG #ffffff
```

### DARK — "Aegean Night"

```
WINDOW  #13171d   deep-sea near-black (faint blue tint, NOT cool slate)
SURFACE #1c222b   raised cards / tables
ALT     #252c37   zebra / heading fill
INK     #e7eaef   primary text
MUTED   #98a1af   secondary
FAINT   #69727f   hints / disabled
BORDER  #2f3742   hairlines
ACCENT        #4a9be0   brighter Aegean blue reads better on dark
ACCENT_DK     #3d86c9
ACCENT_FG     #ffffff
ACCENT_TINT   #21344c   selected row (muted sea blue)
ACCENT_DIM    #35506e
ACCENT_FG_DIM #c6d6e8
SUCCESS #59c07a  SUCCESS_DK #4bb06c  SUCCESS_DIM #2f5540
DANGER  #e8735a  DANGER_DK  #e05a3f
WARN    #e5a75a
TOOLTIP_BG #2f3742  TOOLTIP_FG #e7eaef
```

- **STATUS_BADGE** (`_STATUS_BADGE`, 7 tracker statuses × 2 modes): re-tune to the new
  system — shift `interested` into the Aegean-blue family, keep all 7 distinct + legible
  on both modes (the existing dict is separately legibility-tuned; don't just inherit).
- Base ttkbootstrap themes stay `cosmo`/`darkly` (flat element layouts); our palette
  overrides ride on top exactly as today.

## Typography

Bundle **OFL** fonts (free to redistribute in the exe) under `assets/fonts/`, register
them **per-process at runtime** (no install/admin/restart) via
`ctypes AddFontResourceEx(path, FR_PRIVATE|FR_NOT_ENUM, 0)`; graceful fallback to
Segoe UI / Georgia / Consolas if a family isn't found in `tkfont.families()`.

```
SANS  = "Inter"          → fallback "Segoe UI"    (body / UI)
SERIF = "Fraunces"       → fallback "Georgia"     (editorial headlines)   [or Source Serif 4]
MONO  = "JetBrains Mono" → fallback "Consolas"    (numerals in tables, code/log panes)

FONT        = (SANS, 10)          FONT_SM  = (SANS, 9)     FONT_BOLD = (SANS, 10, "bold")
FONT_H1     = (SERIF, 20)         FONT_H2  = (SANS, 11, "bold")   FONT_MONO = (MONO, 10)
FONT_DISPLAY= (SERIF, 28)   # top-bar wordmark / empty-state hero
FONT_NUM    = (MONO, 9)     # score / salary numerals in Treeviews (right-aligned)
```

Serif for `H1`/display is what flips the read from "generic SaaS" to "editorial."
Mono only on data/code — never body.

## Spacing / radius tokens (new)

```
SP = (4, 8, 12, 16, 24, 32)   # 8px base grid — replace ad-hoc paddings
RADIUS_BTN = 7   RADIUS_CHIP = 6   RADIUS_CARD = 0   # hybrid: controls round, tables square
```

## New modules

- **`ui/fonts.py`** — register bundled TTFs (`AddFontResourceEx` FR_PRIVATE|FR_NOT_ENUM),
  best-effort `RemoveFontResourceEx` at exit; expose resolved `SANS/SERIF/MONO` names with
  fallback detection. Idempotent, root-independent (safe under the test suite's per-test roots).
- **`ui/chrome.py`** — Pillow: supersampled anti-aliased `rounded_rect` PNGs; 9-slice ttk
  **element images** for Accent/Ghost/Success/Danger buttons + `TEntry`/`TCombobox` at
  RADIUS_BTN with real hover/pressed states (the Sun Valley/Forest ttk technique); rounded
  score-chip images. Cache keyed on (mode, size, dpi). **Flat fallback if Pillow absent.**
- **`ui/palette.py`** — Ctrl+K command palette: borderless Toplevel + fuzzy filter over
  (a) all inbox/queue/tracker jobs and (b) app actions (switch tab, run search, toggle dark,
  open guide, new project…). Reuses existing tab/data accessors.
- **`ui/icons.py`** — Lucide SVG→PNG at fixed stroke, tinted to INK/MUTED/ACCENT per mode,
  cached; replaces the 13 emoji/glyphs + score circles + `empty_state`/`tip_strip` glyphs.
  Fallback to current emoji if render deps absent.
- **Top bar** (`ui/topbar.py` or inline in `gui.py`) — the **missing hero**: serif wordmark
  "JobScout" + a hand-drawn-style star/asterisk mark in accent (Canvas-drawn), subtle paper
  bg, right-aligned global controls (project switcher, dark toggle, "⌘K" hint). Above the notebook.
- **`assets/fonts/`**, **`assets/icons/`** — bundled assets; add to `app.spec` `datas`.

## Phases (each independently shippable; suite stays green)

**P0 — Foundations** _(low risk, ~1 file + assets)_: `assets/fonts/` + `ui/fonts.py`;
rewrite `_LIGHT`/`_DARK` → Aegean; add SP/RADIUS tokens; rewrite `FONT_*` + add
`FONT_DISPLAY`/`FONT_NUM`; call font-register before styles in `apply_theme`. → reskins ~95%.
_Files:_ `ui/theme.py`, `ui/fonts.py`(new), `assets/fonts/`(new), tests.

**P1 — Chrome & rhythm** _(`theme.py` + top bar)_: branded top bar above notebook; retune
`apply_theme` ttk styles (8px paddings, Treeview rowheight ~32 + mono numerals column font,
notebook tab weight + accent underline, warm hairlines, accent focus rings, slim scrollbars);
retune `header_bar`(serif title)/`tip_strip`/`empty_state`; fix the 5 `gui.py` + 2 `help.py`
font tuples. _Files:_ `gui.py`, `ui/theme.py`, `ui/help.py`, `ui/topbar.py`(new).

**P2 — Rounded/elevated (hybrid corners)** _(the only real new render code)_: `ui/chrome.py`
9-slice rounded buttons + subtle-round `TEntry`/`TCombobox`; rounded score chips replacing
emoji circles; tables/panels stay squared. Flat fallback if Pillow missing.
_Files:_ `ui/chrome.py`(new), `ui/theme.py`, `gui.py` (score-column chip render).

**P3 — Delight** _(optional cap)_: `ui/palette.py` Ctrl+K palette bound globally; `ui/icons.py`
Lucide set replacing the 13 emoji/glyphs + score/empty/tip icons.
_Files:_ `ui/palette.py`(new), `ui/icons.py`(new), `assets/icons/`(new), `gui.py`.

## Testing / guardrails

- Keep **1222** tests green; add: font fallback (missing family → default), chrome fallback
  (no Pillow → flat), palette filter logic, icon loader fallback, new palette-key/token presence.
- Respect the `ttkbootstrap.Style` **singleton lifecycle** (`apply_theme` rebuilds per-test
  roots): font registration must be idempotent + not require a root.
- **exe:** `app.spec` `datas` += `assets/fonts`, `assets/icons`; add `PIL` hiddenimports if the
  frozen build misses it. Live `py gui.py` sanity check both modes each phase.
- Cache all generated PNGs (per mode+dpi); no per-frame redraw (tkinter has no compositor).

## Risks / notes

- **Font licensing:** Fraunces / Source Serif 4 / Inter / JetBrains Mono are all **OFL** →
  safe to bundle + redistribute in the exe. (Verify each license file ships.)
- **Blue cliché:** mitigated by saturated flag-blue `#0d5eaf` + serif headlines + terracotta
  secondary — not pale azure. Keep the accent to ONE hue in chrome.
- **Warm-paper + blue tension:** paper is neutral-warm (`#f4f3ee`), not yellow cream — pairs cleanly.
- **tkinter ceilings (accepted):** no true animation (fake via `after()` sparingly or skip),
  no OS-titlebar rounding, Combobox popdown stays semi-native, raster chrome regenerates per DPI.
- **Dependency:** P2/P3 need Pillow (+ an SVG→PNG path for icons, e.g. `cairosvg` or pre-rendered
  PNGs to avoid a native dep). Prefer pre-rendered PNG icon assets to keep the exe light.

## Execution approach (recommend)

Per the delegate-buildout default this qualifies, BUT the palette/fonts are **taste-defining**.
Recommend: **build P0 + the top bar inline** (lock the vibe against a live `py gui.py` with
Alex's eye), then **delegate the mechanical P1(rest)/P2/P3 buildout to GLM** under this spec +
Opus verify — or build all inline if Alex prefers. Await Alex's call on inline-vs-delegate.
