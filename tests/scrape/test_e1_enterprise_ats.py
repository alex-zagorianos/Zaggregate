"""E1 (ATS scraper wave 2) tests: paylocity, eightfold, adp, oracle_orc, phenom,
breezy, pinpoint, teamtailor, jazzhr.

All fixture-based (socket-guarded). Real-response-derived fixtures live in
tests/fixtures/e1/; the teamtailor/jazzhr XML and the two doc-derived shapes are
noted in each scraper's module docstring. Live probes stay OUT of pytest.
"""
import json
from pathlib import Path

import pytest
import requests

from tests.scrape._scrape_fakes import FakeResp as _Resp, patch_session

FX = Path(__file__).resolve().parents[1] / "fixtures" / "e1"


def _json(name):
    return json.loads((FX / name).read_text(encoding="utf-8"))


def _text(name):
    return (FX / name).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Paylocity (simple list)
# --------------------------------------------------------------------------
import scrape.paylocity_scraper as PAY


def test_paylocity_maps(monkeypatch):
    patch_session(monkeypatch, PAY, lambda *a, **k: _Resp(_json("paylocity.json")))
    jobs = PAY.fetch("abc-guid")
    assert len(jobs) == 2
    j = jobs[0]
    assert j.title == "Controls Engineer"
    assert j.company == "Acme Manufacturing"
    assert j.location == "Cincinnati, OH"
    assert j.source_api == "careers"
    assert j.job_id == "paylocity_1001"
    assert j.url.endswith("Controls-Engineer")
    # description folds in requirements + department, tags stripped.
    assert "Allen-Bradley" in j.description and "Engineering" in j.description
    assert "<" not in j.description
    assert j.board_count == 2


def test_paylocity_keyword_filter(monkeypatch):
    patch_session(monkeypatch, PAY, lambda *a, **k: _Resp(_json("paylocity.json")))
    jobs = PAY.fetch("abc-guid", keyword="controls")
    assert [j.title for j in jobs] == ["Controls Engineer"]


def test_paylocity_error_soft(monkeypatch):
    patch_session(monkeypatch, PAY,
                  lambda *a, **k: (_ for _ in ()).throw(requests.RequestException()))
    assert PAY.fetch("abc-guid") == []


def test_paylocity_non_dict_soft(monkeypatch):
    patch_session(monkeypatch, PAY, lambda *a, **k: _Resp([1, 2, 3]))
    assert PAY.fetch("abc-guid") == []


# --------------------------------------------------------------------------
# Eightfold (paginated positions)
# --------------------------------------------------------------------------
import scrape.eightfold_scraper as EF


def _ef_pager(pages):
    """Return a handler that serves eightfold pages by ?start offset."""
    def handler(*a, **k):
        start = int((k.get("params") or {}).get("start", 0))
        idx = start // EF._PAGE
        return _Resp(pages[idx] if idx < len(pages) else {"count": 0, "positions": []})
    return handler


def test_eightfold_maps(monkeypatch):
    data = _json("eightfold.json")
    patch_session(monkeypatch, EF, _ef_pager([data]))
    jobs = EF.fetch("albemarle:albemarle.com")
    assert len(jobs) == 2
    j = jobs[0]
    assert j.title  # non-empty title
    assert j.company == "Albemarle"
    assert j.location  # a location string
    assert j.job_id.startswith("eightfold_")
    assert j.url.startswith("https://albemarle.eightfold.ai/careers/job/")
    # board_count reflects the top-level count, not just this page.
    assert j.board_count == data["count"]


def test_eightfold_pagination(monkeypatch):
    # Two full pages then stop: page0 has _PAGE positions, page1 has 1.
    base = _json("eightfold.json")["positions"][0]
    page0 = {"count": 999, "positions": [dict(base, id=1000 + i) for i in range(EF._PAGE)]}
    page1 = {"count": 999, "positions": [dict(base, id=2001)]}
    patch_session(monkeypatch, EF, _ef_pager([page0, page1]))
    jobs = EF.fetch("acme:acme.com")
    assert len(jobs) == EF._PAGE + 1  # both pages consumed, short page ends it


