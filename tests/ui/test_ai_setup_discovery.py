"""Phase 1 — tiered/uncapped AI-setup keyword schema (search-discovery-plan §5).

The OLD prompt capped recall at birth: it literally asked for "1-5 real job
titles" into a flat `target_titles` list, and gated `field` to CANONICAL_FIELDS
— neither ceiling had a matching downstream cap (`cfg['keywords']` is never
truncated). This suite covers the fix: a free-text `field`, a TIERED/UNCAPPED
`keywords` object (core/adjacent/exploratory), and `negatives` as suggestions
only. `exploratory` terms are offered into the `search.discovery.pool`
keyword_pool instead of the live query set; `negatives` fold into
`cfg['suggested_excludes']`, never the hard-drop `hard_no_titles`.

Also covers backward compatibility: a stale cached prompt or an older client
still emitting the OLD flat `target_titles` shape must keep applying unchanged.
"""
import json

import pytest

import config
import workspace
from tracker import db
from search.discovery import pool
from ui import ai_setup


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Mirrors tests/ui/test_ai_setup.py's fixture (project config/preferences)
    PLUS tests/discovery/test_pool.py's tmp_db fixture (tracker.db) — apply_setup
    now writes BOTH the project config/preferences AND the keyword_pool table."""
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "PREFERENCES_JSON", tmp_path / "preferences.json")
    monkeypatch.setattr(config, "PREFERENCES_MD", tmp_path / "preferences.md")
    monkeypatch.setattr(config, "COMPANIES_JSON", tmp_path / "companies.json")
    monkeypatch.setattr(workspace, "BASE_DIR", tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    return tmp_path


_TIERED = {
    "field": "data analytics",
    "experience_level": "mid",
    "keywords": {
        "core": ["Data Analyst", "BI Analyst"],
        "adjacent": ["Reporting Analyst", "Analytics Associate"],
        "exploratory": ["Insights Generalist", "Decision Scientist"],
    },
    "negatives": ["unpaid", "commission only"],
    "location": {"city": "Phoenix", "state": "AZ", "remote_ok": True},
    "min_salary": 85000,
}


def _block(payload=None):
    return "```json\n" + json.dumps(payload if payload is not None else _TIERED) + "\n```"


# ── tiered keywords: core+adjacent active in cfg, exploratory -> pool ─────────
def test_ai_setup_tiered_keywords_parse(isolated):
    summary = ai_setup.apply_setup(_block())
    cfg = workspace.load_config()
    assert cfg["keywords"] == ["Data Analyst", "BI Analyst",
                               "Reporting Analyst", "Analytics Associate"]
    # Exploratory titles never land in the live query set...
    assert "Insights Generalist" not in cfg["keywords"]
    assert "Decision Scientist" not in cfg["keywords"]
    # ...they land in the keyword_pool instead, tagged source='ai'/suggested.
    suggested = {r["term"]: r for r in pool.get_pool(status="suggested")}
    assert "Insights Generalist" in suggested
    assert "Decision Scientist" in suggested
    assert suggested["Insights Generalist"]["tier"] == "exploratory"
    assert suggested["Insights Generalist"]["source"] == "ai"
    assert suggested["Decision Scientist"]["tier"] == "exploratory"
    assert summary["field"] == "data analytics"
    assert summary["suggested_exploratory"] == ["Insights Generalist", "Decision Scientist"]


def test_ai_setup_tiered_location_and_salary_parse(isolated):
    parsed = ai_setup.parse_setup_block(_block())
    assert parsed["answers"]["location"] == "Phoenix, AZ"
    assert parsed["answers"]["remote_ok"] is True
    assert parsed["answers"]["salary_min"] == 85000
    assert parsed["answers"]["level"] == "Mid"          # experience_level -> wizard level


# ── backward compat: legacy target_titles shape still applies unchanged ──────
def test_ai_setup_legacy_target_titles_still_parses(isolated):
    legacy = {
        "field": "nursing",
        "target_titles": ["Registered Nurse", "ICU Nurse"],
        "location": "Boise, ID",
        "remote_ok": False,
        "salary_floor": 70000,
        "seniority": "mid",
        "preferences_md": "I want ICU roles.",
    }
    summary = ai_setup.apply_setup(_block(legacy))
    cfg = workspace.load_config()
    assert cfg["keywords"] == ["Registered Nurse", "ICU Nurse"]
    assert cfg["industry"] == "nursing"
    assert cfg["salary_min"] == 70000
    assert summary["field"] == "nursing"
    assert summary["target_titles"] == ["Registered Nurse", "ICU Nurse"]
    # A flat legacy list carries no tier signal -- nothing seeds the pool.
    assert pool.get_pool() == []
    assert summary["suggested_exploratory"] == []


def test_ai_setup_legacy_comma_string_titles_still_split(isolated):
    # Pre-existing weak-AI tolerance (S35): a comma-joined STRING instead of a
    # JSON list must still split into individual titles under the legacy path.
    legacy = dict(field="sales", target_titles="Account Exec, SDR, BDR",
                  location="NYC", seniority="mid")
    parsed = ai_setup.parse_setup_block(_block(legacy))
    assert parsed["answers"]["roles"] == ["Account Exec", "SDR", "BDR"]


# ── field: no longer gated by CANONICAL_FIELDS ────────────────────────────────
def test_ai_setup_field_no_longer_gated_by_canonical_list(isolated):
    # A field that resolves to a "generic" (no-routing) industry_profile must
    # be ACCEPTED (full reach), never rejected -- the whole point of removing
    # CANONICAL_FIELDS as a validation gate.
    generic = dict(_TIERED, field="underwater basket weaving")
    parsed = ai_setup.parse_setup_block(_block(generic))
    assert parsed["answers"]["industry"] == "underwater basket weaving"

    # A real off-list field (routes via the eng-like/seed tier) is also fine.
    real = dict(_TIERED, field="biomedical engineering")
    parsed2 = ai_setup.parse_setup_block(_block(real))
    assert parsed2["answers"]["industry"] == "biomedical engineering"


def test_ai_setup_blank_field_still_rejected(isolated):
    # The ONE remaining gate: a genuinely blank field has nothing to search on.
    blank = dict(_TIERED, field="")
    with pytest.raises(ai_setup.SetupBlockError) as ei:
        ai_setup.parse_setup_block(_block(blank))
    assert "missing a 'field'" in str(ei.value)


# ── negatives: suggestions only, never a hard drop ────────────────────────────
def test_ai_setup_negatives_never_reach_hard_no_titles(isolated):
    ai_setup.apply_setup(_block())
    cfg = workspace.load_config()
    assert cfg["suggested_excludes"] == ["unpaid", "commission only"]
    assert "hard_no_titles" not in cfg


def test_ai_setup_negatives_optional_and_never_raises(isolated):
    # Negatives are suggestions-only: a missing/malformed shape is just "none",
    # never an error (unlike keywords, which IS required).
    no_negatives = {k: v for k, v in _TIERED.items() if k != "negatives"}
    summary = ai_setup.apply_setup(_block(no_negatives))
    assert summary["suggested_excludes"] == []
    cfg = workspace.load_config()
    assert "suggested_excludes" not in cfg


# ── no length cap: 40 keywords all apply, none truncated ─────────────────────
def test_ai_setup_no_length_cap(isolated):
    many_core = [f"Title {i}" for i in range(20)]
    many_adjacent = [f"Adjacent Title {i}" for i in range(20)]
    block = dict(_TIERED, keywords={"core": many_core, "adjacent": many_adjacent,
                                    "exploratory": []})
    ai_setup.apply_setup(_block(block))
    cfg = workspace.load_config()
    assert len(cfg["keywords"]) == 40
    assert set(cfg["keywords"]) == set(many_core + many_adjacent)


def test_ai_setup_keywords_core_adjacent_deduped(isolated):
    # A title repeated across tiers (a weak AI might do this) must not double
    # up in the live query set.
    block = dict(_TIERED, keywords={
        "core": ["Data Analyst"], "adjacent": ["Data Analyst", "BI Analyst"],
        "exploratory": []})
    parsed = ai_setup.parse_setup_block(_block(block))
    assert parsed["answers"]["roles"] == ["Data Analyst", "BI Analyst"]


def test_ai_setup_keywords_both_tiers_empty_raises(isolated):
    block = dict(_TIERED, keywords={"core": [], "adjacent": [], "exploratory": ["x"]})
    with pytest.raises(ai_setup.SetupBlockError):
        ai_setup.parse_setup_block(_block(block))


def test_ai_setup_keywords_comma_string_tier_is_split_not_rejected(isolated):
    # A weak AI emitting a comma-joined STRING (not a JSON array) for a tier is
    # tolerated the same way legacy target_titles is (S35 precedent) -- split,
    # not rejected.
    block = dict(_TIERED, keywords={"core": "Data Analyst, BI Analyst",
                                    "adjacent": [], "exploratory": []})
    parsed = ai_setup.parse_setup_block(_block(block))
    assert parsed["answers"]["roles"] == ["Data Analyst", "BI Analyst"]


def test_ai_setup_keywords_bad_tier_shape_raises(isolated):
    # Only a genuinely non-array (non-string, non-list) tier shape is ever
    # rejected -- never a length.
    block = dict(_TIERED, keywords={"core": 12345, "adjacent": [], "exploratory": []})
    with pytest.raises(ai_setup.SetupBlockError):
        ai_setup.parse_setup_block(_block(block))


# ── prompt text: no "1-5" cap, field is free text, tiered keys documented ────
def test_ai_setup_prompt_has_no_cap_and_field_is_free_text():
    p = ai_setup.build_setup_prompt()
    assert "1-5" not in p
    assert "MAXIMUM RECALL" in p
    assert "no length limit" in p.lower()
    for key in ("keywords", "core", "adjacent", "exploratory", "negatives",
                "experience_level", "min_salary", "remote_ok"):
        assert key in p
    low = p.lower()
    assert "free text" in low
    assert "not limited to any fixed list" in low
    # The old canonical-field pick-list is gone from the prompt (P1: field is
    # free text, not a fixed vocabulary).
    assert "chosen only from this list" not in low


def test_ai_setup_full_prompt_also_has_no_cap_and_shares_body():
    # build_full_setup_prompt shares _config_block_body -- verify it inherits
    # the same fix (no drift between the two prompts).
    full = ai_setup.build_full_setup_prompt()
    assert "1-5" not in full
    assert "MAXIMUM RECALL" in full
    assert "keywords" in full and "```seeds" in full


# ── combined config+seeds reply still splits correctly under the new schema ──
def test_ai_setup_full_reply_splits_under_new_schema(isolated):
    reply = (
        "```json\n" + json.dumps(_TIERED) + "\n```\n\n"
        "```seeds\n"
        "Acme | https://boards.greenhouse.io/acme\n"
        "```\n"
    )
    config_text, seed_text = ai_setup.split_full_reply(reply)
    parsed = ai_setup.parse_setup_block(config_text)
    assert parsed["answers"]["industry"] == "data analytics"
    assert parsed["answers"]["roles"] == ["Data Analyst", "BI Analyst",
                                          "Reporting Analyst", "Analytics Associate"]
    assert "Acme | https://boards.greenhouse.io/acme" in seed_text
