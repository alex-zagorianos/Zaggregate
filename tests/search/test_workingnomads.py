import json
from pathlib import Path

from search.workingnomads_client import WorkingNomadsClient

FX = Path(__file__).resolve().parents[1] / "fixtures" / "workingnomads.json"


def _payload():
    return json.loads(FX.read_text(encoding="utf-8"))


def _client(tmp_path):
    return WorkingNomadsClient(cache_dir=tmp_path, cache_enabled=False)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _stub_fetch(client, payload):
    client.session.get = lambda *a, **k: _FakeResponse(payload)


def test_search_and_parse_maps_fields(tmp_path):
    client = _client(tmp_path)
    _stub_fetch(client, _payload())
    jobs = client.search_and_parse("backend engineer", location="", salary_min=None, page=1)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.title == "Senior Backend Engineer"
    assert job.company == "Acme Corp"
    assert job.source_api == "workingnomads"
    assert job.location == "Worldwide"
    assert "Senior Backend Engineer" in job.description
    assert "<strong>" not in job.description


def test_location_defaults_to_remote_when_blank(tmp_path):
    client = _client(tmp_path)
    _stub_fetch(client, _payload())
    jobs = client.search_and_parse("product designer", location="", salary_min=None, page=1)
    assert len(jobs) == 1
    assert jobs[0].location == "Remote"


def test_keyword_filter_excludes_non_matching(tmp_path):
    client = _client(tmp_path)
    _stub_fetch(client, _payload())
    jobs = client.search_and_parse("neurosurgeon", location="", salary_min=None, page=1)
    assert jobs == []


def test_page_two_is_empty(tmp_path):
    client = _client(tmp_path)
    _stub_fetch(client, _payload())
    assert client.search("anything", page=2) == {"jobs": []}


def test_non_list_payload_returns_empty(tmp_path):
    client = _client(tmp_path)
    _stub_fetch(client, {"error": "not a list"})
    jobs = client.search_and_parse("anything", location="", salary_min=None, page=1)
    assert jobs == []


def test_none_payload_returns_empty(tmp_path):
    client = _client(tmp_path)
    _stub_fetch(client, None)
    jobs = client.search_and_parse("anything", location="", salary_min=None, page=1)
    assert jobs == []
