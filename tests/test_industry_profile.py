"""The genre-agnostic resolver: user override > shipped seed > generic fallback.
Emitted Muse categories must always be real (an invalid one zeroes the source)."""
import json
import industry_profile as ip


def setup_function(_):
    ip.clear_cache()


def test_empty_and_eng_resolve_to_engineering():
    for q in ("", "controls_engineering", "software", "robotics"):
        p = ip.resolve(q)
        assert p.eng_like is True
        assert p.muse_categories == ["Software Engineering", "Science and Engineering"]
        assert p.jobicy_industry == "engineering"


def test_all_emitted_muse_categories_are_valid():
    for q in ["health_informatics", "finance", "nursing", "legal", "culinary arts",
              "construction", "education", "marketing", "energy", "logistics", ""]:
        for c in ip.resolve(q).muse_categories:
            assert c in ip.MUSE_CATEGORIES_ALL, f"{q!r} -> invalid Muse category {c!r}"


def test_health_profile():
    p = ip.resolve("health_informatics")
    assert "Healthcare" in p.muse_categories
    assert p.jobicy_industry is None            # Jobicy is tech-only -> skip
    assert "informatics" in p.title_terms
    assert p.query_synonyms                       # widen recall for the field


def test_finance_profile():
    p = ip.resolve("finance")
    assert "Accounting and Finance" in p.muse_categories
    assert p.jobicy_industry == "finance"


def test_unknown_genre_is_generic_full_reach():
    p = ip.resolve("underwater basket weaving")
    assert p.source == "generic"
    assert p.muse_categories == []                # [] = fetch ALL categories (full reach)
    assert p.jobicy_industry is None


def test_sanitize_drops_invalid_muse():
    assert ip._sanitize_muse(["Healthcare", "Engineering", "Bogus"]) == ["Healthcare"]


def test_user_override_wins(tmp_path, monkeypatch):
    f = tmp_path / "industry_profiles.json"
    monkeypatch.setattr(ip, "_user_json_path", lambda: f)
    ip.clear_cache()
    ip.save_override("health_informatics",
                     {"muse_categories": ["Data and Analytics", "Bogus"],
                      "jobicy_industry": "data-science",
                      "query_synonyms": ["ehr"], "title_terms": ["x"]})
    p = ip.resolve("health_informatics")
    assert p.source == "user"
    assert p.muse_categories == ["Data and Analytics"]   # bogus sanitized out
    assert p.jobicy_industry == "data-science"


def test_ai_prompt_lists_only_real_categories():
    prompt = ip.build_ai_prompt("culinary arts")
    assert "Food and Hospitality Services" in prompt
    assert "culinary arts" in prompt
