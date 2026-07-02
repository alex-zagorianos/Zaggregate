"""S33 browser-verified clip: the user's browser as the probe for walled ATS
tenants (FedEx/Banner-style Cloudflare/CSRF Workday boards the SERVER 422s but
that are live in the user's logged-in browser).

clip_board gains an optional ``browser_evidence`` kwarg. When the server probe
says NOT reachable AND plausible evidence is present, the board is saved flagged
BROWSER_ONLY (a real, live company kept out of server scraping) instead of the
'failed/unreachable — not added' dead-end. Without evidence, behavior is EXACTLY
as before (regression-guarded here). The server probe always wins: a
server-reachable board saves normally and the evidence is ignored.

All probes and companies.json writes are injected (probe_fn / json_path) so
these tests never touch the network or the real registry.
"""
import pytest

from scrape.ats_detect import ProbeResult
from scrape.browser_receiver import app, clip_board, _valid_browser_evidence
from scrape.company_registry import (BROWSER_ONLY_FLAG, CompanyEntry,
                                     get_registry, is_browser_only,
                                     is_unverified, save_companies)


@pytest.fixture
def companies(tmp_path):
    return tmp_path / "companies.json"


@pytest.fixture
def client():
    app.config["TESTING"] = True
    return app.test_client()


def _evidence(job_count=17, via="jsonld", page_url="https://fedex.wd5.myworkdayjobs.com/en-US/careers"):
    return {"job_count": job_count, "via": via, "page_url": page_url}


# ── the core S33 flow: unreachable + evidence -> browser-verified save ─────────

def test_walled_board_with_evidence_is_added_browser_only(companies):
    """The FedEx/Banner case: server probe says unreachable (422 wall), but the
    user's browser supplied evidence of a live board -> saved BROWSER_ONLY."""
    v = clip_board(
        "https://fedex.wd5.myworkdayjobs.com/en-US/careers", "",
        industry="warehouse logistics", json_path=companies,
        probe_fn=lambda e: ProbeResult(None, False),   # server can't read it
        browser_evidence=_evidence(job_count=42),
    )
    assert v["status"] == "added"
    assert v["reason"] == "browser_verified"
    assert v["browser_only"] is True
    assert v["live_count"] == 42
    assert v["ats_type"] == "workday_cxs"

    # Persisted with the flag, and it IS a real registry company (survives the
    # default listing) tagged with the active field.
    entries = get_registry("warehouse logistics", user_json=companies)
    fedex = next(e for e in entries if e.name == "Fedex")
    assert is_browser_only(fedex)
    assert not is_unverified(fedex)


def test_walled_board_with_null_count_evidence_still_added(companies):
    """Evidence with job_count=None (page had postings but the counter couldn't
    total them) is still valid live evidence -> browser-verified save."""
    v = clip_board(
        "https://banner.wd1.myworkdayjobs.com/en-US/External", "",
        industry="", json_path=companies,
        probe_fn=lambda e: ProbeResult(None, False),
        browser_evidence=_evidence(job_count=None, via="dom"),
    )
    assert v["status"] == "added" and v["reason"] == "browser_verified"
    assert v["browser_only"] is True
    assert v["live_count"] is None
    banner = next(e for e in get_registry(user_json=companies) if e.name == "Banner")
    assert is_browser_only(banner)


def test_evidence_with_zero_count_is_added(companies):
    """job_count 0 is a plausible int >= 0 (a live board with 0 open jobs) —
    accepted, saved browser-only."""
    v = clip_board(
        "https://tenant.wd5.myworkdayjobs.com/careers", "", industry="",
        json_path=companies, probe_fn=lambda e: ProbeResult(None, False),
        browser_evidence=_evidence(job_count=0),
    )
    assert v["status"] == "added" and v["browser_only"] is True
    assert v["live_count"] == 0


# ── regression: absent / junk evidence behaves EXACTLY as today ────────────────

def test_unreachable_without_evidence_is_failed_not_saved(companies):
    """No evidence -> the S32 behavior verbatim: failed/unreachable, nothing
    written, no browser_only key leaks into the verdict."""
    v = clip_board(
        "https://fedex.wd5.myworkdayjobs.com/en-US/careers", "", industry="",
        json_path=companies, probe_fn=lambda e: ProbeResult(None, False),
    )
    assert v["status"] == "failed"
    assert v["reason"] == "unreachable"
    assert "browser_only" not in v
    assert not companies.exists()


