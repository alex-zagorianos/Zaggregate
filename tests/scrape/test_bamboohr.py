import json
from pathlib import Path

import scrape.bamboohr_scraper as B

FX = Path(__file__).resolve().parents[1] / "fixtures" / "bamboohr_list.json"


def _payload():
    return json.loads(FX.read_text(encoding="utf-8"))


def _stub_fetcher(payload=None):
    data = payload if payload is not None else _payload()
    return lambda url: data


def test_fetch_maps_all_jobs():
    jobs = B.fetch("acme", fetcher=_stub_fetcher())
    assert len(jobs) == 4
    assert all(j.source_api == "careers" for j in jobs)
    assert all(j.board_count == 4 for j in jobs)
    assert all(j.description == "" for j in jobs)


# ── review s26 F2: a null/soft-deleted entry in the result array must be
#    skipped, not crash the whole board. ──
def test_fetch_skips_malformed_entries():
    payload = {"result": [
        {"jobOpeningName": "A", "id": 1},
        None,                                   # soft-deleted row
        {"jobOpeningName": "B", "id": 2},
        "not-a-dict",                           # junk row
    ]}
    jobs = B.fetch("acme", fetcher=_stub_fetcher(payload))
    assert [j.title for j in jobs] == ["A", "B"]   # 2 valid, no raise


def test_fetch_maps_remote_atslocation():
    jobs = B.fetch("acme", fetcher=_stub_fetcher())
    remote = next(j for j in jobs if j.job_id == "bamboohr_1001")
    assert remote.title == "Automation Test Engineer"
    assert remote.location == "Remote"
    assert remote.company == "Acme"
    assert remote.url == "https://acme.bamboohr.com/careers/1001"
    assert remote.created == "2026-06-15"


def test_fetch_maps_city_state_atslocation():
    jobs = B.fetch("acme", fetcher=_stub_fetcher())
    j = next(job for job in jobs if job.job_id == "bamboohr_1002")
    assert j.location == "Cincinnati, OH"
    assert j.created == "2026-06-20"  # falls back to postingDate


def test_fetch_maps_flat_location_fields():
    jobs = B.fetch("acme", fetcher=_stub_fetcher())
    j = next(job for job in jobs if job.job_id == "bamboohr_1003")
    assert j.location == "Dayton, OH"


def test_keyword_filter_matches_title_and_department():
    jobs = B.fetch("acme", keyword="engineer", fetcher=_stub_fetcher())
    titles = {j.title for j in jobs}
    assert titles == {"Automation Test Engineer", "Controls Engineer"}


def test_keyword_filter_empty_keeps_all():
    jobs = B.fetch("acme", keyword="", fetcher=_stub_fetcher())
    assert len(jobs) == 4


def test_malformed_json_returns_empty():
    jobs = B.fetch("acme", fetcher=_stub_fetcher({"unexpected": "shape"}))
    assert jobs == []


def test_empty_result_returns_empty():
    jobs = B.fetch("acme", fetcher=_stub_fetcher({"result": [], "meta": {}}))
    assert jobs == []


def test_non_dict_payload_returns_empty():
    jobs = B.fetch("acme", fetcher=_stub_fetcher(["not", "a", "dict"]))
    assert jobs == []


def test_network_error_fetcher_returns_empty_no_raise():
    def boom(url):
        raise ConnectionError("simulated network failure")

    jobs = B.fetch("acme", fetcher=boom)
    assert jobs == []


def test_string_json_payload_is_parsed():
    jobs = B.fetch("acme", fetcher=lambda url: json.dumps(_payload()))
    assert len(jobs) == 4
