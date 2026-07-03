"""Modern Tk/ttk theme + reusable UI helpers, built on ttkbootstrap.

Single source of truth for colors, fonts, themed-button factories, header bars,
tip strips, zebra striping, text panes, and tooltips, so every tab looks
consistent and a non-technical user always sees the same affordances.

The visual engine is **ttkbootstrap**: `apply_theme()` installs a flat, modern
ttkbootstrap base theme (cosmo for light, darkly for dark) and then layers the
app's own palette + named styles on top. ttkbootstrap's element layouts are flat
by design, so the old `clam` light/dark bevel — which rendered as jarring white
outlines around every input in dark mode — is gone at the engine level. We keep
full control of the brand palette (the indigo accent, surface elevation) by
overriding colors on top of the base theme; the base only supplies the flat
rendering and sane defaults for anything we don't touch.

Call `apply_theme(root)` once, right after creating the root window and before
building any widgets, so the ttk styles exist when tabs are constructed.
"""
import tkinter as tk
from tkinter import ttk

# Capture the *vanilla* classic-tk widget constructors BEFORE importing
# ttkbootstrap. On import, ttkbootstrap monkeypatches tk.Frame/Label/Text/etc. to
# force-recolor every classic widget to its own flat palette (update_frame_style
# forces bg=theme.bg, update_label_style forces fg/bg, update_text_style forces
# the input colors). That would obliterate this app's hand-painted chrome — the
# accent left-rules, the colored Job-Tracker status badges, the surface-elevation
# step, the score-band label colors — and ignore the explicit colors we pass. We
# only want ttkbootstrap's *ttk* theming (its flat, bevel-free element layouts are
# what kills the old dark-mode white outlines); the classic tk widgets must keep
# OUR colors. So we restore the vanilla constructors right after import.
_TK_CLASSIC = (tk.Frame, tk.Label, tk.Text, tk.Canvas, tk.Listbox, tk.Toplevel,
               tk.Menu, tk.Button, tk.Entry, tk.Checkbutton, tk.Radiobutton,
               tk.Scale, tk.Spinbox, tk.LabelFrame, tk.Scrollbar, tk.Menubutton,
               tk.PanedWindow, tk.Message)
_VANILLA_TK_INIT = {c: c.__init__ for c in _TK_CLASSIC}

import ttkbootstrap as tb
from ttkbootstrap.publisher import Publisher

for _cls, _init in _VANILLA_TK_INIT.items():
    _cls.__init__ = _init

# ── Palette ───────────────────────────────────────────────────────────────────
# Two modes share one set of color *names*; `set_mode()` swaps which values those
# module-level names hold, so every `theme.X` reference (and every helper below)
# picks up the active mode the next time a widget is built. Light is the default.
#
# These are the app's own modern palette (indigo brand + clear surface
# elevation). ttkbootstrap supplies the flat widget *rendering*; these supply the
# *colors* — so the look stays on-brand and consistent between the ttk widgets and
# the hand-painted tk chrome (headers, badges, score glyphs) that read these names.
_LIGHT = {
    "WINDOW":  "#f4f3ee",  # whitewashed paper — app background behind the tabs
    "SURFACE": "#fcfbf8",  # cards, headers, tables
    "ALT":     "#eae8e0",  # zebra rows / subtle fills / table headings
    "INK":     "#16191f",  # primary text (near-black, faint cool)
    "MUTED":   "#565d68",  # secondary text
    "FAINT":   "#8b909a",  # hints / disabled text
    "BORDER":  "#dcdad0",  # separators, input borders, hairlines (soft warm-gray)
    "ACCENT":      "#0d5eaf",  # the single brand accent (Aegean / Greek-flag blue)
    "ACCENT_DK":   "#0a4a8c",  # hover / pressed
    "ACCENT_FG":   "#ffffff",  # text on an accent button
    "ACCENT_TINT": "#e3edf9",  # selected table row / soft accent fill
    "ACCENT_DIM":  "#a7c4e6",  # disabled accent
    "ACCENT_FG_DIM": "#eaf1fb",  # text on a disabled accent button
    "SUCCESS":     "#3f8f5b",
    "SUCCESS_DK":  "#35784c",
    "SUCCESS_DIM": "#b3ccb9",   # disabled success button
    "DANGER":      "#c14a34",
    "DANGER_DK":   "#a63d2a",
    "WARN":        "#cf8a3c",
    "TOOLTIP_BG":  "#16191f",   # dark chip on a light app
    "TOOLTIP_FG":  "#ffffff",
}
_DARK = {
    "WINDOW":  "#13171d",  # deep-sea near-black (faint blue tint, not cool slate)
    "SURFACE": "#1c222b",  # raised cards / tables / headers (clear elevation step)
    "ALT":     "#252c37",  # zebra rows / subtle fills / table headings
    "INK":     "#e7eaef",  # primary text
    "MUTED":   "#98a1af",  # secondary text
    "FAINT":   "#69727f",  # hints / disabled text
    "BORDER":  "#2f3742",  # separators, input borders — subtle, NOT white
    "ACCENT":      "#4a9be0",  # brighter Aegean blue reads better on dark
    "ACCENT_DK":   "#3d86c9",
    "ACCENT_FG":   "#ffffff",
    "ACCENT_TINT": "#21344c",  # selected table row (muted sea blue, dark)
    "ACCENT_DIM":  "#35506e",
    "ACCENT_FG_DIM": "#c6d6e8",
    "SUCCESS":     "#59c07a",
    "SUCCESS_DK":  "#4bb06c",
    "SUCCESS_DIM": "#2f5540",
    "DANGER":      "#e8735a",
    "DANGER_DK":   "#e05a3f",
    "WARN":        "#e5a75a",
    "TOOLTIP_BG":  "#2f3742",  # light chip on a dark app
    "TOOLTIP_FG":  "#e7eaef",
}
_PALETTES = {"light": _LIGHT, "dark": _DARK}

