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


def test_consulting_profile():
    p = ip.resolve("management consulting")
    assert p.source == "seed"
    assert p.muse_categories == ["Management", "Business Operations"]
    assert p.jobicy_industry == "business"          # knowledge work -> tech boards kept
    assert "advisory services" in p.query_synonyms
    assert "consultant" in p.title_terms and "engagement manager" in p.title_terms
    # the triggers scope tightly: consultant/advisory/strategy-consulting all hit it
    for q in ("consultant", "advisory", "strategy-consulting"):
        ip.clear_cache()
        assert ip.resolve(q).jobicy_industry == "business"


def test_consulting_does_not_misfire_on_bare_strategy():
    # "strategy" alone is deliberately NOT a consulting trigger (would misfire on
    # product/marketing strategy roles); it falls through to generic full-reach.
    p = ip.resolve("strategy")
    assert p.source == "generic"


def test_consulting_is_knowledge_work_keeps_tech_sources():
    # Consulting IS desk/knowledge work: tech-skewed boards must NOT be gated off.
    from search.keyword_strategy import gate_tech_sources, TECH_SKEWED_SOURCES
    src = list(TECH_SKEWED_SOURCES)
    assert gate_tech_sources(src, "management consulting") == src


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


# ── SOC major-group source map (item 23) ────────────────────────────────────
def test_soc_major_groups_has_23_entries():
    assert len(ip.SOC_MAJOR_GROUPS) == 23


def test_soc_major_groups_codes_are_two_digit_even():
    # BLS/O*NET-SOC major groups are the odd 2-digit prefixes 11..55.
    expected = {f"{n:02d}" for n in range(11, 56, 2)}
    assert set(ip.SOC_MAJOR_GROUPS.keys()) == expected


def test_soc_major_groups_only_emit_valid_muse_categories():
    for code, knobs in ip.SOC_MAJOR_GROUPS.items():
        for cat in knobs["muse"]:
            assert cat in ip.MUSE_CATEGORIES_ALL, f"group {code} -> invalid Muse category {cat!r}"


# ── O*NET-SOC exact-match tier (item 22) ────────────────────────────────────
# NOTE: this tier deliberately does a DETERMINISTIC lookup against
# coverage.entity._onet()'s table (+ title_core normalization), NOT
# coverage.entity.normalize_title()'s fuzzy path -- verified 2026-07-01 against
# the full ~62k-row real O*NET dataset that its rapidfuzz token_set_ratio
# scorer hands out misleadingly high/exact-looking scores to UNRELATED
# occupations (permutation/subset leniency), which is fine for that module's
# own dedup use case but not safe for ROUTING which job sources get queried.
# Tests below mock coverage.entity._onet (the table), the real seam used.
def _fake_table(entries: dict) -> dict:
    return dict(entries)


def test_onet_tier_fires_for_unseeded_occupation(monkeypatch):
    # "phlebotomist" has no seed rule and isn't tech/eng.
    monkeypatch.setattr("coverage.entity._onet",
                        lambda: _fake_table({"phlebotomist": ("31-9097.00", "Phlebotomists")}))
    p = ip.resolve("phlebotomist")
    assert p.source == "onet"
    assert p.muse_categories == ["Healthcare"]          # SOC 31 -> Healthcare Support
    assert p.jobicy_industry is None
    assert p.eng_like is False
    assert "phlebotomists" in p.title_terms


def test_onet_tier_no_exact_match_falls_through_to_generic(monkeypatch):
    monkeypatch.setattr("coverage.entity._onet",
                        lambda: _fake_table({"phlebotomist": ("31-9097.00", "Phlebotomists")}))
    p = ip.resolve("some obscure field xyz")
    assert p.source == "generic"


def test_onet_tier_singular_plural_fallback(monkeypatch):
    # O*NET canonical titles are almost always plural; a user's free-text field
    # is often singular -- the simple +/-"s" fallback must bridge that.
    monkeypatch.setattr("coverage.entity._onet",
                        lambda: _fake_table({"phlebotomists": ("31-9097.00", "Phlebotomists")}))
    p = ip.resolve("phlebotomist")
    assert p.source == "onet"


