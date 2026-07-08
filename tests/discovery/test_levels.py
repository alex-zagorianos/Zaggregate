"""level_query_variants -- Phase 7 experience-level query-phrasing variants.

Pure function, no DB needed. Pins the hard safety rule: senior/manager/exec
never generate query-side variants (the exact recall-collapse
keyword_strategy.deseniorize() was built to prevent).
"""
from search.discovery import levels


def test_no_query_variants_for_senior_manager_exec():
    for level in ("senior", "manager", "exec", "Senior", "Manager/Exec"):
        assert levels.level_query_variants(["Controls Engineer"], level) == []


def test_entry_variants_are_additive():
    variants = levels.level_query_variants(["Controls Engineer"], "entry")
    terms = [v["term"] for v in variants]

    assert "Controls Engineer" not in terms
    assert any(t.startswith("Junior ") for t in terms)
    assert any(t.startswith("Associate ") for t in terms)
    assert any(t.startswith("Entry Level ") for t in terms)
    assert any(t.endswith(" I") for t in terms)
    for v in variants:
        assert v["tier"] == "exploratory"
        assert v["source"] == "level_variant"
        assert v["status"] == "suggested"


def test_mid_variants_small():
    variants = levels.level_query_variants(["Controls Engineer"], "mid")
    assert variants  # non-empty
    assert len(variants) <= 3
    terms = [v["term"] for v in variants]
    assert "Controls Engineer" not in terms


def test_blank_level_empty():
    assert levels.level_query_variants(["Controls Engineer"], "") == []
