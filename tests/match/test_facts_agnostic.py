"""Plan 3 GOAL 1 (1E) — field-agnostic facts: byte-identical for engineering,
universal role buckets + profile skills for other fields, cache never leaks
across profiles."""
from match import facts as F
from models import JobResult


def _job(title, desc="", company="Acme", loc="Cincinnati, OH", jid="1"):
    return JobResult(title, company, loc, None, None, desc, "http://x/%s" % jid,
                     "kw", "", job_id=jid)


def test_eng_posting_byte_identical_default_vs_tech_industry():
    j = _job("Senior Controls Engineer",
             "PLC, SCADA, servo motion control and robotics. Design and build.")
    base = F.extract_facts(j)                                  # today's behavior
    tech = F.extract_facts(j, industry="controls_engineering")  # eng industry
    assert base == tech                                       # role map unchanged
    assert base["role_type"] == "build"
    assert "plc" in base["top_skills"]


def test_is_tech_industry():
    assert F.is_tech_industry("") and F.is_tech_industry("controls_engineering")
    assert F.is_tech_industry("software")
    assert not F.is_tech_industry("health_informatics")
    assert not F.is_tech_industry("nursing")


def test_non_tech_industry_uses_universal_role_buckets():
    j = _job("Registered Nurse — Clinical Informatics",
             "Provide patient care and clinical documentation support.")
    eng = F.extract_facts(j)                                  # eng map -> misses it
    health = F.extract_facts(j, industry="health_informatics")
    assert health["role_type"] == "care"
    assert eng["role_type"] != "care"                        # proves the gating


def test_profile_skills_replace_vocab_for_non_tech():
    j = _job("Staff Accountant", "GAAP, QuickBooks, reconciliation, payroll.")
    facts = F.extract_facts(j, industry="finance",
                            skill_terms=["gaap", "quickbooks", "payroll"])
    assert set(facts["top_skills"]) == {"gaap", "quickbooks", "payroll"}
    assert len(facts["top_skills"]) <= 6                     # same token budget


def test_facts_cache_isolated_by_profile(tmp_path, monkeypatch):
    # Same job_key, two different profiles -> two cache files, no cross-serving.
    import config
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    j = _job("Analyst", "clinical informatics and gaap accounting", jid="shared")

    eng = F.facts_for(j)                                      # default -> {key}.json
    health = F.facts_for(j, industry="health_informatics",
                         skill_terms=["informatics"])         # -> {key}.{sig}.json
    files = {p.name for p in (tmp_path / "extracted").glob("*.json")}
    assert len(files) == 2                                    # separate cache slots
    assert any("." in n.replace(".json", "") for n in files)  # one is signed
    # The health profile must NOT be served the eng-cached facts.
    assert health["top_skills"] == ["informatics"]
    assert eng["top_skills"] != ["informatics"]


def test_default_cache_filename_unchanged(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    j = _job("Controls Engineer", "plc scada", jid="ctrl")
    F.facts_for(j)                                            # default path
    names = {p.name for p in (tmp_path / "extracted").glob("*.json")}
    assert names == {f"{j.job_key}.json"}                     # byte-identical name