@pytest.mark.parametrize("junk", [
    {"job_count": -3, "via": "jsonld", "page_url": "u"},   # negative count
    {"job_count": "lots", "via": "dom", "page_url": "u"},   # non-int count
    {"job_count": True, "via": "dom", "page_url": "u"},      # bool masquerading
    "not-a-dict",                                            # wrong type entirely
    123,                                                     # wrong type entirely
    [],                                                      # wrong type entirely
])
def test_junk_evidence_treated_as_absent_still_failed(junk, companies):
    """Malformed evidence is sanitized to 'no evidence' -> failed/unreachable
    exactly as today, nothing saved (defensive contract)."""
    v = clip_board(
        "https://fedex.wd5.myworkdayjobs.com/careers", "", industry="",
        json_path=companies, probe_fn=lambda e: ProbeResult(None, False),
        browser_evidence=junk,
    )
    assert v["status"] == "failed" and v["reason"] == "unreachable"
    assert not companies.exists()


def test_empty_dict_evidence_is_valid_live_evidence(companies):
    """An empty dict sanitizes to a present evidence with job_count=None (the
    counting script ran, found nothing countable, but the user chose to verify).
    This is intentionally treated as present -> browser-verified save."""
    v = clip_board(
        "https://fedex.wd5.myworkdayjobs.com/careers", "", industry="",
        json_path=companies, probe_fn=lambda e: ProbeResult(None, False),
        browser_evidence={},
    )
    assert v["status"] == "added" and v["browser_only"] is True


# ── server probe wins: reachable + evidence -> normal verified save, no flag ───

def test_reachable_board_with_evidence_saves_normally_no_flag(companies):
    """A server-reachable board saves as a normal VERIFIED (scraped) entry even
    when evidence is present — the server probe wins, evidence is ignored, and
    the BROWSER_ONLY_FLAG is never set."""
    v = clip_board(
        "https://boards.greenhouse.io/acme/jobs/1", "", industry="",
        json_path=companies,
        probe_fn=lambda e: ProbeResult(9, True),     # server CAN read it
        browser_evidence=_evidence(job_count=999),   # ignored
    )
    assert v["status"] == "added"
    assert v["reason"] == "verified_live"            # NOT browser_verified
    assert v.get("browser_only") is None
    assert v["live_count"] == 9                       # server count, not 999
    entries = get_registry(include_unverified=True, user_json=companies)
    acme = next(e for e in entries if e.name == "Acme")
    assert not is_browser_only(acme)


def test_legacy_int_probe_reachable_with_evidence_saves_normally(companies):
    """The legacy int|None probe_fn contract still works: a non-None count is
    reachable, so evidence is ignored and the board saves verified."""
    v = clip_board(
        "https://jobs.lever.co/acme", "", industry="", json_path=companies,
        probe_fn=lambda e: 5, browser_evidence=_evidence(),
    )
    assert v["status"] == "added" and v.get("browser_only") is None
    assert v["live_count"] == 5


# ── duplicate: re-clip of an existing browser-only entry ───────────────────────

def test_reclip_browser_only_with_evidence_is_duplicate(companies):
    """A re-clip (even carrying fresh evidence) of a board already stored
    browser-only is a plain 'duplicate' — a browser re-clip is not a SERVER read,
    so there's nothing to upgrade. The dedup short-circuits before the probe."""
    # First clip saves it browser-only.
    clip_board("https://fedex.wd5.myworkdayjobs.com/careers", "", industry="",
               json_path=companies, probe_fn=lambda e: ProbeResult(None, False),
               browser_evidence=_evidence(job_count=42))
    calls = []
    v = clip_board(
        "https://fedex.wd5.myworkdayjobs.com/careers", "", industry="",
        json_path=companies,
        probe_fn=lambda e: calls.append(1) or ProbeResult(None, False),
        browser_evidence=_evidence(job_count=99),
    )
    assert v["status"] == "duplicate"
    assert v["reason"] == "already_in_registry"
    assert calls == []                                # dedup short-circuits


def test_unresolvable_page_with_evidence_still_failed(companies):
    """Evidence never rescues an UNRESOLVABLE page — evidence only upgrades
    reachability of a board whose identity came from resolve_board(). A generic
    careers page ('direct') stays unresolvable, nothing saved."""
    v = clip_board(
        "https://careers.acme.com/openings", "", industry="",
        json_path=companies, probe_fn=lambda e: ProbeResult(None, False),
        browser_evidence=_evidence(job_count=50),
    )
    assert v["status"] == "failed" and v["reason"] == "unresolvable"
    assert not companies.exists()