# Which flat ttkbootstrap base theme backs each mode. The base supplies the
# bevel-free element layouts + sane defaults; our palette overrides the colors.
_BASE_THEME = {"light": "cosmo", "dark": "darkly"}

# Per-mode foreground colors for the Job-Tracker status badges. The light set is
# the original saturated palette; the dark set is brightened so each status stays
# legible on the dark rows (the saturated darks would otherwise go muddy).
_STATUS_BADGE = {
    "light": {"interested": "#1565c0", "applied": "#2e7d32",
              "phone_screen": "#e65100", "interview": "#bf360c",
              "offer": "#1b5e20", "accepted": "#00695c",
              "rejected": "#c62828", "withdrawn": "#757575",
              "ghosted": "#8d6e63"},
    "dark":  {"interested": "#5b9bf0", "applied": "#66bb6a",
              "phone_screen": "#ffa726", "interview": "#ff8a65",
              "offer": "#81c784", "accepted": "#4db6ac",
              "rejected": "#ef5350", "withdrawn": "#9aa3b2",
              "ghosted": "#bcaaa4"},
}
_mode = "light"


def set_mode(mode: str) -> str:
    """Point the module-level color names at the given mode's palette ('light' or
    'dark'; unknown falls back to light). Affects widgets built *after* this call;
    pair with apply_theme() (restyles ttk live) + a UI rebuild for tk widgets.
    Returns the resolved mode."""
    global _mode, STATUS_COLORS, STATUS_BADGE
    pal = _PALETTES.get(mode, _LIGHT)
    _mode = "dark" if pal is _DARK else "light"
    globals().update(pal)
    STATUS_COLORS = {"ok": SUCCESS, "work": WARN, "info": ACCENT,
                     "muted": MUTED, "err": DANGER}
    STATUS_BADGE = _STATUS_BADGE[_mode]
    return _mode


def current_mode() -> str:
    return _mode


def toggle_mode() -> str:
    """Flip light<->dark and return the new mode (does not restyle; caller does)."""
    return set_mode("dark" if _mode == "light" else "light")


# Install the default palette so `theme.WINDOW` etc. exist at import time.
set_mode("light")

# ── Fonts (plain tuples; valid before a root exists) ────────────────────────────
# Font families. Bundled OFL fonts (Inter / Fraunces / JetBrains Mono) are a later
# enhancement; for now we resolve to high-quality Windows-native families so the
# editorial serif look ships with zero bundled assets. Tk silently falls back if a
# family is absent, so these are safe on any Windows box.
SANS  = "Segoe UI"   # body / UI
SERIF = "Georgia"    # editorial headlines (built-in Windows transitional serif)
MONO  = "Consolas"   # numerals in tables, code / log panes

