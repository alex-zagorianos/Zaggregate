"""A4 slice: LICENSES & CERTIFICATIONS reach the generated resume docx and the
generator tool schema exposes summary + certifications. No network."""
from docx import Document

from resume import docx_builder as db
from resume.generator import RESUME_TOOL, _INSTRUCTIONS


def _paras(buf):
    return [p.text for p in Document(buf).paragraphs]


def test_docx_renders_certifications_section():
    data = {
        "contact": {"name": "Jane Smith", "email": "j@x.com", "phone": "555",
                    "location": "Cincinnati, OH"},
        "summary": "Seasoned RN.",
        "skills": ["Clinical: ICU, telemetry"],
        "certifications": ["RN - Ohio Board of Nursing", "BLS/ACLS (AHA)"],
        "experience": [{"company": "Mercy", "title": "Charge Nurse",
                        "bullets": ["Led ICU."]}],
        "education": [{"institution": "UC", "degree": "BSN"}],
        "cover_letter": "Dear team,",
    }
    texts = _paras(db.build_resume_docx(data))
    joined = "\n".join(texts)
    assert "LICENSES & CERTIFICATIONS" in joined
    assert "RN - Ohio Board of Nursing" in joined
    assert "BLS/ACLS (AHA)" in joined
    # Rendered ABOVE the experience section.
    assert joined.index("LICENSES & CERTIFICATIONS") < joined.index("EXPERIENCE")


def test_docx_omits_certs_section_when_empty():
    data = {
        "contact": {"name": "Alex", "email": "a@x.com", "phone": "1",
                    "location": "Cincinnati"},
        "summary": "Engineer.",
        "skills": ["Languages: Python"],
        "experience": [{"company": "G90", "title": "Controls Engineer",
                        "bullets": ["Built."]}],
        "education": [{"institution": "UC", "degree": "BSME"}],
        "cover_letter": "Hi.",
    }
    joined = "\n".join(_paras(db.build_resume_docx(data)))
    assert "LICENSES & CERTIFICATIONS" not in joined  # byte-identical for eng


def test_generator_tool_schema_exposes_summary_and_certs():
    props = RESUME_TOOL["input_schema"]["properties"]
    assert "summary" in props
    assert "certifications" in props
    assert props["certifications"]["type"] == "array"


def test_generator_instructions_are_field_neutral():
    # No hard-coded tech-only track enumeration; certifications called out.
    txt = _INSTRUCTIONS.lower()
    assert "certification" in txt
    assert "any field" in txt or "any field" in txt or "nursing" in txt
    # The old fixed "software / controls / data / mechanical" track list is gone.
    assert "software / \ncontrols / data / mechanical" not in txt
    assert "controls / data / mechanical" not in _INSTRUCTIONS