def test_eightfold_gated_403_soft(monkeypatch):
    patch_session(monkeypatch, EF, lambda *a, **k: _Resp({"message": "Not authorized"}, status_code=403))
    assert EF.fetch("eaton:eaton.com") == []


def test_eightfold_keyword_filter(monkeypatch):
    data = _json("eightfold.json")
    # Force a known title to filter on.
    data["positions"][0]["name"] = "Reliability Engineer"
    data["positions"][1]["name"] = "Chef"
    patch_session(monkeypatch, EF, _ef_pager([data]))
    jobs = EF.fetch("acme:acme.com", keyword="reliability")
    assert [j.title for j in jobs] == ["Reliability Engineer"]


# --------------------------------------------------------------------------
# ADP (paginated jobRequisitions)
# --------------------------------------------------------------------------
import scrape.adp_scraper as ADP


def _adp_pager(pages):
    def handler(*a, **k):
        skip = int((k.get("params") or {}).get("$skip", 0))
        idx = skip // ADP._PAGE
        return _Resp(pages[idx] if idx < len(pages) else {"jobRequisitions": [], "meta": {}})
    return handler


def test_adp_maps(monkeypatch):
    data = _json("adp.json")
    patch_session(monkeypatch, ADP, _adp_pager([data]))
    jobs = ADP.fetch("f1758074-bb0b-4d6b-8d46-3a90ce325365")
    assert len(jobs) == 2
    j = jobs[0]
    assert j.title  # non-empty
    assert j.location  # city, state from requisitionLocations
    assert j.job_id.startswith("adp_")
    assert j.description == ""  # list feed has no body
    assert j.board_count == data["meta"]["totalNumber"]


def test_adp_permanent_404_soft(monkeypatch):
    patch_session(monkeypatch, ADP, lambda *a, **k: _Resp({}, status_code=404))
    assert ADP.fetch("some-cid") == []


def test_adp_keyword_filter(monkeypatch):
    data = _json("adp.json")
    data["jobRequisitions"][0]["requisitionTitle"] = "Investigator"
    data["jobRequisitions"][1]["requisitionTitle"] = "Nurse"
    patch_session(monkeypatch, ADP, _adp_pager([data]))
    jobs = ADP.fetch("cid", keyword="investigator")
    assert [j.title for j in jobs] == ["Investigator"]


# --------------------------------------------------------------------------
# Oracle ORC (paginated requisitionList under items[0])
# --------------------------------------------------------------------------
import scrape.oracle_orc_scraper as ORC


def _orc_pager(pages):
    def handler(*a, **k):
        finder = (k.get("params") or {}).get("finder", "")
        import re
        m = re.search(r"offset=(\d+)", finder)
        offset = int(m.group(1)) if m else 0
        idx = offset // ORC._PAGE
        return _Resp(pages[idx] if idx < len(pages) else {"items": []})
    return handler


def test_oracle_orc_maps(monkeypatch):
    data = _json("oracle_orc.json")
    patch_session(monkeypatch, ORC, _orc_pager([data]))
    jobs = ORC.fetch("eswt.fa.us6.oraclecloud.com", site="CX_1")
    assert len(jobs) == 2
    j = jobs[0]
    assert j.title
    assert j.location
    assert j.job_id.startswith("oracleorc_")
    assert "/sites/CX_1/job/" in j.url
    assert j.board_count == 382


def test_oracle_orc_needs_site(monkeypatch):
    # No site + discovery returns "" -> skip, no network attempted.
    monkeypatch.setattr(ORC, "discover_site_number", lambda host, **k: "")
    assert ORC.fetch("eswt.fa.us6.oraclecloud.com") == []


