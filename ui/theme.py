"""Clean, light, modern Tk/ttk theme + reusable UI helpers.

Single source of truth for colors, fonts, themed-button factories, header bars,
tip strips, zebra striping, and tooltips, so every tab looks consistent and a
non-technical user always sees the same affordances.

Call `apply_theme(root)` once, right after creating the root window and before
building any widgets, so the ttk styles exist when tabs are constructed.
"""
import tkinter as tk
from tkinter import ttk

# ── Palette ───────────────────────────────────────────────────────────────────
# Two modes share one set of color *names*; `set_mode()` swaps which values those
# module-level names hold, so every `theme.X` reference (and every helper below)
# picks up the active mode the next time a widget is built. Light is the default.
_LIGHT = {
    "WINDOW":  "#eef1f5",  # app background behind the tabs
    "SURFACE": "#ffffff",  # cards, headers, tables
    "ALT":     "#f5f7fa",  # zebra rows / subtle fills / table headings
    "INK":     "#1f2937",  # primary text
    "MUTED":   "#6b7280",  # secondary text
    "FAINT":   "#9aa3af",  # hints / disabled text
    "BORDER":  "#e3e7ec",  # separators, input borders, hairlines
    "ACCENT":      "#3b5bdb",  # the single brand accent
    "ACCENT_DK":   "#2f49b0",  # hover / pressed
    "ACCENT_FG":   "#ffffff",  # text on an accent button
    "ACCENT_TINT": "#e7ecff",  # selected table row / soft accent fill
    "ACCENT_DIM":  "#b9c2ea",  # disabled accent
    "ACCENT_FG_DIM": "#eef1ff",  # text on a disabled accent button
    "SUCCESS":     "#2e7d32",
    "SUCCESS_DK":  "#1b5e20",
    "SUCCESS_DIM": "#a9c8aa",   # disabled success button
    "DANGER":      "#c62828",
    "DANGER_DK":   "#a01b1b",
    "WARN":        "#e65100",
    "TOOLTIP_BG":  "#1f2937",   # dark chip on a light app
    "TOOLTIP_FG":  "#ffffff",
}
_DARK = {
    "WINDOW":  "#1a1d23",  # near-black, not pure black (less eye strain)
    "SURFACE": "#242830",  # raised cards / tables / headers
    "ALT":     "#2c313b",  # zebra rows / subtle fills / table headings
    "INK":     "#e7eaf0",  # primary text
    "MUTED":   "#9aa3b2",  # secondary text
    "FAINT":   "#6b7484",  # hints / disabled text
    "BORDER":  "#3a414d",  # separators, input borders, hairlines
    "ACCENT":      "#5c7cfa",  # brighter blue reads better on dark
    "ACCENT_DK":   "#4c6ef5",
    "ACCENT_FG":   "#ffffff",
    "ACCENT_TINT": "#2b3553",  # selected table row (muted blue, dark)
    "ACCENT_DIM":  "#3a4566",
    "ACCENT_FG_DIM": "#c8d0e8",
    "SUCCESS":     "#4caf50",
    "SUCCESS_DK":  "#3d8b40",
    "SUCCESS_DIM": "#3a5a3b",
    "DANGER":      "#ef5350",
    "DANGER_DK":   "#c62828",
    "WARN":        "#ffa726",
    "TOOLTIP_BG":  "#3a414d",  # light chip on a dark app
    "TOOLTIP_FG":  "#e7eaf0",
}
_PALETTES = {"light": _LIGHT, "dark": _DARK}