FONT       = (SANS, 10)
FONT_SM    = (SANS, 9)
FONT_BOLD  = (SANS, 10, "bold")
FONT_H1    = (SERIF, 19)          # serif headline — the editorial signal
FONT_H2    = (SANS, 11, "bold")
FONT_MONO  = (MONO, 10)
FONT_MONO_SM = (MONO, 9)          # dense mono (Text panes, timelines, code)
FONT_DISPLAY = (SERIF, 26)        # top-bar wordmark / empty-state hero (used in later phases)
FONT_NUM   = (MONO, 9)            # right-aligned score / salary numerals in tables (later phases)

# Guide (in-app help) reader typography — a serif h1 (editorial), a sans h2, and a
# comfortable serif body so the Guide reads like a document, not a settings panel.
# Centralized here so the Guide follows the same font tokens as the rest of the app
# (and a future bundled-serif swap flows through automatically).
FONT_GUIDE_H1 = (SERIF, 17, "bold")
FONT_GUIDE_H2 = (SANS, 12, "bold")

# Spacing scale (8px base grid) + corner radii, consumed by the chrome retune in
# later phases. Additive names — nothing references them yet.
SP = (4, 8, 12, 16, 24, 32)
RADIUS_BTN = 7
RADIUS_CHIP = 6
RADIUS_CARD = 0


def base_theme() -> str:
    """The ttkbootstrap base theme name backing the active mode (for tests/debug)."""
    return _BASE_THEME[_mode]


