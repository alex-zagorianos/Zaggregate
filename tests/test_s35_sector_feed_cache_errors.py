"""S35 finding #5 (critical): a transient RSS/XML/JSON parse failure inside a
sector-feed client must NOT be cached as if it were a successful empty result
-- that used to silence the whole source for the full cache TTL. Covers all
five sector-feed clients (higheredjobs, rnjobsite, jobsacuk, reap, edjoin) plus
the shared SingleFeedClient._cached() template they route through.

Contract under test, per client:
  * fetch/parse ERROR -> no cache file written, a WARNING is logged (asserted
    via capsys, mirroring tests/discover/test_discoverer_loud.py -- applog's
    console handler echoes WARNING+ records with a "WARNING:" prefix), and the
    exception still propagates (search_engine._run_client's per-keyword catch
    sees it exactly as before).
  * fetch succeeds with a genuinely empty feed -> IS cached (a real empty
    result must not be re-fetched every run).
"""
import pytest
import requests

from search.edjoin_client import EdjoinClient
from search.higheredjobs_client import HigherEdJobsClient
from search.jobsacuk_client import JobsAcUkClient
from search.reap_client import ReapClient
from search.rnjobsite_client import RNJobSiteClient


class _Resp:
    def __init__(self, content=b"", status_code=200):
        self.content = content
        self.text = content.decode("utf-8", "ignore") if isinstance(content, bytes) else content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        import json as _json
        return _json.loads(self.text)


_GOOD_HIGHERED_XML = (
    b'<?xml version="1.0"?><rss version="2.0"><channel><title>H</title>'
    b'</channel></rss>'
)
_BAD_XML = b"<this is not >< valid xml at all"


# ---------------------------------------------------------------------------
# HigherEdJobs
# ---------------------------------------------------------------------------
def test_higheredjobs_parse_error_not_cached_and_warns(tmp_path, monkeypatch, capsys):
    c = HigherEdJobsClient(cache_dir=tmp_path, cache_enabled=True, industry="education")
    assert c.cat_ids  # sanity: education client polls something
    cat_id = c.cat_ids[0]
    monkeypatch.setattr(c.session, "get", lambda *a, **k: _Resp(_BAD_XML))
    with pytest.raises(Exception):
        c._fetch_category(cat_id)
    assert list(tmp_path.rglob("*.json")) == []  # no cache file written
    out = capsys.readouterr().out
    assert "WARNING" in out and "higheredjobs" in out


def test_higheredjobs_empty_success_is_cached(tmp_path, monkeypatch):
    c = HigherEdJobsClient(cache_dir=tmp_path, cache_enabled=True, industry="education")
    cat_id = c.cat_ids[0]
    monkeypatch.setattr(c.session, "get", lambda *a, **k: _Resp(_GOOD_HIGHERED_XML))
    items = c._fetch_category(cat_id)
    assert items == []
    assert list(tmp_path.rglob("*.json"))  # a real empty result IS cached


# ---------------------------------------------------------------------------
# RNJobSite
# ---------------------------------------------------------------------------
_GOOD_RN_XML = (
    b'<?xml version="1.0"?><rss version="2.0"><channel><title>RN</title>'
    b'</channel></rss>'
)


def test_rnjobsite_parse_error_not_cached_and_warns(tmp_path, monkeypatch, capsys):
    c = RNJobSiteClient(cache_dir=tmp_path, cache_enabled=True, industry="nursing")
    monkeypatch.setattr(c.session, "get", lambda *a, **k: _Resp(_BAD_XML))
    with pytest.raises(Exception):
        c._fetch("base", "https://www.rnjobsite.com/rss/jobs")
    assert list(tmp_path.rglob("*.json")) == []
    out = capsys.readouterr().out
    assert "WARNING" in out and "rnjobsite" in out


def test_rnjobsite_empty_success_is_cached(tmp_path, monkeypatch):
    c = RNJobSiteClient(cache_dir=tmp_path, cache_enabled=True, industry="nursing")
    monkeypatch.setattr(c.session, "get", lambda *a, **k: _Resp(_GOOD_RN_XML))
    items = c._fetch("base", "https://www.rnjobsite.com/rss/jobs")
    assert items == []
    assert list(tmp_path.rglob("*.json"))


# ---------------------------------------------------------------------------
# jobs.ac.uk
# ---------------------------------------------------------------------------
_GOOD_JOBSACUK_XML = (
    b'<?xml version="1.0"?><rss version="2.0"><channel><title>J</title>'
    b'</channel></rss>'
)