def test_oracle_orc_discovers_site(monkeypatch):
    data = _json("oracle_orc.json")
    monkeypatch.setattr(ORC, "discover_site_number", lambda host, **k: "CX_1")
    patch_session(monkeypatch, ORC, _orc_pager([data]))
    jobs = ORC.fetch("eswt.fa.us6.oraclecloud.com")
    assert len(jobs) == 2


def test_oracle_orc_permanent_soft(monkeypatch):
    patch_session(monkeypatch, ORC, lambda *a, **k: _Resp({}, status_code=404))
    assert ORC.fetch("host.oraclecloud.com", site="CX_1") == []


def test_oracle_orc_keyword_filter(monkeypatch):
    data = _json("oracle_orc.json")
    data["items"][0]["requisitionList"][0]["Title"] = "Anesthesia Technician"
    data["items"][0]["requisitionList"][1]["Title"] = "Marketing Manager"
    patch_session(monkeypatch, ORC, _orc_pager([data]))
    jobs = ORC.fetch("host.oraclecloud.com", site="CX_1", keyword="anesthesia")
    assert [j.title for j in jobs] == ["Anesthesia Technician"]


# --------------------------------------------------------------------------
# Phenom (POST /widgets)
# --------------------------------------------------------------------------
import scrape.phenom_scraper as PH


def _ph_pager(pages):
    def handler(*a, **k):
        body = json.loads(k.get("data") or "{}")
        frm = int(body.get("from", 0))
        idx = frm // PH._PAGE
        empty = {"refineSearch": {"data": {"jobs": [], "totalHits": 0}}}
        return _Resp(pages[idx] if idx < len(pages) else empty)
    return handler


def test_phenom_maps(monkeypatch):
    data = _json("phenom.json")
    patch_session(monkeypatch, PH, _ph_pager([data]))
    jobs = PH.fetch("careers.geaerospace.com", ref_num="GAOGAYGLOBAL")
    assert len(jobs) == 2
    j = jobs[0]
    assert j.title
    assert j.location
    assert j.job_id.startswith("phenom_")
    assert j.board_count == 3


def test_phenom_needs_refnum(monkeypatch):
    monkeypatch.setattr(PH, "discover_ref_num", lambda dom, **k: "")
    assert PH.fetch("careers.acme.com") == []


def test_phenom_discovers_refnum(monkeypatch):
    data = _json("phenom.json")
    monkeypatch.setattr(PH, "discover_ref_num", lambda dom, **k: "REF")
    patch_session(monkeypatch, PH, _ph_pager([data]))
    assert len(PH.fetch("careers.acme.com")) == 2


def test_phenom_permanent_soft(monkeypatch):
    patch_session(monkeypatch, PH, lambda *a, **k: _Resp({}, status_code=404))
    assert PH.fetch("careers.acme.com", ref_num="REF") == []


def test_phenom_keyword_filter(monkeypatch):
    data = _json("phenom.json")
    data["refineSearch"]["data"]["jobs"][0]["title"] = "Refrigeration Engineer"
    data["refineSearch"]["data"]["jobs"][1]["title"] = "Barista"
    patch_session(monkeypatch, PH, _ph_pager([data]))
    jobs = PH.fetch("careers.acme.com", ref_num="REF", keyword="refrigeration")
    assert [j.title for j in jobs] == ["Refrigeration Engineer"]


# --------------------------------------------------------------------------
# Breezy (simple list)
# --------------------------------------------------------------------------
import scrape.breezy_scraper as BZ


def test_breezy_maps(monkeypatch):
    patch_session(monkeypatch, BZ, lambda *a, **k: _Resp(_json("breezy.json")))
    jobs = BZ.fetch("acme")
    assert len(jobs) == 2
    j = jobs[0]
    assert j.title
    assert j.job_id.startswith("breezy_")
    assert j.source_api == "careers"


def test_breezy_error_soft(monkeypatch):
    patch_session(monkeypatch, BZ,
                  lambda *a, **k: (_ for _ in ()).throw(requests.RequestException()))
    assert BZ.fetch("acme") == []


