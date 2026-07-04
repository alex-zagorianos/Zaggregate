"""Phase 0d: unit-test gui._web_smoke() — the frozen web-UI smoke hook.

The hook runs the receiver's Flask app (webui blueprint mounted at import) on a
loopback port in a daemon thread and GETs /app + /api/status over urllib. This
is the SAME code path the frozen exe runs under ZAGGREGATE_WEB_SMOKE=1, so a
green test here means the seams the packaging phase must prove (webui import +
static serving) are exercised in the dev tree too.

Loopback sockets are allowed by the top-level conftest network guard, so calling
_web_smoke() directly (no @pytest.mark.network) opens a real in-process server on
127.0.0.1 and hits it — no external network, no subprocess spawn.
"""
import socket

import pytest

import gui


def _free_port() -> int:
    """Grab an ephemeral loopback port the smoke server can bind, so the test is
    independent of the live 5002 receiver / 5003 default smoke port."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_web_smoke_serves_app_and_status(monkeypatch):
    # Set the env var the hook honors (defensive: also pass port explicitly so
    # the test never races the default 5003) and exercise the real seam.
    port = _free_port()
    monkeypatch.setenv("ZAGGREGATE_WEB_SMOKE", "1")
    monkeypatch.setenv("ZAGGREGATE_SMOKE_PORT", str(port))

    res = gui._web_smoke(port=port)

    assert res["listening"] is True, res
    # /app: the built SPA shell — 200 text/html carrying the React mount point.
    assert res["app"]["code"] == 200, res
    assert "text/html" in res["app"]["content_type"], res
    assert res["app"]["has_root"] is True, res
    # /api/status: the engine seam is alive and reports ok:true.
    assert res["status"]["code"] == 200, res
    assert res["status"]["ok"] is True, res
    # Overall verdict the frozen exe exits on.
    assert res["ok"] is True, res


def test_web_smoke_env_default_port(monkeypatch):
    """With no explicit port arg, the hook reads ZAGGREGATE_SMOKE_PORT (the exe's
    contract). Point it at a free ephemeral port so we don't collide with 5003."""
    port = _free_port()
    monkeypatch.setenv("ZAGGREGATE_SMOKE_PORT", str(port))

    res = gui._web_smoke()  # port=None -> reads the env var

    assert res["port"] == port
    assert res["ok"] is True, res
