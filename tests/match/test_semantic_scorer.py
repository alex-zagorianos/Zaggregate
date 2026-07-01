"""match/scorer.py semantic component: OFF by default (byte-identical), and when
enabled it adds a bounded 'sem' component that reflects profile<->job similarity."""
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import match.semantic as sem
from match.scorer import score_job
from models import JobResult


def _job(title, desc):
    return JobResult(title=title, company="Acme", location="Cincinnati, OH",
                     salary_min=None, salary_max=None, description=desc,
                     url="http://x/1", source_keyword="", created="", source_api="t")


def _reset():
    sem._model = None
    sem._load_failed = False
    sem._embed_one.cache_clear()


def test_disabled_by_default_no_sem_component(monkeypatch):
    monkeypatch.delenv("SEMANTIC_RANKING", raising=False)
    monkeypatch.setattr(sem.config, "SEMANTIC_RANKING", False, raising=False)
    _reset()
    # Even when a profile is passed, a disabled semantic layer must not fire.
    score, notes = score_job(_job("Clinical Informatics Manager", "healthcare analytics"),
                             keywords=["clinical informatics"], location="Cincinnati, OH",
                             semantic_profile="health informatics analytics leader")
    assert "sem" not in notes
    # And the score equals the same call with no profile at all (byte-identical path).
    score2, _ = score_job(_job("Clinical Informatics Manager", "healthcare analytics"),
                          keywords=["clinical informatics"], location="Cincinnati, OH")
    assert score == score2


# Real-model path (skips cleanly without model2vec / the cached model).
_HAVE = False
try:
    import model2vec  # noqa: F401
    _HAVE = sem._load() is not None
except Exception:
    _HAVE = False
finally:
    _reset()

real = pytest.mark.skipif(not _HAVE, reason="model2vec/model unavailable")


@real
def test_enabled_adds_sem_and_orders_by_semantics(monkeypatch):
    monkeypatch.setenv("SEMANTIC_RANKING", "1")
    _reset()
    profile = ("20 years health informatics, business intelligence, Power BI, Epic "
               "Clarity, SQL, healthcare analytics leadership")
    # Two jobs with the SAME keyword/location/data profile so only semantics differ.
    health = _job("Informatics Lead", "Lead healthcare analytics and BI strategy, Epic, Power BI")
    nurse = _job("Informatics Lead", "Registered nurse duties, patient care, ICU night shift")
    s_health, n_health = score_job(health, keywords=["informatics"], location="Cincinnati, OH",
                                   semantic_profile=profile)
    s_nurse, n_nurse = score_job(nurse, keywords=["informatics"], location="Cincinnati, OH",
                                 semantic_profile=profile)
    assert "sem" in n_health and "sem" in n_nurse
    assert s_health > s_nurse            # semantic signal separates same-keyword jobs


@real
def test_enabled_but_no_profile_abstains(monkeypatch):
    monkeypatch.setenv("SEMANTIC_RANKING", "1")
    _reset()
    _, notes = score_job(_job("Informatics Lead", "analytics"),
                         keywords=["informatics"], location="Cincinnati, OH",
                         semantic_profile=None)
    assert "sem" not in notes