def apply_theme(root, mode=None) -> ttk.Style:
    """Install the modern ttkbootstrap styling on `root` for the given mode
    ('light' or 'dark'; None keeps the current mode). Safe to call repeatedly —
    re-calling with a new mode restyles every ttk widget live. Returns the Style.

    ttkbootstrap's ``Style`` is a process-wide singleton bound to the root it was
    first built against. The test suite (and a live theme toggle) need a Style that
    tracks the *current* root, so we reset the singleton and rebuild it here against
    the active default root each call — the Tcl-level style state lives on the
    interpreter, so existing widgets still restyle correctly."""
    if mode is not None:
        set_mode(mode)

    # ttkbootstrap keeps a process-wide Style singleton bound to the root it was
    # first built against, plus a Publisher registry of widget subscriptions. Two
    # cases to handle:
    #   • Live toggle (same root): REUSE the existing Style and theme_use() the new
    #     base. theme_use accumulates each theme's builder on that instance, so a
    #     repeated light<->dark flip is safe. (Rebuilding the Style here instead
    #     would land on theme_use's "already a Tcl theme" branch, which skips
    #     populating the *new* instance's _theme_objects -> KeyError on configure.)
    #   • Fresh root (the test suite builds a new Tk per test): the singleton is
    #     bound to a now-destroyed root, so drop stale subscriptions and rebind.
    base = _BASE_THEME[_mode]
    target = root._root()  # the Tk interpreter this root belongs to

    # Drop accumulated widget subscriptions first. On a live toggle the
    # about-to-be-rebuilt tabs still hold combobox subscriptions; theme_use()
    # publishes to every subscriber, and any already-destroyed one crashes ("bad
    # window path name"). The caller rebuilds its tabs right after, so fresh
    # widgets re-subscribe; new comboboxes also style their popdown at
    # construction, not via this publish.
    Publisher.clear_subscribers()

    # ttkbootstrap's Style is a process-wide singleton designed for ONE long-lived
    # root; the app honors that (one root for its whole life). The test suite,
    # though, spins up many short-lived Tk roots. Re-constructing the Style per
    # root re-runs Style.__init__ — including a localization/msgcat init that
    # races against root setup/teardown and fails intermittently. So build the
    # Style ONCE, then for any later root just REBIND it (master/tk) to that
    # root's interpreter and re-apply the theme: theme_use() +
    # _create_ttk_styles_on_theme_change() rebuild every registered style on the
    # new interpreter, and our explicit configure() calls below re-paint our
    # custom styles every call regardless.
    inst = tb.Style.instance
    if inst is None:
        tk._default_root = target
        style = tb.Style(theme=base)
    else:
        try:
            inst.master = target
            inst.tk = target.tk
        except (tk.TclError, AttributeError):
            pass
        style = inst
        style.theme_use(base)
    root.configure(bg=WINDOW)

    # Base — repaint the inherited flat theme with our palette.
    style.configure(".", background=WINDOW, foreground=INK, font=FONT)
    style.configure("TFrame", background=WINDOW)
    style.configure("Surface.TFrame", background=SURFACE)
    style.configure("Card.TFrame", background=SURFACE)
    style.configure("TLabel", background=WINDOW, foreground=INK, font=FONT)
    style.configure("Muted.TLabel", background=WINDOW, foreground=MUTED, font=FONT_SM)
    style.configure("H1.TLabel", background=SURFACE, foreground=INK, font=FONT_H1)
    style.configure("H2.TLabel", background=WINDOW, foreground=INK, font=FONT_H2)

    # Buttons — flat, padded; one accent per context, ghost for the rest.
    style.configure("TButton", font=FONT_SM, padding=(12, 7),
                    relief="flat", borderwidth=0)
    style.configure("Ghost.TButton", background=SURFACE, foreground=INK,
                    bordercolor=BORDER, borderwidth=1, relief="solid",
                    focuscolor=ACCENT)
    style.map("Ghost.TButton",
              background=[("active", ALT), ("pressed", BORDER), ("disabled", SURFACE)],
              foreground=[("disabled", FAINT)],
              bordercolor=[("active", ACCENT), ("focus", ACCENT)])
    style.configure("Accent.TButton", background=ACCENT, foreground=ACCENT_FG,
                    bordercolor=ACCENT, borderwidth=0, focuscolor=ACCENT_FG)
    style.map("Accent.TButton",
              background=[("active", ACCENT_DK), ("pressed", ACCENT_DK),
                          ("disabled", ACCENT_DIM)],
              foreground=[("disabled", ACCENT_FG_DIM)])
    style.configure("Success.TButton", background=SUCCESS, foreground="#ffffff",
                    borderwidth=0, focuscolor="#ffffff")
    style.map("Success.TButton",
              background=[("active", SUCCESS_DK), ("pressed", SUCCESS_DK),
                          ("disabled", SUCCESS_DIM)])
    style.configure("Danger.TButton", background=DANGER, foreground="#ffffff",
                    borderwidth=0, focuscolor="#ffffff")
    style.map("Danger.TButton",
              background=[("active", DANGER_DK), ("pressed", DANGER_DK)])

    # Inputs
    style.configure("TEntry", fieldbackground=SURFACE, foreground=INK,
                    bordercolor=BORDER, borderwidth=1, relief="flat",
                    insertcolor=INK, padding=5)
    style.map("TEntry", bordercolor=[("focus", ACCENT)])
    style.configure("TCombobox", fieldbackground=SURFACE, background=SURFACE,
                    foreground=INK, bordercolor=BORDER, borderwidth=1,
                    arrowcolor=INK, padding=4)
    style.map("TCombobox",
              fieldbackground=[("readonly", SURFACE)],
              background=[("readonly", SURFACE)],
              foreground=[("readonly", INK)],
              bordercolor=[("focus", ACCENT)],
              arrowcolor=[("active", ACCENT)])
    style.configure("TCheckbutton", background=WINDOW, foreground=INK, font=FONT_SM,
                    focuscolor=ACCENT)
    style.map("TCheckbutton",
              background=[("active", WINDOW)],
              indicatorcolor=[("selected", ACCENT)])

    # Treeview (tables)
    style.configure("Treeview", background=SURFACE, fieldbackground=SURFACE,
                    foreground=INK, rowheight=30, borderwidth=0, font=FONT_SM)
    style.configure("Treeview.Heading", background=ALT, foreground=MUTED,
                    font=FONT_BOLD, relief="flat", padding=(8, 8), borderwidth=0)
    style.map("Treeview.Heading", background=[("active", BORDER)])
    style.map("Treeview",
              background=[("selected", ACCENT_TINT)],
              foreground=[("selected", INK)])

    # Notebook (tab strip) — modern, flat, accent on the active tab.
    style.configure("TNotebook", background=WINDOW, borderwidth=0,
                    tabmargins=(8, 6, 8, 0))
    style.configure("TNotebook.Tab", background=WINDOW, foreground=MUTED,
                    font=FONT_SM, padding=(16, 9), borderwidth=0)
    style.map("TNotebook.Tab",
              background=[("selected", SURFACE), ("active", ALT)],
              foreground=[("selected", ACCENT)],
              font=[("selected", FONT_BOLD)])

    # Slim themed scrollbars
    for orient in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
        style.configure(orient, background=ALT, troughcolor=WINDOW,
                        bordercolor=WINDOW, arrowcolor=MUTED, relief="flat",
                        borderwidth=0)
        style.map(orient, background=[("active", BORDER), ("pressed", ACCENT)])

    # Progressbar (used by long-running search/generate flows)
    style.configure("TProgressbar", background=ACCENT, troughcolor=ALT,
                    bordercolor=ALT, borderwidth=0)

    # Combobox dropdown list (the popdown) is a plain Tk Listbox that the ttk
    # theme never reaches, so without this it stays OS-default white — a glaring
    # white panel in dark mode. The option DB is read when each popdown is
    # realized, so set it here (re-applied on every mode switch; comboboxes
    # rebuild with the tabs).
    root.option_add("*TCombobox*Listbox.background", SURFACE)
    root.option_add("*TCombobox*Listbox.foreground", INK)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", ACCENT_FG)
    root.option_add("*TCombobox*Listbox.font", FONT_SM)

    # Rounded button chrome (Pillow 9-slice). Fully guarded — if Pillow is missing
    # or anything fails, buttons stay flat and the theme is otherwise unaffected.
    try:
        from ui import chrome
        chrome.install_rounded_buttons(style, root)
    except Exception:
        pass

    return style


