"""Theme: pure helpers always; ttk styling + widget factories when a display
is available (skipped headlessly)."""
import tkinter as tk
from tkinter import ttk

import pytest

from ui import theme


def test_row_tag_alternates():
    assert theme.row_tag(0) == "oddrow"
    assert theme.row_tag(1) == "evenrow"
    assert theme.row_tag(2) == "oddrow"


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
