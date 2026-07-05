"""Outreach prompt routes on the applications blueprint (B5).

* GET /api/applications/<id>/followup-prompt        follow-up vs thank-you select
* GET /api/applications/<id>/interview-prep-prompt   experience-grounded prep
Both are reads (not origin-gated) returning {ok, prompt}; unknown id → 404.
Mirrors tests/webui/test_network.py's style (client + tmp_db + service seeding).
"""
import pytest

import config
import workspace


@pytest.fixture(autouse=True)
def _tmp_experience(tmp_path, monkeypatch):
    """Isolate the experience.md the interview-prep route reads so the mining
    assertions are deterministic and no real user data is touched."""
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)
    exp = tmp_path / "experience.md"
    exp.write_text(
        "## EDUCATION\nB.S. ME, State Polytechnic University\n\n"
        "## WORK EXPERIENCE\nControls Engineer, Globex Corporation, 2019-2023\n",
        encoding="utf-8")
    monkeypatch.setattr(workspace, "experience_file", lambda slug=None: exp)
    return tmp_path


# ── follow-up / thank-you prompt ───────────────────────────────────────────────

def test_followup_prompt_is_followup_for_a_fresh_application(client, tmp_db):
    from tracker import service
    app_id = service.add_manual_job(title="Backend Engineer", company="Globex",
                                    status="applied")
    r = client.get(f"/api/applications/{app_id}/followup-prompt")
    body = r.get_json()
    assert r.status_code == 200 and body["ok"] is True
    assert body["stage"] == "followup"
    assert "post-application follow-up" in body["prompt"]
    assert "exactly ONE follow-up" in body["prompt"]
    assert "Globex" in body["prompt"]


def test_followup_prompt_is_thank_you_after_an_interview_round(client, tmp_db):
    from tracker import service
    app_id = service.add_manual_job(title="Backend Engineer", company="Globex",
                                    status="applied")
    # Adding a round advances status AND is itself a thank-you trigger.
    service.add_interview_round(app_id, kind="onsite", interviewer="Dana",
                                scheduled_at="2026-07-01")
    r = client.get(f"/api/applications/{app_id}/followup-prompt")
    body = r.get_json()
    assert r.status_code == 200 and body["ok"] is True
    assert body["stage"] == "thank_you"
    assert "THANK-YOU" in body["prompt"]
    assert "within 24 hours" in body["prompt"]
    # Round context grounds the note.
    assert "Dana" in body["prompt"]


def test_followup_prompt_thank_you_by_status_without_a_round(client, tmp_db):
    from tracker import service
    app_id = service.add_manual_job(title="PM", company="Acme",
                                    status="interview")
    body = client.get(f"/api/applications/{app_id}/followup-prompt").get_json()
    assert body["stage"] == "thank_you"


def test_followup_prompt_unknown_id_404(client, tmp_db):
    r = client.get("/api/applications/987654/followup-prompt")
    assert r.status_code == 404
    assert r.get_json()["ok"] is False


# ── interview prep prompt ──────────────────────────────────────────────────────

def test_interview_prep_prompt_folds_in_experience(client, tmp_db):
    from tracker import service
    app_id = service.add_manual_job(
        title="Senior Controls Engineer", company="Acme Robotics",
        location="Cincinnati, OH")
    r = client.get(f"/api/applications/{app_id}/interview-prep-prompt")
    body = r.get_json()
    assert r.status_code == 200 and body["ok"] is True
    assert "Senior Controls Engineer" in body["prompt"]
    assert "Ten practice questions" in body["prompt"]
    assert "Red flags to listen for" in body["prompt"]
    # The isolated experience.md flowed in.
    assert "Globex Corporation" in body["prompt"]
    assert "State Polytechnic University" in body["prompt"]


def test_interview_prep_prompt_unknown_id_404(client, tmp_db):
    r = client.get("/api/applications/987654/interview-prep-prompt")
    assert r.status_code == 404
    assert r.get_json()["ok"] is False