# --------------------------------------------------------------------------
# Pinpoint (simple list under data)
# --------------------------------------------------------------------------
import scrape.pinpoint_scraper as PP


def test_pinpoint_maps(monkeypatch):
    patch_session(monkeypatch, PP, lambda *a, **k: _Resp(_json("pinpoint.json")))
    jobs = PP.fetch("workwithus")
    assert len(jobs) == 2
    j = jobs[0]
    assert j.title
    assert j.job_id.startswith("pinpoint_")
    assert j.url.startswith("http")


def test_pinpoint_xrw_header(monkeypatch):
    seen = {}

    def handler(*a, **k):
        seen.update(k.get("headers") or {})
        return _Resp(_json("pinpoint.json"))
    patch_session(monkeypatch, PP, handler)
    PP.fetch("acme")
    assert seen.get("X-Requested-With") == "XMLHttpRequest"


def test_pinpoint_error_soft(monkeypatch):
    patch_session(monkeypatch, PP,
                  lambda *a, **k: (_ for _ in ()).throw(requests.RequestException()))
    assert PP.fetch("acme") == []


# --------------------------------------------------------------------------
# Teamtailor (RSS)
# --------------------------------------------------------------------------
import scrape.teamtailor_scraper as TT


def test_teamtailor_maps(monkeypatch):
    patch_session(monkeypatch, TT, lambda *a, **k: _Resp(text=_text("teamtailor.rss")))
    jobs = TT.fetch("acme")
    assert len(jobs) == 2
    j = jobs[0]
    assert j.title == "Senior Controls Engineer"
    assert j.location == "Cincinnati, OH"        # from nested <tt:location><tt:name>
    assert j.url.endswith("senior-controls-engineer")
    assert j.job_id.startswith("teamtailor_")
    assert "PLC" in j.description and "<" not in j.description


def test_teamtailor_keyword_filter(monkeypatch):
    patch_session(monkeypatch, TT, lambda *a, **k: _Resp(text=_text("teamtailor.rss")))
    jobs = TT.fetch("acme", keyword="controls")
    assert [j.title for j in jobs] == ["Senior Controls Engineer"]


def test_teamtailor_error_soft(monkeypatch):
    patch_session(monkeypatch, TT,
                  lambda *a, **k: (_ for _ in ()).throw(requests.RequestException()))
    assert TT.fetch("acme") == []


def test_teamtailor_malformed_soft(monkeypatch):
    patch_session(monkeypatch, TT, lambda *a, **k: _Resp(text="<rss><broken"))
    assert TT.fetch("acme") == []


# --------------------------------------------------------------------------
# JazzHR (applytojob XML — PROVISIONAL doc-derived shape)
# --------------------------------------------------------------------------
import scrape.jazzhr_scraper as JZ


def test_jazzhr_maps(monkeypatch):
    patch_session(monkeypatch, JZ, lambda *a, **k: _Resp(text=_text("jazzhr.xml")))
    jobs = JZ.fetch("acme")
    assert len(jobs) == 2
    j = jobs[0]
    assert j.title == "Automation Engineer"
    assert j.location == "Cincinnati, OH"
    assert j.job_id == "jazzhr_abc123"
    assert j.url.endswith("automation-engineer")
    assert "automation" in j.description.lower()


def test_jazzhr_keyword_filter(monkeypatch):
    patch_session(monkeypatch, JZ, lambda *a, **k: _Resp(text=_text("jazzhr.xml")))
    jobs = JZ.fetch("acme", keyword="automation")
    assert [j.title for j in jobs] == ["Automation Engineer"]


def test_jazzhr_error_soft(monkeypatch):
    patch_session(monkeypatch, JZ,
                  lambda *a, **k: (_ for _ in ()).throw(requests.RequestException()))
    assert JZ.fetch("acme") == []
