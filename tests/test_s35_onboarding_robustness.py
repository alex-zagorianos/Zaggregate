"""S35 — cheap-AI onboarding robustness.

Locks in the S35 hardening that lets a WEAK/free-tier AI's imperfect output still
onboard a user (the app's stated goal: get anyone the widest net of jobs). Two
surfaces:

  1. ui.ai_setup.parse_setup_block — the profile config block. A weak AI emits
     colloquial salary ("140k"), seniority ("director"), comma-joined titles,
     smart quotes, // comments, or two fenced blocks. None of these should HARD-
     BLOCK onboarding.
  2. scrape.ats_detect.parse_line — the company-seed lines. Markdown bullets /
     numbered lists must still resolve their ATS slug (not a mangled 'direct'),
     and prose the AI wraps around the list must be DROPPED, never saved as a
     junk company.

All pure/offline (parse_line and parse_setup_block touch no registry/network).
"""
import json

import pytest

from ui import ai_setup
from scrape.ats_detect import parse_line


# ── setup parser: weak-AI value formats must not hard-block ────────────────────
def _block(payload_overrides):
    base = {"field": "finance", "target_titles": ["Analyst"],
            "location": "NYC", "seniority": "mid", "preferences_md": "x"}
    base.update(payload_overrides)
    return "```json\n" + json.dumps(base) + "\n```"


@pytest.mark.parametrize("raw,expect", [
    ("140k", 140000),
    ("140K", 140000),
    ("$140,000", 140000),
    ("$120,000 per year", 120000),
    ("120000/yr", 120000),
    ("100000-150000", 100000),   # low end of a range
    ("1.4m", 1400000),
    (85000, 85000),
    (0, None),
    ("", None),
])
def test_salary_shorthand_is_coerced_not_blocked(raw, expect):
    parsed = ai_setup.parse_setup_block(_block({"salary_floor": raw}))
    assert parsed["answers"]["salary_min"] == expect


@pytest.mark.parametrize("raw,expect_level", [
    ("director", "Manager/Exec"),
    ("VP", "Manager/Exec"),
    ("C-level", "Manager/Exec"),
    ("CEO", "Manager/Exec"),
    ("intern", "Entry"),
    ("new grad", "Entry"),
    ("associate", "Mid"),
    ("staff", "Senior"),
    ("principal", "Senior"),
])
def test_seniority_aliases_accepted(raw, expect_level):
    parsed = ai_setup.parse_setup_block(_block({"seniority": raw}))
    assert parsed["answers"]["level"] == expect_level


def test_radius_with_unit_words_is_coerced():
    parsed = ai_setup.parse_setup_block(_block({"radius_miles": "25 miles"}))
    assert parsed["extras"]["radius"] == 25


def test_comma_joined_titles_string_is_split():
    parsed = ai_setup.parse_setup_block(
        _block({"target_titles": "Account Exec, SDR, BDR"}))
    assert parsed["answers"]["roles"] == ["Account Exec", "SDR", "BDR"]


def test_smart_curly_quotes_do_not_block():
    text = ('```json\n{“field”:“nursing”,'
            '“target_titles”:[“RN”],'
            '“location”:“Columbus, OH”,'
            '“seniority”:“mid”,'
            '“preferences_md”:“x”}\n```')
    parsed = ai_setup.parse_setup_block(text)
    assert parsed["answers"]["roles"] == ["RN"]
    assert parsed["answers"]["industry"] == "nursing"


def test_js_comments_in_json_do_not_block():
    text = ('```json\n{\n  "field":"nursing", // healthcare\n'
            '  "target_titles":["RN"],\n  "location":"Columbus, OH",\n'
            '  "seniority":"mid","preferences_md":"x"\n}\n```')
    assert ai_setup.parse_setup_block(text)["answers"]["roles"] == ["RN"]


def test_two_fences_picks_the_complete_block():
    # A weak AI emits a partial example, THEN the real block. The complete one
    # (most expected keys) must win, not the first.
    text = ('```json\n{"field":"sales"}\n```\nand here is the real one:\n'
            '```json\n{"field":"sales","target_titles":["AE"],'
            '"location":"Miami, FL","seniority":"mid","preferences_md":"x"}\n```')
    parsed = ai_setup.parse_setup_block(text)
    assert parsed["answers"]["roles"] == ["AE"]
    assert parsed["answers"]["location"] == "Miami, FL"


def test_offlist_trade_field_resolved_via_onet_is_accepted():
    # "machinist" is not in CANONICAL_FIELDS but the O*NET tier routes it — a real
    # blue-collar occupation must not hard-block onboarding.
    parsed = ai_setup.parse_setup_block(_block({"field": "machinist"}))
    assert parsed["extras"]["field_token"] == "machinist"


def test_pure_typo_field_still_rejected():
    # The generic-reach typo guard must survive: a nonsense field that resolves to
    # 'generic' (no routing) is still rejected, so a real mistake is caught.
    with pytest.raises(ai_setup.SetupBlockError):
        ai_setup.parse_setup_block(_block({"field": "quantum astrology"}))


# ── seed parser: parse_line must rescue formats and reject prose ───────────────
def test_prose_line_without_url_is_dropped():
    # A weak AI wraps the list in prose; those lines must NOT become junk
    # 'direct' companies (registry pollution).
    assert parse_line("Here are some employers:") is None
    assert parse_line("Hope this helps!") is None
    assert parse_line("Sure, I can help with that.") is None


@pytest.mark.parametrize("line", [
    "- Acme Corp: https://boards.greenhouse.io/acme",
    "* Acme Corp - https://boards.greenhouse.io/acme",
    "1. Acme Corp - https://boards.greenhouse.io/acme",
    "2) Acme Corp | https://boards.greenhouse.io/acme",
])
def test_bulleted_or_numbered_careers_url_resolves_ats(line):
    e = parse_line(line)
    assert e is not None
    assert e.ats_type == "greenhouse"
    assert e.slug == "acme"
    assert "Acme Corp" in e.name and "-" not in e.name and ":" not in e.name


def test_markdown_bold_stripped_from_name():
    e = parse_line("**Acme Corp** | https://boards.greenhouse.io/acme")
    assert e is not None and e.ats_type == "greenhouse" and e.slug == "acme"
    assert "*" not in e.name


def test_plain_pipe_and_bare_url_still_work():
    e1 = parse_line("Beta Inc | https://jobs.lever.co/beta")
    assert e1.ats_type == "lever" and e1.slug == "beta" and e1.name == "Beta Inc"
    e2 = parse_line("https://boards.greenhouse.io/gamma")
    assert e2.ats_type == "greenhouse" and e2.slug == "gamma"


def test_power_form_three_fields_preserved():
    e = parse_line("Delta | greenhouse | delta")
    assert e.ats_type == "greenhouse" and e.slug == "delta" and e.name == "Delta"


def test_name_colon_url_form_resolves():
    e = parse_line("Acme Corp: https://jobs.ashbyhq.com/acme")
    assert e.ats_type == "ashby" and e.slug == "acme" and e.name == "Acme Corp"


def test_trailing_sentence_period_stripped_from_url():
    e = parse_line("Acme | https://boards.greenhouse.io/acme.")
    assert e.slug == "acme"
