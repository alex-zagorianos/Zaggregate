"""Bridge JSON extraction, fit-token mapping, and resume type/truncation guards.

Covers:
  * _extract_json     — clean / fenced / trailing-comma repair / array-vs-object
  * parse_fit_response + match_fit_to_jobs (token mapping + mismatch skip)
  * parse_resume_response / parse_batch_resume_response type + truncation guards
"""
import pytest

import claude_bridge as cb
from claude_bridge import (
    BridgeParseError,
    _extract_json,
    build_fit_prompt,
    fit_token,
    match_fit_to_jobs,
    parse_batch_resume_response,
    parse_fit_response,
    parse_resume_response,
)
from models import JobResult


def _job(title="Controls Engineer", company="Acme", url="https://x/1"):
    return JobResult(
        title=title, company=company, location="Cincinnati, OH",
        salary_min=None, salary_max=None, description="desc",
        url=url, source_keyword="", created="2026-06-01",
    )


# ── _extract_json ─────────────────────────────────────────────────────────────

def test_extract_clean_object():
    out = _extract_json('{"a": 1}', prefer="object")
    assert out == '{"a": 1}'


def test_extract_strips_json_fence():
    text = 'Sure:\n```json\n{"a": 1}\n```\nhope that helps'
    assert _extract_json(text, prefer="object") == '{"a": 1}'


def test_extract_repairs_trailing_comma_object():
    # A single stray comma before } would sink strict json.loads; the tolerant
    # pass must strip it and return parseable JSON.
    import json
    repaired = _extract_json('{"a": 1, "b": 2,}', prefer="object")
    assert json.loads(repaired) == {"a": 1, "b": 2}


def test_extract_repairs_trailing_comma_array():
    import json
    repaired = _extract_json('[{"i": 1, "fit": 80,}, {"i": 2, "fit": 70,},]',
                             prefer="array")
    data = json.loads(repaired)
    assert [d["i"] for d in data] == [1, 2]


def test_extract_prefers_object_over_inner_array():
    # A resume object whose skills field is an array must extract as the whole
    # object, not the inner array (preserves the MISSED-2 behavior).
    import json
    text = '{"skills": ["a", "b"], "summary": "s"}'
    out = _extract_json(text, prefer="object")
    assert json.loads(out) == {"skills": ["a", "b"], "summary": "s"}


def test_extract_prefers_array_when_asked():
    import json
    text = 'prose [{"i": 1}] more prose'
    out = _extract_json(text, prefer="array")
    assert json.loads(out) == [{"i": 1}]


# ── parse_fit_response ────────────────────────────────────────────────────────

def test_parse_fit_returns_list_of_items():
    out = parse_fit_response(
        '[{"i": 1, "token": "abc12345", "fit": 85, "why": "good", "flags": ""}]'
    )
    assert isinstance(out, list)
    item = out[0]
    assert item["i"] == 1
    assert item["token"] == "abc12345"
    assert item["fit_score"] == 85
    assert item["rationale"] == "good"


def test_parse_fit_folds_flags_into_rationale():
    # Red flags must survive into the single rationale field callers persist.
    out = parse_fit_response('[{"i": 1, "fit": 40, "why": "meh", "flags": "clearance"}]')
    assert "clearance" in out[0]["rationale"]
    assert out[0]["flags"] == "clearance"


def test_parse_fit_clamps_score():
    out = parse_fit_response('[{"i": 1, "fit": 250}]')
    assert out[0]["fit_score"] == 100
    out = parse_fit_response('[{"i": 1, "fit": -5}]')
    assert out[0]["fit_score"] == 0


def test_parse_fit_skips_entries_without_score():
    out = parse_fit_response('[{"i": 1}, {"i": 2, "fit": 60}]')
    assert [d["i"] for d in out] == [2]


def test_parse_fit_trailing_comma_batch():
    # The whole point of SCORE-4: one trailing comma must not sink the batch.
    payload = '[{"i": 1, "fit": 80},{"i": 2, "fit": 70},]'
    out = parse_fit_response(payload)
    assert [d["fit_score"] for d in out] == [80, 70]


def test_parse_fit_raises_when_nothing_valid():
    with pytest.raises(BridgeParseError):
        parse_fit_response("no json here at all")


# ── match_fit_to_jobs ─────────────────────────────────────────────────────────

