"""Wave 9 — _extract_json tolerates stray brackets in surrounding prose."""
import json
import claude_bridge as cb


def test_stray_bracket_after_array_is_handled():
    txt = 'Scores: [{"i": 1, "fit": 90}]  -- see also [the docs]'
    got = cb._extract_json(txt, prefer="array")
    assert json.loads(got) == [{"i": 1, "fit": 90}]


def test_stray_brace_after_object_is_handled():
    txt = 'Result: {"name": "Acme", "fit": 80}  (notes: {n/a})'
    got = cb._extract_json(txt, prefer="object")
    assert json.loads(got) == {"name": "Acme", "fit": 80}


def test_plain_payloads_still_parse():
    assert json.loads(cb._extract_json('[{"i": 1}]', prefer="array")) == [{"i": 1}]
    assert json.loads(cb._extract_json('{"a": 1}')) == {"a": 1}
