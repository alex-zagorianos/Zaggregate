"""D3 — API contract sweep: route inventory audit + security regression sweep.

This is a *meta-test* module (test-plan section D3, 2026-07-04 web-UI deep test).
Where the per-blueprint suites assert each route's behavior one at a time, this
module enumerates ``app.url_map`` as a whole and asserts *cross-cutting*
invariants that no single route test can guarantee:

* **D3.1 origin-gate completeness** — EVERY mutating (POST/PUT/PATCH/DELETE)
  ``/api/*`` route is origin-gated (introspectable ``__origin_gated__`` marker set
  by :func:`webui.security.require_local_origin`), except a small, explicitly
  documented exception set. A newly-added mutating route that forgets the gate
  fails here even if its own test passes — the whole point of a meta-test.
* **D3.1 error envelope** — handler-emitted 4xx responses are the JSON
  ``{ok:false,error}`` envelope, not HTML.
* **D3.2 traversal defense on EVERY download route** — one parametrized place
  proving ``../`` / encoded-separator / absolute-path spellings never escape the
  locked base on the export, queue, resume, and ``/app`` static download families.
* **D3.2 secret absence** — a seeded API credential never appears verbatim in the
  ``/api/settings/keys`` masked-status response (across ALL sources/fields) nor in
  a probe (``/test``) response body.

The exception set below is the load-bearing contract: to remove a route from it,
that route must become genuinely origin-gated. To ADD one, it must be a
documented pure-read (no side effect) or a differently-gated hook — with the
reason recorded here.
"""
from __future__ import annotations

import json as _json

import pytest

import config
from scrape.browser_receiver import app as _app
import webui  # noqa: F401 — ensure the package registers onto the app
from ui import settings as ui_settings


# ── shared helpers ─────────────────────────────────────────────────────────────

_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_LOOPBACK = "http://127.0.0.1:5002"


def _ensure_registered():
    """register_webui is idempotent; call it so the audit runs even if an earlier
    import-order left the app un-mounted in this process."""
    try:
        webui.register_webui(_app)
    except Exception:  # pragma: no cover — already registered
        pass


def _is_origin_gated(view_fn) -> bool:
    """True iff ``view_fn`` (or anything in its ``__wrapped__`` chain) carries the
    ``__origin_gated__`` marker :func:`require_local_origin` stamps on its wrapper.

    Walking the ``__wrapped__`` chain (not just the top object) means the audit
    still passes if a future decorator is stacked OUTSIDE the gate without
    ``functools.wraps`` propagating the marker up — belt-and-suspenders against a
    silent regression where the gate is present but its marker got shadowed."""
    seen: set[int] = set()
    cur = view_fn
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if getattr(cur, "__origin_gated__", False) is True:
            return True
        cur = getattr(cur, "__wrapped__", None)
    return False


def _mutating_api_rules():
    """Every ``/api/*`` url rule that answers at least one mutating method, as
    ``(endpoint, rule, methods)`` tuples sorted by rule for stable failure output."""
    _ensure_registered()
    out = []
    for r in _app.url_map.iter_rules():
        methods = (r.methods or set()) - {"HEAD", "OPTIONS"}
        rule = str(r.rule)
        if not rule.startswith("/api"):
            continue
        if not (methods & _MUTATING_METHODS):
            continue
        out.append((r.endpoint, rule, tuple(sorted(methods))))
    return sorted(out, key=lambda t: t[1])


# ── D3.1 — mutating routes are origin-gated (with a documented exception set) ───

