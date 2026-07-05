"""Apply Queue API (Phase 4): ranked ordering, resume prompt/paste, batch flows,
API generate (409 without a key), AI fit rank prompt/reply, single-flight, download
traversal-lock, and 403s on every mutating route.

claude_bridge parsers and the Anthropic-calling seams are monkeypatched for
deterministic, offline outputs; ordering is asserted against seeded interested rows.
"""
import pytest

import workspace
from tracker import db


_LOOPBACK = "http://127.0.0.1:5002"
_H = {"Origin": _LOOPBACK}


@pytest.fixture(autouse=True)
def _active_slug(monkeypatch):
    monkeypatch.setattr(workspace, "active_slug", lambda: "projA")


@pytest.fixture(autouse=True)
def _reset_queue_locks():
    from webui.api import queue as q
    with q._locks_guard:
        q._project_locks.clear()
    yield
    with q._locks_guard:
        q._project_locks.clear()


def _add(status="interested", **kw):
    """Seed an interested application; score/fit_score go through add_job's **extra."""
    fields = dict(title=kw.pop("title", "Job"), company=kw.pop("company", "Acme"),
                  location=kw.pop("location", "Remote"),
                  url=kw.pop("url", "https://x/1"),
                  salary_text=kw.pop("salary_text", ""), source="adzuna",
                  status=status)
    jid = db.add_job(**fields, **kw)
    return jid


# ── ordering ──────────────────────────────────────────────────────────────────

def test_queue_ranked_fit_then_score_desc(client, tmp_db):
    """Ordering = fit_score desc, then score desc (fit-else-score), mirroring
    ApplyQueueTab.refresh's ``(fit_score or -1, score or -1)`` reverse sort."""
    a = _add(title="low-fit-high-score", score=95)                 # fit None
    b = _add(title="high-fit", url="https://x/2", score=10)
    db.update_job(b, fit_score=90)
    c = _add(title="mid-fit", url="https://x/3", score=50)
    db.update_job(c, fit_score=40)

    rows = client.get("/api/queue").get_json()["rows"]
    titles = [r["title"] for r in rows]
    # fit rows first (90, 40) then the fit-less row (falls to -1) ordered by score.
    assert titles == ["high-fit", "mid-fit", "low-fit-high-score"]


def test_queue_row_has_ats_referral_docs(client, tmp_db, monkeypatch):
    from match import ats_hint
    from tracker import service
    monkeypatch.setattr(ats_hint, "ats_label", lambda url: "Greenhouse")
    monkeypatch.setattr(service, "referral_hint",
                        lambda company: "You know 1 person at Acme")
    _add(title="J", url="https://boards.greenhouse.io/acme/1", resume_path="/out/r.docx")
    row = client.get("/api/queue").get_json()["rows"][0]
    assert row["ats_label"] == "Greenhouse"
    assert row["referral"] == "You know 1 person at Acme"
    assert row["docs_path"] == "/out/r.docx"


# ── single-job resume prompt / paste ──────────────────────────────────────────

def test_resume_prompt_ok(client, tmp_db, monkeypatch):
    jid = _add(title="Sr Eng", description="Build distributed systems.")
    monkeypatch.setattr("resume.service.build_prompt",
                        lambda posting: f"PROMPT::{posting[:20]}")
    resp = client.get(f"/api/queue/{jid}/resume-prompt")
    assert resp.status_code == 200
    assert resp.get_json()["prompt"].startswith("PROMPT::Title: Sr Eng")


def test_resume_prompt_no_description_400(client, tmp_db):
    jid = _add(title="No Desc", description="")
    resp = client.get(f"/api/queue/{jid}/resume-prompt")
    assert resp.status_code == 400
    assert "description" in resp.get_json()["error"]


def test_resume_prompt_unknown_404(client, tmp_db):
    assert client.get("/api/queue/99999/resume-prompt").status_code == 404


# ── copy pack (B7 item 5) ──────────────────────────────────────────────────────

def _write_experience(tmp_path, monkeypatch, body):
    exp = tmp_path / "experience.md"
    exp.write_text(body, encoding="utf-8")
    monkeypatch.setattr(workspace, "experience_file", lambda slug=None: exp)
    return exp


