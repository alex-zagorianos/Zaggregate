"""Web-UI launcher: ``py -m webui`` (and the ``gui.py --web`` / ``--desktop`` /
frozen-exe flags).

One process = the app (the migration-plan invariant). This starts the SAME Flask
app the browser extension already talks to — ``scrape.browser_receiver.app``, with
the ``webui`` blueprint mounted at import via ``register_webui`` — bound to
loopback only, then presents ``/app`` one of two ways:

* **Browser mode** (default / ``--web``): opens the default browser at ``/app``
  once the socket is listening; the server runs on the MAIN thread (blocks).
* **Desktop mode** (``--desktop``): the server runs on a DAEMON thread and a
  native window (pywebview → Edge WebView2 on Windows) hosts ``/app`` on the
  main thread — no browser chrome, its own taskbar entry, closes like an app.
  Closing the window exits the process (the daemon server dies with it).
  pywebview is imported LAZILY inside the desktop branch; when it is missing
  (stripped install), desktop mode degrades to browser mode with a note rather
  than crashing — the app must always come up.

The tkinter GUI is never imported here, so this path stays fully headless (the
frozen exe gets ``--web``/``--desktop`` for free because the PyInstaller entry is
``gui.py``, which delegates to :func:`main` before creating any Tk window).

Sequence (matches the tk/daily entry points):
1. ``userdata.bootstrap()`` — ensure the data folder exists + is seeded (a fresh
   unzip just works), emit the sync-folder warning if under OneDrive/Dropbox.
2. Pin the active project ONCE for this process (the receiver OWNS the process
   here, like the standalone ``browser_receiver.__main__`` / mcp_server pattern —
   a project switch in another process must not repoint this receiver's writes).
3. Present ``http://127.0.0.1:<PORT_RECEIVER>/app`` per mode (browser open after
   the socket accepts, or the native window whose first load retries internally).
4. Serve until the browser-mode server is interrupted / the desktop window closes.

Security: 127.0.0.1 ONLY (never 0.0.0.0 — documented in browser_receiver). Nothing
new is exposed beyond what the receiver already serves + the origin-gated /api —
desktop mode is the same loopback server in a native window.
"""
from __future__ import annotations

import sys
import threading
import time
import socket
import webbrowser


def _wait_and_open(host: str, port: int, *, open_browser=webbrowser.open,
                   timeout: float = 8.0, sleep=time.sleep,
                   connect=socket.create_connection) -> bool:
    """Poll until the server socket accepts a connection, then open the browser at
    ``/app``. Returns True if it opened (server came up), False on timeout. The
    ``open_browser`` / ``sleep`` / ``connect`` seams are injected so the unit tests
    exercise the logic with NO real browser, socket, or wall-clock wait."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with connect((host, port), timeout=0.25):
                open_browser(f"http://{host}:{port}/app")
                return True
        except OSError:
            sleep(0.15)
    return False


def _serve(app, host: str, port: int) -> None:
    """Run the Flask dev server on the main thread (blocks). Split out so tests can
    patch it (never actually bind a socket under pytest)."""
    app.run(host=host, port=port, debug=False, use_reloader=False)


# Native-window sizing: comfortable for the Inbox split view, resizable, and a
# floor that keeps the filter bar usable. Purely presentational.
_DESKTOP_SIZE = (1360, 900)
_DESKTOP_MIN = (980, 640)


def _run_desktop(app, host: str, port: int, *, serve=None) -> int:
    """Desktop mode: serve on a daemon thread, host ``/app`` in a native pywebview
    window on the main thread (pywebview requires it). Returns the exit code.

    ``private_mode=False`` is REQUIRED: the frontend keeps the theme choice (and
    other view prefs) in localStorage, and pywebview's default private mode wipes
    storage every launch — the app would forget dark mode on every open.

    Falls back to browser mode when pywebview (or its WebView2 backend) is
    unavailable — the server itself must never be the casualty of a missing
    window toolkit.

    ``serve`` defaults to the module-level ``_serve`` resolved at CALL time (not
    def time) so tests that monkeypatch ``wm._serve`` keep working."""
    serve = serve or _serve
    try:
        import webview  # pywebview — lazy: only the desktop branch needs it
    except Exception:  # noqa: BLE001 — any import/backend failure -> fallback
        print("Desktop window unavailable (pywebview not installed) — "
              "opening in your browser instead.")
        return _run_browser(app, host, port, serve=serve)

    server = threading.Thread(target=serve, args=(app, host, port),
                              name="web-server", daemon=True)
    server.start()

    print(f"Zaggregate desktop window on http://{host}:{port}/app "
          f"(close the window to quit)")
    webview.create_window(
        "Zaggregate", f"http://{host}:{port}/app",
        width=_DESKTOP_SIZE[0], height=_DESKTOP_SIZE[1],
        min_size=_DESKTOP_MIN,
    )
    webview.start(private_mode=False)  # blocks until the window is closed
    return 0


def _run_browser(app, host: str, port: int, *, serve=None) -> int:
    """Browser mode: open the default browser once the socket accepts (background
    waiter) and serve on the main thread (blocks until interrupted). ``serve``
    resolves the module-level ``_serve`` at call time (monkeypatch-friendly)."""
    serve = serve or _serve
    opener = threading.Thread(
        target=_wait_and_open, args=(host, port),
        name="web-open-browser", daemon=True)
    opener.start()

    print(f"Zaggregate web UI on http://{host}:{port}/app  (Ctrl+C to stop)")
    try:
        serve(app, host, port)
    except KeyboardInterrupt:
        return 0
    return 0


def main(argv=None) -> int:
    """Bootstrap data, pin the project, and present the web UI on loopback per
    mode (``--desktop`` -> native window, else browser). Blocks until the server
    stops / the window closes; returns a process exit code."""
    argv = list(argv or [])
    # 1. First-run/every-run data bootstrap (fresh unzip just works).
    try:
        import userdata
        userdata.bootstrap()
    except Exception:  # noqa: BLE001 — a bootstrap hiccup must not stop the server
        pass

    from config import PORT_RECEIVER

    # 2. Import the receiver app (webui blueprint mounted at import) + pin once.
    from scrape import browser_receiver as rcv
    try:
        import workspace
        workspace.pin_active(workspace.active_slug())
    except Exception:  # noqa: BLE001 — pinning is best-effort at launch
        pass

    host, port = rcv.HOST, PORT_RECEIVER

    # 3+4. Present + serve per mode.
    if "--desktop" in argv:
        return _run_desktop(rcv.app, host, port)
    return _run_browser(rcv.app, host, port)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
