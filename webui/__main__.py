"""Web-UI launcher: ``py -m webui`` (and the ``gui.py --web`` / frozen-exe flag).

One process = the app (the migration-plan invariant). This starts the SAME Flask
app the browser extension already talks to — ``scrape.browser_receiver.app``, with
the ``webui`` blueprint mounted at import via ``register_webui`` — bound to
loopback only, and opens the default browser at ``/app`` once it's listening. The
tkinter GUI is never imported here, so this path stays fully headless (the frozen
exe gets ``--web`` for free because the PyInstaller entry is ``gui.py``, which
delegates to :func:`main` before creating any Tk window).

Sequence (matches the tk/daily entry points):
1. ``userdata.bootstrap()`` — ensure the data folder exists + is seeded (a fresh
   unzip just works), emit the sync-folder warning if under OneDrive/Dropbox.
2. Pin the active project ONCE for this process (the receiver OWNS the process
   here, like the standalone ``browser_receiver.__main__`` / mcp_server pattern —
   a project switch in another process must not repoint this receiver's writes).
3. Open the browser at ``http://127.0.0.1:<PORT_RECEIVER>/app`` AFTER the socket
   is accepting (a background waiter opens it; the main thread runs the server).
4. ``app.run(host=127.0.0.1, port=PORT_RECEIVER)`` on the MAIN thread (blocks).

Security: 127.0.0.1 ONLY (never 0.0.0.0 — documented in browser_receiver). Nothing
new is exposed beyond what the receiver already serves + the origin-gated /api.
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


def main(argv=None) -> int:
    """Bootstrap data, pin the project, open the browser, and serve the web UI on
    loopback (blocks until the server stops). Returns a process exit code. ``argv``
    is accepted for signature stability / future flags (currently unused)."""
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

    # 3. Open the browser once the socket is listening (background thread — the
    # main thread is about to block in app.run).
    opener = threading.Thread(
        target=_wait_and_open, args=(host, port),
        name="web-open-browser", daemon=True)
    opener.start()

    print(f"Zaggregate web UI on http://{host}:{port}/app  (Ctrl+C to stop)")

    # 4. Serve on the main thread (blocks until interrupted).
    try:
        _serve(rcv.app, host, port)
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
