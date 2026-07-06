"""Pillow-rendered rounded chrome for ttk: rounded button backgrounds (9-slice
image elements) + small colored score-band chips for a Treeview #0 gutter.

Anti-aliased; degrades to a flat/no-op if Pillow/ImageTk is unavailable. All images
are interpreter-bound and cached per (interpreter, key) so repeated apply_theme()
across the live theme-toggle and the test suite's many short-lived Tk roots neither
crash (idempotent creation + mode-specific element names) nor leak."""
import tkinter as tk

try:
    from PIL import Image, ImageDraw, ImageTk
    _OK = True
except Exception:                                  # Pillow not installed
    _OK = False

from ui import theme


def available():
    return _OK


def _store(widget):
    """Per-root image cache attached to the Tk root, so cached PhotoImages live and
    die with their interpreter. (A module-level dict keyed by id(root) would both
    leak dead interpreters — PhotoImage holds its master alive — and hand a new root
    stale images when CPython reuses a freed id.)"""
    root = widget._root()
    cache = getattr(root, "_chrome_img_cache", None)
    if cache is None:
        cache = {}
        try:
            root._chrome_img_cache = cache
        except (AttributeError, tk.TclError):
            pass
    return cache


def _rr(w, h, rad, fill, outline=None, ss=4):
    """A supersampled, anti-aliased rounded-rect RGBA image."""
    W, H, R = w * ss, h * ss, rad * ss
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle(
        [0, 0, W - 1, H - 1], radius=R, fill=fill, outline=outline,
        width=(ss if outline else 0))
    return im.resize((w, h), Image.LANCZOS)


def _photo(widget, key, w, h, rad, fill, outline=None):
    store = _store(widget)
    if key not in store:
        store[key] = ImageTk.PhotoImage(_rr(w, h, rad, fill, outline), master=widget)
    return store[key]


def install_rounded_buttons(style, root):
    """Give the four button styles rounded 9-slice backgrounds. Idempotent per
    interpreter; element names carry the mode so a live light/dark toggle re-points
    the layout to the correctly-colored images. No-op if Pillow is unavailable."""
    if not _OK:
        return
    R = theme.RADIUS_BTN
    size = 2 * R + 14
    mode = theme.current_mode()
    specs = [
        ("Accent.TButton", theme.ACCENT, theme.ACCENT_DK, theme.ACCENT_DK,
         theme.ACCENT_DIM, theme.ACCENT_FG, theme.ACCENT_FG_DIM, None),
        ("Ghost.TButton", theme.SURFACE, theme.ALT, theme.BORDER,
         theme.SURFACE, theme.INK, theme.FAINT, theme.BORDER),
        ("Success.TButton", theme.SUCCESS, theme.SUCCESS_DK, theme.SUCCESS_DK,
         theme.SUCCESS_DIM, "#ffffff", "#ffffff", None),
        ("Danger.TButton", theme.DANGER, theme.DANGER_DK, theme.DANGER_DK,
         theme.DANGER, "#ffffff", "#ffffff", None),
    ]
    try:
        existing = set(style.element_names())
    except tk.TclError:
        existing = set()
    for name, fill, active, pressed, disabled, fg, fg_dim, outline in specs:
        elem = f"{name}.rr.{mode}"
        if elem not in existing:
            n = _photo(root, f"{name}:{mode}:n", size, size, R, fill, outline)
            a = _photo(root, f"{name}:{mode}:a", size, size, R, active, outline)
            p = _photo(root, f"{name}:{mode}:p", size, size, R, pressed, outline)
            d = _photo(root, f"{name}:{mode}:d", size, size, R, disabled, outline)
            try:
                style.element_create(elem, "image", n, ("pressed", p),
                                     ("active", a), ("disabled", d),
                                     border=R, sticky="nsew", padding=(14, 7))
            except tk.TclError:
                continue   # already created on this interpreter — fine
        style.layout(name, [(elem, {"sticky": "nsew", "children":
                                    [("Button.label", {"sticky": "nsew"})]})])
        style.configure(name, foreground=fg, font=theme.FONT_SM, anchor="center",
                        borderwidth=0)
        style.map(name, foreground=[("disabled", fg_dim)])


_CHIP = (16, 16, 5)   # w, h, radius


def score_chip(widget, n):
    """A small rounded colored chip PhotoImage for a 0-100 score's band
    (good/mid/low), or '' when unscored or Pillow is unavailable ('' clears any
    prior image on a Treeview #0 cell)."""
    if not _OK:
        return ""
    band = theme.score_band(n)
    if band == "none":
        return ""
    w, h, r = _CHIP
    return _photo(widget, f"chip:{band}:{theme.current_mode()}", w, h, r,
                  theme.band_color(band))


def enable_score_chips(tree, width=34):
    """Turn on a left #0 image gutter (sized for a score chip) on a Treeview.
    Pair with score_chip() in the row inserts. No-op if Pillow is unavailable so
    the table keeps its plain numeric score."""
    if not _OK:
        return
    tree.configure(show="tree headings")
    tree.heading("#0", text="")
    tree.column("#0", width=width, minwidth=width, stretch=False, anchor="center")
