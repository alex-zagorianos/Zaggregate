"""Inbox triage mutations + the AI round-trip (export / download / import /
score-reply) + bulk dismiss/undo, undo-rerank, single-row fit.

All mutating routes are origin-gated; happy paths send a loopback Origin, and the
header-less 403 is asserted on at least one mutating route per concern. The export
download is locked to the export dir — a traversal attempt must 404, never leak.
"""
import io
import json

from models import JobResult
from tracker import db, service


_LOOPBACK = "http://127.0.0.1:5002"
_H = {"Origin": _LOOPBACK}


def _job(url, *, title="Software Developer", company="Acme", score=70,
         description="controls", source_api="adzuna"):
    return JobResult(title=title, company=company, location="Cincinnati, OH",
                     salary_min=None, salary_max=None, description=description,
                     url=url, source_keyword="", created="2026-06-21",
                     source_api=source_api, score=score)


def _seed(n=1):
    db.inbox_add_many([_job(f"https://x/{i}", company=f"C{i}") for i in range(n)])
    return [r["id"] for r in db.inbox_all()]


# ── bulk dismiss + undo round-trip ────────────────────────────────────────────

def test_bulk_dismiss_and_undo_round_trip(client, tmp_db):
    ids = _seed(3)
    resp = client.post("/api/inbox/dismiss-bulk", headers=_H,
                       json={"ids": ids})
    body = resp.get_json()
    assert resp.status_code == 200 and body["ok"] is True
    assert body["dismissed"] == 3
    assert db.inbox_count() == 0
    token = body["undo_token"]

    undo = client.post("/api/inbox/undo-dismiss", headers=_H,
                       json={"undo_token": token})
    ubody = undo.get_json()
    assert ubody["ok"] is True and ubody["restored"] == 3
    assert db.inbox_count() == 3


def test_bulk_dismiss_skips_unknown_ids(client, tmp_db):
    ids = _seed(2)
    resp = client.post("/api/inbox/dismiss-bulk", headers=_H,
                       json={"ids": ids + [999999]})
    assert resp.get_json()["dismissed"] == 2      # unknown id skipped, no error
    assert db.inbox_count() == 0


def test_undo_dismiss_no_token_pops_latest(client, tmp_db):
    ids = _seed(1)
    client.post("/api/inbox/dismiss-bulk", headers=_H, json={"ids": ids})
    undo = client.post("/api/inbox/undo-dismiss", headers=_H, json={})
    assert undo.get_json()["restored"] == 1


def test_undo_dismiss_nothing_to_undo(client, tmp_db):
    undo = client.post("/api/inbox/undo-dismiss", headers=_H, json={})
    assert undo.get_json() == {"ok": True, "restored": 0}


def test_bulk_dismiss_headerless_403(client, tmp_db):
    ids = _seed(1)
    resp = client.post("/api/inbox/dismiss-bulk", json={"ids": ids})
    assert resp.status_code == 403
    assert db.inbox_count() == 1      # nothing dismissed


# ── single-row fit ────────────────────────────────────────────────────────────

def test_set_fit(client, tmp_db):
    rid = _seed(1)[0]
    resp = client.post(f"/api/inbox/{rid}/fit", headers=_H,
                       json={"fit": 77, "why": "good overlap"})
    assert resp.status_code == 200 and resp.get_json() == {"ok": True}
    row = {r["id"]: r for r in db.inbox_all()}[rid]
    assert row["fit"] == 77 and row["fit_why"] == "good overlap"


def test_set_fit_unknown_404(client, tmp_db):
    assert client.post("/api/inbox/999999/fit", headers=_H,
                       json={"fit": 5}).status_code == 404


def test_set_fit_bad_value_400(client, tmp_db):
    rid = _seed(1)[0]
    assert client.post(f"/api/inbox/{rid}/fit", headers=_H,
                       json={"fit": "abc"}).status_code == 400


# ── undo-rerank ───────────────────────────────────────────────────────────────

def test_undo_rerank_calls_service(client, tmp_db, monkeypatch):
    calls = {}

    def fake_undo(scope):
        calls["scope"] = scope
        return 4
    monkeypatch.setattr(service, "undo_last_rerank", fake_undo)
    resp = client.post("/api/inbox/undo-rerank", headers=_H)
    assert resp.get_json() == {"ok": True, "restored": 4}
    assert calls["scope"] == "any"        # tk parity: undo across ALL routes


# ── export -> download (traversal locked) ─────────────────────────────────────

def test_export_then_download(client, tmp_db):
    _seed(2)
    resp = client.post("/api/inbox/export", headers=_H,
                       json={"scope": "all", "fmt": "csv"})
    body = resp.get_json()
    assert resp.status_code == 200 and body["ok"] is True
    assert body["count"] == 2
    names = [f["name"] for f in body["files"]]
    # csv + prompt always written; no md for fmt=csv.
    assert any(n.endswith("ranking_export.csv") for n in names)
    assert any(n.endswith("prompt.md") for n in names)

    url = next(f["download_url"] for f in body["files"]
               if f["name"].endswith(".csv"))
    dl = client.get(url)
    assert dl.status_code == 200
    assert b"job_key" in dl.data           # the export CSV carrier column