# Endpoints that ANSWER a mutating method but are DELIBERATELY not origin-gated.
# Each entry records WHY. A meta-test that just skipped "the ungated ones" would
# be worthless; this set is a hard allow-list — a new ungated mutating route is a
# FAILURE until it is either gated or consciously added here with a reason.
_GATE_EXCEPTIONS = {
    # Private test hooks: gated by TESTING-mode + pytest-resident (runs.py
    # _test_hooks_enabled), NOT by origin. They 404 in any shipped process.
    "webui_api.webui_runs._start_test_job":
        "TESTING+pytest gated hook, 404 outside a test run",
    "webui_api.webui_runs._release_test_job":
        "TESTING+pytest gated hook, 404 outside a test run",
    # Pure-read parses declared POST for a JSON body but with NO side effect —
    # their docstrings say 'READ-only ... no gate'. A cross-site page could call
    # them but learns nothing it couldn't compute itself and mutates nothing.
    "webui_api.webui_onboarding.onboarding_salary_parse":
        "READ-only salary parse, no side effect (docstring-declared)",
    "webui_api.webui_resume.resume_prompt":
        "READ-only prompt builder, no side effect (docstring-declared)",
}


def test_gate_exceptions_are_all_real_routes():
    """Guard the guard: every endpoint named in the exception set must actually
    exist as a mutating /api route, so a rename can't leave a stale free pass that
    would silently excuse a genuinely ungated route sharing the old name."""
    live = {ep for ep, _rule, _m in _mutating_api_rules()}
    stale = set(_GATE_EXCEPTIONS) - live
    assert not stale, f"exception set names non-existent mutating routes: {stale}"


def test_every_mutating_api_route_is_origin_gated():
    """D3.1: enumerate app.url_map; assert every mutating /api/* route is
    origin-gated (introspectable marker) except the documented exception set."""
    _ensure_registered()
    offenders = []
    for endpoint, rule, methods in _mutating_api_rules():
        if endpoint in _GATE_EXCEPTIONS:
            continue
        vf = _app.view_functions.get(endpoint)
        if not _is_origin_gated(vf):
            offenders.append(f"{'/'.join(methods)} {rule} ({endpoint})")
    assert not offenders, (
        "mutating /api routes missing the origin gate (add @require_local_origin, "
        "or record a documented exception in _GATE_EXCEPTIONS):\n  "
        + "\n  ".join(offenders)
    )


def test_gate_actually_403s_a_sampled_route_per_module(client):
    """D3.1/D3.2 cross-check: the marker isn't just cosmetic — a header-less POST
    to a gated route from EACH api module actually 403s with the JSON envelope,
    proving the marker tracks a real gate. One representative route per module."""
    # (path, method) — a mutating route in each api module, chosen to need no body
    # setup to reach the gate (the gate runs before the handler).
    samples = [
        ("/api/project", "post"),                       # system
        ("/api/settings/theme", "put"),                 # settings
        ("/api/runs/daily", "post"),                    # runs
        ("/api/applications", "post"),                  # applications
        ("/api/inbox/1/track", "post"),                 # inbox
        ("/api/search", "post"),                        # search
        ("/api/queue/rank", "post"),                    # queue
        ("/api/resume/from-paste", "post"),             # resume
        ("/api/onboarding", "post"),                    # onboarding
        ("/api/companies/add", "post"),                 # companies
        ("/api/backup/restore", "post"),                # guide
        ("/api/settings/keys/adzuna/split", "post"),    # settings-keys
    ]
    for path, method in samples:
        resp = getattr(client, method)(path)  # NO Origin/Referer header
        assert resp.status_code == 403, (path, resp.status_code)
        body = resp.get_json()
        assert body == {"ok": False, "error": "forbidden origin"}, (path, body)


def test_foreign_origin_403s_a_sampled_route(client):
    """D3.2: a PRESENT-but-foreign Origin is denied (not just the header-less
    case) on a mutating route."""
    resp = client.post("/api/project",
                       headers={"Origin": "https://evil.example.com"},
                       json={"slug": "whatever"})
    assert resp.status_code == 403
    assert resp.get_json() == {"ok": False, "error": "forbidden origin"}


# ── D3.1 — handler error responses are the JSON envelope, not HTML ─────────────

