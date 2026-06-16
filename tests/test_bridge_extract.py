"""_extract_json must prefer the object container for resume replies (2026-06)."""
from claude_bridge import parse_resume_response, parse_fit_response


def test_resume_object_with_only_an_array_field():
    reply = (
        'Here you go:\n'
        '{"contact": {"name": "Pat", "email": "", "phone": "", "location": ""}, '
        '"summary": "s", "education": "BS ME", "skills": ["python", "controls"], '
        '"experience": "led projects", "cover_letter": "c"}'
    )
    data = parse_resume_response(reply)
    assert isinstance(data, dict)
    assert data["skills"] == ["python", "controls"]


def test_fit_array_still_parses():
    out = parse_fit_response('[{"i": 1, "fit": 80, "why": "good", "flags": ""}]')
    assert out[1]["fit"] == 80
