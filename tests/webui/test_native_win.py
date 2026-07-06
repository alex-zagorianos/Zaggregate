"""webui/native_win.py unit tests — the pure logic (COLORREF math, palette
pins, icon path resolution) plus the no-crash guarantees for the Win32-facing
entry points. No test here creates a real window; hwnd=0 must short-circuit
every native call.
"""
import pytest

from webui import native_win


# ── COLORREF conversion ────────────────────────────────────────────────────────
def test_colorref_is_bgr_packed():
    # '#rrggbb' -> 0x00BBGGRR (Win32 COLORREF byte order).
    assert native_win._colorref("#0d5eaf") == 0xAF5E0D
    assert native_win._colorref("ffffff") == 0xFFFFFF
    assert native_win._colorref("#000000") == 0x000000
    assert native_win._colorref("#16191f") == 0x1F1916


# ── caption palette pins ───────────────────────────────────────────────────────
def test_caption_palette_matches_ui_theme():
    """native_win pins the caption hexes instead of importing ui.theme (whose
    module-level tkinter import would break webui's tk-free rule). This pin
    test is the drift guard: if the Aegean palette changes, update _CAPTION."""
    theme = pytest.importorskip("ui.theme")
    assert native_win._CAPTION[False] == (theme._LIGHT["WINDOW"],
                                          theme._LIGHT["INK"])
    assert native_win._CAPTION[True] == (theme._DARK["WINDOW"],
                                         theme._DARK["INK"])


# ── icon asset ─────────────────────────────────────────────────────────────────
def test_icon_asset_is_committed():
    p = native_win.icon_path()
    assert p.name == "zaggregate.ico"
    assert p.is_file(), "data_static/zaggregate.ico missing — run scripts/make_icon.py"
    # A real multi-size .ico, not a placeholder: ICONDIR magic + several images.
    blob = p.read_bytes()
    assert blob[:4] == b"\x00\x00\x01\x00"
    count = int.from_bytes(blob[4:6], "little")
    assert count >= 4


# ── no-crash guarantees with no window ─────────────────────────────────────────
def test_apply_calls_noop_without_hwnd():
    assert native_win.apply_icon(0) is False
    assert native_win.apply_caption(0, dark=True) is False
    assert native_win.apply_caption(0, dark=False) is False


def test_apply_icon_noop_when_ico_missing(tmp_path):
    # A valid-looking hwnd but a missing file must still be a clean False.
    assert native_win.apply_icon(12345, ico=tmp_path / "nope.ico") is False


def test_apply_chrome_false_when_window_absent(monkeypatch):
    monkeypatch.setattr(native_win, "find_window", lambda *a, **k: 0)
    assert native_win.apply_chrome(dark=True) is False


def test_find_window_returns_zero_for_unknown_title():
    # Single attempt (retries=1) — nothing on this desktop has this title.
    assert native_win.find_window("zg-no-such-window-xyzzy", retries=1) == 0


# ── ThemeBridge (the pywebview js_api) ─────────────────────────────────────────
def test_theme_bridge_maps_modes_to_dark_flag(monkeypatch):
    seen = []
    monkeypatch.setattr(native_win, "apply_chrome",
                        lambda *, dark: seen.append(dark) or True)
    bridge = native_win.ThemeBridge()
    assert bridge.set_theme("dark") is True
    assert bridge.set_theme("light") is True
    assert bridge.set_theme("garbage-from-js") is True   # treated as light
    assert seen == [True, False, False]


def test_theme_bridge_swallows_chrome_errors(monkeypatch):
    def boom(*, dark):
        raise RuntimeError("dwm exploded")
    monkeypatch.setattr(native_win, "apply_chrome", boom)
    assert native_win.ThemeBridge().set_theme("dark") is False