def test_match_maps_by_token_even_when_reordered():
    j1, j2 = _job(url="https://x/1"), _job(url="https://x/2")
    jobs = [j1, j2]
    # Model returns them out of order but echoes the correct tokens.
    parsed = [
        {"i": 1, "token": fit_token(j2), "fit_score": 70, "rationale": "two"},
        {"i": 2, "token": fit_token(j1), "fit_score": 90, "rationale": "one"},
    ]
    out = match_fit_to_jobs(jobs, parsed)
    # Emitted in jobs order, mapped by token (not by the wrong positional i).
    assert out[0][0] is j1 and out[0][1] == 90
    assert out[1][0] is j2 and out[1][1] == 70


def test_match_falls_back_to_positional_i_without_token():
    j1, j2 = _job(url="https://x/1"), _job(url="https://x/2")
    parsed = [
        {"i": 1, "token": "", "fit_score": 50, "rationale": "a"},
        {"i": 2, "token": "", "fit_score": 60, "rationale": "b"},
    ]
    out = match_fit_to_jobs([j1, j2], parsed)
    assert [t[1] for t in out] == [50, 60]


def test_match_skips_unknown_token_and_out_of_range():
    j1 = _job(url="https://x/1")
    parsed = [
        {"i": 1, "token": "deadbeef", "fit_score": 99, "rationale": "ghost"},
        {"i": 5, "token": "", "fit_score": 40, "rationale": "oob"},
    ]
    out = match_fit_to_jobs([j1], parsed)
    assert out == []  # both mismatches skipped, nothing applied


def test_match_full_round_trip_via_prompt_and_parse():
    j1, j2 = _job(url="https://a/1"), _job(url="https://b/2")
    prompt = build_fit_prompt([j1, j2], "PROFILE")
    assert fit_token(j1) in prompt and fit_token(j2) in prompt
    reply = (
        f'[{{"i": 1, "token": "{fit_token(j1)}", "fit": 88, "why": "yes", "flags": ""}},'
        f'{{"i": 2, "token": "{fit_token(j2)}", "fit": 55, "why": "meh", "flags": ""}}]'
    )
    out = match_fit_to_jobs([j1, j2], parse_fit_response(reply))
    assert out[0][0] is j1 and out[0][1] == 88
    assert out[1][0] is j2 and out[1][1] == 55


def test_fit_token_is_stable_8_chars():
    j = _job(url="https://x/1")
    assert fit_token(j) == fit_token(j)
    assert len(fit_token(j)) == 8


def test_fit_token_falls_back_to_title_company_without_url():
    a = _job(url="")
    b = _job(url="", title="Other")
    assert fit_token(a) != fit_token(b)
    assert len(fit_token(a)) == 8


# ── EXT-6 / P4: fit preference is per-profile and neutral by default ───────────

def test_default_fit_preference_is_neutral():
    """De-Alex'd: the app-wide 'prefers smaller companies' bias is gone. The
    default preference is empty and adds NO bias sentence to the prompt."""
    assert cb.DEFAULT_FIT_PREFERENCE == ""
    prompt = build_fit_prompt([_job()], "P")
    assert "smaller companies" not in prompt
    # No orphaned placeholder left in the instructions.
    assert "__PREFERENCE__" not in prompt


def test_fit_preference_can_be_overridden():
    prompt = build_fit_prompt([_job()], "P", preference="Prefers remote roles.")
    assert "Prefers remote roles." in prompt
    assert "smaller companies" not in prompt


def test_compact_prompt_omits_bias_when_neutral():
    from match.facts import facts_for
    j = _job()
    prompt = cb.build_fit_prompt_compact([j], [facts_for(j)], "P")
    assert "smaller companies" not in prompt
    assert "__PREFERENCE__" not in prompt


# ── parse_resume_response: type + truncation guards (RESUME-2) ─────────────────

_GOOD_RESUME = {
    "contact": {"name": "Pat", "email": "", "phone": "", "location": ""},
    "summary": "s",
    "skills": ["python"],
    "experience": [{"company": "X", "title": "Eng", "bullets": ["b"]}],
    "education": [{"institution": "Y", "degree": "BS"}],
    "cover_letter": "c",
}


def _resume_json(**overrides):
    import json
    data = dict(_GOOD_RESUME)
    data.update(overrides)
    return json.dumps(data)


def test_resume_good_payload_parses():
    data = parse_resume_response(_resume_json())
    assert data["skills"] == ["python"]


def test_resume_rejects_wrong_typed_skills():
    with pytest.raises(BridgeParseError, match="wrong field types"):
        parse_resume_response(_resume_json(skills="python, controls"))


