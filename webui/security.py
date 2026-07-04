"""Origin gate for mutating web-UI routes, mirroring
``scrape.browser_receiver._origin_allowed`` semantics.

Why a copy instead of an import: the receiver imports ``webui`` (register_webui),
so importing ``browser_receiver`` back into ``webui`` would be a circular import.
The core string check :func:`_origin_allowed_str` is therefore a faithful,
independently-testable mirror — ``tests/webui/test_security.py`` asserts a
parity table against the receiver's function so the two never drift.

Two INTENTIONAL divergences from the receiver, both documented and asserted:

1. **``::1`` superset** — :func:`_origin_allowed_str` also allows the IPv6
   loopback host ``::1`` (the receiver's tuple predates IPv6 loopback). A superset
   can only ever ALLOW an extra loopback host, never deny one the receiver allows,
   so the parity table still holds for the receiver's own host set.
2. **Decorator strictness on absent headers** — the receiver's bare
   ``_origin_allowed("")`` DENIES an empty/absent origin (``urlparse("")`` -> no
   scheme). :func:`require_local_origin` matches that receiver behavior: a mutating
   request with BOTH ``Origin`` and ``Referer`` absent is DENIED (403). This is
   stricter than :func:`origin_allowed` (see below), and deliberately so — a
   mutating route should never run a side effect for a header-less caller.

The public surface adds two things the receiver's bare helper lacks, both needed
for a browser-navigated SPA (not just an extension POST):

* :func:`origin_allowed` takes the Flask ``request`` and consults BOTH ``Origin``
  and ``Referer`` — a same-origin ``fetch`` from the served ``/app`` page may omit
  ``Origin`` on a GET but always carries a ``Referer``. When BOTH are absent it
  returns True: this is a READ-context leniency for GET callers (a curl / same-
  process test client with no headers cannot be a cross-site browser forgery,
  which is the only thing this gate defends against, and a hostile local process
  already owns the box). MUTATING routes must NOT rely on this leniency — they use
  the stricter decorator, which denies the absent-both case (divergence #2).
* :func:`require_local_origin` — a decorator for mutating routes that 403s a
  foreign origin (or a header-less request) with a JSON body, matching the API's
  ``{ok:false,error:...}`` envelope.
"""
from __future__ import annotations

import functools
from urllib.parse import urlparse

from flask import request as _flask_request, jsonify

# Mirror of browser_receiver's module constants (kept in lockstep; the parity
# test enforces identical verdicts).
_ALLOWED_ORIGIN_SCHEME = "chrome-extension"
_ALLOWED_LOCALHOST_HOSTS = ("127.0.0.1", "localhost", "::1")


def _origin_allowed_str(origin: str) -> bool:
    """True only for the unpacked extension's ``chrome-extension://`` origin or an
    http(s) loopback origin. Exact mirror of
    ``browser_receiver._origin_allowed`` (with ``::1`` added — the receiver's tuple
    predates IPv6 loopback; a superset here can only ever ALLOW an extra loopback
    host, never deny one the receiver allows, so the parity table still holds for
    the receiver's own host set)."""
    parsed = urlparse(origin or "")
    if parsed.scheme == _ALLOWED_ORIGIN_SCHEME:
        return True
    if parsed.scheme in ("http", "https") and parsed.hostname in _ALLOWED_LOCALHOST_HOSTS:
        return True
    return False


def origin_allowed(request=None) -> bool:
    """Origin gate for a Flask request.

    Consults ``Origin`` first, then falls back to ``Referer`` (a browser GET/PUT
    from the served page may omit Origin but carries a Referer). When BOTH headers
    are absent the request is allowed — a header-less caller (curl, the test
    client, a same-process fetch) cannot be a cross-site browser forgery, which is
    the sole threat this gate addresses. A PRESENT-but-foreign Origin/Referer is
    denied.
    """
    req = request if request is not None else _flask_request
    origin = req.headers.get("Origin", "") or ""
    referer = req.headers.get("Referer", "") or ""
    if not origin and not referer:
        return True
    if origin:
        return _origin_allowed_str(origin)
    # No Origin, but a Referer is present — judge by the referer's scheme+host.
    return _origin_allowed_str(referer)


def _mutating_origin_allowed(request) -> bool:
    """Strict origin verdict for a MUTATING route. Unlike :func:`origin_allowed`,
    a request with BOTH ``Origin`` and ``Referer`` absent is DENIED — a mutating
    handler must never run a side effect for a header-less caller. This matches the
    receiver's ``_origin_allowed("")`` (which denies the empty origin) rather than
    the read-context leniency :func:`origin_allowed` grants GET callers.
    """
    origin = request.headers.get("Origin", "") or ""
    referer = request.headers.get("Referer", "") or ""
    if not origin and not referer:
        return False  # absent-both -> deny for mutating routes (divergence #2)
    if origin:
        return _origin_allowed_str(origin)
    return _origin_allowed_str(referer)


def require_local_origin(fn):
    """Decorator: 403 a mutating route whose Origin/Referer is a foreign browser
    origin OR absent entirely, before the handler runs any side effect. Uses the
    STRICT :func:`_mutating_origin_allowed` verdict (denies the header-less case),
    not the lenient read-context :func:`origin_allowed`. JSON body matches the API
    envelope ``{ok:false, error:"forbidden origin"}``."""
    @functools.wraps(fn)
    def _wrapped(*args, **kwargs):
        if not _mutating_origin_allowed(_flask_request):
            return jsonify({"ok": False, "error": "forbidden origin"}), 403
        return fn(*args, **kwargs)
    return _wrapped
