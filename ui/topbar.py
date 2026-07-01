"""Branded top bar: a serif wordmark + an accent 'star' mark + a hairline rule.

Gives the app a visual identity (it previously had no hero/branding). Pure
classic-tk chrome colored from ui.theme, so the host destroys + rebuilds it on a
light/dark switch to pick up the new palette."""
import math
import tkinter as tk

from ui import theme


def _draw_star(canvas, cx, cy, r, color, points=6):
    """A simple hand-drawn-style asterisk/star mark (N crossing strokes)."""
    canvas.delete("all")
    for i in range(points):
        a = math.pi * i / points
        canvas.create_line(cx - r * math.cos(a), cy - r * math.sin(a),
                            cx + r * math.cos(a), cy + r * math.sin(a),
                            fill=color, width=2, capstyle="round")


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
    star = tk.Canvas(bar, width=sz, height=sz, bg=theme.SURFACE,
                     highlightthickness=0, bd=0)
    star.pack(side="left", padx=(14, 8), pady=(8, 8))
    _draw_star(star, sz / 2, sz / 2, sz / 2 - 5, theme.ACCENT)

    tk.Label(bar, text="JobScout", bg=theme.SURFACE, fg=theme.INK,
             font=theme.FONT_DISPLAY).pack(side="left", pady=(4, 8))
    tk.Label(bar, text="   find · rank · apply", bg=theme.SURFACE,
             fg=theme.MUTED, font=theme.FONT_SM).pack(side="left", pady=(4, 8))

    wrap.actions = tk.Frame(bar, bg=theme.SURFACE)
    wrap.actions.pack(side="right", padx=(0, 12))

    tk.Frame(wrap, bg=theme.BORDER, height=1).pack(fill="x", side="top")
    return wrap
