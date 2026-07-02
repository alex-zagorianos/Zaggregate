"""Seed-My-Area Leg B — CareerOneStop Business Finder client + seed pipeline.

This machine has NO CareerOneStop key and every CareerOneStop developer/docs page
403/500s to an automated fetch (see discover/business_finder.py CITATION), so these
are FIXTURE-based: the request path + field mapping are exercised against the
DOCUMENTED response shape, and a recorded-fixture toggle (COS_BF_FIXTURE) makes the
whole thing replayable byte-for-byte the moment Alex drops in one real response.
The downstream half (name -> domain -> ats_detect probe) is validated live in the
build session; here it is exercised via injected fakes so the suite stays offline.
"""
import json

import pytest

import discover.business_finder as bf
from discover.seed_metro import DEFAULT_MAX_EMPLOYERS, SeedResult, seed_my_metro
from scrape.company_registry import CompanyEntry


# ── documented response shape (BusinessList of business records) ──────────────
# Field names per the Business Finder tool docs (find-businesses-help.aspx) — the
# fixture a real key would produce. Kept here so a test failure points straight at
# the mapping if the live shape differs.
_DOC_RESPONSE = {
    "BusinessList": [
        {
            "CompanyName": "St. Luke's Health System",
            "Address1": "190 E Bannock St",
            "City": "Boise", "StateAbbr": "ID", "Zip": "83712",
            "Phone": "208-555-0100", "Naics": "622110",
            "Industry": "General Medical and Surgical Hospitals",
            "WebSite": "https://www.stlukesonline.org", "Distance": "2.1",
        },
        {
            "CompanyName": "No Website Clinic",
            "City": "Boise", "StateAbbr": "ID",
        },
    ],
    "RecordCount": 2,
}


# ── industry -> Business Finder keyword mapping (the documented choice) ────────
@pytest.mark.parametrize("field,expected", [
    ("nursing", "hospital"),        # curated employer-type hint
    ("nurse", "hospital"),
    ("teaching", "school"),
    ("consulting", "consulting"),
    ("warehouse logistics", "warehouse"),   # multi-word, hint on first token
])
def test_keyword_hint_wins(field, expected):
    assert bf._industry_to_keyword(field) == expected


def test_keyword_falls_back_to_synonym_then_raw():
    # data analytics has a query_synonym ("data analyst") in industry_profile.
    assert bf._industry_to_keyword("data analytics") == "data analyst"
    # a field with no hint and no synonym returns the raw text, spaces preserved
    # (it's a search keyword, not an underscore-normalized registry tag).
    assert bf._industry_to_keyword("underwater basket weaving") == "underwater basket weaving"


def test_keyword_empty_field_is_empty():
    assert bf._industry_to_keyword("") == ""
    assert bf._industry_to_keyword("   ") == ""


# ── parse: documented shape -> normalized employer dicts ──────────────────────
def test_parse_documented_shape():
    c = bf.BusinessFinderClient(user_id="U", token="T", cache_enabled=False)
    out = c.parse_businesses(_DOC_RESPONSE)
    assert len(out) == 2
    first = out[0]
    assert first["name"] == "St. Luke's Health System"
    assert first["domain"] == "stlukesonline.org"      # www stripped, registrable host
    assert first["state"] == "ID"
    assert first["zip"] == "83712"
    assert first["naics"] == "622110"
    # a record with no website still parses (domain "" -> pipeline guesses/drop).
    assert out[1]["name"] == "No Website Clinic"
    assert out[1]["domain"] == ""


def test_parse_field_aliases():
    """A casing/spelling variant upstream must not zero a business out."""
    c = bf.BusinessFinderClient(user_id="U", token="T", cache_enabled=False)
    raw = {"Businesses": [{"Name": "Acme", "Url": "acme.com", "State": "OH",
                           "NaicsTitle": "Widgets"}]}
    out = c.parse_businesses(raw)
    assert out[0]["name"] == "Acme"
    assert out[0]["domain"] == "acme.com"
    assert out[0]["state"] == "OH"
    assert out[0]["industry"] == "Widgets"


# ── request URL: documented path-segment shape, ',' escaped ───────────────────
def test_build_url_escapes_location_comma():
    c = bf.BusinessFinderClient(user_id="UID", token="TOK", cache_enabled=False)
    url = c._build_url("hospital", "Cincinnati, OH", 10)
    assert url.startswith(bf.BUSINESS_FINDER_URL.rstrip("/") + "/UID/hospital/")
    assert "Cincinnati%2C%20OH" in url          # comma + space escaped, no path split
    assert url.endswith("/25/10")               # default radius / limit last


# ── key gating: unkeyed = clean self-skip (no raise, one warn) ────────────────
def test_unkeyed_client_self_skips(monkeypatch):
    import config
    monkeypatch.setattr(config, "SECRETS_DIR", None, raising=False)
    monkeypatch.delenv("CAREERONESTOP_USER_ID", raising=False)
    monkeypatch.delenv("CAREERONESTOP_TOKEN", raising=False)
    monkeypatch.setattr(config, "resolve_secret", lambda *a, **k: None)
    c = bf.BusinessFinderClient(cache_enabled=False)
    assert c.has_key() is False
    # returns [] rather than raising; a keyless GUI/CLI path is a no-op.
    assert c.find_employers(industry="nursing", location="Boise, ID") == []


# ── fixture toggle: replay a recorded real response byte-for-byte ─────────────
def test_fixture_toggle_replays(monkeypatch, tmp_path):
    fx = tmp_path / "bf.json"
    fx.write_text(json.dumps(_DOC_RESPONSE), encoding="utf-8")
    monkeypatch.setenv(bf._FIXTURE_ENV, str(fx))
    # even with NO key, the fixture short-circuits the network:
    c = bf.BusinessFinderClient(user_id=None, token=None, cache_enabled=False)
    out = c.find_employers(keyword="hospital", location="Boise, ID")
    assert [e["name"] for e in out] == ["St. Luke's Health System", "No Website Clinic"]


