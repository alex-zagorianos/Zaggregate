"""Branded top bar: the "Zaggregate" wordmark + a bold "Z" zag mark + a hairline.

Gives the app a visual identity (it previously had no hero/branding). Pure
classic-tk chrome colored from ui.theme, so the host destroys + rebuilds it on a
light/dark switch to pick up the new palette."""
import tkinter as tk

from ui import theme


def _draw_zmark(canvas, x, y, s, color):
    """A bold zig-zag 'Z' (the 'zag' of Zaggregate) inside the s×s box at (x, y)."""
    canvas.delete("all")
    pad = s * 0.18
    x0, y0, x1, y1 = x + pad, y + pad, x + s - pad, y + s - pad
    w = max(2, int(round(s * 0.12)))
    canvas.create_line(x0, y0, x1, y0, fill=color, width=w, capstyle="round")   # top bar
    canvas.create_line(x1, y0, x0, y1, fill=color, width=w, capstyle="round")   # diagonal
    canvas.create_line(x0, y1, x1, y1, fill=color, width=w, capstyle="round")   # bottom bar


def build_top_bar(parent, before=None):
    """Pack a branded bar (+ bottom hairline) at the top of `parent`, above the
    `before` widget if given. Returns the wrap frame; destroy it to remove both the
    bar and its hairline together. `wrap.actions` is an empty right-side frame the
    caller may pack global controls into."""
    wrap = tk.Frame(parent, bg=theme.SURFACE)
    if before is not None:
        wrap.pack(fill="x", side="top", before=before)
    else:
        wrap.pack(fill="x", side="top")

    bar = tk.Frame(wrap, bg=theme.SURFACE)
    bar.pack(fill="x", side="top")

    sz = 32
    mark = tk.Canvas(bar, width=sz, height=sz, bg=theme.SURFACE,
                     highlightthickness=0, bd=0)
    mark.pack(side="left", padx=(14, 8), pady=(8, 8))
    _draw_zmark(mark, 0, 0, sz, theme.ACCENT)

    # Wordmark: "Zag" (accent) + "gregate" (ink) — the personal-brand root, emphasized.
    tk.Label(bar, text="Zag", bg=theme.SURFACE, fg=theme.ACCENT,
             font=theme.FONT_DISPLAY, padx=0, bd=0).pack(side="left", padx=0, pady=(4, 8))
    tk.Label(bar, text="gregate", bg=theme.SURFACE, fg=theme.INK,
             font=theme.FONT_DISPLAY, padx=0, bd=0).pack(side="left", padx=0, pady=(4, 8))
    tk.Label(bar, text="   find · rank · apply", bg=theme.SURFACE,
             fg=theme.MUTED, font=theme.FONT_SM).pack(side="left", pady=(4, 8))

    wrap.actions = tk.Frame(bar, bg=theme.SURFACE)
    wrap.actions.pack(side="right", padx=(0, 12))

    tk.Frame(wrap, bg=theme.BORDER, height=1).pack(fill="x", side="top")
    return wrap
