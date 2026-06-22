"""_extract_json must prefer the object container for resume replies (2026-06)."""
from claude_bridge import parse_resume_response, parse_fit_response


def test_resume_object_with_only_an_array_field():
    # education/experience are lists per the contract (RESUME-2 type validation);
    # this still exercises _extract_json's object-container preference.
    reply = (
        'Here you go:\n'
        '{"contact": {"name": "Pat", "email": "", "phone": "", "location": ""}, '
        '"summary": "s", "education": ["BS ME"], "skills": ["python", "controls"], '
        '"experience": [{"company": "X", "title": "Eng", "bullets": ["led projects"]}], '
        '"cover_letter": "c"}'
    )
    data = parse_resume_response(reply)
    assert isinstance(data, dict)
    assert data["skills"] == ["python", "controls"]


def test_fit_array_still_parses():
    # parse_fit_response now returns a list of {i, token, fit_score, ...} dicts
    # (SCORE-5), not a {job_number: {...}} mapping.
    out = parse_fit_response('[{"i": 1, "fit": 80, "why": "good", "flags": ""}]')
    assert out[0]["fit_score"] == 80
    assert out[0]["i"] == 1
