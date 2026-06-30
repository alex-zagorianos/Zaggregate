"""Wave 8b — on-demand stealth-browser install helper (mocked; no real download)."""
import subprocess
import scrape.stealth_fetch as sf


def test_install_requires_scrapling(monkeypatch):
    monkeypatch.setattr(sf, "available", lambda: False)
    ok, msg = sf.install()
    assert ok is False and "scrapling" in msg.lower()


def test_install_success_via_driver(monkeypatch):
    monkeypatch.setattr(sf, "available", lambda: True)

    class _R:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())
    ok, msg = sf.install()
    assert ok is True and "ready" in msg.lower()


def test_install_failure_gives_manual_command(monkeypatch):
    monkeypatch.setattr(sf, "available", lambda: True)

    def _boom(*a, **k):
        raise OSError("no driver")

    monkeypatch.setattr(subprocess, "run", _boom)
    ok, msg = sf.install()
    assert ok is False and "scrapling install" in msg


def test_browsers_ready_false_without_scrapling(monkeypatch):
    monkeypatch.setattr(sf, "available", lambda: False)
    assert sf.browsers_ready() is False
