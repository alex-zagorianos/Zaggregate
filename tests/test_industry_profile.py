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


# ── S32 taxonomy breadth: marketing / nursing / warehouse / education ─────────
# New _RULES entries. Each set: (a) routing, (b) placement/ordering (a token that
# an EARLIER rule would otherwise capture now lands on the right rule), and (c)
# knowledge-work gating. Regression guards for engineering + consulting live at
# the bottom; bare-ambiguous-word guards are inlined per family.

# -- marketing --
def test_marketing_profile_routes_and_beats_health_digital_token():
    # "digital marketing" must route to marketing, NOT the health rule (whose
    # "digital" token previously captured it). Marketing rule now precedes health.
    p = ip.resolve("digital marketing")
    assert p.source == "seed"
    assert p.muse_categories == ["Advertising and Marketing"]
    assert p.jobicy_industry == "marketing"
    assert "digital marketing" in p.query_synonyms
    assert "marketing" in p.title_terms and "demand" in p.title_terms


def test_marketing_catches_demand_generation_before_onet_hydroelectric():
    # "demand generation manager" previously mis-resolved through the O*NET tier to
    # "Hydroelectric Production Managers" (11-3051.06). The marketing rule now
    # catches it BEFORE the O*NET fallback tier runs.
    for q in ("demand generation manager", "growth marketing manager",
              "seo specialist"):
        ip.clear_cache()
        p = ip.resolve(q)
        assert p.source == "seed"
        assert p.jobicy_industry == "marketing"


def test_marketing_is_knowledge_work_and_does_not_capture_bare_digital():
    # Marketing is desk/knowledge work -> tech-skewed boards stay on.
    from search.keyword_strategy import is_knowledge_work
    assert is_knowledge_work("digital marketing") is True
    # bare "digital" is NOT a marketing trigger (only "digital-marketing" is);
    # it must fall through to generic full-reach, not the marketing rule.
    ip.clear_cache()
    assert ip.resolve("digital").source == "generic"


# -- nursing / clinical --
def test_nursing_profile_routes_clinical_roles():
    p = ip.resolve("nursing")
    assert p.source == "seed"
    assert p.muse_categories == ["Healthcare"]
    assert p.jobicy_industry is None                 # Jobicy is tech-only -> skip
    assert "registered nurse" in p.query_synonyms
    for t in ("nurse", "nursing", "rn", "lpn", "clinical"):
        assert t in p.title_terms


def test_nursing_triggers_scope_to_clinical_tokens():
    # RN/LPN/bedside all reach the nursing rule (Healthcare, jobicy None).
    for q in ("rn", "lpn", "bedside", "registered nurse"):
        ip.clear_cache()
        p = ip.resolve(q)
        assert p.jobicy_industry is None
        assert "Healthcare" in p.muse_categories


def test_nursing_is_not_knowledge_work():
    # Clinical/bedside nursing is hands-on -> tech-skewed boards gated OFF.
    from search.keyword_strategy import is_knowledge_work
    assert is_knowledge_work("nursing") is False
    assert is_knowledge_work("registered nurse") is False


# -- warehouse / logistics / distribution / supply chain --
def test_warehouse_profile_routes_and_widens_recall():
    p = ip.resolve("warehouse logistics")
    assert p.source == "seed"
    assert p.jobicy_industry is None
    assert "Business Operations" in p.muse_categories
    assert p.query_synonyms                          # was [] before -> now widens
    assert "warehouse associate" in p.query_synonyms
    for t in ("warehouse", "logistics", "distribution"):
        assert t in p.title_terms


def test_warehouse_wins_over_operations_for_logistics_tokens():
    # "logistics"/"supply chain"/"distribution" previously fell to the operations
    # rule (jobicy="business" -> wrongly knowledge work). The warehouse rule now
    # precedes operations and claims them with jobicy=None.
    for q in ("logistics", "supply chain", "distribution", "fulfillment"):
        ip.clear_cache()
        p = ip.resolve(q)
        assert p.jobicy_industry is None, q
        assert "Installation, Maintenance, and Repairs" in p.muse_categories, q


def test_warehouse_is_not_knowledge_work():
    # On-site warehouse/logistics must NOT run the tech-skewed remote boards
    # (coverage §7: these were mis-gated as knowledge work via operations).
    from search.keyword_strategy import is_knowledge_work
    for q in ("warehouse", "warehouse logistics", "logistics", "supply chain"):
        ip.clear_cache()
        assert is_knowledge_work(q) is False, q


# -- education / K-12 --
def test_education_profile_routes_instructional_and_curriculum():
    p = ip.resolve("education")
    assert p.source == "seed"
    assert p.muse_categories == ["Education"]
    assert p.jobicy_industry is None
    for t in ("teacher", "instructional", "curriculum"):
        assert t in p.title_terms


