from pathlib import Path

from search.weworkremotely_client import WeWorkRemotelyClient

FX = Path(__file__).resolve().parents[1] / "fixtures" / "weworkremotely.rss"


def _fixture_bytes() -> bytes:
    return FX.read_bytes()


def _client(tmp_path):
    return WeWorkRemotelyClient(cache_dir=tmp_path, cache_enabled=False)


class _FakeResponse:
    def __init__(self, content: bytes):
        self.content = content

    def raise_for_status(self):
        pass


def _stub_fetch(client, content: bytes):
    client.session.get = lambda *a, **k: _FakeResponse(content)


# ── review r2 F2: a region like "Anywhere in the World" must read as remote so
#    geo/filter doesn't hide these remote-only postings from the default view. ──
def test_region_marked_remote(tmp_path):
    client = _client(tmp_path)
    raw = {"items": [{"title": "Acme: Backend Engineer",
                      "link": "u", "description": "d",
                      "region": "Anywhere in the World", "pubDate": ""}]}
    job = client.parse_results(raw, "backend")[0]
    assert "remote" in job.location.lower()          # "Anywhere in the World (Remote)"
    from geo.filter import classify
    assert classify(job.location, job.title, "Cincinnati, OH") == "remote"


def test_title_splits_on_first_colon(tmp_path):
    client = _client(tmp_path)
    _stub_fetch(client, _fixture_bytes())
    jobs = client.search_and_parse("backend engineer", location="", salary_min=None, page=1)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.company == "Acme Corp"
    assert job.title == "Senior Backend Engineer"
    assert job.source_api == "weworkremotely"
    assert job.location == "Anywhere in the World (Remote)"   # remote-only board
    assert "Senior Backend Engineer" in job.description
    assert "<strong>" not in job.description


def test_colon_less_title_falls_back_to_region_company(tmp_path):
    client = _client(tmp_path)
    _stub_fetch(client, _fixture_bytes())
    jobs = client.search_and_parse("full stack developer", location="", salary_min=None, page=1)
    assert len(jobs) == 1
    job = jobs[0]
    # No ": " in <title> -> whole string is the title, company falls back to
    # <type> (this item has no <region>).
    assert job.title == "Full Stack Developer Wanted"
    assert job.company == "Anywhere in the World"
    assert job.source_api == "weworkremotely"


def test_keyword_filter_excludes_non_matching(tmp_path):
    client = _client(tmp_path)
    _stub_fetch(client, _fixture_bytes())
    jobs = client.search_and_parse("neurosurgeon", location="", salary_min=None, page=1)
    assert jobs == []


def test_keyword_filter_matches_description_when_title_generic(tmp_path):
    client = _client(tmp_path)
    _stub_fetch(client, _fixture_bytes())
    # "Figma" only appears in the Globex item's description, not its title.
    jobs = client.search_and_parse("figma", location="", salary_min=None, page=1)
    assert len(jobs) == 1
    assert jobs[0].company == "Globex"


def test_page_two_is_empty(tmp_path):
    client = _client(tmp_path)
    _stub_fetch(client, _fixture_bytes())
    assert client.search("anything", page=2) == {"items": []}


def test_malformed_xml_returns_empty_list_no_raise(tmp_path):
    client = _client(tmp_path)
    _stub_fetch(client, b"<rss><channel><item><title>Oops</title></not-closed>")
    jobs = client.search_and_parse("anything", location="", salary_min=None, page=1)
    assert jobs == []
