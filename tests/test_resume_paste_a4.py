"""A4 slice: the P0 resume-paste crash fix + first-class SUMMARY / LICENSES &
CERTIFICATIONS sections.

The mandatory acceptance test: a plain-text nurse resume paste -> the wizard
completes -> load_experience succeeds -> no ValueError anywhere. Fixture-based,
no network, no dependence on the (gitignored) root experience.md.
"""
import json

import pytest

import config
import workspace
from ui import setup_wizard as sw
from resume import experience_parser as ep


# -- plain-text nurse resume (the live-reproduced crash input) -------------------
_NURSE_PLAIN = """\
Jane Smith, RN
jane.smith@example.com | (513) 555-0182 | Cincinnati, OH

Dedicated registered nurse with 8 years of critical-care experience.

WORK EXPERIENCE
Mercy Health - Cincinnati, OH
Charge Nurse, ICU (2019-present)
Led a 12-bed intensive care unit across night shifts.

LICENSES & CERTIFICATIONS
RN - Ohio Board of Nursing
BLS, ACLS (American Heart Association)

EDUCATION
BSN, University of Cincinnati
"""

_NURSE_NO_HEADINGS = """\
Jane Smith, RN
jane.smith@example.com | (513) 555-0182

Dedicated registered nurse with 8 years of critical-care experience across ICU
and telemetry units. Charge nurse experience on night shifts. RN licensed in Ohio;
BLS and ACLS certified.
"""


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "PREFERENCES_JSON", tmp_path / "preferences.json")
    monkeypatch.setattr(config, "PREFERENCES_MD", tmp_path / "preferences.md")
    monkeypatch.setattr(workspace, "BASE_DIR", tmp_path)
    return tmp_path


# -- structure_resume_text (pure) ------------------------------------------------
def test_structure_promotes_allcaps_headings():
    out, changed = sw.structure_resume_text(_NURSE_PLAIN)
    assert changed is True
    # The recognizable heading lines are promoted to '## ' headings.
    assert "## WORK EXPERIENCE" in out
    assert "## LICENSES & CERTIFICATIONS" in out
    assert "## EDUCATION" in out
    # No text is lost.
    assert "Charge Nurse, ICU" in out
    assert "RN - Ohio Board of Nursing" in out


def test_structure_wraps_headingless_paste():
    out, changed = sw.structure_resume_text(_NURSE_NO_HEADINGS)
    assert changed is True
    assert "## WORK EXPERIENCE" in out
    # Contact-looking leading lines go under CONTACT.
    assert "## CONTACT" in out
    assert "jane.smith@example.com" in out
    # The body text survives.
    assert "critical-care experience" in out


def test_structure_leaves_markdown_untouched():
    md = "# Experience\n\n## WORK EXPERIENCE\n\nBuilt machines."
    out, changed = sw.structure_resume_text(md)
    assert changed is False
    assert out == md.strip()


def test_structure_empty_is_noop():
    assert sw.structure_resume_text("") == ("", False)
    assert sw.structure_resume_text("   \n  ") == ("", False)


def test_structure_does_not_promote_sentences():
    # A real sentence that merely contains a heading-ish word must NOT be promoted.
    text = ("I gained experience running multiple projects, and my education "
            "shaped how I lead teams.")
    out, changed = sw.structure_resume_text(text)
    # Wrapped (path B), not promoted mid-sentence.
    assert "## WORK EXPERIENCE" in out
    assert out.count("## ") <= 2  # at most CONTACT + WORK EXPERIENCE
    assert "my education" in out  # sentence body intact, not turned into a heading


# -- bare "Experience" heading: orphan work-history must not be dropped ----------
_BARE_EXPERIENCE_PLAIN = """\
Alex Fresh
Mechanical Engineer

Experience
Manufacturing Engineer, Acme Corp, 2022-2026
- Designed fixtures for CNC machining

Education
BS Mechanical Engineering, State University, 2022
"""


def test_structure_bare_experience_heading_keeps_work_history():
    """A résumé that uses a bare 'Experience' heading (a very common convention)
    used to lose its ENTIRE work history: the parser deliberately won't alias a
    bare 'Experience' (H1-title collision), so Path A promoted only 'Education' and
    left the name/title/Experience-block as orphan text the downstream parser
    drops — while still reporting restructured=True. The orphan block before the
    first recognized heading must now be folded into CONTACT/WORK EXPERIENCE, so no
    pasted text is invisible. (scenario-test finding #1)"""
    out, changed = sw.structure_resume_text(_BARE_EXPERIENCE_PLAIN)
    assert changed is True
    assert "## WORK EXPERIENCE" in out
    assert "## EDUCATION" in out
    # The load-bearing content — the actual job entry — must survive, not vanish.
    assert "Manufacturing Engineer" in out
    assert "Acme Corp" in out
    assert "Designed fixtures for CNC machining" in out


def test_bare_experience_paste_reaches_parser_work_experience(isolated):
    """End-to-end: the bare-'Experience' paste applied through the wizard must land
    real work-history in the parser's work_experience section, not an empty one."""
    sw.apply({
        "roles": ["mechanical engineer"],
        "location": "Cincinnati, OH",
        "remote_ok": True,
        "salary_min": None,
        "resume_text": _BARE_EXPERIENCE_PLAIN,
        "about": "",
    })
    parsed = ep.load_experience(workspace.experience_file())  # strict, must not raise
    assert parsed["work_experience"], "work history was silently dropped"
    assert "Manufacturing Engineer" in parsed["work_experience"]
    assert "Acme Corp" in parsed["work_experience"]
    assert parsed["education"]


