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
SRC = ROOT / "src"          # all app code lives under src/ (2026-07 restructure)
for _p in (str(SRC), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

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


@pytest.fixture(autouse=True)
def _reset_per_run_module_state():
    """Clear per-RUN module-global state between tests (S35b review finding).

    applog._WARNED_ONCE dedups warn_once() per process: a test that warms a key
    (e.g. 'careerjet:no-affid') silently swallows the SAME warning in a later
    test, whose capsys assertion then fails — but only in orders that differ
    from default collection (repro: test_b2_source_keys.py::test_careerjet_
    keyless_self_skip followed by tests/search/test_careerjet.py::test_no_affid
    _warns_and_empty). scrape.discoverer._RUN_QUERY_MEMO is the same class of
    per-run global. Reset both here so no individual test has to remember to —
    the inline resets scattered in older test files become harmless no-ops."""
    import applog
    applog.reset_run_warnings()
    try:
        from scrape import discoverer
        discoverer.reset_run_memo()
    except Exception:
        pass  # discoverer optional in stripped-down environments
    yield
