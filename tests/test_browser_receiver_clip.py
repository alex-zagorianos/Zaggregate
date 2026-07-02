"""SB-3 browser clip-to-seed: the /clip endpoint + its pure core (clip_board).

One-click "Add this employer's board to my registry" from the extension. The
receiver resolves a clipped job-posting/board URL to its board root, verifies it
live at clip time, and saves it via the P0-6 gate tagged with the active
project's industry — or returns a clear failure verdict, never silently saving
an unverified/junk board.

All probes and companies.json writes are injected (probe_fn / json_path) so
these tests never touch the network or the real registry.
"""
import pytest

from scrape.browser_receiver import app, clip_board
from scrape.company_registry import (CompanyEntry, UNVERIFIED_FLAG, get_registry,
                                     is_unverified, save_companies)


@pytest.fixture
def client():
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture
def companies(tmp_path):
    return tmp_path / "companies.json"


# ── verdict paths (clip_board core) ───────────────────────────────────────────

def test_clip_resolvable_posting_live_is_added_and_saved(companies):
    """A clipped greenhouse *posting* URL resolves to the board root, probes
    live, and is saved tagged with the active industry."""
    v = clip_board(
        "https://boards.greenhouse.io/acme/jobs/4567890", "Acme Careers",
        industry="mechanical engineering", json_path=companies,
        probe_fn=lambda e: 42,
    )
    assert v["status"] == "added"
    assert v["ats_type"] == "greenhouse"
    assert v["company"] == "Acme"
    assert v["slug"] == "acme"
    assert v["live_count"] == 42
    assert v["industry"] == "mechanical engineering"

    # Actually persisted, tagged, and surfaced by the token-aware matcher.
    names = {c.name for c in get_registry("mechanical engineering", user_json=companies)}
    assert "Acme" in names


def test_clip_direct_board_url_is_added(companies):
    """A clip of the board ROOT (not a posting) works identically."""
    v = clip_board("https://jobs.lever.co/acme", "", industry="",
                   json_path=companies, probe_fn=lambda e: 7)
    assert v["status"] == "added"
    assert (v["ats_type"], v["slug"]) == ("lever", "acme")
    assert v["live_count"] == 7


def test_clip_unreachable_board_is_failed_not_saved(companies):
    """A resolvable ATS whose probe returns None (dead slug / unreachable) is a
    failure verdict and is NOT written — the gate exists to keep these out."""
    v = clip_board("https://jobs.lever.co/deadco/uuid", "", industry="",
                   json_path=companies, probe_fn=lambda e: None)
    assert v["status"] == "failed"
    assert v["reason"] == "unreachable"
    assert v["ats_type"] == "lever"
    # Nothing saved: no companies.json written, so no user entry named Deadco.
    assert not companies.exists()
    assert "Deadco" not in {e.name for e in get_registry(user_json=companies)}


def test_clip_workday_cxs_walled_is_failed_not_saved(companies):
    """A clip of a 422-walled Workday tenant (probe_board -> reachable=False) is a
    failure verdict and is NOT written — same bucket as any unreachable board."""
    from scrape.ats_detect import ProbeResult
    v = clip_board("https://fedex.wd5.myworkdayjobs.com/en-US/careers", "",
                   industry="warehouse logistics", json_path=companies,
                   probe_fn=lambda e: ProbeResult(None, False))
    assert v["status"] == "failed" and v["reason"] == "unreachable"
    assert v["ats_type"] == "workday_cxs"
    assert not companies.exists()


def test_clip_workday_cxs_live_empty_is_added(companies):
    """A clip of a genuinely-live Workday board with 0 open jobs (probe_board ->
    reachable=True, count 0) verifies and IS saved (live_count 0)."""
    from scrape.ats_detect import ProbeResult
    v = clip_board("https://liveco.wd1.myworkdayjobs.com/en-US/External", "",
                   industry="", json_path=companies,
                   probe_fn=lambda e: ProbeResult(0, True))
    assert v["status"] == "added"
    assert v["ats_type"] == "workday_cxs"
    assert v["live_count"] == 0
    assert "Liveco" in {e.name for e in get_registry(user_json=companies)}


