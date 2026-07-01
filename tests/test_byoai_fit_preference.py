"""De-Alex the prompt (C2 / review P4 item 6).

fit_preference is a per-profile bias sentence, default '' = NEUTRAL. Empty means
no bias sentence appears on ANY route (bridge/API compact + file/schema). A set
preference is woven through unchanged.
"""
import models
import preferences
import ranker
from rerank import schema


def _job(url="https://x.co/1"):
    return models.JobResult(
        title="Controls Engineer", company="Acme", location="Cincinnati, OH",
        salary_min=100000, salary_max=None, description="C++ motion control",
        url=url, source_keyword="", created="", source_api="test")


# ── preferences.load exposes fit_preference ───────────────────────────────────

def test_load_defaults_fit_preference_empty(tmp_path):
    prefs = preferences.load(prefs_md=str(tmp_path / "nope.md"),
                             prefs_json=str(tmp_path / "nope.json"))
    assert prefs["fit_preference"] == ""


def test_load_reads_fit_preference(tmp_path):
    import json
    j = tmp_path / "preferences.json"
    j.write_text(json.dumps({"fit_preference": "Prefers remote-only roles."}),
                 encoding="utf-8")
    prefs = preferences.load(prefs_md=str(tmp_path / "nope.md"), prefs_json=str(j))
    assert prefs["fit_preference"] == "Prefers remote-only roles."


# ── ranker.build_request threads the preference (empty => no bias) ────────────

def test_build_request_neutral_by_default():
    prefs = {"profile_md": "controls roles", "hard": {}, "fit_preference": ""}
    req = ranker.build_request([_job()], prefs=prefs, experience_summary="C++")
    assert "smaller companies" not in req
    assert "__PREFERENCE__" not in req


def test_build_request_weaves_preference():
    prefs = {"profile_md": "controls roles", "hard": {},
             "fit_preference": "Bias toward mission-driven nonprofits."}
    req = ranker.build_request([_job()], prefs=prefs, experience_summary="C++")
    assert "mission-driven nonprofits" in req


def test_build_compact_request_weaves_preference():
    prefs = {"profile_md": "controls roles", "hard": {},
             "fit_preference": "Bias toward mission-driven nonprofits."}
    req = ranker.build_compact_request([_job()], prefs=prefs, cfg={})
    assert "mission-driven nonprofits" in req


def test_build_compact_request_neutral_by_default():
    prefs = {"profile_md": "controls roles", "hard": {}, "fit_preference": ""}
    req = ranker.build_compact_request([_job()], prefs=prefs, cfg={})
    assert "smaller companies" not in req
    assert "__PREFERENCE__" not in req


# ── file route (schema.build_prompt) derives the same sentence ────────────────

def test_schema_prompt_neutral_by_default():
    p = schema.build_prompt("controls roles")
    assert "smaller companies" not in p
    assert "Scoring guide" in p


def test_schema_prompt_weaves_preference():
    p = schema.build_prompt("controls roles", "Bias toward mission-driven nonprofits.")
    assert "mission-driven nonprofits" in p
