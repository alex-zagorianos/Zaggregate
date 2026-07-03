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


def test_top_bar_renders_tools_button_when_menu_given(root):
    # S34: passing a tools_menu adds a discoverable 'Tools' entry point in the bar.
    theme.apply_theme(root, mode="light")
    menu = tk.Menu(root, tearoff=0)
    menu.add_command(label="Do a thing", command=lambda: None)
    wrap = topbar.build_top_bar(root, tools_menu=menu)
    root.update_idletasks()

    def _find_tools(widget):
        for child in widget.winfo_children():
            if isinstance(child, tk.Label) and "Tools" in str(child.cget("text")):
                return child
            found = _find_tools(child)
            if found is not None:
                return found
        return None

    btn = _find_tools(wrap)
    assert btn is not None, "Tools button missing from top bar"
    assert str(btn.cget("bg")) == theme.SURFACE   # topbar-styled, no new color


def test_top_bar_omits_tools_button_without_menu(root):
    # Back-compat: no menu -> no Tools button (the wizard's header bar, etc.).
    theme.apply_theme(root, mode="light")
    wrap = topbar.build_top_bar(root)
    root.update_idletasks()

    def _has_tools(widget):
        for child in widget.winfo_children():
            if isinstance(child, tk.Label) and "Tools" in str(child.cget("text")):
                return True
            if _has_tools(child):
                return True
        return False

    assert not _has_tools(wrap)
