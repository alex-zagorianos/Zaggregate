"""A1: daily_run's tiered-scrape default flips ON above ~200 registry companies,
while an explicit tiered_scrape in the config always wins. Pure-function test of
_tiered_default -- no run, no DB writes."""
import daily_run
from scrape import company_registry


def _patch_count(monkeypatch, n):
    monkeypatch.setattr(company_registry, "industry_company_count", lambda *a, **k: n)


def test_default_off_at_or_below_threshold(monkeypatch):
    _patch_count(monkeypatch, 200)
    assert daily_run._tiered_default({}, None) is False


def test_default_on_above_threshold(monkeypatch):
    _patch_count(monkeypatch, 201)
    assert daily_run._tiered_default({}, None) is True


def test_default_on_for_large_registry(monkeypatch):
    _patch_count(monkeypatch, 626)
    assert daily_run._tiered_default({}, None) is True


def test_explicit_true_wins_even_when_small(monkeypatch):
    _patch_count(monkeypatch, 5)
    assert daily_run._tiered_default({"tiered_scrape": True}, None) is True


def test_explicit_false_wins_even_when_large(monkeypatch):
    _patch_count(monkeypatch, 999)
    assert daily_run._tiered_default({"tiered_scrape": False}, None) is False


def test_count_error_degrades_to_off(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("registry read failed")
    monkeypatch.setattr(company_registry, "industry_company_count", boom)
    assert daily_run._tiered_default({}, None) is False
