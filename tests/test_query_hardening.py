"""Hardening cases for the boolean query parser (2026-06 review)."""
from search.query import parse


def m(q, hay):
    return parse(q).matches(hay)


def test_stray_paren_does_not_silently_drop_tokens():
    q = "controls) senior"
    assert m(q, "Senior Controls Engineer")
    assert not m(q, "Controls Engineer")
    assert not m(q, "Senior Manager")


def test_empty_parens_do_not_leak_a_paren_term():
    q = parse("()")
    assert q.positive_terms() == []
    assert q.matches("anything at all")


def test_empty_phrase_does_not_force_a_match_under_or():
    q = 'senior OR ""'
    assert m(q, "Senior Engineer")
    assert not m(q, "Controls Technician")
