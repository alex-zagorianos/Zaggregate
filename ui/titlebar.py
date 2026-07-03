"""Theme the native Windows title bar (caption) to match the app palette.

Windows draws the OS title bar itself; tkinter can't paint it. The Desktop Window
Manager (DWM) exposes per-window attributes that let an app tint the caption:

  * DWMWA_USE_IMMERSIVE_DARK_MODE (20; 19 on early Win10 builds) — flips the
    caption to the dark or light system rendering.
  * DWMWA_CAPTION_COLOR (35) and DWMWA_TEXT_COLOR (36) — set the exact caption
    background / text color (Windows 11 build >= 22000 only).

We apply the app's SURFACE color to the caption and INK to the caption text in
both modes, so the title bar reads as part of the app instead of a bright OS strip
above a dark window.

Everything here is a hard no-op off Windows, on unsupported builds, and under the
headless test suite (no real HWND) — guarded by a platform/build check plus a
blanket try/except, because a themed title bar must never be able to crash the app.
"""
import sys

# DWM attribute ordinals (dwmapi.h).
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19   # Windows 10 builds 17763..18985
_DWMWA_CAPTION_COLOR = 35
_DWMWA_TEXT_COLOR = 36

# Win 11 gained DWMWA_CAPTION_COLOR/_TEXT_COLOR at build 22000.
_WIN11_MIN_BUILD = 22000
# The newer immersive-dark-mode ordinal (20) landed at build 18985.
_DARKMODE_NEW_MIN_BUILD = 18985


def _win_build() -> int:
    """The Windows build number, or 0 when not on Windows / undetectable."""
    if not sys.platform.startswith("win"):
        return 0
    try:
        return int(sys.getwindowsversion().build)   # type: ignore[attr-defined]
    except Exception:
        return 0


def supported() -> bool:
    """True only on a Windows build new enough to theme the caption at all."""
    return _win_build() >= _DARKMODE_NEW_MIN_BUILD


def _hwnd_for(window) -> int:
    """Resolve the real top-level HWND for a Tk window. winfo_id() returns the Tk
    child frame's handle; the OS caption belongs to its parent, so walk up via
    GetParent. Returns 0 on any failure."""
    import ctypes
    try:
        window.update_idletasks()   # ensure the HWND exists before we ask for it
        child = int(window.winfo_id())
    except Exception:
        return 0
    try:
        parent = ctypes.windll.user32.GetParent(child)
        return parent or child
    except Exception:
        return child


def _hex_to_colorref(hex_color: str) -> int:
    """'#rrggbb' -> a Win32 COLORREF (0x00bbggrr). Raises ValueError on bad input."""
    s = hex_color.lstrip("#")
    if len(s) != 6:
        raise ValueError(hex_color)
    r = int(s[0:2], 16)
    g = int(s[2:4], 16)
    b = int(s[4:6], 16)
    return (b << 16) | (g << 8) | r


def _set_attr_int(dwm, hwnd, attr, value) -> bool:
    """DwmSetWindowAttribute(hwnd, attr, &int32, 4). Returns True on S_OK."""
    import ctypes
    val = ctypes.c_int(int(value))
    res = dwm.DwmSetWindowAttribute(
        ctypes.wintypes.HWND(hwnd), ctypes.c_uint(attr),
        ctypes.byref(val), ctypes.sizeof(val))
    return res == 0


def apply_to(window, mode=None) -> bool:
    """Tint `window`'s native title bar to the active theme. `mode` forces
    'light'/'dark'; None reads the theme's current mode. Returns True if at least
    one DWM attribute was set, False when unsupported or on any error (never
    raises). Safe to call repeatedly and on every Toplevel."""
    if not supported():
        return False
    try:
        import ctypes
        import ctypes.wintypes  # noqa: F401  (populates ctypes.wintypes)
        from ui import theme
    except Exception:
        return False

    resolved = mode if mode in ("light", "dark") else theme.current_mode()
    build = _win_build()
    hwnd = _hwnd_for(window)
    if not hwnd:
        return False

    try:
        dwm = ctypes.windll.dwmapi
    except Exception:
        return False

    ok = False
    dark_flag = 1 if resolved == "dark" else 0
    # Immersive dark mode — try the modern ordinal, fall back to the old one on
    # early Win10 builds. Either succeeding counts.
    try:
        if _set_attr_int(dwm, hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE, dark_flag):
            ok = True
        elif _set_attr_int(dwm, hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, dark_flag):
            ok = True
    except Exception:
        pass

    # Exact caption + text colors (Win 11 only). Paint the caption our SURFACE and
    # the text our INK so the bar matches the window body in both modes.
    if build >= _WIN11_MIN_BUILD:
        try:
            caption = _hex_to_colorref(theme.SURFACE)
            text = _hex_to_colorref(theme.INK)
            if _set_attr_int(dwm, hwnd, _DWMWA_CAPTION_COLOR, caption):
                ok = True
            if _set_attr_int(dwm, hwnd, _DWMWA_TEXT_COLOR, text):
                ok = True
        except Exception:
            pass
    return ok


_BIND_TAG = "_titlebar_themed"


def install(root) -> None:
    """Theme `root`'s caption now AND every Toplevel created later, via one class
    binding on <Map> — the central hook so dialogs pick up the themed caption
    without touching each Toplevel construction site. Idempotent; a hard no-op off
    Windows or on unsupported builds. Never raises."""
    if not supported():
        return
    try:
        apply_to(root)
    except Exception:
        pass
    try:
        # Bind on the Toplevel class so any dialog created anywhere gets themed the
        # first time it maps. Guarded per-window (once flag) so we don't re-tint on
        # every map. bind_class survives root rebuilds (it's interpreter-level).
        def _on_map(event):
            w = event.widget
            if getattr(w, _BIND_TAG, False):
                return
            try:
                setattr(w, _BIND_TAG, True)
            except Exception:
                pass
            try:
                apply_to(w)
            except Exception:
                pass

        root.bind_class("Toplevel", "<Map>", _on_map, add="+")
    except Exception:
        pass


def retheme_all(root) -> None:
    """Re-apply the current theme's caption color to `root` and every existing
    Toplevel (used on a live light/dark switch). Best-effort; never raises."""
    if not supported():
        return
    try:
        apply_to(root)
    except Exception:
        pass
    try:
        import tkinter as tk
        for w in root.winfo_children():
            if isinstance(w, tk.Toplevel):
                try:
                    apply_to(w)
                except Exception:
                    pass
    except Exception:
        pass
