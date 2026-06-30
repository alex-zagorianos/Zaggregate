from models import JobResult
from match.scorer import score_job


def _job(title, desc=""):
    return JobResult(title=title, company="X", location="Remote", salary_min=None,
                     salary_max=None, description=desc, url="http://x/1",
                     source_keyword="", created="")


def _score(title, desc, excludes):
    s, notes = score_job(_job(title, desc), keywords=["controls engineer"],
                         location="Remote", skill_terms=frozenset(),
                         exclude_keywords=excludes)
    return s, notes


def test_exclude_keyword_no_substring_false_positive():
    base, _ = _score("Controls Engineer", "maintain and improve maintainability", [])
    pen, notes = _score("Controls Engineer", "maintain and improve maintainability", ["ai"])
    assert pen == base          # 'ai' is not a standalone word in 'maintain'
    assert "PENALTY" not in notes


def test_exclude_keyword_matches_whole_word():
    base, _ = _score("Controls Engineer", "build ai systems", [])
    pen, notes = _score("Controls Engineer", "build ai systems", ["ai"])
    assert pen < base
    assert "PENALTY: ai" in notes


def test_exclude_keyword_multiword_phrase():
    base, _ = _score("Controls Engineer", "machine learning research", [])
    pen, _ = _score("Controls Engineer", "machine learning research", ["machine learning"])
    assert pen < base
