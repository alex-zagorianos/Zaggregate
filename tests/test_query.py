"""Boolean keyword query parsing/matching."""
from search.query import parse


def m(q, hay):
    return parse(q).matches(hay)


# ── back-compat: plain keywords behave like the old matcher ───────────────────
def test_single_word_substring():
    assert m("automation", "Automation Engineer")
    assert not m("automation", "Controls Engineer")


def test_multiword_is_implicit_and_with_trailing_s_strip():
    # "controls engineer" -> control(s) AND engineer
    assert m("controls engineer", "Control Systems Engineer")
    assert not m("controls engineer", "Controls Technician")  # no "engineer"


# ── phrases ───────────────────────────────────────────────────────────────────
def test_quoted_phrase_must_be_contiguous():
    assert m('"controls engineer"', "Senior Controls Engineer")
    assert not m('"controls engineer"', "Controls Lead Engineer")


# ── OR ────────────────────────────────────────────────────────────────────────
def test_or_matches_either_branch():
    q = "controls OR automation"
    assert m(q, "Automation Engineer")
    assert m(q, "Controls Engineer")
    assert not m(q, "Software Engineer")


# ── NOT and leading-minus ─────────────────────────────────────────────────────
def test_not_excludes():
    assert not m("engineer NOT senior", "Senior Engineer")
    assert m("engineer NOT senior", "Controls Engineer")


def test_minus_is_negation():
    assert not m("engineer -intern", "Engineering Intern")
    assert m("engineer -intern", "Controls Engineer")


# ── grouping / precedence ─────────────────────────────────────────────────────
def test_parens_group_or_under_not():
    q = "(controls OR automation) NOT senior"
    assert m(q, "Automation Engineer")
    assert not m(q, "Senior Automation Engineer")


def test_precedence_not_binds_tighter_than_and():
    # "ai NOT engineer" under implicit AND with controls:
    q = "controls NOT intern"
    assert m(q, "Controls Engineer")
    assert not m(q, "Controls Intern")


# ── positive_terms (drops negated) ────────────────────────────────────────────
def test_positive_terms_excludes_negated():
    pos = parse('"controls engineer" OR automation NOT senior').positive_terms()
    assert "controls engineer" in pos
    assert "automation" in pos
    assert "senior" not in pos


# ── robustness ────────────────────────────────────────────────────────────────
def test_empty_query_matches_anything():
    assert m("", "whatever")


def test_the_ai_engineer_case():
    # A controls-focused keyword set never matches an AI Engineer title.
    kws = ['"controls engineer"', "automation engineer", "mechanical engineer"]
    assert not any(parse(k).matches("AI Engineer") for k in kws)
    assert any(parse(k).matches("Controls Engineer") for k in kws)
