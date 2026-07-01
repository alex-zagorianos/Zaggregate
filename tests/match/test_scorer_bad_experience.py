"""Defense-in-depth (P2 item 12): a malformed experience.md (no '## ' headings --
a raw wizard paste) makes resume.experience_parser.load_experience raise
ValueError. scorer.extract_skill_terms / profile_text must catch that and degrade
to a NEUTRAL empty result, so a bad profile file never kills a scoring/daily run.
(The parser itself is fixed elsewhere; this pins the scorer's resilience.)"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from match import scorer
from models import JobResult


def _bad_experience(tmp_path) -> Path:
    # Plain-text resume with no markdown section headings -> parser ValueError.
    p = tmp_path / "experience.md"
    p.write_text("Jane Doe\nRegistered Nurse with 10 years bedside ICU experience.\n"
                 "Skilled in patient care, EHR, and IV therapy.\n", encoding="utf-8")
    return p


def test_extract_skill_terms_degrades_on_malformed(tmp_path):
    scorer._cache.clear()
    got = scorer.extract_skill_terms(experience_path=_bad_experience(tmp_path))
    assert got == frozenset()          # neutral, not a crash


def test_profile_text_degrades_on_malformed(tmp_path):
    scorer._profile_cache.clear()
    assert scorer.profile_text(experience_path=_bad_experience(tmp_path)) == ""


def test_score_job_survives_malformed_experience(tmp_path):
    # A full score_job call using the malformed profile must still return a score.
    scorer._cache.clear()
    terms = scorer.extract_skill_terms(experience_path=_bad_experience(tmp_path))
    job = JobResult(title="Registered Nurse", company="Mercy", location="Cincinnati, OH",
                    salary_min=None, salary_max=None, description="ICU patient care",
                    url="http://x/1", source_keyword="", created="", source_api="t")
    score, notes = scorer.score_job(job, keywords=["registered nurse"],
                                    location="Cincinnati, OH", skill_terms=terms)
    assert isinstance(score, int) and 0 <= score <= 100
