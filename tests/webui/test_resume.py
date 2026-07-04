"""Resume Generator API (Phase 4): prompt build, paste -> DOCX downloads, parse
error 400, download traversal-lock, and 403s on the mutating routes.

claude_bridge / resume.service seams are monkeypatched for offline determinism.
"""
import pytest

import workspace


_LOOPBACK = "http://127.0.0.1:5002"
_H = {"Origin": _LOOPBACK}


@pytest.fixture(autouse=True)
def _active_slug(monkeypatch):
    monkeypatch.setattr(workspace, "active_slug", lambda: "projA")


# ── prompt ────────────────────────────────────────────────────────────────────

def test_resume_prompt_ok(client, monkeypatch):
    monkeypatch.setattr("resume.service.build_prompt",
                        lambda posting: f"PROMPT::{posting}")
    resp = client.post("/api/resume/prompt",
                       json={"posting_text": "Sr Engineer at Acme"})
    assert resp.status_code == 200
    assert resp.get_json()["prompt"] == "PROMPT::Sr Engineer at Acme"


def test_resume_prompt_empty_400(client):
    resp = client.post("/api/resume/prompt", json={"posting_text": "  "})
    assert resp.status_code == 400
    assert "posting" in resp.get_json()["error"]


def test_resume_prompt_build_error_400(client, monkeypatch):
    def boom(posting):
        raise ValueError("Job posting is empty.")
    monkeypatch.setattr("resume.service.build_prompt", boom)
    resp = client.post("/api/resume/prompt", json={"posting_text": "x"})
    assert resp.status_code == 400


# ── paste -> DOCX downloads ───────────────────────────────────────────────────

def test_resume_from_paste_returns_downloads(client, monkeypatch, _isolate_output_dir):
    out = _isolate_output_dir
    r = out / "resume_2026.docx"
    c = out / "cover_letter_2026.docx"
    r.write_text("R")
    c.write_text("C")
    monkeypatch.setattr("resume.service.data_from_paste", lambda text: {"ok": 1})
    monkeypatch.setattr("resume.service.save_bundle_from_data",
                        lambda data, output_dir: (r, c))
    resp = client.post("/api/resume/from-paste", headers=_H,
                       json={"reply_text": "REPLY"})
    assert resp.status_code == 200
    files = resp.get_json()["files"]
    assert {f["name"] for f in files} == {"resume_2026.docx", "cover_letter_2026.docx"}
    assert files[0]["download_url"] == "/api/resume/download/resume_2026.docx"


def test_resume_from_paste_no_reply_400(client):
    assert client.post("/api/resume/from-paste", headers=_H,
                       json={"reply_text": ""}).status_code == 400


def test_resume_from_paste_parse_error_400(client, monkeypatch):
    from claude_bridge import BridgeParseError

    def boom(text):
        raise BridgeParseError("could not parse")
    monkeypatch.setattr("resume.service.data_from_paste", boom)
    resp = client.post("/api/resume/from-paste", headers=_H,
                       json={"reply_text": "junk"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "could not parse"


def test_resume_from_paste_docx_error_500(client, monkeypatch):
    monkeypatch.setattr("resume.service.data_from_paste", lambda text: {"ok": 1})

    def boom(data, output_dir):
        raise RuntimeError("docx render failed")
    monkeypatch.setattr("resume.service.save_bundle_from_data", boom)
    resp = client.post("/api/resume/from-paste", headers=_H,
                       json={"reply_text": "R"})
    assert resp.status_code == 500


# ── download traversal-lock (shared webui.downloads) ──────────────────────────

def test_resume_download_serves_real_file(client, _isolate_output_dir):
    (_isolate_output_dir / "resume_x.docx").write_text("DOCX")
    resp = client.get("/api/resume/download/resume_x.docx")
    assert resp.status_code == 200 and resp.get_data() == b"DOCX"


def test_resume_download_traversal_404(client, _isolate_output_dir):
    assert client.get("/api/resume/download/..%2f..%2fetc%2fpasswd").status_code == 404


def test_resume_download_missing_404(client, _isolate_output_dir):
    assert client.get("/api/resume/download/nope.docx").status_code == 404


# ── 403s ──────────────────────────────────────────────────────────────────────

def test_resume_from_paste_headerless_403(client):
    assert client.post("/api/resume/from-paste",
                       json={"reply_text": "x"}).status_code == 403


def test_resume_prompt_is_read_only_no_gate(client, monkeypatch):
    """/resume/prompt is READ-only (no side effect) -> not origin-gated, so a
    header-less call still works (mirrors the tk prompt build having no write)."""
    monkeypatch.setattr("resume.service.build_prompt", lambda posting: "P")
    resp = client.post("/api/resume/prompt", json={"posting_text": "x"})
    assert resp.status_code == 200