def test_handler_4xx_responses_are_json_envelope(client, tmp_db):
    """D3.1: spot-check that handler-emitted 4xx responses are the JSON
    ``{ok:false,error}`` envelope with an application/json content type — not a
    Werkzeug HTML error page. (An UNMATCHED route legitimately falls through to
    Flask's default HTML 404; this checks the routes our handlers own.)"""
    H = {"Origin": _LOOPBACK}
    cases = [
        # (method, path, kwargs, expected_status)
        ("get",  "/api/applications/999999/rounds/1/ics", {}, 404),   # unknown app
        ("post", "/api/project", {"json": {"slug": "nope"}, "headers": H}, 400),  # bad slug
        ("post", "/api/project", {}, 403),                            # header-less -> gate
        ("put",  "/api/settings/keys/nosuch", {"json": {"x": "y"}, "headers": H}, 404),  # unknown source
        ("get",  "/api/queue/99999/resume-prompt", {}, 404),          # unknown job
    ]
    for method, path, kwargs, status in cases:
        resp = getattr(client, method)(path, **kwargs)
        assert resp.status_code == status, (path, resp.status_code)
        ctype = resp.headers.get("Content-Type", "")
        assert "application/json" in ctype, (path, ctype)
        body = resp.get_json()
        assert isinstance(body, dict) and body.get("ok") is False, (path, body)
        assert body.get("error"), (path, body)


# ── D3.2 — traversal defense on EVERY download route ───────────────────────────
# The per-module suites each cover their own download route's traversal 404; this
# consolidates a traversal sweep across the WHOLE download surface in one place so
# a newly-added download family that forgets the lock is caught here. The static
# /app traversal (with an out-of-root secret leak assertion) lives in
# test_static.py; this covers the JSON-API download families.

# Each download family is base-locked to workspace.output_dir() (via the webui
# conftest's autouse _isolate_output_dir fixture), so a traversal target resolves
# outside that tmp base and 404s. Spellings cover: dotdot, encoded-dotdot,
# backslash, mixed-encoding, and an absolute path.
_TRAVERSAL_SPELLINGS = [
    "..%2f..%2fsecret.txt",
    "..%2f..%2f..%2fconfig.py",
    "%2e%2e%2f%2e%2e%2fsecret.txt",
    "..%5c..%5csecret.txt",
    "....//secret.txt",
]

# (route-prefix, needs_db) for every user-name-parameterized download route.
_DOWNLOAD_ROUTES = [
    "/api/inbox/export/download/",   # inbox export (manual is_relative_to lock)
    "/api/queue/download/",          # apply-queue (shared send_locked)
    "/api/resume/download/",         # resume bundle (shared send_locked)
]


@pytest.mark.parametrize("prefix", _DOWNLOAD_ROUTES)
@pytest.mark.parametrize("spelling", _TRAVERSAL_SPELLINGS)
def test_download_route_traversal_404(client, tmp_db, prefix, spelling):
    """D3.2: no traversal spelling escapes any download route's locked base.
    A 404 (never a 200 that served an out-of-base file) is the only pass."""
    resp = client.get(prefix + spelling)
    assert resp.status_code == 404, (prefix + spelling, resp.status_code)


def test_download_traversal_never_serves_out_of_base_file(client, tmp_db,
                                                          _isolate_output_dir,
                                                          tmp_path):
    """D3.2 (leak proof): plant a secret file OUTSIDE the locked output base and
    prove no download route's traversal spelling returns its bytes. The autouse
    fixture locks output_dir to ``tmp_path/ws_output``; the secret is a sibling,
    reachable only via a successful ``..`` escape."""
    secret = tmp_path / "ws_output_SECRET.txt"
    secret_body = b"ZAG-DOWNLOAD-OUT-OF-BASE-SECRET"
    secret.write_text(secret_body.decode(), encoding="utf-8")
    # Point each traversal at the planted sibling by name.
    name = "..%2f" + secret.name
    for prefix in _DOWNLOAD_ROUTES:
        resp = client.get(prefix + name)
        assert resp.status_code == 404, (prefix, resp.status_code)
        assert secret_body not in resp.get_data(), prefix


# ── D3.2 — no raw secret leaks in keys/probe responses (broad sweep) ───────────

