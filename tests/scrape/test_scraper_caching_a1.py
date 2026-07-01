"""A1: the five previously-uncached ATS scrapers (workable/recruitee/rippling/
personio/bamboohr) now hit the cache on a second keyword within a run -- a live
board is fetched once, not once per keyword. Fixture-based, no network."""
import json

import pytest

import scrape.bamboohr_scraper as BAM
import scrape.personio_scraper as PER
import scrape.recruitee_scraper as REC
import scrape.rippling_scraper as RIP
import scrape.workable_scraper as WRK
from tests.scrape._scrape_fakes import FakeResp, patch_session


def _counting_session(module, monkeypatch, resp_factory):
    """Patch a scraper module's session so every .get increments a counter and
    returns resp_factory()."""
    calls = {"n": 0}

    def handler(*a, **k):
        calls["n"] += 1
        return resp_factory()

    patch_session(monkeypatch, module, handler)
    return calls


WORKABLE = {"name": "Acme", "jobs": [
    {"title": "Controls Engineer", "description": "PLC and automation.",
     "location": {"city": "Cincinnati", "country": "US"}, "url": "https://x/ABC/",
     "shortcode": "ABC", "published_on": "2026-06-01"}]}

RECRUITEE = {"offers": [
    {"title": "Automation Engineer", "description": "Automate the line.",
     "city": "Cincinnati", "country": "US", "careers_url": "https://x/1",
     "id": 1, "published_at": "2026-06-01", "company_name": "Beta Co"}]}

RIPPLING = [
    {"name": "Test Engineer", "description": "Test rigs.",
     "workLocation": {"label": "Cincinnati, OH"}, "department": {"label": "QA"},
     "url": "https://x/r1", "id": "r1", "createdAt": "2026-06-01"}]

BAMBOO = {"result": [
    {"jobOpeningName": "Controls Engineer", "departmentLabel": "Eng",
     "id": 7, "datePosted": "2026-06-01",
     "location": {"city": "Cincinnati", "state": "OH"}}]}

PERSONIO_XML = (
    "<?xml version='1.0' encoding='UTF-8'?><workzag-jobs>"
    "<position><id>9001</id><name>Embedded Engineer</name>"
    "<office>Cincinnati</office><createdAt>2026-06-01</createdAt>"
    "<jobDescriptions><jobDescription><value>firmware and C</value>"
    "</jobDescription></jobDescriptions></position></workzag-jobs>"
)


@pytest.mark.parametrize("module,fetch,resp_factory,slug", [
    (WRK, WRK.fetch, lambda: FakeResp(WORKABLE), "acme"),
    (REC, REC.fetch, lambda: FakeResp(RECRUITEE), "beta"),
    (RIP, RIP.fetch, lambda: FakeResp(RIPPLING), "gamma"),
    (BAM, BAM.fetch, lambda: FakeResp(BAMBOO), "delta"),
    (PER, PER.fetch, lambda: FakeResp(text=PERSONIO_XML), "epsilon"),
])
def test_second_keyword_reuses_cache(module, fetch, resp_factory, slug,
                                     tmp_path, monkeypatch):
    calls = _counting_session(module, monkeypatch, resp_factory)

    r1 = fetch(slug, keyword="engineer", cache_dir=tmp_path, cache_enabled=True)
    assert calls["n"] == 1                      # cold fetch

    # A second keyword within the same run (fresh cache) must NOT re-fetch.
    r2 = fetch(slug, keyword="engineer", cache_dir=tmp_path, cache_enabled=True)
    assert calls["n"] == 1                      # cache hit, no extra network call
    assert isinstance(r1, list) and isinstance(r2, list)


@pytest.mark.parametrize("module,fetch,slug", [
    (WRK, WRK.fetch, "acme"),
    (REC, REC.fetch, "beta"),
    (RIP, RIP.fetch, "gamma"),
    (BAM, BAM.fetch, "delta"),
    (PER, PER.fetch, "epsilon"),
])
def test_permanent_404_marks_failed_and_skips_refetch(module, fetch, slug,
                                                      tmp_path, monkeypatch):
    calls = _counting_session(module, monkeypatch,
                              lambda: FakeResp(None, status_code=404))
    assert fetch(slug, keyword="x", cache_dir=tmp_path, cache_enabled=True) == []
    assert calls["n"] == 1
    # Second run sees the _FAILED marker and does not re-probe the dead board.
    assert fetch(slug, keyword="x", cache_dir=tmp_path, cache_enabled=True) == []
    assert calls["n"] == 1


@pytest.mark.parametrize("module,fetch,slug,cache_name", [
    (WRK, WRK.fetch, "acme", "workable_acme.json"),
    (REC, REC.fetch, "beta", "recruitee_beta.json"),
    (RIP, RIP.fetch, "gamma", "rippling_gamma.json"),
    (BAM, BAM.fetch, "delta", "bamboohr_delta.json"),
    (PER, PER.fetch, "epsilon", "personio_epsilon.json"),
])
def test_transient_429_does_not_poison(module, fetch, slug, cache_name,
                                       tmp_path, monkeypatch):
    from scrape.cache_helpers import is_failed, read_cache
    calls = _counting_session(module, monkeypatch,
                              lambda: FakeResp(None, status_code=429))
    assert fetch(slug, keyword="x", cache_dir=tmp_path, cache_enabled=True) == []
    # The board must NOT be negative-cached on a transient throttle.
    assert is_failed(read_cache(tmp_path / cache_name)) is not True
    assert fetch(slug, keyword="x", cache_dir=tmp_path, cache_enabled=True) == []
    assert calls["n"] == 2      # both runs actually hit the network (not skipped)
