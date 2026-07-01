"""Tests for Workday CSRF priming + offset paging (WS-2b).
CSRF priming still uses a bare requests.get (patched here); the jobs POST now
goes through the shared retry/Retry-After session (_make_session), so that is
patched via a fake session whose .post replays the scripted responses."""
import requests
import scrape.workday_scraper as W
from scrape.company_registry import CompanyEntry


class _FakePostSession:
    def __init__(self, post_fn):
        self._post_fn = post_fn
    def post(self, *a, **k):
        return self._post_fn(*a, **k)


def _patch_post(monkeypatch, post_fn):
    monkeypatch.setattr(W, "_make_session", lambda *a, **k: _FakePostSession(post_fn))


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


def test_prime_csrf_then_paged(tmp_path, monkeypatch):
    """CSRF GET fires once, then offset paging pulls all 3 jobs."""
    gets, posts = [], []
    post_call = {"n": 0}

    def fake_get(url, **k):
        gets.append(url)
        r = _Resp(text="<html>careers</html>", cookies={"CALYPSO_CSRF_TOKEN": "tok"})
        return r

    def fake_post(url, **k):
        offset = (k.get("json") or {}).get("offset", 0)
        posts.append(offset)
        post_call["n"] += 1
        if offset == 0:
            # First page: _PAGE_LIMIT jobs so paging triggers
            jobs = [
                {"title": f"Job {i}", "externalPath": f"/job/R{i}", "locationsText": "Cincinnati, OH", "reqId": f"R{i}"}
                for i in range(W._PAGE_LIMIT)
            ]
            return _Resp({"total": W._PAGE_LIMIT + 1, "jobPostings": jobs})
        # Second page: 1 job (short page → end)
        return _Resp({"total": W._PAGE_LIMIT + 1,
                      "jobPostings": [{"title": "Last Job", "externalPath": "/job/Rlast",
                                       "locationsText": "Cincinnati, OH", "reqId": "Rlast"}]})

    monkeypatch.setattr(requests, "get", fake_get)
    _patch_post(monkeypatch, fake_post)

    jobs = W.scrape_workday(_company(), "engineer", tmp_path, cache_enabled=False)
    assert len(gets) >= 1                          # CSRF GET fired
    assert len(jobs) == W._PAGE_LIMIT + 1          # full first page + 1 overflow job
    assert any(j.title == "Last Job" for j in jobs)
    assert all(j.source_api == "careers" for j in jobs)


def test_prime_failure_falls_back_to_bare_post(tmp_path, monkeypatch):
    """CSRF GET fails; scraper still POSTs and returns the single result."""
    def fail_get(url, **k):
        raise requests.RequestException("blocked")

    def fake_post(url, **k):
        return _Resp({"total": 1,
                      "jobPostings": [{"title": "Controls Engineer", "externalPath": "/job/A_R1",
                                       "locationsText": "Cincinnati, OH", "reqId": "R1"}]})

    monkeypatch.setattr(requests, "get", fail_get)
    _patch_post(monkeypatch, fake_post)

    jobs = W.scrape_workday(_company(), "engineer", tmp_path, cache_enabled=False)
    assert len(jobs) == 1                          # degraded gracefully to a single bare POST