def test_http_error_is_fail_soft(monkeypatch):
    """A non-OK HTTP status returns [] (fail-soft), never raises."""
    c = bf.BusinessFinderClient(user_id="U", token="T", cache_enabled=False)

    class _Resp:
        status_code = 500
        ok = False

    monkeypatch.setattr(c.session, "get", lambda *a, **k: _Resp())
    assert c.find_employers(keyword="x", location="y") == []


# ── seed pipeline: verified-only save, correct tagging, dry-run, no-key ───────
class _FakeBF:
    def __init__(self, employers, key=True):
        self._e = employers
        self._k = key

    def has_key(self):
        return self._k

    def find_employers(self, *, industry="", keyword="", location="", limit=40):
        return list(self._e)


def _fake_rv_factory(verified, dropped):
    captured = {}

    def _rv(cands, tags, *, metro_tag, existing_names):
        captured["tags"] = list(tags)
        captured["cands"] = list(cands)
        captured["existing"] = list(existing_names)
        return verified, dropped

    return _rv, captured


def test_seed_saves_only_verified_and_tags(monkeypatch):
    employers = [
        {"name": "St Lukes", "domain": "stlukesonline.org"},
        {"name": "Dead Co", "domain": "deadco.example"},
        {"name": "No Site", "domain": ""},          # excluded: no domain to resolve
    ]
    verified = [(CompanyEntry("St Lukes", "greenhouse", "stlukes", []), 7)]
    dropped = [({"name": "Dead Co"}, "no live jobs")]
    rv, captured = _fake_rv_factory(verified, dropped)
    saved = {}

    def _save(entries, *a):
        saved["entries"] = list(entries)
        return len(entries)

    res = seed_my_metro(industry="nursing", metro="Boise, ID",
                        client=_FakeBF(employers), resolve_and_verify_fn=rv,
                        save_fn=_save, log=lambda m: None)
    assert res.discovered == 3
    assert res.with_domain == 2           # "No Site" dropped before resolve
    assert res.verified == 1
    assert res.added == 1
    # tag = raw field (token-aware matcher normalizes) + metro tag; NOT underscored.
    assert "nursing" in captured["tags"]
    assert "boise-id" in captured["tags"]
    assert saved["entries"][0].name == "St Lukes"


def test_seed_dry_run_writes_nothing(monkeypatch):
    employers = [{"name": "Acme", "domain": "acme.com"}]
    verified = [(CompanyEntry("Acme", "lever", "acme", []), 3)]
    rv, _ = _fake_rv_factory(verified, [])

    def _save(entries, *a):
        raise AssertionError("save must not be called on a dry run")

    res = seed_my_metro(industry="widgets", metro="X", dry_run=True,
                        client=_FakeBF(employers), resolve_and_verify_fn=rv,
                        save_fn=_save, log=lambda m: None)
    assert res.verified == 1
    assert res.added == 0


def test_seed_no_key_is_honest(monkeypatch):
    res = seed_my_metro(industry="nursing", metro="Boise",
                        client=_FakeBF([], key=False), log=lambda m: None)
    assert res.has_key is False
    assert res.added == 0
    assert "CareerOneStop" in res.note


def test_seed_no_employers_note(monkeypatch):
    res = seed_my_metro(industry="nursing", metro="Boise",
                        client=_FakeBF([]), log=lambda m: None)
    assert res.discovered == 0
    assert res.added == 0
    assert res.note                       # a human explanation, not silent


def test_seed_no_field_or_keyword_note():
    res = seed_my_metro(industry="", metro="", client=_FakeBF([]), log=lambda m: None)
    assert res.added == 0
    assert "nothing to seed" in res.note.lower()


def test_seed_result_as_dict_shape():
    res = SeedResult(industry="nursing", metro="Boise", verified=2, added=2)
    d = res.as_dict()
    assert d["industry"] == "nursing" and d["added"] == 2
    assert "drop_reasons" in d


# ── GUI dialog helpers (no display needed) ────────────────────────────────────
def test_gui_key_check_reflects_secret(monkeypatch):
    import config
    from ui import seed_area
    monkeypatch.setattr(config, "resolve_secret", lambda *a, **k: None)
    assert seed_area._has_careeronestop_key() is False
    monkeypatch.setattr(config, "resolve_secret", lambda *a, **k: "x")
    assert seed_area._has_careeronestop_key() is True


def test_gui_prefill_reads_active_config(monkeypatch):
    import workspace
    from ui import seed_area
    monkeypatch.setattr(workspace, "load_config",
                        lambda *a, **k: {"industry": "nursing", "location": "Boise, ID"})
    assert seed_area._active_field_and_metro() == ("nursing", "Boise, ID")


def test_gui_open_dialog_builds_or_noops(monkeypatch):
    """With a display the dialog builds and is destroyable; with none it returns
    None (the TclError guard). Exercises both the unkeyed and keyed render paths."""
    import config
    import workspace
    from ui import seed_area
    monkeypatch.setattr(workspace, "load_config",
                        lambda *a, **k: {"industry": "nursing", "location": "Boise"})
    for keyed in (False, True):
        monkeypatch.setattr(config, "resolve_secret",
                            lambda *a, _k=keyed, **k: ("x" if _k else None))
        win = seed_area.open_dialog(parent=None)
        if win is None:            # headless CI: clean no-op
            continue
        try:
            assert win.winfo_toplevel() is not None
        finally:
            win.destroy()