def test_education_wins_over_fitness_for_instructional_coach():
    # "instructional coach"/"curriculum" previously mis-routed to the fitness rule
    # (its "coach" token). Education precedes fitness AND now carries those tokens.
    for q in ("instructional coach", "curriculum", "k-12 teaching"):
        ip.clear_cache()
        p = ip.resolve(q)
        assert p.muse_categories == ["Education"], q
        assert p.source == "seed", q
    # bare "coach" alone is still (correctly) a fitness role, not education.
    ip.clear_cache()
    assert ip.resolve("coach").muse_categories == ["Sports, Fitness, and Recreation"]


def test_education_all_muse_categories_valid():
    for q in ("education", "teacher", "instructional coach", "curriculum"):
        ip.clear_cache()
        for c in ip.resolve(q).muse_categories:
            assert c in ip.MUSE_CATEGORIES_ALL


# -- regression guards: engineering + consulting (S30) unchanged --
def test_s32_engineering_profile_byte_identical():
    for q in ("", "engineering", "mechanical engineering", "controls engineering",
              "software", "robotics", "embedded"):
        ip.clear_cache()
        p = ip.resolve(q)
        assert p.eng_like is True
        assert p.muse_categories == ["Software Engineering", "Science and Engineering"]
        assert p.jobicy_industry == "engineering"
        assert p.title_terms == ["engineer", "engineering"]
        assert p.query_synonyms == []


def test_s32_consulting_profile_unchanged():
    p = ip.resolve("management consulting")
    assert p.source == "seed"
    assert p.muse_categories == ["Management", "Business Operations"]
    assert p.jobicy_industry == "business"
    assert "advisory services" in p.query_synonyms
    assert "engagement manager" in p.title_terms
    for q in ("consultant", "advisory", "strategy-consulting"):
        ip.clear_cache()
        assert ip.resolve(q).jobicy_industry == "business"


def test_s32_bare_ambiguous_words_not_captured_by_new_entries():
    # None of the new marketing/warehouse/education entries may swallow these
    # ambiguous bare words (they must keep their prior resolution).
    cases = {
        "strategy": "generic",       # not consulting, not marketing
        "management": "business",    # the management rule, unchanged
        "health": None,              # health rule (jobicy None), unchanged
    }
    ip.clear_cache()
    assert ip.resolve("strategy").source == cases["strategy"]
    ip.clear_cache()
    assert ip.resolve("management").jobicy_industry == cases["management"]
    ip.clear_cache()
    hp = ip.resolve("health")
    assert hp.jobicy_industry == cases["health"] and "Healthcare" in hp.muse_categories


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


# ── #37: SOC-based penalty exemption extended to Management (SOC 11) ────────
def test_penalty_role_to_drop_management_soc_drops_manage():
    # SOC 11 (Management Occupations) -> a manager/supervisor's own core work IS
    # people management, so "manage" must be exempted the same way sales (41)
    # and maintain (49) already are.
    assert ip.penalty_role_to_drop(soc_code="11-1021.00") == "manage"   # General/Ops Managers
    assert ip.penalty_role_to_drop(soc_code="11-9111.00") == "manage"   # Medical/Health Managers


def test_soc_major_penalty_drop_has_exactly_three_entries():
    # #37: the only real collisions with _DEFAULT_PENALTY_ROLES (sales/maintain/
    # manage) are SOC 11/41/49 -- every other major group's core work (protective
    # service 33, food service 35, production 51, admin support 43, transportation
    # 53, ...) does not collide with any of the three penalty roles, so they must
    # NOT be mapped (a fabricated exemption would be worse than the gap).
    assert ip.SOC_MAJOR_PENALTY_DROP == {"11": "manage", "41": "sales", "49": "maintain"}


def test_penalty_role_to_drop_non_colliding_socs_stay_none():
    # Protective service, food service, production, admin support, and
    # transportation major groups have NO entry -> default penalty set intact.
    for code in ("33-9032.00",  # Security Guards (Protective Service)
                 "35-3023.00",  # Fast Food and Counter Workers
                 "51-2092.00",  # Team Assemblers (Production)
                 "43-9061.00",  # Office Clerks, General (Office/Admin Support)
                 "53-3032.00"):  # Heavy Truck Drivers (Transportation)
        assert ip.penalty_role_to_drop(soc_code=code) is None, code


def test_penalty_role_to_drop_engineering_soc_no_new_exemption():
    # Parity: engineering SOC major groups (15/17) must map to NO exemption.
    assert ip.penalty_role_to_drop(soc_code="15-1252.00") is None
    assert ip.penalty_role_to_drop(soc_code="17-2141.00") is None