def test_jobsacuk_parse_error_not_cached_and_warns(tmp_path, monkeypatch, capsys):
    c = JobsAcUkClient(cache_dir=tmp_path, cache_enabled=True, industry="nursing",
                       opt_in=True)
    assert c.areas
    monkeypatch.setattr(c.session, "get", lambda *a, **k: _Resp(_BAD_XML))
    with pytest.raises(Exception):
        c._fetch_area(c.areas[0])
    assert list(tmp_path.rglob("*.json")) == []
    out = capsys.readouterr().out
    assert "WARNING" in out and "jobsacuk" in out


def test_jobsacuk_empty_success_is_cached(tmp_path, monkeypatch):
    c = JobsAcUkClient(cache_dir=tmp_path, cache_enabled=True, industry="nursing",
                       opt_in=True)
    monkeypatch.setattr(c.session, "get", lambda *a, **k: _Resp(_GOOD_JOBSACUK_XML))
    items = c._fetch_area(c.areas[0])
    assert items == []
    assert list(tmp_path.rglob("*.json"))


# ---------------------------------------------------------------------------
# REAP
# ---------------------------------------------------------------------------
def test_reap_parse_error_not_cached_and_warns(tmp_path, monkeypatch, capsys):
    c = ReapClient(cache_dir=tmp_path, cache_enabled=True, industry="education",
                   location="Columbus, OH")
    assert c.portal
    # Force a BeautifulSoup-breaking input: html.parser is very lenient, so
    # simulate the real failure mode by making BeautifulSoup itself raise.
    import search.reap_client as reap_mod
    monkeypatch.setattr(reap_mod, "BeautifulSoup",
                        lambda *a, **k: (_ for _ in ()).throw(ValueError("boom")))
    monkeypatch.setattr(c.session, "get", lambda *a, **k: _Resp(b"<html></html>"))
    with pytest.raises(Exception):
        c._fetch_category(c.portal, 100)
    assert list(tmp_path.rglob("*.json")) == []
    out = capsys.readouterr().out
    assert "WARNING" in out and "reap" in out


def test_reap_empty_success_is_cached(tmp_path, monkeypatch):
    c = ReapClient(cache_dir=tmp_path, cache_enabled=True, industry="education",
                   location="Columbus, OH")
    assert c.portal
    monkeypatch.setattr(c.session, "get", lambda *a, **k: _Resp(b"<html><body></body></html>"))
    rows = c._fetch_category(c.portal, 100)
    assert rows == []
    assert list(tmp_path.rglob("*.json"))


# ---------------------------------------------------------------------------
# EdJoin
# ---------------------------------------------------------------------------
def test_edjoin_non_json_response_not_cached_and_warns(tmp_path, monkeypatch, capsys):
    c = EdjoinClient(cache_dir=tmp_path, cache_enabled=True, industry="education",
                     location="Los Angeles, CA")
    assert c.active
    monkeypatch.setattr(c, "_endpoint_allows", lambda: True)
    # An HTML error/maintenance page served with HTTP 200 -> resp.json() raises.
    monkeypatch.setattr(c.session, "get",
                        lambda *a, **k: _Resp(b"<html>Service Unavailable</html>"))
    with pytest.raises(Exception):
        c.search("teacher", location="Los Angeles, CA", page=1)
    assert list(tmp_path.rglob("*.json")) == []
    out = capsys.readouterr().out
    assert "WARNING" in out and "edjoin" in out


def test_edjoin_empty_success_is_cached(tmp_path, monkeypatch):
    c = EdjoinClient(cache_dir=tmp_path, cache_enabled=True, industry="education",
                     location="Los Angeles, CA")
    monkeypatch.setattr(c, "_endpoint_allows", lambda: True)
    monkeypatch.setattr(c.session, "get",
                        lambda *a, **k: _Resp(b'{"data": []}'))
    raw = c.search("teacher", location="Los Angeles, CA", page=1)
    assert raw["data"] == []
    assert list(tmp_path.rglob("*.json"))


def test_edjoin_robots_disallow_is_legitimate_empty_and_cached(tmp_path, monkeypatch):
    # A robots.txt disallow is a real "0 rows" outcome, not a parse error -- it
    # must still cache normally (unlike the ValueError-from-json() path above).
    c = EdjoinClient(cache_dir=tmp_path, cache_enabled=True, industry="education",
                     location="Los Angeles, CA")
    monkeypatch.setattr(c, "_endpoint_allows", lambda: False)
    raw = c.search("teacher", location="Los Angeles, CA", page=1)
    assert raw["data"] == []
    assert list(tmp_path.rglob("*.json"))
