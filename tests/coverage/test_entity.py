from coverage import entity as E

def test_canonicalize_company_strips_suffix_and_punct():
    assert E.canonicalize_company("Acme, Inc.") == "acme"

def test_canonicalize_company_alias():
    assert E.canonicalize_company("Optum") == "unitedhealth"

def test_normalize_title_known_soc_and_seniority():
    nt = E.normalize_title("Senior Software Developer")
    assert nt.soc_code.startswith("15-1252")
    assert nt.seniority and "senior" in nt.seniority

def test_normalize_title_unmapped():
    assert E.normalize_title("zxqw blorp").soc_code == "00-0000"

def test_normalize_location_remote_and_city():
    assert E.normalize_location("Remote").is_remote is True
    nl = E.normalize_location("Cincinnati, OH")
    assert nl.city == "Cincinnati" and nl.state == "OH"

def test_job_key_cross_source_collision():
    a = type("J", (), {"company": "Acme, Inc.", "title": "Senior Software Developer", "location": "Cincinnati, OH"})()
    b = type("J", (), {"company": "Acme Inc",   "title": "Software Developer",         "location": "Cincinnati"})()
    assert E.job_key_for(a) == E.job_key_for(b)
    assert len(E.job_key_for(a)) == 16

def test_job_key_distinct_role_differs():
    a = type("J", (), {"company": "Acme", "title": "Software Developer", "location": "Cincinnati, OH"})()
    b = type("J", (), {"company": "Acme", "title": "Mechanical Engineer", "location": "Cincinnati, OH"})()
    assert E.job_key_for(a) != E.job_key_for(b)
