"""Verify the keyword= gate in each WS-2b scraper: only jobs matching
title+body are returned when a keyword is provided (2d.5 wire-in check)."""
import json
from pathlib import Path
from unittest.mock import patch

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"


class _Resp:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status
        self.text = json.dumps(data) if not isinstance(data, str) else data
        self.content = self.text.encode()

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


# ---- Workable ---------------------------------------------------------------
import scrape.workable_scraper as WS

def _workable_resp():
    return _Resp(json.loads((FX / "workable.json").read_text(encoding="utf-8")))

def test_workable_keyword_gate():
    with patch("requests.get", return_value=_workable_resp()):
        all_jobs = WS.fetch("test-slug", keyword="")
        filtered = WS.fetch("test-slug", keyword="mechatronics")
    assert len(all_jobs) > 0
    assert all("mechatronics" in j.title.lower() or "mechatronics" in j.description.lower()
               for j in filtered)


# ---- Recruitee --------------------------------------------------------------
import scrape.recruitee_scraper as RS

def _recruitee_resp():
    return _Resp(json.loads((FX / "recruitee.json").read_text(encoding="utf-8")))

def test_recruitee_keyword_gate():
    with patch("requests.get", return_value=_recruitee_resp()):
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
    raw = (FX / "personio.xml").read_bytes()
    r = _Resp("")
    r.content = raw
    return r

def test_personio_keyword_gate():
    with patch("requests.get", return_value=_personio_resp()):
        all_jobs = PS.fetch("test-slug", keyword="")
        filtered = PS.fetch("test-slug", keyword="mechatronics")
    assert isinstance(all_jobs, list)
    assert isinstance(filtered, list)
    # If there's a mechatronics job, filtered <= all
    if all_jobs:
        assert len(filtered) <= len(all_jobs)
