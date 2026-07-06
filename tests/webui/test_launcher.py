"""Web launcher (``py -m webui`` / ``gui.py --web``) unit tests (Phase 5).

No real browser opens, no real socket binds, no wall-clock waits — the launcher's
seams (``_serve`` / ``webbrowser.open`` / socket connect / sleep) are injected or
monkeypatched so the arg handling + sequencing are asserted deterministically.
"""
import pytest

import webui.__main__ as wm


# ── _wait_and_open (injected seams: connect / sleep / open_browser) ───────────
def test_wait_and_open_opens_when_listening():
    opened = {}

    def fake_connect(addr, timeout=None):
        # A context manager that "connects" immediately.
        class _C:
            def __enter__(self_): return self_
            def __exit__(self_, *a): return False
        return _C()

    ok = wm._wait_and_open(
        "127.0.0.1", 5002,
        open_browser=lambda url: opened.setdefault("url", url),
        connect=fake_connect, sleep=lambda s: None)
    assert ok is True
    assert opened["url"] == "http://127.0.0.1:5002/app"


def test_wait_and_open_times_out_without_server():
    calls = {"n": 0}

    def never_connect(addr, timeout=None):
        calls["n"] += 1
        raise OSError("refused")

    opened = {}
    ok = wm._wait_and_open(
        "127.0.0.1", 5002, timeout=0.05,
        open_browser=lambda url: opened.setdefault("url", url),
        connect=never_connect, sleep=lambda s: None)
    assert ok is False
    assert "url" not in opened          # never opened the browser
    assert calls["n"] >= 1              # tried at least once


# ── main() sequencing (no real server / browser) ──────────────────────────────
def test_main_bootstraps_pins_and_serves(monkeypatch):
    events = []

    # userdata.bootstrap is called first.
    import userdata
    monkeypatch.setattr(userdata, "bootstrap",
                        lambda: events.append("bootstrap"))

    # The project is pinned once for this process.
    import workspace
    monkeypatch.setattr(workspace, "active_slug", lambda: "myproj")
    monkeypatch.setattr(workspace, "pin_active",
                        lambda slug: events.append(("pin", slug)))

    # _serve is patched so no socket binds; it records the app+host+port.
    def fake_serve(app, host, port):
        events.append(("serve", host, port))

    monkeypatch.setattr(wm, "_serve", fake_serve)

    # The browser-opener thread is neutralized so no real browser opens and the
    # test doesn't depend on a background socket poll.
    import threading
    monkeypatch.setattr(wm.threading, "Thread",
                        lambda *a, **k: _NoopThread())

    rc = wm.main([])
    assert rc == 0
    assert events[0] == "bootstrap"
    assert ("pin", "myproj") in events
    # Served on loopback + the receiver port.
    from config import PORT_RECEIVER
    serve_evt = next(e for e in events if isinstance(e, tuple) and e[0] == "serve")
    assert serve_evt[1] == "127.0.0.1"
    assert serve_evt[2] == PORT_RECEIVER


def test_main_bootstrap_failure_is_nonfatal(monkeypatch):
    import userdata
    def boom():
        raise RuntimeError("bootstrap broke")
    monkeypatch.setattr(userdata, "bootstrap", boom)

    import workspace
    monkeypatch.setattr(workspace, "active_slug", lambda: None)
    monkeypatch.setattr(workspace, "pin_active", lambda slug: None)
    served = {}
    monkeypatch.setattr(wm, "_serve",
                        lambda app, host, port: served.setdefault("ok", True))
    monkeypatch.setattr(wm.threading, "Thread", lambda *a, **k: _NoopThread())

    # A bootstrap failure must NOT stop the server from starting.
    assert wm.main([]) == 0
    assert served.get("ok") is True


def test_main_keyboardinterrupt_returns_zero(monkeypatch):
    import userdata, workspace
    monkeypatch.setattr(userdata, "bootstrap", lambda: None)
    monkeypatch.setattr(workspace, "active_slug", lambda: None)
    monkeypatch.setattr(workspace, "pin_active", lambda slug: None)
    monkeypatch.setattr(wm.threading, "Thread", lambda *a, **k: _NoopThread())

    def ctrl_c(app, host, port):
        raise KeyboardInterrupt()
    monkeypatch.setattr(wm, "_serve", ctrl_c)
    assert wm.main([]) == 0


class _NoopThread:
    def __init__(self, *a, **k):
        pass
    def start(self):
        pass


# ── gui.py --web delegation (arg handling, no Tk) ─────────────────────────────
def test_gui_web_flag_delegates_to_launcher(monkeypatch):
    import sys
    import gui

    called = {}
    def fake_web_main(argv):
        called["argv"] = argv
        return 0
    # gui.main imports webui.__main__.main lazily; patch the source.
    monkeypatch.setattr(wm, "main", fake_web_main)
    monkeypatch.setattr(sys, "argv", ["gui.py", "--web"])

    rc = gui.main()
    assert rc == 0
    assert called["argv"] == ["--web"]


