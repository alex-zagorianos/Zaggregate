import json
from types import SimpleNamespace

import preferences
import workspace


def _job(title="Engineer", location="", salary_min=None, salary_max=None):
    return SimpleNamespace(title=title, location=location, salary_min=salary_min,
                           salary_max=salary_max)


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


def test_hard_gate_salary_uses_max_or_min():
    # P0#8: a $70k-$120k job must NOT die against a $90k floor on its range FLOOR;
    # the gate now tests the disclosed MAX-or-min (aligns with comp.meets_floor).
    hard = {**preferences._DEFAULT_HARD, "salary_min": 90000}
    keep = _job(salary_min=70000, salary_max=120000)   # max clears the floor -> kept
    drop = _job(salary_min=60000, salary_max=80000)    # max below floor -> dropped
    out = preferences.hard_gate([keep, drop], hard)
    assert keep in out and drop not in out


def test_hard_gate_location_metro_variant_accepts_greater_area():
    # P0#8: prefs "Cincinnati, OH" must accept a job in "Greater Cincinnati Area"
    # (bare-city expansion), not just an exact substring.
    hard = {**preferences._DEFAULT_HARD, "locations": ["Cincinnati, OH"],
            "remote_ok": False}
    jobs = [_job(location="Greater Cincinnati Area"), _job(location="Austin, TX")]
    out = preferences.hard_gate(jobs, hard)
    locs = [j.location for j in out]
    assert "Greater Cincinnati Area" in locs
    assert "Austin, TX" not in locs


def test_hard_gate_reports_per_reason_counts():
    hard = {**preferences._DEFAULT_HARD, "salary_min": 90000,
            "locations": ["Cincinnati"], "remote_ok": False,
            "dealbreakers": ["clearance"]}
    jobs = [
        _job(title="SWE (clearance required)"),          # title drop
        _job(salary_min=50000, salary_max=60000),        # salary drop
        _job(location="Austin, TX"),                     # location drop
        _job(title="Controls Engineer", location="Cincinnati, OH"),  # kept
    ]
    counts = {}
    out = preferences.hard_gate(jobs, hard, counts=counts)
    assert len(out) == 1
    assert counts["title"] == 1
    assert counts["salary"] == 1
    assert counts["location"] == 1


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


def test_hard_gate_blocker_is_word_boundary_not_substring():
    """S35 (Alex-approved): design philosophy = never over-drop; the gate cuts a
    clearly-stated blocker TOKEN only. A 'sales' dealbreaker must not kill
    'Salesforce Engineer'; 'it' must not kill 'Editor'."""
    hard = {**preferences._DEFAULT_HARD, "dealbreakers": ["sales", "it"]}
    jobs = [
        _job(title="Salesforce Engineer"),        # kept — 'sales' is a substring, not a token
        _job(title="Sales Engineer"),             # dropped — 'sales' token
        _job(title="Editor"),                     # kept — 'it' inside 'Editor'
        _job(title="IT Support Specialist"),      # dropped — 'it' token
        _job(title="Sales Development Rep"),      # dropped
    ]
    counts = {}
    out = preferences.hard_gate(jobs, hard, counts=counts)
    assert [j.title for j in out] == ["Salesforce Engineer", "Editor"]
    assert counts["title"] == 3


def test_hard_gate_blocker_with_nonword_edges_still_matches_own_token():
    # Lookaround boundaries (not \b) so 'c++' / 'sr.' blockers match themselves.
    hard = {**preferences._DEFAULT_HARD, "seniority_exclude": ["sr."]}
    jobs = [_job(title="Sr. Staff Engineer"), _job(title="Engineer")]
    out = preferences.hard_gate(jobs, hard)
    assert [j.title for j in out] == ["Engineer"]


def test_hard_gate_multiword_blocker_matches_phrase():
    hard = {**preferences._DEFAULT_HARD, "dealbreakers": ["door to door"]}
    jobs = [_job(title="Door to Door Sales"), _job(title="Front Door Product Lead")]
    out = preferences.hard_gate(jobs, hard)
    assert [j.title for j in out] == ["Front Door Product Lead"]
