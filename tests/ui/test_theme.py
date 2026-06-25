"""Theme: pure helpers always; ttk styling + widget factories when a display
is available (skipped headlessly)."""
import tkinter as tk
from tkinter import ttk

import pytest

from ui import theme


@pytest.fixture(autouse=True)
def _restore_mode():
    # Theme mode is module-global; leave it as we found it for other tests.
    before = theme.current_mode()
    yield
    theme.set_mode(before)


def test_row_tag_alternates():
    assert theme.row_tag(0) == "oddrow"
    assert theme.row_tag(1) == "evenrow"
    assert theme.row_tag(2) == "oddrow"


def test_score_band_thresholds():
    assert theme.score_band(82) == "good"
    assert theme.score_band(70) == "good"
    assert theme.score_band(69) == "mid"
    assert theme.score_band(45) == "mid"
    assert theme.score_band(44) == "low"
    assert theme.score_band(0) == "low"
    assert theme.score_band(-1) == "none"        # unscored
    assert theme.score_band(None) == "none"
    assert theme.score_band("x") == "none"


def test_score_glyph_and_band_color():
    assert theme.score_glyph(90) == theme.BAND_GLYPH["good"]
    assert theme.score_glyph(-1) == ""           # blank when unscored
    # band_color accepts a number or a key, and tracks the active palette
    theme.set_mode("light")
    assert theme.band_color(90) == theme.SUCCESS
    assert theme.band_color("low") == theme.DANGER
    theme.set_mode("dark")
    assert theme.band_color(90) == theme.SUCCESS  # resolves to the dark green


def test_empty_state_builds(_restore_mode=None):
    try:
        root = tk.Tk()
    except tk.TclError:
        import pytest
        pytest.skip("no display")
    try:
        theme.apply_theme(root)
        calls = []
        f = theme.empty_state(root, "Nothing here yet", "Go to Search",
                              lambda: calls.append(1))
        f.pack(fill="both", expand=True)
        root.update_idletasks()
        assert f.winfo_exists()
    finally:
        root.destroy()


def test_modes_swap_palette_and_track_current():
    theme.set_mode("light")
    assert theme.current_mode() == "light"
    light_win = theme.WINDOW
    light_ink = theme.INK
    theme.set_mode("dark")
    assert theme.current_mode() == "dark"
    assert theme.WINDOW != light_win          # background actually changed
    assert theme.INK != light_ink             # text color actually changed
    # Dark really is darker than its text (sanity on the inversion).
    assert theme.WINDOW.lower() < theme.INK.lower()
    # Semantic status colors are rebuilt to point at the active accent/success.
    assert theme.STATUS_COLORS["info"] == theme.ACCENT
    assert theme.STATUS_COLORS["ok"] == theme.SUCCESS


def test_toggle_and_unknown_mode_falls_back_to_light():
    theme.set_mode("light")
    assert theme.toggle_mode() == "dark"
    assert theme.toggle_mode() == "light"
    assert theme.set_mode("chartreuse") == "light"   # unknown -> light


def test_tooltip_colors_present_both_modes():
    for mode in ("light", "dark"):
        theme.set_mode(mode)
        assert theme.TOOLTIP_BG.startswith("#")
        assert theme.TOOLTIP_FG.startswith("#")


def test_status_badge_swaps_by_mode():
    theme.set_mode("light")
    light = dict(theme.STATUS_BADGE)
    theme.set_mode("dark")
    dark = dict(theme.STATUS_BADGE)
    statuses = {"interested", "applied", "phone_screen", "interview",
                "offer", "rejected", "withdrawn"}
    assert set(light) == set(dark) == statuses
    assert light != dark                       # dark badges are brightened
    assert all(v.startswith("#") for v in dark.values())


def test_palette_and_fonts_present():
    for name in ("WINDOW", "SURFACE", "INK", "ACCENT", "BORDER", "MUTED"):
        assert getattr(theme, name).startswith("#")
    assert theme.FONT[0] == "Segoe UI"


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    r.withdraw()
    yield r
    r.destroy()


def test_apply_theme_installs_clam(root):
    style = theme.apply_theme(root)
    assert style.theme_use() == "clam"


def test_apply_theme_dark_restyles_live(root):
    theme.apply_theme(root, mode="dark")
    assert theme.current_mode() == "dark"
    style = ttk.Style(root)
    # The ttk base style now carries the dark window background (restyled live).
    assert style.lookup("TFrame", "background") == theme.WINDOW
    theme.apply_theme(root, mode="light")
    assert style.lookup("TFrame", "background") == theme.WINDOW


def test_button_factory_kinds(root):
    theme.apply_theme(root)
    for kind, want in [("accent", "Accent.TButton"), ("ghost", "Ghost.TButton"),
                       ("success", "Success.TButton"), ("danger", "Danger.TButton")]:
        b = theme.btn(root, kind, lambda: None, kind)
        assert isinstance(b, ttk.Button)
        assert str(b.cget("style")) == want


def test_header_tip_zebra_build(root):
    theme.apply_theme(root)
    theme.header_bar(root, "Title", "subtitle")
    theme.tip_strip(root, "a helpful tip")
    tree = ttk.Treeview(root, columns=("a",), show="headings")
    theme.zebra(tree)
    tree.insert("", "end", values=("x",), tags=(theme.row_tag(0),))
    theme.tip(theme.btn(root, "x", lambda: None), "tooltip text")
    root.update_idletasks()  # forces widget realization; raises on bad options


def test_style_menu_takes_active_palette(root):
    # tk menus ignore ttk styling, so style_menu must paint them per mode.
    theme.apply_theme(root, mode="dark")
    m = theme.style_menu(tk.Menu(root))
    assert str(m.cget("background")) == theme.SURFACE
    assert str(m.cget("foreground")) == theme.INK
    assert str(m.cget("activebackground")) == theme.ACCENT
    theme.apply_theme(root, mode="light")
    m2 = theme.style_menu(tk.Menu(root))
    assert str(m2.cget("background")) == theme.SURFACE   # follows the light palette


def test_combobox_popdown_is_darkened(root):
    # The popdown Listbox isn't a ttk widget; apply_theme must set its colors via
    # the option DB so the dropdown isn't OS-default white in dark mode.
    theme.apply_theme(root, mode="dark")
    cb = ttk.Combobox(root, values=["a", "b"])
    cb.pack()
    root.update_idletasks()
    try:
        popdown = cb.tk.call("ttk::combobox::PopdownWindow", cb)
        bg = cb.tk.call(f"{popdown}.f.l", "cget", "-background")
    except tk.TclError:
        pytest.skip("combobox popdown internals unavailable on this Tk build")
    assert str(bg) == theme.SURFACE
