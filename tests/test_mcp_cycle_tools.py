"""MCP application-cycle + resume + skillgap tools (C2 / review P4 item 5).

Direct function-call tests against a temp DB (mirroring the existing MCP tests),
no network, no live AI.
"""
import json

import pytest

pytest.importorskip("mcp")

import mcp_server
import tracker.db as db


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    return db.DB_PATH


def _app(title="Controls Engineer", company="Acme", status="interested",
         description="We need a controls engineer with PLC and C++.", **kw):
    return db.add_job(title=title, company=company, location="Cincinnati, OH",
                      url=kw.pop("url", "https://x/1"), status=status,
                      description=description, **kw)


# ── pipeline ──────────────────────────────────────────────────────────────────

def test_list_and_get_application(tmp_db):
    aid = _app()
    lst = mcp_server.list_applications()
    assert lst and lst[0]["id"] == aid and lst[0]["status"] == "interested"
    full = mcp_server.get_application(aid)
    assert full["description"].startswith("We need")
    assert "days_in_stage" in full


def test_list_applications_status_filter(tmp_db):
    _app(company="A", status="interested", url="https://x/1")
    b = _app(company="B", status="applied", url="https://x/2")
    only = mcp_server.list_applications(status="applied")
    assert [r["id"] for r in only] == [b]


def test_set_status_records_transition(tmp_db):
    aid = _app()
    out = mcp_server.set_status(aid, "applied")
    assert out["status"] == "applied"
    assert db.get_job(aid)["status"] == "applied"


def test_set_follow_up_and_due(tmp_db):
    aid = _app(status="applied")
    mcp_server.set_follow_up(aid, "2000-01-01")   # in the past -> overdue
    due = mcp_server.followups_due()
    assert any(r["id"] == aid and r["due_kind"] == "follow-up" for r in due)


def test_funnel_counts(tmp_db):
    _app(company="A", status="interested", url="https://x/1")
    _app(company="B", status="applied", url="https://x/2")
    f = mcp_server.funnel()
    assert f["interested"] == 1 and f["applied"] == 1 and f["all"] == 2


def test_draft_followup_context(tmp_db):
    aid = _app(status="applied")
    db.update_job(aid, date_applied="2000-01-01", contact="Jane R.")
    ctx = mcp_server.draft_followup_context(aid)
    assert ctx["company"] == "Acme" and ctx["contact"] == "Jane R."
    assert ctx["days_since_applied"] is not None and ctx["days_since_applied"] > 0
    assert "controls engineer" in ctx["jd_snapshot"].lower()


def test_draft_followup_context_missing(tmp_db):
    assert "error" in mcp_server.draft_followup_context(999999)


# ── resume + skillgap ─────────────────────────────────────────────────────────

def test_skill_gap_for_inbox(tmp_db):
    from models import JobResult
    db.inbox_add_many([JobResult(
        title="Controls Engineer", company="Acme", location="Cincinnati, OH",
        salary_min=None, salary_max=None,
        description="Experience with Kubernetes and PyTorch required.",
        url="https://x/1", source_keyword="", created="", source_api="adzuna",
        score=70)])
    iid = db.inbox_all()[0]["id"]
    gap = mcp_server.skill_gap(iid)
    assert "matched" in gap and "missing" in gap
    assert any(t.lower() == "kubernetes" for t in gap["missing"])


def test_skill_gap_missing_row(tmp_db):
    assert "error" in mcp_server.skill_gap(999999)


def test_get_resume_prompt_from_inbox(tmp_db, monkeypatch):
    from models import JobResult
    from resume import service as rsvc
    # build_prompt binds load_experience at import; patch it on the service module.
    monkeypatch.setattr(rsvc, "load_experience",
                        lambda: {"work_experience": "### Controls Engineer\n- built PLC lines",
                                 "skills": "PLC, C++"})
    db.inbox_add_many([JobResult(
        title="Automation Engineer", company="Beta", location="Remote",
        salary_min=None, salary_max=None,
        description="Automate lines. Experience with ROS a plus.",
        url="https://x/2", source_keyword="", created="", source_api="adzuna",
        score=70)])
    iid = db.inbox_all()[0]["id"]
    out = mcp_server.get_resume_prompt(inbox_id=iid)
    assert out["company"] == "Beta"
    assert "JOB POSTING" in out["prompt"] and "Automate lines" in out["prompt"]


def test_get_resume_prompt_requires_an_id(tmp_db):
    assert "error" in mcp_server.get_resume_prompt()


def test_save_resume_writes_docx(tmp_db, tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "out")
    data = {
        "contact": {"name": "Pat", "email": "p@x", "phone": "1", "location": "Cincinnati"},
        "summary": "s", "skills": ["PLC"],
        "experience": [{"company": "Acme", "title": "Eng", "duration": "2y",
                        "location": "OH", "bullets": ["did X"]}],
        "education": [{"institution": "UC", "degree": "BSME", "graduated": "2020",
                       "details": []}],
        "cover_letter": "Dear team,\n\nHi.",
    }
    out = mcp_server.save_resume(json.dumps(data), company="Beta")
    assert "resume_path" in out and out["resume_path"].endswith(".docx")
    from pathlib import Path
    assert Path(out["resume_path"]).exists() and Path(out["cover_path"]).exists()


def test_save_resume_bad_json(tmp_db):
    assert "error" in mcp_server.save_resume("{not json")