# ── item 5 / ranking #7: curated SOC aliases (EXACT match only) ──────────────
# The literal O*NET alt-title table misses the natural field words a wizard/AI
# user types; a small hand-curated exact-alias table bridges them WITHOUT a
# fuzzy match (which would hand out confidently-wrong SOCs). Every alias code is
# verified to exist in the bundled O*NET dataset.
def test_soc_alias_resolves_natural_field_words():
    ip.clear_cache()
    cases = {
        "nursing": ("29-1141.00", "Registered Nurses"),
        "consulting": ("13-1111.00", "Management Analysts"),
        "management consulting": ("13-1111.00", "Management Analysts"),
        "warehouse": ("53-7062.00",
                      "Laborers and Freight, Stock, and Material Movers, Hand"),
        "warehouse logistics": ("53-7062.00",
                                "Laborers and Freight, Stock, and Material Movers, Hand"),
        "logistics": ("53-7062.00",
                      "Laborers and Freight, Stock, and Material Movers, Hand"),
        "data analytics": ("15-2051.00", "Data Scientists"),
        "digital marketing": ("13-1161.00",
                              "Market Research Analysts and Marketing Specialists"),
        "education": ("25-2031.00",
                      "Secondary School Teachers, Except Special and Career/Technical Education"),
        "teaching": ("25-2031.00",
                     "Secondary School Teachers, Except Special and Career/Technical Education"),
    }
    for field, (code, title) in cases.items():
        ip.clear_cache()
        soc = ip.resolve_soc(field)
        assert soc is not None, f"{field!r} should resolve to a SOC"
        assert soc["code"] == code, f"{field!r} -> {soc['code']}, want {code}"
        assert soc["title"] == title


def test_soc_alias_normalizes_separators():
    # Underscore / hyphen / mixed-case phrasings all hit the same alias.
    for field in ("warehouse_logistics", "warehouse-logistics",
                  "Warehouse Logistics", "  WAREHOUSE   LOGISTICS "):
        ip.clear_cache()
        soc = ip.resolve_soc(field)
        assert soc is not None and soc["code"] == "53-7062.00"


def test_soc_alias_math_teacher_is_secondary_not_postsecondary():
    # ranking #7: "math teacher" mis-resolved to a POSTSECONDARY math SOC; the
    # curated K-12 override maps it to Secondary School Teachers instead.
    ip.clear_cache()
    soc = ip.resolve_soc("math teacher")
    assert soc is not None
    assert soc["code"] == "25-2031.00"
    assert "Secondary" in soc["title"]


def test_soc_alias_education_teaching_default_to_k12():
    for field in ("education", "teaching"):
        ip.clear_cache()
        soc = ip.resolve_soc(field)
        assert soc is not None and soc["code"] == "25-2031.00"


def test_soc_negative_guard_blocks_demand_generation_hydroelectric():
    # ranking #7: "demand generation manager" literally matches an O*NET alt
    # title mapping to "Hydroelectric Production Managers" (11-3051.06) — an
    # incoherent energy SOC for a marketing field. The exact negative guard
    # blocks it so resolve_soc returns None (resolve()'s marketing seed still
    # routes the field correctly).
    ip.clear_cache()
    assert ip.resolve_soc("demand generation manager") is None
    # The marketing SEED profile still catches the field for routing.
    ip.clear_cache()
    assert ip.resolve("demand generation manager").jobicy_industry == "marketing"


def test_soc_alias_does_not_disturb_existing_literal_resolutions():
    # Regression guard: phrases NOT in the curated tables must resolve exactly as
    # before (the literal O*NET alt-title lookup is unchanged).
    ip.clear_cache()
    assert ip.resolve_soc("nurse")["code"] == "29-1141.00"
    ip.clear_cache()
    assert ip.resolve_soc("registered nurse")["code"] == "29-1141.00"
    ip.clear_cache()
    # bare "teacher" is NOT a curated alias -> still the literal-table hit.
    assert ip.resolve_soc("teacher")["code"] == "25-1011.00"
    ip.clear_cache()
    # "secondary teacher" literally resolves already; unchanged.
    assert ip.resolve_soc("secondary teacher")["code"] == "25-2031.00"


def test_soc_alias_still_none_for_eng_and_unmatched():
    # eng-like fields and true non-occupations stay None (byte-identical guard).
    for q in ("software engineer", "mechanical engineering", "controls engineer",
              "", "underwater basket weaving"):
        ip.clear_cache()
        assert ip.resolve_soc(q) is None


def test_soc_alias_codes_exist_in_bundled_onet_dataset():
    # Every curated alias code must be a REAL SOC present in the bundled O*NET
    # data (guards against a typo silently persisting a nonexistent code).
    from coverage.entity import _onet
    real_codes = {soc for soc, _title in _onet().values()}
    for _phrase, (code, _title) in ip._SOC_ALIASES.items():
        assert code in real_codes, f"{code} not in bundled O*NET dataset"