def test_resume_rejects_string_experience():
    with pytest.raises(BridgeParseError, match="wrong field types"):
        parse_resume_response(_resume_json(experience="led projects"))


def test_resume_missing_key_still_caught():
    import json
    payload = dict(_GOOD_RESUME)
    del payload["cover_letter"]
    with pytest.raises(BridgeParseError, match="missing"):
        parse_resume_response(json.dumps(payload))


def test_resume_truncated_reply_raises_clearly():
    # A cut copy: object opened, never closed -> the truncation message, not a
    # raw json error, so we never emit a half/wrong doc.
    truncated = '{"contact": {"name": "Pat"}, "summary": "s", "skills": ["a"'
    with pytest.raises(BridgeParseError, match="cut off"):
        parse_resume_response(truncated)


# ── parse_batch_resume_response: range + type guard (RESUME-2) ─────────────────

def test_batch_requires_i_in_range():
    import json
    item = dict(_GOOD_RESUME)
    item["i"] = 9  # out of range for a 2-job batch
    text = json.dumps([item])
    with pytest.raises(BridgeParseError):
        parse_batch_resume_response(text, expected_count=2)


def test_batch_no_positional_fallback_when_i_missing():
    import json
    item = dict(_GOOD_RESUME)  # no "i" key
    with pytest.raises(BridgeParseError):
        parse_batch_resume_response(json.dumps([item]))


def test_batch_keeps_good_skips_bad_typed():
    import json
    good = dict(_GOOD_RESUME); good["i"] = 1
    bad = dict(_GOOD_RESUME); bad["i"] = 2; bad["skills"] = "x, y"  # wrong type
    out = parse_batch_resume_response(json.dumps([good, bad]), expected_count=2)
    assert list(out) == [1]


# ── experience_parser: RESUME-1 drift tolerance + zero-section guard ───────────

from resume.experience_parser import (  # noqa: E402
    EXPERIENCE_SECTIONS,
    contact_name,
    load_experience,
)


def test_parser_tolerates_case_colon_and_h1_drift(tmp_path):
    md = (
        "# Experience\n\n"
        "## Contact:\n- Name: Jane Doe\n\n"
        "## technical skills\nPython, Controls\n\n"
        "## Work History\n### Acme\n- did things\n"
    )
    f = tmp_path / "experience.md"
    f.write_text(md, encoding="utf-8")
    exp = load_experience(f)
    assert "Jane Doe" in exp["contact"]
    assert "Python" in exp["skills"]            # 'technical skills' (lowercase)
    assert "Acme" in exp["work_experience"]     # 'Work History' alias


def test_parser_h1_title_does_not_shadow_work_experience(tmp_path):
    # A bare '# Experience' document title must NOT be treated as WORK
    # EXPERIENCE; the real '## WORK EXPERIENCE' section wins.
    md = (
        "# Experience\n\nintro banner text\n\n"
        "## CONTACT\n- Name: Sam\n\n"
        "## WORK EXPERIENCE\n### RealCo\n- shipped\n"
    )
    f = tmp_path / "experience.md"
    f.write_text(md, encoding="utf-8")
    exp = load_experience(f)
    assert "RealCo" in exp["work_experience"]
    assert "intro banner" not in exp["work_experience"]


def test_parser_raises_naming_headings_when_none_found(tmp_path):
    md = "# Resume\n\nsome freeform text with no known headings\n"
    f = tmp_path / "experience.md"
    f.write_text(md, encoding="utf-8")
    with pytest.raises(ValueError) as ei:
        load_experience(f)
    # The error names the expected headings so the user can fix the file.
    for canon in EXPERIENCE_SECTIONS.values():
        assert canon in str(ei.value)


def test_parser_empty_sections_present_do_not_raise(tmp_path):
    # The new-project seed ships present-but-empty sections; that must parse.
    md = "# Experience\n\n## CONTACT\n\n## WORK EXPERIENCE\n"
    f = tmp_path / "experience.md"
    f.write_text(md, encoding="utf-8")
    exp = load_experience(f)
    assert exp["contact"] == ""


def test_contact_name_reads_name_line():
    assert contact_name({"contact": "- Name: Jane Doe\n- Email: j@x"}) == "Jane Doe"


def test_contact_name_empty_when_no_name_line():
    assert contact_name({"contact": "- Email: only@x\n- Phone: 1"}) == ""
