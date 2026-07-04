"""E1 wiring tests: ats_detect rules, careers_client dispatch routing, jobhive
SEEDABLE extension, funnel enterprise-host extension, and CompanyEntry.extra
round-trip. All offline."""
import json

from scrape.ats_detect import detect_ats
from scrape.company_registry import CompanyEntry, save_companies, _load_user_companies
from scrape.careers_client import CareersClient


# --------------------------------------------------------------------------
# detect_ats host/fingerprint rules
# --------------------------------------------------------------------------
def test_detect_paylocity_all_path():
    assert detect_ats(
        "https://recruiting.paylocity.com/recruiting/jobs/All/abc-123-guid/Acme"
    ) == ("paylocity", "abc-123-guid")


def test_detect_paylocity_guid_tail():
    ats, slug = detect_ats(
        "https://recruiting.paylocity.com/recruiting/jobs/"
        "12345678-1234-1234-1234-1234567890ab/Acme/Controls"
    )
    assert ats == "paylocity"
    assert slug == "12345678-1234-1234-1234-1234567890ab"


def test_detect_eightfold_domain_param():
    assert detect_ats("https://eaton.eightfold.ai/careers?domain=eaton.com") == (
        "eightfold", "eaton:eaton.com")


def test_detect_eightfold_domain_fallback():
    # No domain param -> tenant + '.com' best-effort.
    assert detect_ats("https://albemarle.eightfold.ai/careers") == (
        "eightfold", "albemarle:albemarle.com")


def test_detect_adp_cid():
    assert detect_ats(
        "https://workforcenow.adp.com/mascsr/default/mdf/recruitment/"
        "recruitment.html?cid=f1758074-bb0b-4d6b-8d46-3a90ce325365"
    ) == ("adp", "f1758074-bb0b-4d6b-8d46-3a90ce325365")


def test_detect_oracle_orc():
    assert detect_ats(
        "https://eswt.fa.us6.oraclecloud.com/hcmUI/CandidateExperience/"
        "en/sites/CX_1/requisitions"
    ) == ("oracle_orc", "eswt.fa.us6.oraclecloud.com")


def test_detect_oracle_non_cx_not_orc():
    # An oraclecloud host without a CandidateExperience path is NOT claimed.
    ats, _ = detect_ats("https://something.oraclecloud.com/other")
    assert ats != "oracle_orc"


def test_detect_small_quartet():
    assert detect_ats("https://acme.breezy.hr/") == ("breezy", "acme")
    assert detect_ats("https://acme.pinpointhq.com/") == ("pinpoint", "acme")
    assert detect_ats("https://acme.teamtailor.com/jobs") == ("teamtailor", "acme")
    assert detect_ats("https://acme.applytojob.com/apply") == ("jazzhr", "acme")


def test_detect_phenom_not_autodetected():
    # Phenom lives on careers.*.com which is far too ambiguous to auto-claim.
    ats, _ = detect_ats("https://careers.geaerospace.com/global/en/search-results")
    assert ats != "phenom"


# --------------------------------------------------------------------------
# careers_client dispatch routing (stub each scraper, assert it's called)
# --------------------------------------------------------------------------
def _stub(captured, name):
    def fn(slug, *, keyword="", cache_dir=None, cache_enabled=False, **extra):
        captured[name] = {"slug": slug, "keyword": keyword, "extra": extra}
        return []
    return fn


def _run_dispatch(monkeypatch, tmp_path, attr, ats_type, slug, extra=None):
    import scrape.careers_client as cc
    captured = {}
    monkeypatch.setattr(cc, attr, _stub(captured, attr))
    client = CareersClient(cache_dir=tmp_path, cache_enabled=False, discovery_enabled=False)
    company = CompanyEntry("X", ats_type, slug, [], extra or {})
    client._scrape_one(company, "engineer")
    return captured.get(attr)