def test_copy_pack_ok_with_contact_and_resume(client, tmp_db, monkeypatch, tmp_path):
    _write_experience(tmp_path, monkeypatch,
                      "## CONTACT\n\n- Name: Jane Doe\n- Email: jane@example.com\n"
                      "- Phone: 555-0100\n- Location: Cincinnati, OH\n\n"
                      "## WORK EXPERIENCE\n\n### Engineer, Acme\n\n"
                      "## EDUCATION\n\n- B.S. ME, State U\n")
    monkeypatch.setattr(workspace, "load_config", lambda slug=None: {})
    jid = _add(title="Sr Eng", company="Acme", resume_path="C:/out/jane_acme.docx")
    resp = client.get(f"/api/queue/{jid}/copy-pack")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    text = body["text"]
    assert "Name: Jane Doe" in text
    assert "jane@example.com" in text
    assert "Engineer, Acme" in text
    assert "B.S. ME, State U" in text
    assert "jane_acme.docx" in text


def test_copy_pack_missing_fields_grace(client, tmp_db, monkeypatch, tmp_path):
    """A sparse experience + no resume path yields a clean pack — no placeholder junk."""
    _write_experience(tmp_path, monkeypatch,
                      "## CONTACT\n\n- Name:\n- Email:\n")
    monkeypatch.setattr(workspace, "load_config", lambda slug=None: {})
    jid = _add(title="Sr Eng", company="Acme")  # no resume_path
    text = client.get(f"/api/queue/{jid}/copy-pack").get_json()["text"]
    assert "(unknown)" not in text
    assert "-- Tailored resume --" not in text
    assert "APPLICATION COPY PACK" in text


def test_copy_pack_missing_experience_file_still_builds(client, tmp_db, monkeypatch,
                                                        tmp_path):
    """No experience.md on disk -> the route degrades to an empty-section pack, not
    a 500 (best-effort, like the B4 enrichment pattern)."""
    monkeypatch.setattr(workspace, "experience_file",
                        lambda slug=None: tmp_path / "does_not_exist.md")
    monkeypatch.setattr(workspace, "load_config", lambda slug=None: {})
    jid = _add(title="Sr Eng", company="Acme")
    resp = client.get(f"/api/queue/{jid}/copy-pack")
    assert resp.status_code == 200
    assert "APPLICATION COPY PACK" in resp.get_json()["text"]


def test_copy_pack_unknown_404(client, tmp_db):
    assert client.get("/api/queue/99999/copy-pack").status_code == 404


def test_resume_from_paste_saves_and_returns_downloads(client, tmp_db, monkeypatch,
                                                       tmp_path):
    jid = _add(title="Sr Eng", company="Acme", description="desc")
    monkeypatch.setattr("claude_bridge.parse_resume_response",
                        lambda text: {"resume": "ok"})
    r = tmp_path / "resume_acme.docx"
    c = tmp_path / "cover_acme.docx"
    r.write_text("R")
    c.write_text("C")
    monkeypatch.setattr("resume.service.save_bundle_from_data",
                        lambda data, out, company="": (r, c))
    resp = client.post(f"/api/queue/{jid}/resume-from-paste", headers=_H,
                       json={"text": "REPLY"})
    assert resp.status_code == 200
    files = resp.get_json()["files"]
    assert {f["name"] for f in files} == {"resume_acme.docx", "cover_acme.docx"}
    assert files[0]["download_url"] == "/api/queue/download/resume_acme.docx"
    # resume_path persisted on the application
    assert db.get_job(jid)["resume_path"] == str(r)