# Per-mode foreground colors for the Job-Tracker status badges. The light set is
# the original saturated palette; the dark set is brightened so each status stays
# legible on the dark rows (the saturated darks would otherwise go muddy).
_STATUS_BADGE = {
    "light": {"interested": "#1565c0", "applied": "#2e7d32",
              "phone_screen": "#e65100", "interview": "#bf360c",
              "offer": "#1b5e20", "rejected": "#c62828", "withdrawn": "#757575"},
    "dark":  {"interested": "#5b9bf0", "applied": "#66bb6a",
              "phone_screen": "#ffa726", "interview": "#ff8a65",
              "offer": "#81c784", "rejected": "#ef5350", "withdrawn": "#9aa3b2"},
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
FONT      = ("Segoe UI", 10)
FONT_SM   = ("Segoe UI", 9)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_H1   = ("Segoe UI", 15, "bold")
FONT_H2   = ("Segoe UI", 11, "bold")
FONT_MONO = ("Consolas", 10)


def apply_theme(root, mode=None) -> ttk.Style:
    """Install the modern ttk styling on `root` for the given mode ('light' or
    'dark'; None keeps the current mode). Safe to call repeatedly — re-calling
    with a new mode restyles every ttk widget live. Returns the ttk.Style."""
    if mode is not None:
        set_mode(mode)
    style = ttk.Style(root)
    try:
        style.theme_use("clam")   # the most style-able built-in base theme
    except tk.TclError:
        pass
    root.configure(bg=WINDOW)

    # Base
    style.configure(".", background=WINDOW, foreground=INK, font=FONT)
    style.configure("TFrame", background=WINDOW)
    style.configure("Surface.TFrame", background=SURFACE)
    style.configure("Card.TFrame", background=SURFACE)
    style.configure("TLabel", background=WINDOW, foreground=INK, font=FONT)
    style.configure("Muted.TLabel", background=WINDOW, foreground=MUTED, font=FONT_SM)
    style.configure("H1.TLabel", background=SURFACE, foreground=INK, font=FONT_H1)
    style.configure("H2.TLabel", background=WINDOW, foreground=INK, font=FONT_H2)

    # Buttons — flat, padded; one accent per context, ghost for the rest.
    style.configure("TButton", font=FONT_SM, padding=(12, 6),
                    relief="flat", borderwidth=0)
    style.configure("Ghost.TButton", background=SURFACE, foreground=INK,
                    bordercolor=BORDER, borderwidth=1, relief="solid")
    style.map("Ghost.TButton",
              background=[("active", ALT), ("pressed", BORDER), ("disabled", ALT)],
              foreground=[("disabled", FAINT)],
              bordercolor=[("active", ACCENT)])
    style.configure("Accent.TButton", background=ACCENT, foreground=ACCENT_FG,
                    bordercolor=ACCENT, borderwidth=0)
    style.map("Accent.TButton",
              background=[("active", ACCENT_DK), ("pressed", ACCENT_DK),
                          ("disabled", ACCENT_DIM)],
              foreground=[("disabled", ACCENT_FG_DIM)])
    style.configure("Success.TButton", background=SUCCESS, foreground="#ffffff",
                    borderwidth=0)
    style.map("Success.TButton",
              background=[("active", SUCCESS_DK), ("pressed", SUCCESS_DK),
                          ("disabled", SUCCESS_DIM)])
    style.configure("Danger.TButton", background=DANGER, foreground="#ffffff",
                    borderwidth=0)
    style.map("Danger.TButton",
              background=[("active", DANGER_DK), ("pressed", DANGER_DK)])

    # Inputs
    style.configure("TEntry", fieldbackground=SURFACE, foreground=INK,
                    bordercolor=BORDER, borderwidth=1, relief="solid", padding=4)
    style.map("TEntry", bordercolor=[("focus", ACCENT)])
    style.configure("TCombobox", fieldbackground=SURFACE, background=SURFACE,
                    foreground=INK, bordercolor=BORDER, borderwidth=1,
                    arrowcolor=INK, padding=3)
    style.map("TCombobox",
              fieldbackground=[("readonly", SURFACE)],
              background=[("readonly", SURFACE)],
              bordercolor=[("focus", ACCENT)])
    style.configure("TCheckbutton", background=WINDOW, foreground=INK, font=FONT_SM)
    style.map("TCheckbutton", background=[("active", WINDOW)])

    # Treeview (tables)
    style.configure("Treeview", background=SURFACE, fieldbackground=SURFACE,
                    foreground=INK, rowheight=27, borderwidth=0, font=FONT_SM)
    style.configure("Treeview.Heading", background=ALT, foreground=MUTED,
                    font=FONT_BOLD, relief="flat", padding=(6, 7), borderwidth=0)
    style.map("Treeview.Heading", background=[("active", BORDER)])
    style.map("Treeview",
              background=[("selected", ACCENT_TINT)],
              foreground=[("selected", INK)])

    # Notebook (tab strip)
    style.configure("TNotebook", background=WINDOW, borderwidth=0,
                    tabmargins=(8, 6, 8, 0))
    style.configure("TNotebook.Tab", background=WINDOW, foreground=MUTED,
                    font=FONT_SM, padding=(16, 8), borderwidth=0)
    style.map("TNotebook.Tab",
              background=[("selected", SURFACE)],
              foreground=[("selected", ACCENT)],
              font=[("selected", FONT_BOLD)])

    # Slim light scrollbars
    for orient in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
        style.configure(orient, background=ALT, troughcolor=WINDOW,
                        bordercolor=WINDOW, arrowcolor=MUTED, relief="flat",
                        borderwidth=0)
        style.map(orient, background=[("active", BORDER)])

    # Combobox dropdown list (the popdown) is a plain Tk Listbox that clam never
    # reaches, so without this it stays OS-default white — a glaring white panel
    # in dark mode. The option DB is read when each popdown is realized, so set
    # it here (re-applied on every mode switch; comboboxes rebuild with the tabs).
    root.option_add("*TCombobox*Listbox.background", SURFACE)
    root.option_add("*TCombobox*Listbox.foreground", INK)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", ACCENT_FG)
    root.option_add("*TCombobox*Listbox.font", FONT_SM)

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


def btn(parent, text, command, kind="ghost"):
    """A themed ttk.Button. `kind` is accent (one primary per context),
    ghost (secondary), success, or danger. Caller does the .pack/.grid."""
    return ttk.Button(parent, text=text, command=command,
                      style=_BTN_STYLE.get(kind, "Ghost.TButton"))


def header_bar(parent, title, subtitle=None):
    """A clean light header: accent left-rule, big title, optional subtitle, and
    a bottom hairline. Self-packs at the top of `parent` and returns the bar
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
    bar = tk.Frame(parent, bg=ALT)
    bar.pack(side="top", fill="x")
    tk.Label(bar, text="\N{INFORMATION SOURCE}  " + text, bg=ALT, fg=MUTED,
             font=FONT_SM, anchor="w", justify="left", padx=14, pady=7,
             wraplength=1180).pack(fill="x")
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


def empty_state(parent, text, button_text=None, command=None,
                icon="\N{INBOX TRAY}"):
    """A centered empty-state panel: faint icon + message + optional CTA button.
    Self-contained (the caller does .pack(fill='both', expand=True) and
    .pack_forget()/destroy when data arrives) — mirrors TopPicksTab's empty label
    but generalized with a call-to-action. Returns the frame."""
    frame = tk.Frame(parent, bg=SURFACE)
    inner = tk.Frame(frame, bg=SURFACE)
    inner.place(relx=0.5, rely=0.42, anchor="center")
    tk.Label(inner, text=icon, bg=SURFACE, fg=FAINT,
             font=("Segoe UI", 30)).pack()
    tk.Label(inner, text=text, bg=SURFACE, fg=MUTED, font=FONT, justify="center",
             wraplength=460).pack(pady=(8, 12))
    if button_text and command:
        btn(inner, button_text, command, kind="accent").pack()
    return frame