# ── Reusable widget helpers ─────────────────────────────────────────────────────
_BTN_STYLE = {"accent": "Accent.TButton", "ghost": "Ghost.TButton",
              "success": "Success.TButton", "danger": "Danger.TButton"}


def style_menu(menu):
    """Apply the active palette to a tk.Menu (menubar or cascade). Tk menus
    ignore ttk styling, so without this every menu dropdown renders OS-default
    white — jarring in dark mode. Call on each menu, and re-style on mode switch.
    Returns the menu so it chains."""
    menu.configure(bg=SURFACE, fg=INK, activebackground=ACCENT,
                   activeforeground=ACCENT_FG, disabledforeground=FAINT,
                   selectcolor=INK, relief="flat", borderwidth=0)
    return menu


def text_widget(parent, **kw):
    """A themed classic tk.Text pane. Classic tk widgets aren't reached by ttk
    styling, so each one otherwise carries a default ~white focus highlight ring
    — the second source (after clam's old bevels) of dark-mode white outlines.
    This centralizes a flat, themed border: a 1px highlight ring painted in
    BORDER that turns ACCENT on focus. Caller overrides any option via **kw
    (width/height/wrap/font/bg…) and does the .pack/.grid."""
    opts = dict(bg=SURFACE, fg=INK, insertbackground=INK, relief="flat",
                borderwidth=0, highlightthickness=1, highlightbackground=BORDER,
                highlightcolor=ACCENT, font=FONT_SM, wrap="word", padx=10, pady=8)
    opts.update(kw)
    return tk.Text(parent, **opts)


def btn(parent, text, command, kind="ghost"):
    """A themed ttk.Button. `kind` is accent (one primary per context),
    ghost (secondary), success, or danger. Caller does the .pack/.grid."""
    return ttk.Button(parent, text=text, command=command,
                      style=_BTN_STYLE.get(kind, "Ghost.TButton"))


def header_bar(parent, title, subtitle=None):
    """A clean header: accent left-rule, big title, optional subtitle, and a
    bottom hairline. Self-packs at the top of `parent` and returns the bar
    frame so callers can pack right-aligned controls (count labels, + buttons)
    into it with side='right'."""
    outer = tk.Frame(parent, bg=SURFACE)
    outer.pack(side="top", fill="x")
    tk.Frame(outer, bg=ACCENT, width=4).pack(side="left", fill="y")
    inner = tk.Frame(outer, bg=SURFACE)
    inner.pack(side="left", fill="x", expand=True)
    tk.Label(inner, text=title, bg=SURFACE, fg=INK, font=FONT_H1,
             anchor="w").pack(anchor="w", padx=14, pady=((12, 0) if subtitle else 12))
    if subtitle:
        tk.Label(inner, text=subtitle, bg=SURFACE, fg=MUTED, font=FONT_SM,
                 anchor="w").pack(anchor="w", padx=14, pady=(0, 10))
    tk.Frame(parent, bg=BORDER, height=1).pack(side="top", fill="x")
    return outer


