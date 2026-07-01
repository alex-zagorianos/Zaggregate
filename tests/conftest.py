"""Pytest config — make the project root importable AND fence the suite off from
the network.

The suite has 1500+ tests and no network dependency (every source client is
exercised against fixtures/monkeypatched sessions). An autouse socket guard makes
that guarantee enforceable: any real outbound connection raises, so an
accidentally-unmocked fetch fails loudly instead of silently hitting a live API
(slow, flaky, and a privacy surprise). Loopback (127.0.0.1/::1) is allowed so the
Flask/browser-receiver test clients and any localhost fixtures keep working.

Opt a test out with ``@pytest.mark.network`` when it *must* reach out (there are
currently none; add the marker deliberately and record it as a deviation)."""
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# The real connect methods, captured before any patching.
_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex

# Loopback hosts a test is always allowed to reach (in-process HTTP servers,
# localhost fixtures). Everything else is a real outbound connection.
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "0.0.0.0", ""}


class NetworkBlockedError(RuntimeError):
    """Raised when a test tries to open a non-loopback socket without the
    @pytest.mark.network opt-out."""


def _is_loopback(address) -> bool:
    """True if a socket address tuple points at loopback (so it's allowed)."""
    try:
        host = address[0] if isinstance(address, (tuple, list)) else address
    except Exception:
        return False
    if host in _LOOPBACK_HOSTS:
        return True
    host_s = str(host)
    return host_s.startswith("127.") or host_s == "::1"


def _blocked_connect(self, address, *args, **kwargs):
    if _is_loopback(address):
        return _real_connect(self, address, *args, **kwargs)
    raise NetworkBlockedError(
        f"Blocked outbound network connection to {address!r} during tests. "
        "Mock the request/session, or mark the test @pytest.mark.network if it "
        "genuinely needs the network.")


def _blocked_connect_ex(self, address, *args, **kwargs):
    if _is_loopback(address):
        return _real_connect_ex(self, address, *args, **kwargs)
    raise NetworkBlockedError(
        f"Blocked outbound network connection to {address!r} during tests.")


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "network: test is allowed to make real outbound network connections "
        "(opts out of the autouse socket guard).")


@pytest.fixture(autouse=True)
def _block_network(request, monkeypatch):
    """Fence every test off from real outbound sockets unless it is marked
    @pytest.mark.network. Loopback stays open for in-process servers."""
    if request.node.get_closest_marker("network"):
        return
    monkeypatch.setattr(socket.socket, "connect", _blocked_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked_connect_ex)
