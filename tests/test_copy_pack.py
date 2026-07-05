"""Application copy pack (B7 item 5) — the plaintext block the user pastes into an
ATS. Covers: contact parsing (markdown-list + plain), work/education one-liners,
the tailored-resume path line, config fallbacks, and the missing-fields grace
(never a placeholder like 'Name: (unknown)').
"""
import copy_pack


_FULL = {
    "contact": (
        "- Name: Jane Doe\n"
        "- Email: jane@example.com\n"
        "- Phone: 555-123-4567\n"
        "- Location: Cincinnati, OH\n"
        "- Links: linkedin.com/in/jane\n"
    ),
    "work_experience": (
        "### Senior Engineer, Acme (2022-present)\n"
        "- Led the widget platform\n"
        "### Engineer, Globex (2019-2022)\n"
    ),
    "education": "- B.S. Mechanical Engineering, State U (2019)\n",
}


def test_full_pack_has_all_sections():
    text = copy_pack.build_copy_pack(_FULL, {}, resume_path="C:/out/jane_acme.docx")
    assert "APPLICATION COPY PACK" in text
    assert "Name: Jane Doe" in text
    assert "Email: jane@example.com" in text
    assert "Phone: 555-123-4567" in text
    assert "Location: Cincinnati, OH" in text
    assert "Links: linkedin.com/in/jane" in text
    assert "-- Work history --" in text
    assert "Senior Engineer, Acme (2022-present)" in text
    assert "-- Education --" in text
    assert "B.S. Mechanical Engineering" in text
    assert "-- Tailored resume --" in text
    assert "jane_acme.docx" in text


def test_plain_contact_lines_parse_without_bullets():
    exp = {"contact": "Name: Bob Roe\nEmail: bob@example.com\n"}
    text = copy_pack.build_copy_pack(exp, {})
    assert "Name: Bob Roe" in text
    assert "Email: bob@example.com" in text


def test_missing_fields_are_omitted_not_placeheld():
    """An unfilled seed CONTACT section (empty values) contributes no junk lines."""
    exp = {"contact": "- Name:\n- Email:\n- Phone:\n"}
    text = copy_pack.build_copy_pack(exp, {})
    # No 'Name:' with a value, and no placeholder like '(unknown)'.
    assert "Name:" not in text or "Name: \n" not in text
    assert "(unknown)" not in text
    assert "(none)" not in text
    # A totally-empty contact falls back to the gentle nudge, never junk fields.
    assert "add your contact details" in text.lower()


def test_no_resume_path_omits_that_block():
    text = copy_pack.build_copy_pack(_FULL, {}, resume_path=None)
    assert "-- Tailored resume --" not in text
    text2 = copy_pack.build_copy_pack(_FULL, {}, resume_path="")
    assert "-- Tailored resume --" not in text2


def test_config_fallback_for_name_and_location():
    """A sparse CONTACT section still gets name/location from the project config."""
    exp = {"contact": "- Email: only@example.com\n"}
    cfg = {"name": "Config Person", "location": "Remote"}
    text = copy_pack.build_copy_pack(exp, cfg)
    assert "Name: Config Person" in text
    assert "Location: Remote" in text
    assert "Email: only@example.com" in text


def test_experience_contact_wins_over_config():
    exp = {"contact": "- Name: Real Name\n"}
    cfg = {"name": "Config Name"}
    text = copy_pack.build_copy_pack(exp, cfg)
    assert "Name: Real Name" in text
    assert "Config Name" not in text


def test_empty_everything_still_builds_a_block():
    text = copy_pack.build_copy_pack({}, {})
    assert "APPLICATION COPY PACK" in text
    assert "-- Contact --" in text
    # No work/education blocks when the sections are empty.
    assert "-- Work history --" not in text
    assert "-- Education --" not in text


def test_non_dict_inputs_do_not_crash():
    text = copy_pack.build_copy_pack(None, None, resume_path=None)
    assert "APPLICATION COPY PACK" in text