def test_export_nothing_400(client, tmp_db):
    assert client.post("/api/inbox/export", headers=_H,
                       json={"scope": "all"}).status_code == 400


def test_download_traversal_404(client, tmp_db):
    # A path that tries to climb out of the export dir must 404, never serve.
    for bad in ("..%2f..%2f..%2fconfig.py", "../../conftest.py",
                "nonexistent/ranking_export.csv"):
        resp = client.get(f"/api/inbox/export/download/{bad}")
        assert resp.status_code == 404, bad


def test_export_headerless_403(client, tmp_db):
    _seed(1)
    assert client.post("/api/inbox/export", json={"scope": "all"}).status_code == 403


# ── import (file + paste + bad file) ──────────────────────────────────────────

def _csv_for(rows_by_key, fit=91):
    """A minimal AI-return CSV keyed on the first row's job_key."""
    key = next(iter(rows_by_key))
    return f"job_key,new_fit,fit_rationale\n{key},{fit},strong match\n"


def test_import_file_upload(client, tmp_db):
    _seed(1)
    rows_by_key = service.inbox_rows_by_key()
    csv_text = _csv_for(rows_by_key)
    data = {"policy": "overwrite",
            "file": (io.BytesIO(csv_text.encode("utf-8")), "scores.csv")}
    resp = client.post("/api/inbox/import", headers=_H, data=data,
                       content_type="multipart/form-data")
    res = resp.get_json()["result"]
    assert resp.status_code == 200
    assert res["matched"] == 1 and res["updated"] == 1
    assert res["unmatched"] == 0 and res["errors"] == []


def test_import_text_paste(client, tmp_db):
    _seed(1)
    rows_by_key = service.inbox_rows_by_key()
    resp = client.post("/api/inbox/import", headers=_H,
                       json={"text": _csv_for(rows_by_key), "policy": "overwrite"})
    res = resp.get_json()["result"]
    assert res["matched"] == 1 and res["updated"] == 1


def test_import_bad_file_surfaces_errors_not_500(client, tmp_db):
    _seed(1)
    data = {"file": (io.BytesIO(b"total garbage, not a csv or json"), "junk.csv")}
    resp = client.post("/api/inbox/import", headers=_H, data=data,
                       content_type="multipart/form-data")
    assert resp.status_code == 200          # not a 500
    res = resp.get_json()["result"]
    assert res["errors"]                    # the parse failure is REPORTED
    assert res["updated"] == 0


def test_import_unmatched_reported(client, tmp_db):
    _seed(1)
    resp = client.post("/api/inbox/import", headers=_H, json={
        "text": "job_key,new_fit\nNO_SUCH_KEY,80\n", "policy": "overwrite"})
    res = resp.get_json()["result"]
    assert res["unmatched"] == 1 and res["matched"] == 0


def test_import_no_input_400(client, tmp_db):
    assert client.post("/api/inbox/import", headers=_H, json={}).status_code == 400


def test_import_headerless_403(client, tmp_db):
    assert client.post("/api/inbox/import",
                       json={"text": "x"}).status_code == 403


# ── score-reply (clipboard bridge) ────────────────────────────────────────────

def test_score_reply_applies(client, tmp_db, monkeypatch):
    _seed(2)
    # Stub the engine seam so the test is deterministic and doesn't depend on the
    # exact prompt/parse machinery (exercised in the engine's own tests).
    monkeypatch.setattr(service, "unscored_inbox_rows",
                        lambda rows, **k: rows)
    fake_jobs = [object(), object()]
    monkeypatch.setattr(service, "compact_fit_prompt_for_rows",
                        lambda rows, **k: ("prompt", fake_jobs, []))
    monkeypatch.setattr(service, "score_inbox_from_reply",
                        lambda jobs, text, *, source: (2, []))
    resp = client.post("/api/inbox/score-reply", headers=_H,
                       json={"text": "1. 90\n2. 85"})
    body = resp.get_json()
    assert body == {"ok": True, "applied": 2, "asked": 2, "missed": 0}


def test_score_reply_no_text_400(client, tmp_db):
    assert client.post("/api/inbox/score-reply", headers=_H,
                       json={}).status_code == 400


def test_score_reply_parse_error_400(client, tmp_db, monkeypatch):
    from claude_bridge import BridgeParseError
    _seed(1)
    monkeypatch.setattr(service, "unscored_inbox_rows", lambda rows, **k: rows)
    monkeypatch.setattr(service, "compact_fit_prompt_for_rows",
                        lambda rows, **k: ("p", [object()], []))

    def boom(*a, **k):
        raise BridgeParseError("cannot parse reply")
    monkeypatch.setattr(service, "score_inbox_from_reply", boom)
    resp = client.post("/api/inbox/score-reply", headers=_H,
                       json={"text": "junk"})
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False


def test_score_reply_headerless_403(client, tmp_db):
    assert client.post("/api/inbox/score-reply",
                       json={"text": "x"}).status_code == 403
