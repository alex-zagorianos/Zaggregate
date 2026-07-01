"""Semantic modulation of title credit (P2): when semantic ranking is ACTIVE and
the profile<->job similarity is very low, a full keyword title match is treated as
generic-token noise and its title component is capped (SEMANTIC_TITLE_CAP). This is
abstain-safe -- with no model / semantic off, the score is byte-identical."""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config
from match import scorer
from models import JobResult


def _job(title, desc="Some description."):
    return JobResult(title=title, company="Acme", location="Cincinnati, OH",
                     salary_min=None, salary_max=None, description=desc,
                     url="http://x/" + title.replace(" ", ""), source_keyword="",
                     created="", source_api="t")


KW = ["automation engineer"]
LOC = "Cincinnati, OH"


def test_low_similarity_caps_full_title_match(monkeypatch):
    # A QA role earns a full keyword title match for "automation engineer"; a low
    # semantic similarity vetoes that generic-token credit, capping the title
    # component (title 60%). scorer imports `match.semantic` lazily, so patch there.
    import match.semantic as sem
    monkeypatch.setattr(sem, "similarity", lambda a, b: 0.10)

    capped, notes = scorer.score_job(
        _job("Senior QA Automation Engineer"), keywords=KW, location=LOC,
        semantic_profile="controls automation plc embedded firmware")
    assert "sem-title-cap" in notes
    # Title component reported as the capped value.
    assert "title 60%" in notes


def test_high_similarity_keeps_full_title(monkeypatch):
    import match.semantic as sem
    monkeypatch.setattr(sem, "similarity", lambda a, b: 0.80)
    _, notes = scorer.score_job(
        _job("Senior QA Automation Engineer"), keywords=KW, location=LOC,
        semantic_profile="controls automation plc embedded firmware")
    assert "sem-title-cap" not in notes
    assert "title 100%" in notes


def test_abstains_without_profile_byte_identical(monkeypatch):
    # No semantic_profile -> m is None -> no cap, no sem component; identical to the
    # keyword-only score.
    import match.semantic as sem
    monkeypatch.setattr(sem, "similarity", lambda a, b: 0.10)  # would veto IF consulted
    with_off, notes = scorer.score_job(
        _job("Senior QA Automation Engineer"), keywords=KW, location=LOC)
    assert "sem-title-cap" not in notes
    assert "sem " not in notes
    baseline, _ = scorer.score_job(_job("Senior QA Automation Engineer"),
                                   keywords=KW, location=LOC)
    assert with_off == baseline


def test_low_sim_does_not_cap_a_partial_title(monkeypatch):
    # A title that already scores below the cap isn't lifted or flagged -- the veto
    # only ever LOWERS a high title score, never touches a low one.
    import match.semantic as sem
    monkeypatch.setattr(sem, "similarity", lambda a, b: 0.10)
    _, notes = scorer.score_job(
        _job("Graphic Designer"), keywords=KW, location=LOC,
        semantic_profile="controls automation plc")
    assert "sem-title-cap" not in notes


def test_config_flag_defaults_off():
    # SEMANTIC_RANKING must default OFF (flipping it is Alex's call). Only assert
    # the default when the env var isn't forcing it on for the test process.
    import os
    if "SEMANTIC_RANKING" not in os.environ:
        assert config.SEMANTIC_RANKING is False
