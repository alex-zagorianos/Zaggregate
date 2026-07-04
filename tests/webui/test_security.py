"""Origin-gate parity + request-level behavior for webui.security.

Parity: webui.security._origin_allowed_str must return the SAME verdict as
scrape.browser_receiver._origin_allowed for every case in the receiver's own
host set (the two must never drift — the web layer can't import the receiver, so
this test is the drift guard). The one documented divergence — webui ALSO allows
the IPv6 loopback host ``::1`` — is asserted separately as an intentional
superset (a superset can only widen the loopback allow-list, never deny a host the
receiver allows).
"""
import pytest

from webui import security
import scrape.browser_receiver as br


# Cases that must produce IDENTICAL verdicts in both implementations. Chosen to
# cover: extension scheme, loopback http/https, non-loopback http, foreign https,
# other schemes, empty, malformed.
_PARITY_ORIGINS = [
    "chrome-extension://abcdefghijklmnop",   # allow: extension
    "chrome-extension://",                    # allow: bare extension scheme
    "http://127.0.0.1",                       # allow: loopback
    "http://127.0.0.1:5002",                  # allow: loopback + port
    "https://localhost",                      # allow: loopback https
    "http://localhost:3000",                  # allow: loopback dev port
    "https://evil.example.com",               # deny: foreign https
    "http://192.168.1.50:5002",               # deny: LAN host
    "https://127.0.0.1.evil.com",             # deny: lookalike host
    "ftp://127.0.0.1",                         # deny: non-web scheme on loopback
    "file:///etc/passwd",                     # deny: file scheme
    "moz-extension://abc",                    # deny: non-chrome extension
    "",                                        # deny (str form): empty origin
    "not a url",                              # deny: junk
    "http://",                                 # deny: no host
]


@pytest.mark.parametrize("origin", _PARITY_ORIGINS)
def test_origin_str_parity_with_receiver(origin):
    assert security._origin_allowed_str(origin) == br._origin_allowed(origin), origin


def test_ipv6_loopback_is_intentional_superset():
    # webui allows ::1; the receiver's tuple predates IPv6 loopback. A superset,
    # documented in security.py — never denies a host the receiver allows.
    assert security._origin_allowed_str("http://[::1]:5002") is True
    assert br._origin_allowed("http://[::1]:5002") is False


# ── request-level origin_allowed (Origin OR Referer, both-absent allowance) ────

class _FakeReq:
    def __init__(self, origin=None, referer=None):
        self.headers = {}
        if origin is not None:
            self.headers["Origin"] = origin
        if referer is not None:
            self.headers["Referer"] = referer


def test_both_absent_allowed():
    assert security.origin_allowed(_FakeReq()) is True


def test_origin_present_and_allowed():
    assert security.origin_allowed(
        _FakeReq(origin="chrome-extension://x")) is True


def test_origin_present_and_foreign_denied():
    assert security.origin_allowed(
        _FakeReq(origin="https://evil.example.com")) is False


def test_referer_fallback_when_no_origin():
    # No Origin (common on same-origin GET/PUT), but a loopback Referer -> allowed.
    assert security.origin_allowed(
        _FakeReq(referer="http://127.0.0.1:5002/app")) is True


def test_referer_foreign_denied():
    assert security.origin_allowed(
        _FakeReq(referer="https://evil.example.com/x")) is False


def test_origin_wins_over_referer():
    # A present Origin is judged directly; a foreign Origin is denied even with a
    # loopback Referer (an attacker can't launder a bad Origin through Referer).
    assert security.origin_allowed(
        _FakeReq(origin="https://evil.example.com",
                 referer="http://127.0.0.1/app")) is False


# ── strict mutating-origin verdict (decorator policy, divergence #2) ───────────
# require_local_origin uses _mutating_origin_allowed, which — unlike the lenient
# read-context origin_allowed — DENIES the header-less case, matching the
# receiver's _origin_allowed('') deny.

def test_mutating_both_absent_denied():
    assert security._mutating_origin_allowed(_FakeReq()) is False


def test_mutating_loopback_origin_allowed():
    assert security._mutating_origin_allowed(
        _FakeReq(origin="http://127.0.0.1:5002")) is True


def test_mutating_extension_origin_allowed():
    assert security._mutating_origin_allowed(
        _FakeReq(origin="chrome-extension://x")) is True


def test_mutating_foreign_origin_denied():
    assert security._mutating_origin_allowed(
        _FakeReq(origin="https://evil.example.com")) is False


def test_mutating_referer_fallback_when_no_origin():
    assert security._mutating_origin_allowed(
        _FakeReq(referer="http://127.0.0.1:5002/app")) is True


def test_mutating_diverges_from_lenient_origin_allowed():
    # The two verdicts intentionally differ ONLY on the header-less case: lenient
    # allows (read context), strict denies (mutating context).
    req = _FakeReq()
    assert security.origin_allowed(req) is True
    assert security._mutating_origin_allowed(req) is False
