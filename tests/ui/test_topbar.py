"""Top bar: imports cleanly and builds in both palettes, following theme colors."""
import tkinter as tk

import pytest

import gui  # must import cleanly (also covered by test_smoke)
from ui import theme, topbar


@pytest.fixture(autouse=True)
def _restore_mode():
    before = theme.current_mode()
    yield
    theme.set_mode(before)


def test_topbar_module_imports():
    assert hasattr(topbar, "build_top_bar")
    assert gui is not None


@pytest.fixture
def root():
    try:
        r = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    r.withdraw()
    yield r
    r.destroy()


def test_build_top_bar_light(root):
    theme.apply_theme(root, mode="light")
    wrap = topbar.build_top_bar(root)
    root.update_idletasks()
    assert wrap.winfo_exists()
    assert isinstance(wrap.actions, tk.Frame)
    assert str(wrap.cget("bg")) == theme.SURFACE


def test_build_top_bar_dark_follows_palette(root):
    theme.apply_theme(root, mode="dark")
    wrap = topbar.build_top_bar(root)
    root.update_idletasks()
    assert str(wrap.cget("bg")) == theme.SURFACE   # dark SURFACE, not the light one
