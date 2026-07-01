"""P2 item 8: employment_type as a fact + a hard-gate dimension (full/part-time,
contract, temporary, seasonal, per-diem/PRN). Detection is title-then-description,
None when unmarked; the gate drops a job only when the user set employment_types
AND the job's detected type is present but not allowed."""
from types import SimpleNamespace

import preferences
from match.facts import detect_employment_type, extract_facts
from models import JobResult


def _jr(title, desc=""):
    return JobResult(title=title, company="C", location="Cincinnati, OH",
                     salary_min=None, salary_max=None, description=desc, url="http://x",
                     source_keyword="", created="", source_api="t")


# ── detection ─────────────────────────────────────────────────────────────────
def test_detects_common_types():
    assert detect_employment_type("Registered Nurse - PRN") == "per-diem"
    assert detect_employment_type("Warehouse Associate (Seasonal)") == "seasonal"
    assert detect_employment_type("Software Engineer - Contract") == "contract"
    assert detect_employment_type("Cashier, Part-Time") == "part-time"
    assert detect_employment_type("Staff Nurse", "This is a full-time position.") == "full-time"


def test_unmarked_is_none():
    assert detect_employment_type("Controls Engineer") is None
    assert detect_employment_type("Data Analyst", "Great team, growth path.") is None


def test_title_wins_over_description():
    # A contract marker in the title beats a full-time mention in the body.
    assert detect_employment_type("Contract Developer", "full-time hours") == "contract"


def test_extract_facts_includes_employment_type():
    facts = extract_facts(_jr("RN - PRN Night Shift"))
    assert facts["employment_type"] == "per-diem"
    facts2 = extract_facts(_jr("Controls Engineer"))
    assert facts2["employment_type"] is None


# ── hard-gate enforcement ─────────────────────────────────────────────────────
def _job(title, etype=None):
    return SimpleNamespace(title=title, location="", salary_min=None, salary_max=None,
                           description="", employment_type=etype)


def test_gate_empty_employment_types_keeps_all():
    hard = {**preferences._DEFAULT_HARD, "employment_types": []}
    jobs = [_job("A", "contract"), _job("B", "full-time"), _job("C", None)]
    assert preferences.hard_gate(jobs, hard) == jobs


def test_gate_drops_disallowed_type_keeps_unknown():
    hard = {**preferences._DEFAULT_HARD, "employment_types": ["full-time"]}
    jobs = [_job("FT", "full-time"), _job("Contract", "contract"), _job("Unknown", None)]
    out = preferences.hard_gate(jobs, hard)
    titles = [j.title for j in out]
    assert "FT" in titles           # allowed
    assert "Contract" not in titles  # detected + not allowed -> dropped
    assert "Unknown" in titles       # undetermined -> kept (not a violation)


def test_gate_counts_employment_type_drops():
    hard = {**preferences._DEFAULT_HARD, "employment_types": ["full-time"]}
    counts = {}
    preferences.hard_gate([_job("C", "contract"), _job("F", "full-time")], hard, counts=counts)
    assert counts["employment_type"] == 1
