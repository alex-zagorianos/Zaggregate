"""Native window chrome for desktop mode (Windows): the Z icon in the title
bar/taskbar and caption colors that follow the app theme, so the native frame
blends into the page instead of sitting on it as a stock white bar.

Pure ctypes — no new dependencies, no tkinter (this package must stay
importable headless; the caption hexes are pinned here instead of imported
from ui.theme, whose module-level ``import tkinter`` would break the webui
tk-free guarantee — a test asserts the pins stay equal to the palette).

Every entry point is best-effort: off Windows, with a 0/None hwnd, or on any
Win32 failure it returns False / no-ops. Losing the chrome must never cost the
window itself.
"""
from __future__ import annotations

import ctypes
import sys
import time
from pathlib import Path

_IS_WIN = sys.platform == "win32"

#: Explicit AppUserModelID so dev runs (`py -m webui --desktop`) get their own
#: taskbar identity + this window's icon instead of python.exe's.
APP_ID = "G90.Zaggregate"

#: Window title as passed to webview.create_window — FindWindowW key.
WINDOW_TITLE = "Zaggregate"

# Caption bar (bg, title-text) per mode — pinned copies of ui/theme.py
# _LIGHT/_DARK "WINDOW" + "INK" (see module docstring for why not imported).
_CAPTION = {
    False: ("#f4f3ee", "#16191f"),   # light: Aegean Paper
    True:  ("#13171d", "#e7eaef"),   # dark: Aegean Night
}

# DWM window attributes (dwmapi.h). 20 needs Win10 20H1+; 19 is the pre-20H1
# private value tried as a fallback. 35/36 are Win11-only — on Win10
# DwmSetWindowAttribute just returns a failing HRESULT (no exception) and the
# bar stays default-colored with immersive dark still applied.
_DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_CAPTION_COLOR = 35
_DWMWA_TEXT_COLOR = 36

_WM_SETICON = 0x0080
_ICON_SMALL, _ICON_BIG = 0, 1
_IMAGE_ICON = 1
_LR_LOADFROMFILE = 0x0010

_SWP_FLAGS = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020  # NOSIZE|NOMOVE|NOZORDER|NOACTIVATE|FRAMECHANGED


def _colorref(hex_color: str) -> int:
    """``#rrggbb`` -> Win32 COLORREF (``0x00BBGGRR``)."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (b << 16) | (g << 8) | r


def icon_path() -> Path:
    """The committed .ico — ``data_static/zaggregate.ico`` in a source checkout,
    ``<_MEIPASS>/data_static/zaggregate.ico`` frozen (app.spec bundles
    data_static already)."""
    meipass = getattr(sys, "_MEIPASS", None)
    base = Path(meipass) if meipass else Path(__file__).resolve().parents[1]
    return base / "data_static" / "zaggregate.ico"


def set_app_user_model_id(app_id: str = APP_ID) -> bool:
    """Give the process its own taskbar identity (dev runs otherwise group under
    python.exe and show its icon regardless of WM_SETICON)."""
    if not _IS_WIN:
        return False
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        return True
    except Exception:  # noqa: BLE001 — chrome is never worth a crash
        return False


def find_window(title: str = WINDOW_TITLE, *, retries: int = 20,
                delay: float = 0.05) -> int:
    """Top-level window handle by exact title (0 = not found). Retries briefly:
    callers fire on pywebview's ``shown`` event, but the native frame can lag a
    beat behind it."""
    if not _IS_WIN:
        return 0
    try:
        user32 = ctypes.windll.user32
        user32.FindWindowW.restype = ctypes.c_void_p
        user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        for _ in range(max(1, retries)):
            hwnd = user32.FindWindowW(None, title)
            if hwnd:
                return int(hwnd)
            time.sleep(delay)
    except Exception:  # noqa: BLE001
        pass
    return 0


def apply_icon(hwnd: int, ico: Path | None = None) -> bool:
    """Set the title-bar/Alt-Tab/taskbar icon from the committed .ico (the exe
    resource icon only covers Explorer; a WinForms-hosted window still needs
    WM_SETICON — and dev runs have no exe resource at all)."""
    ico = ico or icon_path()
    if not (_IS_WIN and hwnd) or not Path(ico).is_file():
        return False
    try:
        user32 = ctypes.windll.user32
        user32.LoadImageW.restype = ctypes.c_void_p
        user32.LoadImageW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p,
                                      ctypes.c_uint, ctypes.c_int,
                                      ctypes.c_int, ctypes.c_uint]
        user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                        ctypes.c_void_p, ctypes.c_void_p]
        applied = False
        for which, size in ((_ICON_SMALL, 16), (_ICON_BIG, 32)):
            h = user32.LoadImageW(None, str(ico), _IMAGE_ICON, size, size,
                                  _LR_LOADFROMFILE)
            if h:
                user32.SendMessageW(hwnd, _WM_SETICON, which, h)
                applied = True
        return applied
    except Exception:  # noqa: BLE001
        return False


def apply_caption(hwnd: int, *, dark: bool) -> bool:
    """Color the native caption to the app's own background/ink for ``dark``
    (immersive dark mode + Win11 exact caption/text colors), then nudge a
    frame redraw so a live theme toggle repaints immediately."""
    if not (_IS_WIN and hwnd):
        return False
    try:
        dwm = ctypes.windll.dwmapi
        dwm.DwmSetWindowAttribute.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                              ctypes.c_void_p, ctypes.c_uint]
        val = ctypes.c_int(1 if dark else 0)
        rc = dwm.DwmSetWindowAttribute(
            hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(val), ctypes.sizeof(val))
        if rc != 0:  # pre-20H1 Win10 fallback attribute
            dwm.DwmSetWindowAttribute(
                hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE_OLD,
                ctypes.byref(val), ctypes.sizeof(val))

        bar_hex, text_hex = _CAPTION[bool(dark)]
        for attr, hexc in ((_DWMWA_CAPTION_COLOR, bar_hex),
                           (_DWMWA_TEXT_COLOR, text_hex)):
            c = ctypes.c_uint(_colorref(hexc))
            dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(c),
                                      ctypes.sizeof(c))

        user32 = ctypes.windll.user32
        user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                        ctypes.c_int, ctypes.c_int,
                                        ctypes.c_int, ctypes.c_int,
                                        ctypes.c_uint]
        user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, _SWP_FLAGS)
        return True
    except Exception:  # noqa: BLE001
        return False


def apply_chrome(*, dark: bool) -> bool:
    """Icon + caption in one call (used at window start and on theme toggles).
    Returns True if a window was found and the caption was applied."""
    hwnd = find_window()
    if not hwnd:
        return False
    apply_icon(hwnd)
    return apply_caption(hwnd, dark=dark)


class ThemeBridge:
    """pywebview ``js_api`` — the frontend calls
    ``window.pywebview.api.set_theme("dark"|"light")`` when the user toggles
    theme so the native caption follows instantly. Unknown values are treated
    as light. Browser mode has no bridge; theme.tsx guards on its absence."""

    def set_theme(self, mode) -> bool:  # noqa: ANN001 — JS sends a plain string
        try:
            return apply_chrome(dark=(mode == "dark"))
        except Exception:  # noqa: BLE001
            return False