# -- the mandatory acceptance test -----------------------------------------------
def test_nurse_paste_wizard_completes_and_parses(isolated):
    """A plain-text nurse resume paste -> apply() succeeds -> load_experience()
    (strict) succeeds -> NO ValueError anywhere. This is the P0 the review flagged."""
    info = sw.apply({
        "roles": ["registered nurse"],
        "location": "Cincinnati, OH",
        "remote_ok": False,
        "salary_min": None,
        "resume_text": _NURSE_PLAIN,
        "about": "",
    })
    assert info["resume_restructured"] is True
    exp = workspace.experience_file()
    assert exp.exists()

    # The crash was here: strict load_experience raised ValueError on a
    # heading-less paste. After apply()'s auto-structuring it must parse cleanly.
    parsed = ep.load_experience(exp)  # strict mode, must not raise
    assert parsed["work_experience"]
    # Certifications parsed into their own key AND folded into skills for scoring.
    assert "RN" in parsed["certifications"] or "Ohio Board" in parsed["certifications"]
    assert "RN" in parsed["skills"] or "ACLS" in parsed["skills"]


def test_headingless_paste_never_crashes_scoring_path(isolated):
    """Even a totally structure-free paste must be readable by every downstream
    caller (strict load_experience + the scorer's skill-term extraction)."""
    sw.apply({"roles": ["registered nurse"], "location": "", "salary_min": None,
              "resume_text": _NURSE_NO_HEADINGS, "about": ""})
    exp = workspace.experience_file()
    parsed = ep.load_experience(exp)               # must not raise
    assert "critical-care experience" in parsed["work_experience"]

    from match.scorer import extract_skill_terms
    terms = extract_skill_terms(exp)               # must not raise
    assert isinstance(terms, frozenset)


# -- lenient mode of the parser --------------------------------------------------
def test_lenient_mode_wraps_when_no_sections(tmp_path):
    p = tmp_path / "exp.md"
    p.write_text("Just some free text with no headings at all.", encoding="utf-8")
    # Strict raises...
    with pytest.raises(ValueError):
        ep.load_experience(p)
    # ...lenient returns the body under work_experience.
    data = ep.load_experience(p, lenient=True)
    assert data["work_experience"] == "Just some free text with no headings at all."
    assert data["contact"] == ""


def test_lenient_and_strict_agree_when_structured(tmp_path):
    p = tmp_path / "exp.md"
    p.write_text("## WORK EXPERIENCE\n\nDid things.\n\n## SUMMARY\n\nGood nurse.",
                 encoding="utf-8")
    strict = ep.load_experience(p)
    lenient = ep.load_experience(p, lenient=True)
    assert strict["work_experience"] == lenient["work_experience"] == "Did things."
    assert strict["summary"] == "Good nurse."


# -- first-class SUMMARY / LICENSES & CERTIFICATIONS sections + aliases -----------
@pytest.mark.parametrize("heading,canon", [
    ("CERTIFICATIONS", "LICENSES & CERTIFICATIONS"),
    ("Licenses", "LICENSES & CERTIFICATIONS"),
    ("Licensure", "LICENSES & CERTIFICATIONS"),
    ("Credentials", "LICENSES & CERTIFICATIONS"),
    ("Certificates", "LICENSES & CERTIFICATIONS"),
    ("Professional Summary", "SUMMARY"),
    ("Objective", "SUMMARY"),
    ("Profile", "SUMMARY"),
])
def test_section_aliases_resolve(tmp_path, heading, canon):
    p = tmp_path / "exp.md"
    p.write_text(f"## {heading}\n\nbody-under-{heading}", encoding="utf-8")
    data = ep.load_experience(p)
    dk = {v: k for k, v in ep.EXPERIENCE_SECTIONS.items()}[canon]
    assert data[dk] == f"body-under-{heading}"


def test_certifications_fold_into_skills_for_scorer(tmp_path):
    p = tmp_path / "exp.md"
    p.write_text(
        "## TECHNICAL SKILLS\n\nIV therapy, wound care\n\n"
        "## LICENSES & CERTIFICATIONS\n\nRN, BLS, ACLS, CDL Class A",
        encoding="utf-8")
    data = ep.load_experience(p)
    # Standalone key preserved for the labeled corpus...
    assert "CDL Class A" in data["certifications"]
    # ...AND folded into the 'skills' value the scorer reads.
    assert "ACLS" in data["skills"] and "IV therapy" in data["skills"]

    from match.scorer import extract_skill_terms
    terms = extract_skill_terms(p)
    assert "acls" in terms  # a cert reaches the scorer's skill-term set


def test_no_certs_is_byte_identical_skills(tmp_path):
    # An eng profile with no certifications: skills value is unchanged (no trailing
    # newline / no fold), so Alex's flow is byte-identical.
    p = tmp_path / "exp.md"
    p.write_text("## TECHNICAL SKILLS\n\nPython, C++17", encoding="utf-8")
    data = ep.load_experience(p)
    assert data["skills"] == "Python, C++17"
    assert data["certifications"] == ""


def test_summary_and_certs_in_corpus(tmp_path):
    p = tmp_path / "exp.md"
    p.write_text(
        "## SUMMARY\n\nSeasoned RN.\n\n"
        "## LICENSES & CERTIFICATIONS\n\nRN - Ohio",
        encoding="utf-8")
    data = ep.load_experience(p)
    corpus = ep.experience_corpus(data)
    assert "Summary" in corpus and "Seasoned RN." in corpus
    assert "Licenses & Certifications" in corpus and "RN - Ohio" in corpus