@pytest.mark.parametrize("url", [
    "https://www.google.com/search?q=jobs",   # off-board search result
    "https://careers.acme.com/openings",       # generic careers page ('direct')
    "https://en.wikipedia.org/wiki/Cat",       # random page
])
def test_clip_unresolvable_is_failed_not_saved(url, companies):
    """A page that isn't a recognized live board (the 'direct' fallback / junk)
    returns a clear unresolvable failure and is never saved — even though the
    probe_fn here would 'succeed', it's never reached."""
    v = clip_board(url, "", industry="mechanical engineering",
                   json_path=companies, probe_fn=lambda e: 99)
    assert v["status"] == "failed"
    assert v["reason"] == "unresolvable"
    assert v["live_count"] is None
    assert not companies.exists()   # nothing written


@pytest.mark.parametrize("url", ["", "   ", "not-a-url ~~~", "ftp://x/y"])
def test_clip_empty_or_bad_url_is_failed(url, companies):
    v = clip_board(url, "", json_path=companies, probe_fn=lambda e: 5)
    assert v["status"] == "failed"
    assert v["reason"] == "unresolvable"


def test_clip_duplicate_reclip_reports_duplicate(companies):
    """Re-clipping a board already in the registry reports 'duplicate' (not a
    silent 'added 0'), and doesn't re-probe or double-write."""
    clip_board("https://boards.greenhouse.io/acme/jobs/1", "", industry="",
               json_path=companies, probe_fn=lambda e: 5)

    calls = []
    v = clip_board("https://boards.greenhouse.io/acme/jobs/2", "", industry="",
                   json_path=companies,
                   probe_fn=lambda e: calls.append(1) or 5)
    assert v["status"] == "duplicate"
    assert v["reason"] == "already_in_registry"
    assert calls == []   # dedup short-circuits before the live probe


def test_clip_reverifies_unverified_board_clearing_flag(companies):
    """P0-6 re-verify: a board stored flagged-unverified (e.g. it failed its
    add-time probe and was kept anyway) is NOT reported as a dead-end duplicate
    on re-clip — the live probe runs, the flag is cleared, and it re-enters the
    scraped set."""
    # Seed a flagged-unverified greenhouse board directly.
    save_companies([CompanyEntry("Acme", "greenhouse", "acme", [],
                                 {UNVERIFIED_FLAG: True})], companies)
    assert "Acme" not in {c.name for c in get_registry(user_json=companies)}  # excluded

    calls = []
    v = clip_board("https://boards.greenhouse.io/acme/jobs/1", "", industry="",
                   json_path=companies,
                   probe_fn=lambda e: calls.append(1) or 12)
    assert v["status"] == "added"
    assert v["reason"] == "re_verified"
    assert v["live_count"] == 12
    assert calls == [1]                          # the live probe DID run this time
    # Flag cleared and the board is back in the scraped registry.
    entries = get_registry(include_unverified=True, user_json=companies)
    acme = next(e for e in entries if e.name == "Acme")
    assert not is_unverified(acme)
    assert "Acme" in {c.name for c in get_registry(user_json=companies)}


def test_clip_reverify_that_still_fails_stays_unverified(companies):
    """If the re-clip probe ALSO fails, nothing is upgraded — the board stays
    flagged-unverified (never silently scraped)."""
    save_companies([CompanyEntry("Acme", "greenhouse", "acme", [],
                                 {UNVERIFIED_FLAG: True})], companies)
    v = clip_board("https://boards.greenhouse.io/acme/jobs/1", "", industry="",
                   json_path=companies, probe_fn=lambda e: None)
    assert v["status"] == "failed"
    assert v["reason"] == "unreachable"
    entries = get_registry(include_unverified=True, user_json=companies)
    acme = next(e for e in entries if e.name == "Acme")
    assert is_unverified(acme)                    # still gated out


