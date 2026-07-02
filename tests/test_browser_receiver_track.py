"""S33 single-port tracking + auto-send: the /track endpoint and the /harvest
open_report flag.

/track lets the popup add its collected jobs straight into the tracker DB as
'interested' via the tracker's OWN add path (tracker.db.add_job) — so a general
user never needs the separate `py -m tracker.app` (port 5001) server. The
embedded receiver resolves the ACTIVE project per-request (init_db opens the
active project's DB) and takes no process-wide pin.

open_report=false on /harvest suppresses the surprise browser tab for the
background auto-send path, while the default (omitted / true) keeps the manual
Send button's report-opening behavior unchanged.
"""
import pytest

import scrape.browser_receiver as br
from scrape.browser_receiver import app
from tracker import db


_EXT_ORIGIN = "chrome-extension://abcdefghijklmnop"


@pytest.fixture
def client():
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture
def track_db(tmp_path, monkeypatch):
    """Point tracker.db at a fresh tmp DB (the same fixture pattern the existing
    tracker tests use) so /track writes never touch real user data."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    return db.DB_PATH


def _job(title="Controls Engineer", company="Acme", **over):
    j = {
        "title": title,
        "company": company,
        "location": "Cincinnati, OH",
        "url": "https://example.com/jobs/1",
        "salary_text": "$90,000 - $110,000",
        "source": "linkedin",
    }
    j.update(over)
    return j


# ── /track: happy path writes 'interested' rows via the real tracker path ──────

def test_track_adds_rows_as_interested(client, track_db):
    resp = client.post(
        "/track",
        json={"jobs": [_job(url="https://example.com/jobs/1"),
                       _job("Nurse", "Mercy", url="https://example.com/jobs/2")]},
        headers={"Origin": _EXT_ORIGIN},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {"added": 2, "failed": 0}

    rows = db.get_all("interested")
    assert {(r["title"], r["company"]) for r in rows} == {
        ("Controls Engineer", "Acme"), ("Nurse", "Mercy")}
    # Fields round-tripped through the tracker's own add path.
    acme = next(r for r in rows if r["company"] == "Acme")
    assert acme["status"] == "interested"
    assert acme["location"] == "Cincinnati, OH"
    assert acme["url"] == "https://example.com/jobs/1"
    assert acme["salary_text"] == "$90,000 - $110,000"
    assert acme["source"] == "linkedin"


def test_track_source_defaults_to_browser(client, track_db):
    resp = client.post(
        "/track", json={"jobs": [_job(source=None)]},
        headers={"Origin": _EXT_ORIGIN},
    )
    assert resp.status_code == 200
    assert resp.get_json()["added"] == 1


def test_track_counts_failures_without_title_or_company(client, track_db):
    """A job missing title or company is counted as failed, not silently added —
    same minimum as tracker.app /api/add."""
    resp = client.post(
        "/track",
        json={"jobs": [
            _job(url="https://example.com/jobs/ok"),          # valid
            _job(title="", url="https://example.com/jobs/x"), # no title
            {"company": "NoTitle"},                            # no title
            _job(company="", url="https://example.com/jobs/y"),  # no company
            "not-a-dict",                                      # junk
        ]},
        headers={"Origin": _EXT_ORIGIN},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["added"] == 1
    assert body["failed"] == 4
    assert len(db.get_all("interested")) == 1


# ── /track: origin gate + malformed body ──────────────────────────────────────

def test_track_rejects_missing_origin(client, track_db):
    resp = client.post("/track", json={"jobs": [_job()]})
    assert resp.status_code == 403
    # Nothing written on a rejected origin.
    assert db.get_all("interested") == []


def test_track_rejects_foreign_origin(client, track_db):
    resp = client.post(
        "/track", json={"jobs": [_job()]},
        headers={"Origin": "https://evil.example.com"},
    )
    assert resp.status_code == 403
    assert db.get_all("interested") == []


def test_track_allows_loopback_origin(client, track_db):
    resp = client.post(
        "/track", json={"jobs": [_job()]},
        headers={"Origin": "http://localhost:5002"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["added"] == 1


def test_track_malformed_body_400(client, track_db):
    resp = client.post(
        "/track", json={"nope": 1}, headers={"Origin": _EXT_ORIGIN})
    assert resp.status_code == 400


def test_track_empty_jobs_400(client, track_db):
    resp = client.post(
        "/track", json={"jobs": []}, headers={"Origin": _EXT_ORIGIN})
    assert resp.status_code == 400


def test_track_options_preflight_ok(client):
    resp = client.open(
        "/track", method="OPTIONS", headers={"Origin": _EXT_ORIGIN})
    assert resp.status_code == 200


# ── /harvest: open_report flag (auto-send suppresses the browser tab) ──────────

def _harvest_body(open_report=None):
    body = {"jobs": [{"title": "Engineer", "company": "Acme",
                      "url": "https://example.com/jobs/1"}]}
    if open_report is not None:
        body["open_report"] = open_report
    return body


@pytest.fixture
def harvest_isolated(monkeypatch, tmp_path):
    """Drive /harvest without real side effects (no report files, no inbox
    writes, no network), returning the list webbrowser.open was called with so a
    test can assert whether a tab would have opened. Mirrors the isolation in
    test_browser_receiver_keywords_a4."""
    import workspace
    monkeypatch.setattr(workspace, "output_dir", lambda: tmp_path)
    monkeypatch.setattr("match.scorer.score_jobs", lambda results, **kw: results)
    monkeypatch.setattr("search.cli.load_user_config", lambda: {})
    monkeypatch.setattr("tracker.db.init_db", lambda: None)
    monkeypatch.setattr("tracker.db.inbox_add_many", lambda scored: 0)
    monkeypatch.setattr(br, "generate_html_report", lambda *a, **k: None)
    monkeypatch.setattr(br, "generate_csv_report", lambda *a, **k: None)
    opened = []
    monkeypatch.setattr(br.webbrowser, "open", lambda u: opened.append(u))
    return opened


def test_harvest_open_report_false_does_not_open_browser(client, harvest_isolated):
    resp = client.post(
        "/harvest", json=_harvest_body(open_report=False),
        headers={"Origin": _EXT_ORIGIN})
    assert resp.status_code == 200
    assert harvest_isolated == []  # background auto-send never throws up a tab


def test_harvest_default_opens_browser(client, harvest_isolated):
    resp = client.post(
        "/harvest", json=_harvest_body(),  # flag omitted -> default True
        headers={"Origin": _EXT_ORIGIN})
    assert resp.status_code == 200
    assert len(harvest_isolated) == 1  # manual send behavior unchanged


def test_harvest_open_report_true_opens_browser(client, harvest_isolated):
    resp = client.post(
        "/harvest", json=_harvest_body(open_report=True),
        headers={"Origin": _EXT_ORIGIN})
    assert resp.status_code == 200
    assert len(harvest_isolated) == 1
