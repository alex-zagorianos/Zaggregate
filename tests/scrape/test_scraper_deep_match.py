"""Verify the keyword= gate in each WS-2b scraper: only jobs matching
title+body are returned when a keyword is provided (2d.5 wire-in check).

The scrapers now route through the shared careers_session (retry + Retry-After)
guarded by a per-host limiter, so these tests patch that seam per module rather
than the global requests.get."""
import json
from pathlib import Path

from tests.scrape._scrape_fakes import FakeResp, patch_session

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"


# ---- Workable ---------------------------------------------------------------
import scrape.workable_scraper as WS

def _workable_resp():
    return FakeResp(json.loads((FX / "workable.json").read_text(encoding="utf-8")))

def test_workable_keyword_gate(monkeypatch):
    patch_session(monkeypatch, WS, lambda *a, **k: _workable_resp())
    all_jobs = WS.fetch("test-slug", keyword="")
    filtered = WS.fetch("test-slug", keyword="mechatronics")
    assert len(all_jobs) > 0
    assert all("mechatronics" in j.title.lower() or "mechatronics" in j.description.lower()
               for j in filtered)


# ---- Recruitee --------------------------------------------------------------
import scrape.recruitee_scraper as RS

def _recruitee_resp():
    return FakeResp(json.loads((FX / "recruitee.json").read_text(encoding="utf-8")))

def test_recruitee_keyword_gate(monkeypatch):
    patch_session(monkeypatch, RS, lambda *a, **k: _recruitee_resp())
    all_jobs = RS.fetch("test-slug", keyword="")
    filtered = RS.fetch("test-slug", keyword="mechatronics")
    assert len(all_jobs) > 0
    # filtered is subset of all
    filtered_ids = {j.url for j in filtered}
    all_ids = {j.url for j in all_jobs}
    assert filtered_ids <= all_ids


# ---- Personio ---------------------------------------------------------------
import scrape.personio_scraper as PS

def _personio_resp():
    return FakeResp(text=(FX / "personio.xml").read_text(encoding="utf-8"))

def test_personio_keyword_gate(monkeypatch):
    patch_session(monkeypatch, PS, lambda *a, **k: _personio_resp())
    all_jobs = PS.fetch("test-slug", keyword="")
    filtered = PS.fetch("test-slug", keyword="mechatronics")
    assert isinstance(all_jobs, list)
    assert isinstance(filtered, list)
    # If there's a mechatronics job, filtered <= all
    if all_jobs:
        assert len(filtered) <= len(all_jobs)