def test_onet_tier_unmapped_major_group_falls_through_to_generic(monkeypatch):
    monkeypatch.setattr("coverage.entity._onet",
                        lambda: _fake_table({"some obscure field xyz": ("99-9999.00", "Made Up Occupation")}))
    p = ip.resolve("some obscure field xyz")
    assert p.source == "generic"


def test_seed_rules_win_over_onet_tier(monkeypatch):
    # Even an exact O*NET match must never override an existing seed rule.
    def _boom():
        raise AssertionError("O*NET tier must not be consulted when a seed rule matches")
    monkeypatch.setattr("coverage.entity._onet", _boom)
    p = ip.resolve("nursing")
    assert p.source == "seed"


def test_onet_tier_exception_safety(monkeypatch):
    def _boom():
        raise RuntimeError("data file missing")
    monkeypatch.setattr("coverage.entity._onet", _boom)
    p = ip.resolve("some unseeded field")
    assert p.source == "generic"          # never crashes; falls back to full reach


def test_onet_tier_uses_real_bundled_data_end_to_end():
    # No mocking: exercises the real bundled stub against a title with no seed
    # rule (database roles aren't in _RULES) to prove the wiring works, not just
    # the mocked logic.
    ip.clear_cache()
    p = ip.resolve("database administrator")
    assert p.source == "onet"
    assert p.eng_like is False
    for c in p.muse_categories:
        assert c in ip.MUSE_CATEGORIES_ALL


def test_resolve_soc_returns_stable_code():
    ip.clear_cache()
    soc = ip.resolve_soc("registered nurse")
    assert soc is not None
    assert soc["code"] == "29-1141.00"
    assert soc["title"] == "Registered Nurses"


def test_resolve_soc_none_for_empty_or_unmatched():
    assert ip.resolve_soc("") is None
    assert ip.resolve_soc("underwater basket weaving") is None


def test_related_occupation_titles_noop_for_eng(monkeypatch):
    assert ip.related_occupation_titles("") == []
    assert ip.related_occupation_titles("mechanical engineering") == []


def test_related_occupation_titles_from_same_soc(monkeypatch):
    monkeypatch.setattr("coverage.entity._onet", lambda: {
        "phlebotomist": ("31-9097.00", "Phlebotomists"),
        "phlebotomy technician": ("31-9097.00", "Phlebotomists"),
        "lab assistant": ("31-9099.00", "Other Healthcare Support Workers"),
    })
    out = ip.related_occupation_titles("phlebotomist")
    assert "phlebotomy technician" in out
    assert "lab assistant" not in out          # different SOC code
    assert "phlebotomist" not in out           # excludes the query itself


def test_resolve_soc_skips_eng_industries():
    # An eng/tech field must NOT get a persisted SOC (byte-identical guard);
    # "controls engineer" previously mis-resolved to a chemical-engineer SOC.
    for q in ("software engineer", "mechanical engineer", "controls engineer",
              "robotics", "", "software"):
        assert ip.resolve_soc(q) is None


def test_resolve_soc_returns_code_for_nontech():
    soc = ip.resolve_soc("registered nurse")
    assert soc is not None and soc.get("code") and soc.get("title")


# ── item 10: SOC major-group -> penalty role to drop ─────────────────────────
def test_penalty_role_to_drop_by_soc_code():
    assert ip.penalty_role_to_drop(soc_code="49-9071.00") == "maintain"
    assert ip.penalty_role_to_drop(soc_code="41-4012.00") == "sales"
    assert ip.penalty_role_to_drop(soc_code="15-1252.00") is None   # software dev -> default
    assert ip.penalty_role_to_drop(soc_code="") is None
    assert ip.penalty_role_to_drop() is None


def test_penalty_role_to_drop_by_industry():
    # Resolves a free-text field to a SOC then maps the major group.
    ip.clear_cache()
    # Sales occupations resolve to SOC 41 -> drop "sales".
    got = ip.penalty_role_to_drop(industry="retail salesperson")
    assert got in ("sales", None)  # depends on the bundled O*NET stub; never raises


def test_penalty_role_to_drop_eng_is_none():
    # An eng/tech field must keep the default penalty set (byte-identical for Alex).
    assert ip.penalty_role_to_drop(industry="controls engineer") is None
    assert ip.penalty_role_to_drop(industry="") is None
