"""A search keyword that degrades to a single GENERIC word ("VP Health IT" ->
"health") must not award full title credit to every posting that merely mentions
it (measured: a Phlebotomist / FBI 'Special Agent: Healthcare Services' scored as
high as an on-target role for a health-informatics seeker). A specific single-term
match (Alex's "controls") is unaffected."""
from search import query
from match.scorer import _title_score


def _q(*kws):
    return [query.parse(k) for k in kws]


def test_single_generic_word_match_is_capped():
    qs = _q("VP Health IT")               # -> significant term is just "health"
    assert _title_score(qs, "lab assistant - phlebotomist, mercy health") <= 0.5
    assert _title_score(qs, "special agent: healthcare services") <= 0.5


def test_two_generic_words_not_capped():
    # "health data" is a real signal for a health-data seeker -> keeps credit.
    qs = _q("VP Health Data Analytics")   # sig = health, data, analytics
    assert _title_score(qs, "hospital health data governance lead") > 0.5


def test_specific_single_term_match_full_credit():
    # Alex's field term "controls" is specific (not generic) -> full credit, so a
    # "Process Controls Specialist" is unaffected by the cap.
    qs = _q("controls engineer")          # sig = controls ("engineer" is a stopword)
    assert _title_score(qs, "process controls specialist") == 1.0


def test_specific_field_term_beats_generic():
    # "informatics" is specific -> an on-target title keeps strong credit.
    qs = _q("VP Clinical Informatics")
    assert _title_score(qs, "clinical informatics analyst") > 0.5
