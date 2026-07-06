"""Best-effort Windows balloon/toast notifications via raw ctypes — zero extra
dependencies (no winrt/winsdk/win10toast/plyer) and importable headlessly (no
tk import, so daily_run.py / the web backend can call it without pulling in the
GUI stack).

Mechanism: a minimal message-only window (``HWND_MESSAGE`` parent, so it never
shows on screen) registers a notification-area icon via ``Shell_NotifyIconW``
with ``NIF_INFO`` (the balloon/toast text), then a daemon thread removes the
icon (``NIM_DELETE``) after a short delay — fire-and-forget from the caller's
point of view. Uses the app icon (``data_static/zaggregate.ico``) via
``LoadImageW`` when present, else falls back to a system default icon.

Public API: :func:`notify`. Never raises — any failure (off-Windows, a Win32
call failing, a missing icon) is swallowed and reported via a ``False`` return
so a notification hiccup can never affect the caller (e.g. a scheduled daily
run)."""
from __future__ import annotations

import sys
import threading
from pathlib import Path

# High-fit threshold used by the daily-run trigger (see daily_run.py). Kept
# here (not in config.py) since it's this feature's own constant and this
# module is the natural home for notification-related tuning.
HIGH_FIT_MIN = 80

# How long the notification icon stays in the tray before NIM_DELETE removes it.
_LIFETIME_SECONDS = 10.0

# Shell_NotifyIconW wchar buffer limits (NOTIFYICONDATAW): szTip is 128 wchars,
# szInfoTitle is 64 wchars (63 usable + NUL), szInfo is 256 wchars (255 usable
# + NUL). We truncate defensively to the documented usable lengths.
_TITLE_MAX = 63
_BODY_MAX = 255

_ICON_PATH = Path(__file__).resolve().parent / "data_static" / "zaggregate.ico"


def _truncate(text: str, limit: int) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    # Leave room for an ellipsis so truncation is visible, not just a hard cut.
    if limit <= 1:
        return text[:limit]
    return text[: limit - 1] + "…"