def test_gui_no_web_flag_does_not_delegate(monkeypatch):
    """Without --web, gui.main must NOT call the web launcher (it would fall
    through to the Tk App, which we stub to avoid opening a window)."""
    import sys
    import gui

    monkeypatch.setattr(sys, "argv", ["gui.py", "--daily"])
    web_called = {"n": 0}
    monkeypatch.setattr(wm, "main",
                        lambda argv: web_called.__setitem__("n", web_called["n"] + 1) or 0)
    # Stub the headless-daily path so --daily returns without running the engine.
    monkeypatch.setattr(gui, "_run_headless_daily", lambda argv: 0)

    rc = gui.main()
    assert rc == 0
    assert web_called["n"] == 0   # web launcher never invoked


# ── desktop mode (--desktop -> pywebview native window; S36b) ─────────────────

class _FakeEvent:
    """pywebview's event objects support ``+=`` handler registration."""
    def __init__(self):
        self.handlers = []

    def __iadd__(self, fn):
        self.handlers.append(fn)
        return self


class _FakeWindow:
    def __init__(self):
        class _Events:
            shown = _FakeEvent()
        self.events = _Events()


class _FakeWebview:
    """Stands in for the pywebview module: records create_window/start args."""
    def __init__(self):
        self.created = None
        self.started = None
        self.window = _FakeWindow()

    def create_window(self, title, url, **kw):
        self.created = {"title": title, "url": url, **kw}
        return self.window

    def start(self, **kw):
        self.started = kw


def test_main_desktop_opens_native_window(monkeypatch):
    import sys as _sys
    import userdata, workspace
    monkeypatch.setattr(userdata, "bootstrap", lambda: None)
    monkeypatch.setattr(workspace, "active_slug", lambda: None)
    monkeypatch.setattr(workspace, "pin_active", lambda slug: None)

    fake = _FakeWebview()
    monkeypatch.setitem(_sys.modules, "webview", fake)

    threads = []

    class _RecThread:
        def __init__(self, *a, **k):
            threads.append(k.get("name"))
        def start(self):
            pass

    monkeypatch.setattr(wm.threading, "Thread", _RecThread)
    monkeypatch.setattr(wm, "_serve", lambda app, host, port: None)

    rc = wm.main(["--desktop"])
    assert rc == 0
    from config import PORT_RECEIVER
    # The native window hosts /app on loopback…
    assert fake.created["url"] == f"http://127.0.0.1:{PORT_RECEIVER}/app"
    assert fake.created["title"] == "Zaggregate"
    # …and localStorage must survive relaunches (theme choice lives there).
    assert fake.started == {"private_mode": False}
    # The server runs on a daemon thread (the window owns the main thread).
    assert "web-server" in threads
    # Native chrome (S38): the theme bridge rides js_api and the icon+caption
    # pass is registered on the window's `shown` event.
    from webui import native_win
    assert isinstance(fake.created["js_api"], native_win.ThemeBridge)
    assert len(fake.window.events.shown.handlers) == 1


def test_desktop_chrome_failure_never_blocks_window(monkeypatch):
    """A broken native_win (or an older pywebview without window events) must
    degrade to a stock frame — webview.start still runs."""
    import sys as _sys
    import userdata, workspace
    monkeypatch.setattr(userdata, "bootstrap", lambda: None)
    monkeypatch.setattr(workspace, "active_slug", lambda: None)
    monkeypatch.setattr(workspace, "pin_active", lambda slug: None)

    class _NoWindowWebview(_FakeWebview):
        def create_window(self, title, url, **kw):
            super().create_window(title, url, **kw)
            return None   # older pywebview: no window object -> no .events

    fake = _NoWindowWebview()
    monkeypatch.setitem(_sys.modules, "webview", fake)
    monkeypatch.setattr(wm.threading, "Thread", lambda *a, **k: _NoopThread())
    monkeypatch.setattr(wm, "_serve", lambda app, host, port: None)

    assert wm.main(["--desktop"]) == 0
    assert fake.started == {"private_mode": False}   # window still opened


def test_main_desktop_without_pywebview_falls_back_to_browser(monkeypatch):
    import sys as _sys
    import userdata, workspace
    monkeypatch.setattr(userdata, "bootstrap", lambda: None)
    monkeypatch.setattr(workspace, "active_slug", lambda: None)
    monkeypatch.setattr(workspace, "pin_active", lambda slug: None)

    # A None entry in sys.modules makes `import webview` raise ImportError.
    monkeypatch.setitem(_sys.modules, "webview", None)
    monkeypatch.setattr(wm.threading, "Thread", lambda *a, **k: _NoopThread())

    served = {}
    monkeypatch.setattr(wm, "_serve",
                        lambda app, host, port: served.setdefault("ok", True))
    assert wm.main(["--desktop"]) == 0
    assert served.get("ok") is True   # browser-mode serve took over


def test_gui_desktop_flag_delegates_to_launcher(monkeypatch):
    import sys
    import gui

    called = {}

    def fake_web_main(argv):
        called["argv"] = argv
        return 0

    monkeypatch.setattr(wm, "main", fake_web_main)
    monkeypatch.setattr(sys, "argv", ["gui.py", "--desktop"])
    assert gui.main() == 0
    assert called["argv"] == ["--desktop"]