def test_dispatch_paylocity(tmp_path, monkeypatch):
    # paylocity is a memoizable ats_type (S35 #24): _scrape_one dispatches it
    # ONCE per company with keyword="" (fetch everything) and re-filters in
    # Python, so the underlying scraper always sees keyword="" here.
    got = _run_dispatch(monkeypatch, tmp_path, "scrape_paylocity", "paylocity", "guid1")
    assert got["slug"] == "guid1" and got["keyword"] == ""


def test_dispatch_eightfold(tmp_path, monkeypatch):
    got = _run_dispatch(monkeypatch, tmp_path, "scrape_eightfold", "eightfold", "eaton:eaton.com")
    assert got["slug"] == "eaton:eaton.com"


def test_dispatch_adp(tmp_path, monkeypatch):
    got = _run_dispatch(monkeypatch, tmp_path, "scrape_adp", "adp", "cid1")
    assert got["slug"] == "cid1"


def test_dispatch_oracle_orc_threads_site(tmp_path, monkeypatch):
    got = _run_dispatch(monkeypatch, tmp_path, "scrape_oracle_orc", "oracle_orc",
                        "host.oraclecloud.com", {"site": "CX_1"})
    assert got["slug"] == "host.oraclecloud.com"
    assert got["extra"].get("site") == "CX_1"


def test_dispatch_phenom_threads_refnum(tmp_path, monkeypatch):
    got = _run_dispatch(monkeypatch, tmp_path, "scrape_phenom", "phenom",
                        "careers.acme.com", {"refNum": "REF1"})
    assert got["slug"] == "careers.acme.com"
    assert got["extra"].get("ref_num") == "REF1"


def test_dispatch_small_quartet(tmp_path, monkeypatch):
    for attr, t in (("scrape_breezy", "breezy"), ("scrape_pinpoint", "pinpoint"),
                    ("scrape_teamtailor", "teamtailor"), ("scrape_jazzhr", "jazzhr")):
        got = _run_dispatch(monkeypatch, tmp_path, attr, t, "acme")
        assert got["slug"] == "acme"


# --------------------------------------------------------------------------
# jobhive SEEDABLE_ATS extension
# --------------------------------------------------------------------------
def test_jobhive_seedable_includes_small_quartet():
    from discover.jobhive_seed import SEEDABLE_ATS
    for t in ("breezy", "pinpoint", "teamtailor", "jazzhr"):
        assert t in SEEDABLE_ATS


def test_jobhive_unseedable_excludes_metadata_atses():
    from discover.jobhive_seed import SEEDABLE_ATS, _UNSEEDABLE_WAVE2_ATS
    # eightfold/oracle/phenom/paylocity/adp need side-channel metadata a CSV row
    # can't carry, so they must NOT be in the bulk-seed set.
    for t in _UNSEEDABLE_WAVE2_ATS:
        assert t not in SEEDABLE_ATS


# --------------------------------------------------------------------------
# funnel enterprise-host extension
# --------------------------------------------------------------------------
def test_funnel_enterprise_hosts_extended():
    from discover.funnel import _ENTERPRISE_ATS_HOSTS
    for h in ("eightfold.ai", "oraclecloud.com", "breezy.hr", "pinpointhq.com",
              "teamtailor.com", "applytojob.com"):
        assert h in _ENTERPRISE_ATS_HOSTS


# --------------------------------------------------------------------------
# CompanyEntry.extra round-trips through companies.json
# --------------------------------------------------------------------------
def test_extra_roundtrips(tmp_path):
    path = tmp_path / "companies.json"
    path.write_text(json.dumps({"companies": []}), encoding="utf-8")
    e = CompanyEntry("UC Health", "oracle_orc", "eswt.fa.us6.oraclecloud.com",
                     ["health_informatics"], {"site": "CX_1"})
    added = save_companies([e], path)
    assert added == 1
    loaded = _load_user_companies(path)
    match = [c for c in loaded if c.name == "UC Health"][0]
    assert match.extra == {"site": "CX_1"}
    # A no-extra entry does not emit an "extra" key (byte-clean output).
    e2 = CompanyEntry("Plain Co", "greenhouse", "plainco", [])
    save_companies([e2], path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    plain = [c for c in raw["companies"] if c.get("name") == "Plain Co"][0]
    assert "extra" not in plain
