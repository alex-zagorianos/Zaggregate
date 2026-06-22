import json
from types import SimpleNamespace

import preferences
import workspace


def _job(title="Engineer", location="", salary_min=None):
    return SimpleNamespace(title=title, location=location, salary_min=salary_min)


# ── load ──────────────────────────────────────────────────────────────────────

def test_load_defaults_when_files_missing(tmp_path):
    p = preferences.load(prefs_md=tmp_path / "none.md", prefs_json=tmp_path / "none.json")
    assert p["profile_md"] == ""
    assert p["hard"]["salary_min"] is None
    assert p["hard"]["remote_ok"] is True
    assert p["hard"]["locations"] == []


def test_load_reads_files(tmp_path):
    (tmp_path / "p.md").write_text("I want controls + software roles.", encoding="utf-8")
    (tmp_path / "p.json").write_text(
        json.dumps({"salary_min": 90000, "locations": ["Cincinnati"], "remote_ok": False}),
        encoding="utf-8")
    p = preferences.load(prefs_md=tmp_path / "p.md", prefs_json=tmp_path / "p.json")
    assert "controls" in p["profile_md"]
    assert p["hard"]["salary_min"] == 90000
    assert p["hard"]["locations"] == ["Cincinnati"]
    assert p["hard"]["remote_ok"] is False


def test_load_tolerates_malformed_json(tmp_path):
    (tmp_path / "p.json").write_text("{ not valid json", encoding="utf-8")
    p = preferences.load(prefs_md=tmp_path / "none.md", prefs_json=tmp_path / "p.json")
    assert p["hard"] == preferences._DEFAULT_HARD


def test_load_default_paths_follow_active_project(tmp_path, monkeypatch):
    """With no override args, load() resolves preferences for the ACTIVE project,
    so prefs live beside that project's config/resume (no cross-project bleed)."""
    monkeypatch.setattr(workspace, "BASE_DIR", tmp_path)
    slug = workspace.create_project("Controls", make_active=True)
    pj, pm = workspace.preferences_paths()
    pm.write_text("I want controls roles.", encoding="utf-8")
    pj.write_text(json.dumps({"salary_min": 123000}), encoding="utf-8")
    loaded = preferences.load()                      # no explicit paths
    assert loaded["profile_md"] == "I want controls roles."
    assert loaded["hard"]["salary_min"] == 123000
    assert slug in str(pj)


# ── hard_gate ─────────────────────────────────────────────────────────────────

def test_hard_gate_salary_floor_keeps_unknown():
    hard = {**preferences._DEFAULT_HARD, "salary_min": 90000}
    jobs = [_job(salary_min=70000), _job(salary_min=120000), _job(salary_min=None)]
    out = preferences.hard_gate(jobs, hard)
    assert len(out) == 2  # 70k dropped; 120k and unknown-salary kept


def test_hard_gate_dealbreaker_in_title():
    hard = {**preferences._DEFAULT_HARD, "dealbreakers": ["clearance"]}
    jobs = [_job(title="SWE (TS/SCI clearance required)"), _job(title="Software Engineer")]
    out = preferences.hard_gate(jobs, hard)
    assert [j.title for j in out] == ["Software Engineer"]


def test_hard_gate_location_with_remote_ok():
    hard = {**preferences._DEFAULT_HARD, "locations": ["Cincinnati"], "remote_ok": True}
    jobs = [
        _job(location="Remote (US)"),       # kept via remote_ok
        _job(location="Austin, TX"),        # dropped — wrong location, not remote
        _job(location="Cincinnati, OH"),    # kept via location match
        _job(location=""),                  # kept — unknown location, not gated
    ]
    out = preferences.hard_gate(jobs, hard)
    locs = [j.location for j in out]
    assert "Austin, TX" not in locs
    assert "Remote (US)" in locs
    assert "Cincinnati, OH" in locs
    assert "" in locs


def test_hard_gate_empty_constraints_keeps_all():
    jobs = [_job(salary_min=10000, location="Anywhere"), _job(title="Sales")]
    assert preferences.hard_gate(jobs, dict(preferences._DEFAULT_HARD)) == jobs


# ── migration ─────────────────────────────────────────────────────────────────

def test_migrate_from_user_config():
    cfg = {
        "salary_min": 90000,
        "location": "Cincinnati",
        "exclude_titles": ["sales", "recruiter"],
        "seniority_exclude": ["principal"],
        "keywords": ["controls engineer", "embedded systems engineer"],
    }
    p = preferences.migrate_from_user_config(cfg)
    assert p["hard"]["salary_min"] == 90000
    assert p["hard"]["locations"] == ["Cincinnati"]
    assert "sales" in p["hard"]["dealbreakers"]
    assert "principal" in p["hard"]["seniority_exclude"]
    assert "controls engineer" in p["profile_md"]