def _notify_impl(title: str, body: str) -> bool:
    """The actual Win32 sequence. Raises on any failure; the public ``notify``
    wraps this so callers never see an exception. Split out so tests can
    monkeypatch just this half (or stub ctypes) without touching the public
    fire-and-forget contract."""
    if sys.platform != "win32":
        return False

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32
    kernel32 = ctypes.windll.kernel32

    NIF_INFO = 0x00000010
    NIF_ICON = 0x00000002
    NIF_TIP = 0x00000004
    NIM_ADD = 0x00000000
    NIM_DELETE = 0x00000002
    NIIF_INFO = 0x00000001
    WS_OVERLAPPED = 0x00000000
    HWND_MESSAGE = -3
    IMAGE_ICON = 1
    LR_LOADFROMFILE = 0x00000010
    LR_DEFAULTSIZE = 0x00000040
    LR_DEFAULTCOLOR = 0x00000000
    IDI_APPLICATION = 32512
    CW_USEDEFAULT = 0x80000000 - (1 << 32)  # signed INT_MIN as CW_USEDEFAULT

    # LRESULT/LPARAM are LONG_PTR: 64-bit on Win64. Declaring the callback's
    # return as c_long (32-bit) or leaving DefWindowProcW's argtypes to the
    # ctypes c_int default overflows on real 64-bit lparams ("argument 4:
    # OverflowError" spam from the message pump — caught by live smoke, the
    # stubbed tests can't see it). wintypes.LPARAM is the pointer-sized
    # signed type on both arches, so it stands in for LRESULT too.
    LRESULT = wintypes.LPARAM
    WNDPROC = ctypes.WINFUNCTYPE(
        LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
    )
    user32.DefWindowProcW.restype = LRESULT
    user32.DefWindowProcW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
    ]

    def _wndproc(hwnd, msg, wparam, lparam):
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    _wndproc_ref = WNDPROC(_wndproc)

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [
            ("style", wintypes.UINT),
            ("lpfnWndProc", WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON),
            ("hCursor", wintypes.HANDLE),
            ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
        ]

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("hWnd", wintypes.HWND),
            ("uID", wintypes.UINT),
            ("uFlags", wintypes.UINT),
            ("uCallbackMessage", wintypes.UINT),
            ("hIcon", wintypes.HICON),
            ("szTip", wintypes.WCHAR * 128),
            ("dwState", wintypes.DWORD),
            ("dwStateMask", wintypes.DWORD),
            ("szInfo", wintypes.WCHAR * 256),
            ("uTimeoutOrVersion", wintypes.UINT),
            ("szInfoTitle", wintypes.WCHAR * 64),
            ("dwInfoFlags", wintypes.DWORD),
            ("guidItem", ctypes.c_byte * 16),
            ("hBalloonIcon", wintypes.HICON),
        ]

    hinstance = kernel32.GetModuleHandleW(None)

    class_name = "ZaggregateNotifyWndClass"
    wndclass = WNDCLASSW()
    wndclass.style = 0
    wndclass.lpfnWndProc = _wndproc_ref
    wndclass.cbClsExtra = 0
    wndclass.cbWndExtra = 0
    wndclass.hInstance = hinstance
    wndclass.hIcon = None
    wndclass.hCursor = None
    wndclass.hbrBackground = None
    wndclass.lpszMenuName = None
    wndclass.lpszClassName = class_name

    # RegisterClassW fails (0) if the class already exists from a prior call in
    # this process — that's fine, we just reuse the class name.
    user32.RegisterClassW(ctypes.byref(wndclass))

    hwnd = user32.CreateWindowExW(
        0, class_name, "ZaggregateNotify", WS_OVERLAPPED,
        CW_USEDEFAULT, CW_USEDEFAULT, CW_USEDEFAULT, CW_USEDEFAULT,
        wintypes.HWND(HWND_MESSAGE), None, hinstance, None,
    )
    if not hwnd:
        return False

    hicon = None
    if _ICON_PATH.exists():
        hicon = user32.LoadImageW(
            None, str(_ICON_PATH), IMAGE_ICON, 0, 0,
            LR_LOADFROMFILE | LR_DEFAULTSIZE,
        )
    if not hicon:
        hicon = user32.LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION))

    nid = NOTIFYICONDATAW()
    nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
    nid.hWnd = hwnd
    nid.uID = 1
    nid.uFlags = NIF_INFO | NIF_TIP | (NIF_ICON if hicon else 0)
    nid.uCallbackMessage = 0
    nid.hIcon = hicon or 0
    nid.szTip = _truncate(title, _TITLE_MAX)
    nid.szInfo = _truncate(body, _BODY_MAX)
    nid.szInfoTitle = _truncate(title, _TITLE_MAX)
    nid.dwInfoFlags = NIIF_INFO

    added = shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
    if not added:
        user32.DestroyWindow(hwnd)
        return False

    def _cleanup():
        try:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
        except Exception:
            pass
        try:
            user32.DestroyWindow(hwnd)
        except Exception:
            pass

    timer = threading.Timer(_LIFETIME_SECONDS, _cleanup)
    timer.daemon = True
    timer.start()
    return True


def notify(title: str, body: str) -> bool:
    """Best-effort Windows tray notification. Fire-and-forget: returns True if
    the balloon/toast was successfully raised, False otherwise (off-Windows,
    any Win32 failure, or an unexpected error) — never raises."""
    try:
        return bool(_notify_impl(title or "", body or ""))
    except Exception:
        return False


def high_fit_message(rows: list) -> tuple[int, str] | None:
    """Build the (count, message) pair for a daily run's new high-fit matches,
    or None if there's nothing to announce.

    ``rows`` is any iterable of objects with ``.score``, ``.title``,
    ``.company`` (daily_run's scored ``Result``/``JobResult`` instances) that
    the caller has ALREADY filtered down to "new this run" (e.g. via
    ``r.is_new``) — this function only applies the score threshold and picks
    the top row for the message; it does not re-derive "new" itself, so no
    historical DB re-query is needed."""
    qualifying = [r for r in rows if (getattr(r, "score", None) or 0) >= HIGH_FIT_MIN]
    if not qualifying:
        return None
    top = max(qualifying, key=lambda r: getattr(r, "score", 0) or 0)
    n = len(qualifying)
    plural = "es" if n != 1 else ""
    msg = (f"{n} new high-fit match{plural} — top: {top.title} at "
           f"{top.company} ({top.score})")
    return n, msg


def notify_high_fit_matches(rows: list) -> bool:
    """Fire the 'new high-fit matches' notification for a daily run, if any of
    ``rows`` (already filtered to this run's new rows) qualify. Returns False
    (without calling ``notify``) when nothing qualifies — the same never-raise
    guarantee as :func:`notify` applies transitively."""
    built = high_fit_message(rows)
    if built is None:
        return False
    _n, msg = built
    return notify("Zaggregate", msg)
