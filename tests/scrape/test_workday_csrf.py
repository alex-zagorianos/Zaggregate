import requests
import scrape.workday_scraper as W
from scrape.company_registry import CompanyEntry

class _Resp:
    def __init__(self, payload=None, *, cookies=None, text=""):
        self._p = payload or {}
        self.text = text
        self.cookies = cookies or {}
        self.status_code = 200
    def raise_for_status(self):
        pass
    def json(self):
        return self._p

def _company():
    return CompanyEntry("Cat", "workday", "cat:5:CaterpillarCareers", [])

def test_prime_session_then_paged(tmp_path, monkeypatch):
    gets, posts = [], []

    class _Sess:
        def __init__(self):
            self.headers = {}
            self.cookies = {}
        def get(self, url, **k):
            gets.append(url)
            return _Resp(text="<html>careers</html>", cookies={"CALYPSO_CSRF_TOKEN": "tok"})
        def post(self, url, **k):
            posts.append(k.get("json", {}))
            offset = k.get("json", {}).get("offset", 0)
            if offset == 0:
                return _Resp({"total": 3,
                              "jobPostings": [{"title": "Controls Engineer", "externalPath": "/job/A_R1",
                                               "locationsText": "Cincinnati, OH", "reqId": "R1"},
                                              {"title": "Tech II", "externalPath": "/job/B_R2",
                                               "locationsText": "Peoria, IL", "reqId": "R2"}]})
            return _Resp({"total": 3,
                          "jobPostings": [{"title": "Welder", "externalPath": "/job/C_R3",
                                           "locationsText": "Peoria, IL", "reqId": "R3"}]})

    monkeypatch.setattr(W, "_make_session", lambda: _Sess())
    jobs = W.scrape_workday(_company(), "engineer", tmp_path, cache_enabled=False)
    assert len(gets) >= 1                 # primed the careers page (CSRF GET)
    assert len(jobs) == 3                 # faceted/offset paging pulled all 3
    assert any(j.title == "Controls Engineer" for j in jobs)
    assert all(j.source_api == "careers" for j in jobs)

def test_prime_failure_falls_back_to_bare_post(tmp_path, monkeypatch):
    class _Sess:
        def __init__(self):
            self.headers = {}
            self.cookies = {}
        def get(self, url, **k):
            raise requests.RequestException("blocked")
        def post(self, url, **k):
            return _Resp({"total": 1,
                          "jobPostings": [{"title": "Controls Engineer", "externalPath": "/job/A_R1",
                                           "locationsText": "Cincinnati, OH", "reqId": "R1"}]})
    monkeypatch.setattr(W, "_make_session", lambda: _Sess())
    jobs = W.scrape_workday(_company(), "engineer", tmp_path, cache_enabled=False)
    assert len(jobs) == 1                 # degraded gracefully to a single bare POST