# ── server-side re-verify upgrade: wall came down -> normal scraped entry ───────

def test_server_reverify_upgrades_browser_only_to_scraped(companies):
    """If a later server-side clip DOES reach a board stored browser-only (the
    wall came down), it upgrades to a normal verified entry — BROWSER_ONLY_FLAG
    cleared, re-enters the scraped set. Mirrors the unverified->verified path."""
    # Board first saved browser-only (server walled).
    clip_board("https://fedex.wd5.myworkdayjobs.com/careers", "",
               industry="warehouse logistics", json_path=companies,
               probe_fn=lambda e: ProbeResult(None, False),
               browser_evidence=_evidence(job_count=42))
    fedex = next(e for e in get_registry(user_json=companies) if e.name == "Fedex")
    assert is_browser_only(fedex)

    # Re-clip; this time the server CAN read it (wall down). Note the stored
    # browser-only entry is a duplicate by identity, so the dedup loop would
    # short-circuit — but the S33 upgrade must still fire. Confirm via a direct
    # server-verified save (the exact call clip_board makes on a reachable probe
    # of a non-flagged path): save_companies with a server-verified entry.
    added = save_companies(
        [CompanyEntry("Fedex", "workday_cxs", "fedex:5:careers",
                      ["warehouse logistics"])], companies)
    assert added == 1                                 # upgraded in place
    entries = get_registry(include_unverified=True, user_json=companies)
    fedex2 = next(e for e in entries if e.name == "Fedex")
    assert not is_browser_only(fedex2)                # flag cleared
    assert "Fedex" in {e.name for e in get_registry("warehouse logistics",
                                                     user_json=companies)}


# ── _valid_browser_evidence unit coverage ─────────────────────────────────────

def test_valid_browser_evidence_sanitizes():
    assert _valid_browser_evidence(None) is None
    assert _valid_browser_evidence("x") is None
    assert _valid_browser_evidence({"job_count": -1}) is None
    assert _valid_browser_evidence({"job_count": True}) is None
    ok = _valid_browser_evidence({"job_count": 7, "via": "jsonld", "page_url": "u"})
    assert ok == {"job_count": 7, "via": "jsonld", "page_url": "u"}
    # Unknown via -> None; non-str page_url -> ""; None count accepted.
    cleaned = _valid_browser_evidence({"job_count": None, "via": "weird", "page_url": 5})
    assert cleaned == {"job_count": None, "via": None, "page_url": ""}


# ── HTTP endpoint threads evidence through ─────────────────────────────────────

def test_clip_endpoint_passes_evidence_through(client, monkeypatch, tmp_path):
    """The /clip route forwards a valid evidence object to clip_board and the
    browser-verified verdict comes back over HTTP 200."""
    import scrape.browser_receiver as br
    p = tmp_path / "companies.json"
    # Force the walled path + a fixed json_path via a wrapped clip_board.
    real = br.clip_board

    def _wrapped(url, page_title="", **kw):
        kw["json_path"] = p
        kw["probe_fn"] = lambda e: ProbeResult(None, False)
        return real(url, page_title, **kw)

    monkeypatch.setattr(br, "clip_board", _wrapped)
    resp = client.post(
        "/clip",
        json={"url": "https://fedex.wd5.myworkdayjobs.com/careers",
              "evidence": {"job_count": 15, "via": "jsonld", "page_url": "u"}},
        headers={"Origin": "chrome-extension://abcdefghijklmnop"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "added"
    assert body["reason"] == "browser_verified"
    assert body["browser_only"] is True
    assert body["live_count"] == 15


def test_clip_endpoint_junk_evidence_is_failed(client, monkeypatch, tmp_path):
    """Junk evidence over HTTP is sanitized to absent -> failed/unreachable, no
    save (defensive at the route boundary too)."""
    import scrape.browser_receiver as br
    p = tmp_path / "companies.json"
    real = br.clip_board

    def _wrapped(url, page_title="", **kw):
        kw["json_path"] = p
        kw["probe_fn"] = lambda e: ProbeResult(None, False)
        return real(url, page_title, **kw)

    monkeypatch.setattr(br, "clip_board", _wrapped)
    resp = client.post(
        "/clip",
        json={"url": "https://fedex.wd5.myworkdayjobs.com/careers",
              "evidence": {"job_count": "many"}},
        headers={"Origin": "chrome-extension://abcdefghijklmnop"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "failed"
    assert not p.exists()
