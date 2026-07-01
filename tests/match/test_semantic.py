"""match/semantic.py — optional local Model2Vec similarity signal. The default
(disabled) path must no-op so the deterministic scorer stays byte-identical."""
import importlib
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import match.semantic as sem


def _reset():
    sem._model = None
    sem._load_failed = False
    sem._embed_one.cache_clear()


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SEMANTIC_RANKING", raising=False)
    monkeypatch.setattr(sem.config, "SEMANTIC_RANKING", False, raising=False)
    _reset()
    assert sem.available() is False
    assert sem.similarity("a", "b") is None          # no-op when disabled


def test_env_toggle_parsing(monkeypatch):
    for val, want in [("1", True), ("true", True), ("yes", True),
                      ("0", False), ("false", False), ("", False)]:
        monkeypatch.setenv("SEMANTIC_RANKING", val)
        assert sem._enabled() is want


# The real-model tests need model2vec + the cached model; skip cleanly otherwise.
_HAVE_MODEL = False
try:
    import model2vec  # noqa: F401
    _m = sem._load()
    _HAVE_MODEL = _m is not None
except Exception:
    _HAVE_MODEL = False
finally:
    _reset()

real_model = pytest.mark.skipif(not _HAVE_MODEL, reason="model2vec/model unavailable")


@real_model
def test_available_when_enabled(monkeypatch):
    monkeypatch.setenv("SEMANTIC_RANKING", "1")
    _reset()
    assert sem.available() is True


@real_model
def test_similarity_orders_by_field(monkeypatch):
    monkeypatch.setenv("SEMANTIC_RANKING", "1")
    _reset()
    resume = ("20 years health informatics business intelligence, Power BI, Epic "
              "Clarity, SQL analytics leadership, data governance")
    health_job = "VP of Clinical Informatics — lead healthcare analytics and BI strategy"
    nurse_job = "Registered Nurse, ICU night shift, direct patient care, BLS/ACLS"
    s_health = sem.similarity(resume, health_job)
    s_nurse = sem.similarity(resume, nurse_job)
    assert 0.0 <= s_nurse <= s_health <= 1.0
    assert s_health - s_nurse > 0.1          # clear semantic separation


@real_model
def test_similarity_empty_and_clamp(monkeypatch):
    monkeypatch.setenv("SEMANTIC_RANKING", "1")
    _reset()
    assert sem.similarity("", "x") is None
    assert sem.similarity("data engineer", "") is None
    s = sem.similarity("python", "python")
    assert 0.0 <= s <= 1.0
