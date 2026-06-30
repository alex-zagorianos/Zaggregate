from match import facts as F
from models import JobResult


def _job(title="Controls Engineer", desc="", location="Cincinnati, OH",
         salary_min=None, salary_max=None, url="https://x.co/1"):
    return JobResult(title=title, company="Acme", location=location,
                     salary_min=salary_min, salary_max=salary_max, description=desc,
                     url=url, source_keyword="", created="", source_api="test")


# ── seniority ─────────────────────────────────────────────────────────────────
def test_seniority_from_title():
    assert F.extract_facts(_job("Senior Firmware Engineer"))["seniority"] == "senior"
    assert F.extract_facts(_job("Electrical Engineer Intern"))["seniority"] == "intern"
    assert F.extract_facts(_job("Senior Manager, Embedded Systems"))["seniority"] == "manager"
    assert F.extract_facts(_job("Director of Engineering"))["seniority"] == "director"
    assert F.extract_facts(_job("Staff Controls Engineer"))["seniority"] == "lead"


def test_seniority_roman_level():
    assert F.extract_facts(_job("Systems Engineer I"))["seniority"] == "entry"
    assert F.extract_facts(_job("Controls Engineer III"))["seniority"] == "senior"


def test_seniority_defaults_mid():
    assert F.extract_facts(_job("Controls Engineer"))["seniority"] == "mid"


# ── years / clearance ─────────────────────────────────────────────────────────
def test_required_years_takes_max():
    f = F.extract_facts(_job(desc="3+ years preferred; minimum of 8 years required"))
    assert f["required_years"] == 8


def test_clearance_detected():
    assert F.extract_facts(_job(desc="active security clearance required"))["clearance_required"]
    assert F.extract_facts(_job(desc="TS/SCI eligibility"))["clearance_required"]
    assert not F.extract_facts(_job(desc="great benefits"))["clearance_required"]


# ── location / restriction ────────────────────────────────────────────────────
def test_location_type():
    assert F.extract_facts(_job(location="Remote, US"))["location_type"] == "remote"
    assert F.extract_facts(_job(location="Glen Cove, NY", desc="hybrid 3 days/week"))["location_type"] == "hybrid"
    assert F.extract_facts(_job(location="Austin, TX"))["location_type"] == "onsite"


def test_restriction():
    assert "No visa sponsorship" in F.extract_facts(_job(desc="We are unable to offer Visa sponsorship"))["restriction"]
    assert "Japan" in F.extract_facts(_job(desc="must hold a valid Japanese work visa"))["restriction"]
    assert F.extract_facts(_job(desc="nothing special"))["restriction"] is None


# ── role type ─────────────────────────────────────────────────────────────────
def test_role_type():
    assert F.extract_facts(_job("Software Engineer in Test", "test automation framework"))["role_type"] == "test"
    assert F.extract_facts(_job("Engineering Manager", "manage a team of engineers"))["role_type"] == "manage"
    assert F.extract_facts(_job("Senior Manufacturing Solutions Engineer"))["role_type"] == "sales"
    assert F.extract_facts(_job("Firmware Engineer", "design and develop embedded firmware"))["role_type"] == "build"


# ── comp / skills / summary ───────────────────────────────────────────────────
def test_comp_from_fields_and_text():
    assert F.extract_facts(_job(salary_min=180000, salary_max=230000))["comp_min"] == 180000
    f = F.extract_facts(_job(desc="Pay range: $120,000 - $150,000 annually"))
    assert f["comp_min"] == 120000 and f["comp_max"] == 150000


def test_top_skills_and_summary():
    f = F.extract_facts(_job(desc="C++ firmware for real-time motion control on STM32 with PLC integration"))
    assert "c++" in f["top_skills"] and "firmware" in f["top_skills"]
    s = F.facts_summary(f)
    assert "Role:" in s and "Seniority:" in s and "c++" in s


def test_facts_for_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "_cache_dir", lambda: tmp_path)
    j = _job("Senior Firmware Engineer", "C++ real-time motion control")
    first = F.facts_for(j)
    assert (tmp_path / f"{j.job_key}.json").exists()
    assert F.facts_for(j) == first   # served from cache
