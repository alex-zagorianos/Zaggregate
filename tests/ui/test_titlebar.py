"""Themed native title bar (DWM) — pure helpers + guarded no-op behavior.

The DWM calls only run on a real Windows HWND; the suite runs headless, so these
tests exercise the pure color/build helpers and prove apply_to/install/retheme_all
never raise (the whole module must be a hard no-op off Windows and under pytest)."""
import sys

import pytest

from ui import titlebar


def test_hex_to_colorref_orders_bytes_bgr():
    # COLORREF is 0x00bbggrr: pure red -> 0x0000ff, pure blue -> 0xff0000.
    assert titlebar._hex_to_colorref("#ff0000") == 0x0000FF
    assert titlebar._hex_to_colorref("#0000ff") == 0xFF0000
    assert titlebar._hex_to_colorref("#00ff00") == 0x00FF00
    # A real theme surface color round-trips without error.
    assert isinstance(titlebar._hex_to_colorref("#f4f3ee"), int)


def test_hex_to_colorref_rejects_bad_input():
    with pytest.raises(ValueError):
        titlebar._hex_to_colorref("#fff")
    with pytest.raises(ValueError):
        titlebar._hex_to_colorref("nope")


def test_supported_matches_platform():
    # Off Windows it must be False; on Windows it depends on the build number.
    if not sys.platform.startswith("win"):
        assert titlebar.supported() is False
    else:
        assert titlebar.supported() == (titlebar._win_build() >= 18985)


def test_win_build_is_zero_off_windows():
    if not sys.platform.startswith("win"):
        assert titlebar._win_build() == 0
    else:
        assert titlebar._win_build() > 0


def test_apply_to_never_raises_and_returns_bool():
    # A dummy window with no real HWND must not crash the caller.
    class _Dummy:
        def update_idletasks(self):
            pass

        def winfo_id(self):
            return 0

    out = titlebar.apply_to(_Dummy())
    assert out is False   # no HWND -> nothing set


def test_install_and_retheme_are_noop_safe():
    class _Dummy:
        def update_idletasks(self):
            pass

        def winfo_id(self):
            return 0

        def bind_class(self, *_a, **_k):
            raise RuntimeError("should be swallowed")

        def winfo_children(self):
            return []

    # Neither may raise, even when the underlying window misbehaves.
    titlebar.install(_Dummy())
    titlebar.retheme_all(_Dummy())


def test_apply_to_on_real_root_is_guarded():
    # With a real Tk root: on Windows this actually themes the caption; elsewhere
    # it returns False. Either way it must not raise.
    import tkinter as tk
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    try:
        root.withdraw()
        out = titlebar.apply_to(root, mode="dark")
        assert out in (True, False)
        titlebar.install(root)
        titlebar.retheme_all(root)
    finally:
        root.destroy()