def test_resume_from_paste_parse_error_400(client, tmp_db, monkeypatch):
    from claude_bridge import BridgeParseError
    jid = _add(description="desc")

    def boom(text):
        raise BridgeParseError("could not parse reply")
    monkeypatch.setattr("claude_bridge.parse_resume_response", boom)
    resp = client.post(f"/api/queue/{jid}/resume-from-paste", headers=_H,
                       json={"text": "junk"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "could not parse reply"


def test_resume_from_paste_real_parser_truncated_400(client, tmp_db):
    """The route surfaces a REAL BridgeParseError (not a monkeypatched stand-in):
    feed the genuine parser a truncated reply (mirrors tests/test_claude_bridge.py
    ::test_resume_truncated_reply_raises_clearly) and assert the route lifts the
    parser's own message via str(e). No parser patch — this guards the actual
    exception→400 wiring against a change in how e's message is extracted."""
    jid = _add(description="desc")
    truncated = '{"contact": {"name": "Pat"}, "summary": "s", "skills": ["a"'
    resp = client.post(f"/api/queue/{jid}/resume-from-paste", headers=_H,
                       json={"text": truncated})
    assert resp.status_code == 400
    assert "cut off" in resp.get_json()["error"]


# ── batch prompt / paste ──────────────────────────────────────────────────────

def test_batch_prompt_default_top5_needing_docs(client, tmp_db, monkeypatch):
    """Default batch = queue jobs without a resume AND with a description, capped
    at 5. A job with a resume, or without a description, is excluded."""
    _add(title="need1", url="https://x/1", description="d1", score=90)
    _add(title="have-docs", url="https://x/2", description="d2", score=80,
         resume_path="/out/x.docx")                       # excluded: already has docs
    _add(title="no-desc", url="https://x/3", description="", score=70)  # excluded
    _add(title="need2", url="https://x/4", description="d4", score=60)

    monkeypatch.setattr("resume.service.build_batch_prompt",
                        lambda postings: f"BATCH::{len(postings)}")
    resp = client.post("/api/queue/batch-prompt", headers=_H, json={})
    body = resp.get_json()
    assert body["prompt"] == "BATCH::2"
    # ids are in queue (score desc) order, only the two needing docs
    assert len(body["ids"]) == 2


def test_batch_prompt_nothing_qualifies_400(client, tmp_db):
    _add(title="hasdocs", description="d", resume_path="/out/x.docx")
    assert client.post("/api/queue/batch-prompt", headers=_H,
                       json={}).status_code == 400


def test_batch_from_paste_saves_matched_slots(client, tmp_db, monkeypatch, tmp_path):
    id1 = _add(title="A", company="Acme", url="https://x/1", description="d1")
    id2 = _add(title="B", company="Beta", url="https://x/2", description="d2")
    # slots 1,2 map to ids[0], ids[1]
    monkeypatch.setattr("claude_bridge.parse_batch_resume_response",
                        lambda text: {1: {"n": 1}, 2: {"n": 2}})
    made = {}

    def fake_save(data, out, company=""):
        p = tmp_path / f"resume_{company}.docx"
        p.write_text("x")
        made[company] = p
        return p, None
    monkeypatch.setattr("resume.service.save_bundle_from_data", fake_save)

    resp = client.post("/api/queue/batch-from-paste", headers=_H,
                       json={"text": "REPLY", "ids": [id1, id2]})
    assert resp.status_code == 200
    results = resp.get_json()["results"]
    assert {r["id"] for r in results} == {id1, id2}
    assert all("files" in r for r in results)
    assert db.get_job(id1)["resume_path"].endswith("resume_Acme.docx")


def test_batch_from_paste_out_of_range_slot_ignored(client, tmp_db, monkeypatch,
                                                    tmp_path):
    id1 = _add(title="A", company="Acme", description="d1")
    # slot 5 is out of the ids range (1 id) -> ignored, no crash
    monkeypatch.setattr("claude_bridge.parse_batch_resume_response",
                        lambda text: {1: {"n": 1}, 5: {"n": 5}})
    p = tmp_path / "r.docx"
    p.write_text("x")
    monkeypatch.setattr("resume.service.save_bundle_from_data",
                        lambda data, out, company="": (p, None))
    resp = client.post("/api/queue/batch-from-paste", headers=_H,
                       json={"text": "R", "ids": [id1]})
    assert resp.status_code == 200
    assert len(resp.get_json()["results"]) == 1


def test_batch_from_paste_parse_error_400(client, tmp_db, monkeypatch):
    from claude_bridge import BridgeParseError

    def boom(text):
        raise BridgeParseError("bad batch")
    monkeypatch.setattr("claude_bridge.parse_batch_resume_response", boom)
    resp = client.post("/api/queue/batch-from-paste", headers=_H,
                       json={"text": "x", "ids": [1]})
    assert resp.status_code == 400


def test_batch_from_paste_real_parser_no_valid_objects_400(client, tmp_db):
    """Real parser, no stand-in: a JSON array whose objects all lack the mandatory
    echoed "i" yields zero usable entries -> parse_batch_resume_response raises
    "No valid resume objects found…" (mirrors test_batch_no_positional_fallback…);
    the route must surface it as 400 with the parser's real message."""
    import json
    jid = _add(company="Acme", description="d")
    # A well-formed resume object but WITHOUT the required "i" -> skipped -> empty.
    obj = {
        "contact": {"name": "Pat", "email": "", "phone": "", "location": ""},
        "summary": "s", "skills": ["python"],
        "experience": [{"company": "X", "title": "Eng", "bullets": ["b"]}],
        "education": [{"institution": "Y", "degree": "BS"}],
        "cover_letter": "c",
    }
    resp = client.post("/api/queue/batch-from-paste", headers=_H,
                       json={"text": json.dumps([obj]), "ids": [jid]})
    assert resp.status_code == 400
    assert "No valid resume objects" in resp.get_json()["error"]


# ── server-side API generate ──────────────────────────────────────────────────

def test_generate_409_without_key(client, tmp_db, monkeypatch):
    monkeypatch.setattr("resume.service.api_available", lambda: False)
    jid = _add(description="d")
    resp = client.post(f"/api/queue/{jid}/generate", headers=_H)
    assert resp.status_code == 409
    assert resp.get_json()["error"] == "no api key"


def test_generate_with_key_saves(client, tmp_db, monkeypatch, tmp_path):
    monkeypatch.setattr("resume.service.api_available", lambda: True)
    jid = _add(title="Sr", company="Acme", description="d")
    r = tmp_path / "resume_acme.docx"
    r.write_text("R")
    monkeypatch.setattr("resume.service.save_bundle",
                        lambda posting, out, company="": (r, None))
    resp = client.post(f"/api/queue/{jid}/generate", headers=_H)
    assert resp.status_code == 200
    assert resp.get_json()["files"][0]["name"] == "resume_acme.docx"
    assert db.get_job(jid)["resume_path"] == str(r)


def test_generate_no_description_400(client, tmp_db, monkeypatch):
    monkeypatch.setattr("resume.service.api_available", lambda: True)
    jid = _add(description="")
    assert client.post(f"/api/queue/{jid}/generate",
                       headers=_H).status_code == 400


def test_generate_unknown_404(client, tmp_db, monkeypatch):
    monkeypatch.setattr("resume.service.api_available", lambda: True)
    assert client.post("/api/queue/99999/generate",
                       headers=_H).status_code == 404


# ── AI fit rank ───────────────────────────────────────────────────────────────

def test_rank_prompt_builds_from_compact(client, tmp_db, monkeypatch):
    from tracker import service
    from models import JobResult

    kept = JobResult(title="A", company="Acme", location="", salary_min=None,
                     salary_max=None, description="", url="https://x/1",
                     source_keyword="", created="", job_id="7")

    def fake_compact(rows, prefs=None, cfg=None):
        return ("FITPROMPT", [kept],
                [{"id": 9, "title": "Z", "company": "Zed",
                  "reasons": ["internship"]}])
    monkeypatch.setattr(service, "compact_fit_prompt_for_rows", fake_compact)
    _add(title="A", url="https://x/1", score=50)

    resp = client.post("/api/queue/rank", headers=_H, json={"mode": "prompt"})
    body = resp.get_json()
    assert body["prompt"] == "FITPROMPT"
    assert body["ids"] == [7]
    assert body["dropped"][0]["reasons"] == ["internship"]


def test_rank_prompt_all_filtered_returns_empty(client, tmp_db, monkeypatch):
    from tracker import service
    monkeypatch.setattr(service, "compact_fit_prompt_for_rows",
                        lambda rows, prefs=None, cfg=None: ("", [],
                        [{"id": 1, "title": "x", "company": "y",
                          "reasons": ["clearance"]}]))
    _add(title="A", url="https://x/1")
    resp = client.post("/api/queue/rank", headers=_H, json={"mode": "prompt"})
    body = resp.get_json()
    assert body["ok"] is True
    assert body["prompt"] == "" and body["ids"] == []
    assert body["dropped"][0]["reasons"] == ["clearance"]


def test_rank_reply_applies_scores(client, tmp_db, monkeypatch):
    from tracker import service
    from models import JobResult
    kept = JobResult(title="A", company="Acme", location="", salary_min=None,
                     salary_max=None, description="", url="https://x/1",
                     source_keyword="", created="", job_id="1")
    monkeypatch.setattr(service, "compact_fit_prompt_for_rows",
                        lambda rows, prefs=None, cfg=None: ("P", [kept], []))
    applied = {}
    monkeypatch.setattr(service, "score_applications_from_reply",
                        lambda jobs, reply: applied.setdefault("n", len(jobs)) or 1)
    _add(title="A", url="https://x/1")
    resp = client.post("/api/queue/rank", headers=_H,
                       json={"mode": "reply", "text": "AI reply"})
    assert resp.get_json() == {"ok": True, "applied": 1}
    assert applied["n"] == 1


def test_rank_reply_parse_error_400(client, tmp_db, monkeypatch):
    from tracker import service
    from claude_bridge import BridgeParseError
    from models import JobResult
    kept = JobResult(title="A", company="Acme", location="", salary_min=None,
                     salary_max=None, description="", url="https://x/1",
                     source_keyword="", created="", job_id="1")
    monkeypatch.setattr(service, "compact_fit_prompt_for_rows",
                        lambda rows, prefs=None, cfg=None: ("P", [kept], []))

    def boom(jobs, reply):
        raise BridgeParseError("bad fit reply")
    monkeypatch.setattr(service, "score_applications_from_reply", boom)
    _add(title="A", url="https://x/1")
    resp = client.post("/api/queue/rank", headers=_H,
                       json={"mode": "reply", "text": "x"})
    assert resp.status_code == 400


def test_rank_reply_real_parser_error_400(client, tmp_db, monkeypatch):
    """Real fit parser (score_applications_from_reply -> parse_fit_response), no
    stand-in: only the prompt-set builder is patched (it reaches into match/ and
    isn't under test). A JSON array whose objects carry no "fit" score yields no
    valid scores -> BridgeParseError("No valid job scores…"); the route must
    surface it as 400 with the parser's real message."""
    import json
    from tracker import service
    from models import JobResult
    kept = JobResult(title="A", company="Acme", location="", salary_min=None,
                     salary_max=None, description="", url="https://x/1",
                     source_keyword="", created="", job_id="1")
    monkeypatch.setattr(service, "compact_fit_prompt_for_rows",
                        lambda rows, prefs=None, cfg=None: ("P", [kept], []))
    _add(title="A", url="https://x/1")
    # Valid JSON, but every entry lacks the mandatory "fit" key -> all skipped.
    reply = json.dumps([{"i": 1, "why": "no score here"}])
    resp = client.post("/api/queue/rank", headers=_H,
                       json={"mode": "reply", "text": reply})
    assert resp.status_code == 400
    assert "No valid job scores" in resp.get_json()["error"]


def test_rank_unknown_mode_400(client, tmp_db):
    assert client.post("/api/queue/rank", headers=_H,
                       json={"mode": "bogus"}).status_code == 400


# ── single-flight on the API-calling routes ───────────────────────────────────

def test_generate_single_flight_busy_409(client, tmp_db, monkeypatch):
    """A second generate while one holds the project lock returns 409 busy."""
    monkeypatch.setattr("resume.service.api_available", lambda: True)
    jid = _add(description="d")

    from webui.api import queue as q
    # Pre-acquire the project lock to simulate an in-flight generate/rank.
    lock = q._project_lock("projA")
    lock.acquire()
    try:
        resp = client.post(f"/api/queue/{jid}/generate", headers=_H)
        assert resp.status_code == 409
        assert resp.get_json()["error"] == "busy"
    finally:
        lock.release()


# ── download traversal-lock ───────────────────────────────────────────────────

def test_queue_download_serves_real_file(client, _isolate_output_dir):
    out = _isolate_output_dir
    (out / "resume_acme.docx").write_text("DOCX")
    resp = client.get("/api/queue/download/resume_acme.docx")
    assert resp.status_code == 200
    assert resp.get_data() == b"DOCX"


def test_queue_download_traversal_404(client, _isolate_output_dir):
    resp = client.get("/api/queue/download/..%2f..%2fsecret.txt")
    assert resp.status_code == 404


def test_queue_download_missing_404(client, _isolate_output_dir):
    assert client.get("/api/queue/download/nope.docx").status_code == 404


# ── 403s on mutating routes ───────────────────────────────────────────────────

@pytest.mark.parametrize("method,path,body", [
    ("post", "/api/queue/1/resume-from-paste", {"text": "x"}),
    ("post", "/api/queue/batch-prompt", {}),
    ("post", "/api/queue/batch-from-paste", {"text": "x", "ids": [1]}),
    ("post", "/api/queue/1/generate", None),
    ("post", "/api/queue/rank", {"mode": "prompt"}),
])
def test_queue_mutating_routes_headerless_403(client, method, path, body):
    resp = getattr(client, method)(path, json=body)
    assert resp.status_code == 403