def tip_strip(parent, text):
    """A one-line plain-English helper strip under a header. Self-packs."""
    from ui import icons
    bar = tk.Frame(parent, bg=ALT)
    bar.pack(side="top", fill="x")
    row = tk.Frame(bar, bg=ALT)
    row.pack(fill="x")
    tk.Label(row, text=icons.glyph("info"), bg=ALT, fg=ACCENT,
             font=icons.font(11), pady=7).pack(side="left", padx=(14, 6))
    tk.Label(row, text=text, bg=ALT, fg=MUTED, font=FONT_SM, anchor="w",
             justify="left", pady=7, wraplength=1140).pack(side="left", fill="x")
    tk.Frame(parent, bg=BORDER, height=1).pack(side="top", fill="x")
    return bar


def zebra(tree):
    """Configure alternating-row tags on a Treeview. Callers tag inserted rows
    with row_tag(i) so rows alternate SURFACE / ALT."""
    tree.tag_configure("oddrow", background=SURFACE)
    tree.tag_configure("evenrow", background=ALT)


def row_tag(index: int) -> str:
    """Zebra tag for a 0-based row index (pair with zebra())."""
    return "evenrow" if index % 2 else "oddrow"


class Tooltip:
    """Lightweight hover tooltip for any widget. Shows after a short delay,
    hides on leave or click. stdlib-only (a borderless Toplevel)."""

    def __init__(self, widget, text, delay=450):
        self.widget = widget
        self.text = text
        self.delay = delay
        self._after = None
        self._tip = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _e=None):
        self._cancel()
        self._after = self.widget.after(self.delay, self._show)

    def _show(self):
        if self._tip or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 14
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        except tk.TclError:
            return
        self._tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(tw, text=self.text, bg=TOOLTIP_BG, fg=TOOLTIP_FG, font=FONT_SM,
                 padx=8, pady=5, justify="left", wraplength=320).pack()

    def _hide(self, _e=None):
        self._cancel()
        if self._tip:
            self._tip.destroy()
            self._tip = None

    def _cancel(self):
        if self._after:
            try:
                self.widget.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None


def tip(widget, text):
    """Attach a tooltip and return the widget (so it chains in expressions)."""
    Tooltip(widget, text)
    return widget


# ── Score bands (glanceable triage color coding) ────────────────────────────────
# >=70 strong / 45-69 fair / 0-44 weak / <0 unscored. Surfaced as a colored emoji
# circle prepended to the Score (or Fit) table cell: emoji carry their own color,
# so a single cell reads as red/amber/green WITHOUT ttk per-cell styling, and it
# looks identical in light and dark mode.
def score_band(n) -> str:
    """Band key for a 0-100 score/fit value: 'good' | 'mid' | 'low' | 'none'."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "none"
    if n < 0:
        return "none"
    if n >= 70:
        return "good"
    if n >= 45:
        return "mid"
    return "low"


BAND_GLYPH = {"good": "\U0001F7E2", "mid": "\U0001F7E1",  # 🟢 🟡
              "low": "\U0001F534", "none": ""}            # 🔴 (blank when unscored)


def score_glyph(n) -> str:
    """Colored circle for a score/fit value, for the Score column ('' if unscored)."""
    return BAND_GLYPH[score_band(n)]


def band_color(n) -> str:
    """Active-palette color for a score band (for non-table chips/labels). Accepts
    a numeric value or a band key."""
    key = n if n in BAND_GLYPH else score_band(n)
    return {"good": SUCCESS, "mid": WARN, "low": DANGER, "none": FAINT}[key]


def empty_state(parent, text, button_text=None, command=None, icon=None):
    """A centered empty-state panel: faint icon + message + optional CTA button.
    Self-contained (the caller does .pack(fill='both', expand=True) and
    .pack_forget()/destroy when data arrives) — mirrors TopPicksTab's empty label
    but generalized with a call-to-action. Returns the frame.

    `icon=None` uses a native MDL2 line glyph; a caller may still pass a raw string
    (e.g. an emoji), which renders in the normal UI font."""
    from ui import icons
    frame = tk.Frame(parent, bg=SURFACE)
    inner = tk.Frame(frame, bg=SURFACE)
    inner.place(relx=0.5, rely=0.42, anchor="center")
    if icon is None:
        icon_text, icon_font = icons.glyph("empty"), icons.font(30)
    else:
        icon_text, icon_font = icon, ("Segoe UI", 30)
    tk.Label(inner, text=icon_text, bg=SURFACE, fg=FAINT, font=icon_font).pack()
    tk.Label(inner, text=text, bg=SURFACE, fg=MUTED, font=FONT, justify="center",
             wraplength=460).pack(pady=(8, 12))
    if button_text and command:
        btn(inner, button_text, command, kind="accent").pack()
    return frame