_SOURCE_ENV_VARS = (
    "ADZUNA_APP_ID", "ADZUNA_APP_KEY", "USAJOBS_API_KEY", "USAJOBS_EMAIL",
    "JOOBLE_API_KEY", "CAREERJET_AFFID", "CAREERONESTOP_USER_ID",
    "CAREERONESTOP_TOKEN",
)

# A distinctive per-field secret so a leak anywhere in a serialized response is
# unambiguous. The field NAMES are the persisted secret keys the settings core
# reads/writes (ui.source_keys_core.SOURCES field names).
_SEEDED = {
    "adzuna_app_id": "ZAGSECRETADZID0001",
    "adzuna_app_key": "ZAGSECRETADZKEY0002",
    "usajobs_api_key": "ZAGSECRETUSAJOBS03",
    "usajobs_email": "zagsecret-usajobs@example.test",
    "jooble_api_key": "ZAGSECRETJOOBLE0004",
    "careerjet_affid": "ZAGSECRETCJET00005",
    "careeronestop_user_id": "ZAGSECRETC1SUID006",
    "careeronestop_token": "ZAGSECRETC1STOK007",
}


@pytest.fixture
def seeded_secrets(tmp_path, monkeypatch):
    """Point config.SECRETS_DIR at a tmp dir, strip source env vars (env wins over
    the secret file, so a dev .env could otherwise shadow the seed), then seed a
    distinctive secret into EVERY known source field via the app's own
    ``set_api_key`` mechanism."""
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path / "secrets")
    for var in _SOURCE_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    for name, value in _SEEDED.items():
        ui_settings.set_api_key(name, value)
    return tmp_path / "secrets"


def test_keys_list_never_leaks_any_raw_secret(client, seeded_secrets):
    """D3.2: with a distinct secret seeded in EVERY source field, none of the raw
    values appear anywhere in the ``/api/settings/keys`` response — only set flags
    and last-4 masks. Sweeps the full serialized body for each seeded value."""
    body = client.get("/api/settings/keys").get_json()
    assert body["ok"] is True
    dumped = _json.dumps(body)
    for name, value in _SEEDED.items():
        assert value not in dumped, f"{name} raw value leaked into keys response"
        # The set flag must be True (proves the secret really was seeded, so the
        # absence above is meaningful and not a vacuous 'unset -> nothing to leak').
    # Cross-check at least one field reports set=True with a last-4 mask.
    adzuna = next(s for s in body["sources"] if s["id"] == "adzuna")
    app_id = next(f for f in adzuna["fields"] if f["name"] == "adzuna_app_id")
    assert app_id["set"] is True
    assert app_id["masked"] == "••••0001"  # last-4 of ZAGSECRETADZID0001
    assert "ZAGSECRETADZID0001" not in dumped


def test_keys_probe_response_never_leaks_raw_secret(client, seeded_secrets):
    """D3.2: the live-probe route (``/test``, a no-op under pytest) response body
    must not echo the seeded secret either."""
    resp = client.post("/api/settings/keys/adzuna/test",
                       headers={"Origin": _LOOPBACK})
    assert resp.status_code == 200
    dumped = _json.dumps(resp.get_json())
    for value in _SEEDED.values():
        assert value not in dumped, "probe response leaked a raw secret"


# ── D3.2 — test hooks unreachable without TESTING+pytest ───────────────────────

def test_test_hooks_gated_by_testing_flag(client, monkeypatch):
    """D3.2: the /_test/* hooks 404 when the app is NOT in TESTING mode, even
    though pytest is resident. Both conditions are required (belt-and-suspenders in
    runs._test_hooks_enabled); flipping TESTING off must close them."""
    from scrape.browser_receiver import app as raw_app
    monkeypatch.setitem(raw_app.config, "TESTING", False)
    c = raw_app.test_client()
    for path in ("/api/_test/job", "/api/_test/release/tok"):
        resp = c.post(path, json={}, headers={"Origin": _LOOPBACK})
        assert resp.status_code == 404, (path, resp.status_code)
        assert resp.get_json() == {"ok": False, "error": "not found"}, path
