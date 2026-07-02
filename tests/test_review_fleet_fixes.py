"""Regression pins for the post-build adversarial-review fixes (S29).

Covers the confirmed findings:
  * job_key coalescing is CROSS-SOURCE only — two distinct requisitions with
    identical title/company/city on the SAME host stay separate rows
  * MCP set_status rejects unknown statuses (nothing written)
  * credential redaction: URL-borne keys never reach last_run.json / logs
  * rescore uses effective_keywords (industry-only projects stay title-scored)
  * freshness: the repost flag decays; ancient records are evicted
  * undo-dismiss always clears the dismissed marker
"""
import json

import pytest

import tracker.db as db
from models import JobResult


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    return db.DB_PATH


def _job(url, title="Registered Nurse", company="UC Health",
         location="Cincinnati, OH", source="careers", description="", score=80):
    return JobResult(title=title, company=company, location=location,
                     salary_min=None, salary_max=None, description=description,
                     url=url, source_keyword="", created="2026-07-01",
                     source_api=source, score=score)


# -- job_key coalescing: cross-source only --------------------------------------

def test_same_host_distinct_reqs_stay_separate(tmp_db):
    """A hospital posting N identically-titled reqs on ONE board must keep N
    rows — coalescing them silently drops real openings (review critical)."""
    reqs = [_job(f"https://fa-xxxx.fa.ocs.oraclecloud.com/job/{i}") for i in (1, 2, 3)]
    added = db.inbox_add_many(reqs)
    assert added == 3
    assert db.inbox_count() == 3


def test_cross_host_same_posting_still_coalesces(tmp_db):
    a = _job("https://fa-xxxx.fa.ocs.oraclecloud.com/job/1", description="Full JD.")
    b = _job("https://adzuna.example/ad/99", source="adzuna")
    added = db.inbox_add_many([a, b])
    assert added == 1
    rows = db.inbox_all()
    assert len(rows) == 1
    extras = json.loads(rows[0]["extras"] or "{}")
    assert db.normalize_url(b.url) in extras.get("alt_urls", [])


def test_same_host_rule_holds_across_runs(tmp_db):
    db.inbox_add_many([_job("https://fa-x.oraclecloud.com/job/1")])
    # next run: a DIFFERENT req, same board, same title -> its own row
    db.inbox_add_many([_job("https://fa-x.oraclecloud.com/job/2")])
    assert db.inbox_count() == 2


# -- MCP set_status validation ---------------------------------------------------

def test_mcp_set_status_rejects_unknown(tmp_db):
    pytest.importorskip("mcp")
    import mcp_server
    aid = db.add_job(title="Eng", company="Acme", location="",
                     url="https://x/1", status="interested")
    out = mcp_server.set_status(aid, "interviewing")   # not a valid stage
    assert "error" in out
    assert db.get_job(aid)["status"] == "interested"   # nothing written
    ok = mcp_server.set_status(aid, "ghosted")         # new terminal is valid
    assert ok.get("status") == "ghosted"


# -- credential redaction ---------------------------------------------------------

def test_redact_scrubs_url_credentials():
    import applog
    s = applog.redact(
        "500 Server Error for url: https://api.adzuna.com/v1/api/jobs/us/"
        "search?app_id=abc123&app_key=SECRETKEY99&what=nurse "
        "and https://jooble.org/api/VERYSECRETTOKEN")
    assert "SECRETKEY99" not in s
    assert "abc123" not in s
    assert "VERYSECRETTOKEN" not in s
    assert "[redacted]" in s


def test_write_last_run_redacts_errors(tmp_path, monkeypatch):
    import applog
    import workspace
    monkeypatch.setattr(workspace, "project_dir", lambda slug=None: tmp_path)
    p = applog.write_last_run(
        {"errors": ["jooble: 500 for url: https://jooble.org/api/TOPSECRET123"],
         "added": 0}, project_slug=None)
    assert p is not None
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "TOPSECRET123" not in json.dumps(data)


# -- rescore keyword parity (industry-only projects) ------------------------------

def test_rescore_derives_effective_keywords(tmp_db, monkeypatch):
    from scripts import rescore_inbox
    import search.keyword_strategy as ks
    seen = {}

    def fake_effective(cfg):
        seen["cfg"] = cfg
        return ["health informatics"]

    monkeypatch.setattr(ks, "effective_keywords", fake_effective)
    rescore_inbox.rescore(db_path=tmp_db, cfg={"industry": "health informatics"})
    # rescore must derive its scoring keywords the same way daily_run does,
    # instead of reading the raw (empty) cfg['keywords'].
    assert seen["cfg"] == {"industry": "health informatics"}


# -- freshness: repost decay + retention ------------------------------------------

def test_repost_flag_decays(tmp_path):
    import search.freshness as fr
    sid = "t"
    fr.save_keys(sid, {"k"}, base_dir=tmp_path)          # run 1: present
    fr.save_keys(sid, set(), base_dir=tmp_path)          # run 2: absent
    fr.save_keys(sid, {"k"}, base_dir=tmp_path)          # run 3: reappears
    assert fr.repost_info(sid, base_dir=tmp_path)["k"]["repost"] is True
    for _ in range(fr.REPOST_DECAY_RUNS + 1):            # continuously present
        fr.save_keys(sid, {"k"}, base_dir=tmp_path)
    assert fr.repost_info(sid, base_dir=tmp_path)["k"]["repost"] is False


def test_freshness_evicts_ancient_records(tmp_path):
    import search.freshness as fr
    sid = "t2"
    fr.save_keys(sid, {"old", "fresh"}, base_dir=tmp_path)
    path = fr._path(sid, base_dir=tmp_path)
    state = json.loads(path.read_text(encoding="utf-8"))
    state["keys"]["old"]["last_seen"] = "2020-01-01T00:00:00+00:00"
    path.write_text(json.dumps(state), encoding="utf-8")
    fr.save_keys(sid, {"fresh"}, base_dir=tmp_path)      # triggers eviction
    state = json.loads(path.read_text(encoding="utf-8"))
    assert "old" not in state["keys"]
    assert "fresh" in state["keys"]


# -- undo-dismiss always clears the marker -----------------------------------------

def test_restore_dismissed_clears_marker_even_when_row_exists(tmp_db):
    import tracker.service as service
    j = _job("https://boards.example/acme/1")
    db.inbox_add_many([j])
    norm = db.normalize_url(j.url)
    with db.get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO dismissed (url) VALUES (?)", (norm,))
        conn.commit()
    # The row ALREADY exists in the inbox (INSERT OR IGNORE no-op), but the
    # dismissed marker must still be cleared or the row is re-suppressed on
    # every future run (review finding).
    service.restore_dismissed_rows([{"norm_url": norm, "title": j.title,
                                     "company": j.company}])
    with db.get_conn() as conn:
        left = conn.execute("SELECT COUNT(*) c FROM dismissed WHERE url=?",
                            (norm,)).fetchone()["c"]
    assert left == 0
