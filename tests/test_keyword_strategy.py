"""Tests for search.keyword_strategy — deriving broad, high-recall query keywords
from a user's (often narrow, seniority-laden) target-role list.

The measured problem this fixes: dad's config keywords were exec-title phrases
("VP Clinical Informatics", "Chief Medical Information Officer"), which return ~0
results on job APIs (phrase match). Broad FIELD terms ("clinical informatics")
return 20x more; seniority is handled in scoring, not the query string.
"""
import config
from search import keyword_strategy as ks


def test_deseniorize_strips_leading_seniority():
    assert ks.deseniorize("VP Clinical Informatics") == "clinical informatics"
    assert ks.deseniorize("Senior Controls Engineer") == "controls engineer"
    assert ks.deseniorize("Director Clinical Informatics") == "clinical informatics"
    assert ks.deseniorize("Health Informatics Director") == "health informatics"


def test_deseniorize_strips_dangling_connectives():
    # "VP of Engineering" -> drop vp + a now-leading "of"
    assert ks.deseniorize("VP of Engineering") == "engineering"
    assert ks.deseniorize("Head of Data Science") == "data science"


def test_deseniorize_is_noop_for_plain_ic_titles():
    for t in ("controls engineer", "registered nurse", "staff accountant".replace("staff ", ""),
              "UX designer", "HVAC technician"):
        assert ks.deseniorize(t) == t.lower()


def test_deseniorize_empty_when_only_seniority():
    assert ks.deseniorize("Director") == ""
    assert ks.deseniorize("VP") == ""


def test_broad_keeps_original_when_stem_empty():
    # A pure-seniority token can't be dropped to nothing — keep it so we still query something.
    out = ks.broad_query_keywords(["Director"], "")
    assert "director" in out


def test_broad_dedupes_case_insensitively_preserving_order():
    out = ks.broad_query_keywords(
        ["VP Clinical Informatics", "Director Clinical Informatics", "Clinical Informatics"], "")
    assert out == ["clinical informatics"]


def test_broad_adds_normalized_industry():
    out = ks.broad_query_keywords(["Data Analyst"], "health_informatics")
    assert "data analyst" in out
    assert "health informatics" in out       # underscores -> spaces


def test_broad_dad_profile_expands_recall():
    roles = ["VP Clinical Informatics", "Chief Medical Information Officer",
             "Director Clinical Informatics", "VP Health IT", "Health Informatics Director"]
    out = ks.broad_query_keywords(roles, "health_informatics")
    # the field stems the APIs can actually match
    assert "clinical informatics" in out
    assert "health informatics" in out
    assert "health it" in out
    # none of the zero-recall full exec phrases survive as query terms
    assert "vp clinical informatics" not in out
    assert "chief medical information officer" not in out


def test_broad_is_byte_identical_for_alex_default_keywords():
    # Alex's engineering IC titles carry no seniority tokens -> unchanged (order + values).
    out = ks.broad_query_keywords(list(config.DEFAULT_KEYWORDS), "")
    assert out == [k.lower() for k in config.DEFAULT_KEYWORDS]


def test_broad_does_not_mutate_input():
    roles = ["VP Data"]
    _ = ks.broad_query_keywords(roles, "finance")
    assert roles == ["VP Data"]


def test_broad_drops_too_short_stems():
    # a 2-char leftover isn't a useful query term
    out = ks.broad_query_keywords(["Sr QA"], "")
    assert "qa" not in out or all(len(k) >= 3 for k in out)


def test_broad_adds_bounded_synonyms():
    out = ks.broad_query_keywords(["Data Analyst"], "", synonyms=["business intelligence", "data analyst"])
    assert "business intelligence" in out      # added
    assert out.count("data analyst") == 1      # dup synonym not re-added


def test_effective_keywords_explicit_wins():
    assert ks.effective_keywords({"keywords": ["nurse"], "industry": "health"}) == ["nurse"]


def test_effective_keywords_noneng_project_without_keywords_not_engineering():
    import config
    out = ks.effective_keywords({"industry": "health_informatics"})
    assert "health informatics" in out
    assert out != list(config.DEFAULT_KEYWORDS)   # NOT the engineering fallback


def test_effective_keywords_eng_or_empty_falls_back_to_default():
    import config
    assert ks.effective_keywords({}) == list(config.DEFAULT_KEYWORDS)
    assert ks.effective_keywords({"industry": "controls_engineering"}) == list(config.DEFAULT_KEYWORDS)


# ── Tier 2: related-occupation synonyms (item 26) ────────────────────────────
def test_related_tier_adds_onet_titles_after_tier1(monkeypatch):
    import industry_profile
    monkeypatch.setattr(industry_profile, "related_occupation_titles",
                        lambda industry, exclude=(), limit=6: ["phlebotomy technician"])
    out = ks.broad_query_keywords(["Nurse"], "health_informatics", synonyms=["clinical informatics"])
    assert "clinical informatics" in out       # tier 1 present
    assert "phlebotomy technician" in out      # tier 2 present


def test_related_tier_never_displaces_user_terms(monkeypatch):
    import industry_profile
    monkeypatch.setattr(industry_profile, "related_occupation_titles",
                        lambda industry, exclude=(), limit=6: ["nurse"])  # would dupe a user term
    out = ks.broad_query_keywords(["Nurse"], "health_informatics")
    assert out.count("nurse") == 1


def test_related_tier_respects_combined_synonym_cap(monkeypatch):
    import industry_profile
    monkeypatch.setattr(industry_profile, "related_occupation_titles",
                        lambda industry, exclude=(), limit=6: [f"related term {i}" for i in range(10)])
    tier1 = [f"tier1 term {i}" for i in range(4)]
    out = ks.broad_query_keywords(["Analyst"], "health_informatics", synonyms=tier1)
    added = [k for k in out if k not in ("analyst", "health informatics")]
    assert len(added) <= ks._MAX_SYNONYMS
    # tier 1 fully present (priority), tier 2 only fills the remaining 2 slots
    for t in tier1:
        assert t in out
    assert sum(1 for k in out if k.startswith("related term")) == ks._MAX_SYNONYMS - len(tier1)


def test_related_tier_noop_for_eng_industry():
    # No mocking: industry_profile.related_occupation_titles's own eng_like gate
    # must suppress tier 2 for an explicit eng industry string, same as tier 1's
    # synonyms=[] for the eng seed profile — output is exactly the deseniorized
    # roles + the industry term, nothing more.
    out = ks.broad_query_keywords(["Controls Engineer"], "controls_engineering")
    assert out == ["controls engineer", "controls engineering"]


def test_related_tier_noop_for_empty_industry():
    out = ks.broad_query_keywords(list(config.DEFAULT_KEYWORDS), "")
    assert out == [k.lower() for k in config.DEFAULT_KEYWORDS]


def test_related_tier_end_to_end_real_data():
    # No mocking — exercises the real bundled O*NET data through both modules.
    import industry_profile
    industry_profile.clear_cache()
    out = ks.broad_query_keywords(["Analyst"], "database administrator")
    assert "database administrator" in out