def test_clip_duplicate_detected_by_name_across_slug(companies):
    """Dedup also fires on name (matching save_companies), so a board saved
    under a derived name isn't re-added under a different-cased clip."""
    clip_board("https://jobs.lever.co/acme", "", industry="",
               json_path=companies, probe_fn=lambda e: 3)
    # Same company name 'Acme', different ATS/slug -> still a duplicate by name.
    v = clip_board("https://boards.greenhouse.io/acme", "", industry="",
                   json_path=companies, probe_fn=lambda e: 8)
    assert v["status"] == "duplicate"


# ── industry tagging semantics ────────────────────────────────────────────────

def test_clip_tags_with_active_industry_multiword(companies):
    """The P0-1 case: a multi-word industry tag round-trips through the
    token-aware matcher so the clipped board surfaces for that field."""
    clip_board("https://boards.greenhouse.io/mecheng/jobs/1", "",
               industry="mechanical engineering", json_path=companies,
               probe_fn=lambda e: 4)
    surfaced = {c.name for c in get_registry("mechanical engineering", user_json=companies)}
    assert "Mecheng" in surfaced
    # And it does NOT leak into an unrelated field.
    nursing = {c.name for c in get_registry("nursing", user_json=companies)}
    assert "Mecheng" not in nursing


def test_clip_untagged_when_no_active_industry_is_visible_to_all(companies):
    """No active industry -> the board is saved UNTAGGED, which get_registry
    treats as visible to every search (company_registry semantics)."""
    v = clip_board("https://jobs.lever.co/anyco", "", industry="",
                   json_path=companies, probe_fn=lambda e: 6)
    assert v["status"] == "added"
    for field in ("nursing", "mechanical engineering", "warehouse logistics"):
        names = {c.name for c in get_registry(field, user_json=companies)}
        assert "Anyco" in names, field


def test_clip_added_board_is_verified_not_flagged_unverified(companies):
    """A clip only ever saves VERIFIED boards, so the saved entry must not carry
    the unverified flag (unlike a kept-anyway unreachable paste in the GUI)."""
    clip_board("https://boards.greenhouse.io/acme", "", industry="",
               json_path=companies, probe_fn=lambda e: 5)
    entries = get_registry(include_unverified=True, user_json=companies)
    acme = next(e for e in entries if e.name == "Acme")
    assert not is_unverified(acme)


# ── HTTP endpoint: origin gate + shape ────────────────────────────────────────

def test_clip_endpoint_rejects_missing_origin(client):
    resp = client.post("/clip", json={"url": "https://boards.greenhouse.io/acme"})
    assert resp.status_code == 403


def test_clip_endpoint_rejects_foreign_origin(client):
    resp = client.post(
        "/clip", json={"url": "https://boards.greenhouse.io/acme"},
        headers={"Origin": "https://evil.example.com"},
    )
    assert resp.status_code == 403


def test_clip_endpoint_requires_url(client):
    resp = client.post(
        "/clip", json={"page_title": "x"},
        headers={"Origin": "chrome-extension://abcdefghijklmnop"},
    )
    assert resp.status_code == 400


def test_clip_endpoint_unresolvable_returns_200_failed(client):
    """An unresolvable page is a normal verdict (HTTP 200, status=failed), not a
    server error — so the thin JS renders it without status-code branching."""
    resp = client.post(
        "/clip", json={"url": "https://www.google.com/search?q=jobs"},
        headers={"Origin": "chrome-extension://abcdefghijklmnop"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "failed"
    assert body["reason"] == "unresolvable"


def test_clip_endpoint_options_preflight_ok(client):
    resp = client.open(
        "/clip", method="OPTIONS",
        headers={"Origin": "chrome-extension://abcdefghijklmnop"},
    )
    assert resp.status_code == 200
