"""P4 — per-industry coverage scoping, history persistence, loop-until-dry signal."""
import json

from coverage import registry_history as H
from coverage.registry_coverage import (estimate_coverage,
                                        estimate_coverage_industry, loop_signal)
from scrape.company_registry import CompanyEntry, get_registry


# ── loop_signal transitions ──────────────────────────────────────────────────

def _h(observed, cov):
    return {"observed": observed, "coverage_pct": cov}


def test_loop_signal_rising_when_growing():
    hist = [_h(100, 40), _h(140, 55)]           # +40% -> rising
    assert loop_signal(hist) == "rising"


def test_loop_signal_dry_when_flat():
    hist = [_h(200, 90), _h(200, 90)]           # no new -> dry
    assert loop_signal(hist) == "dry"


def test_loop_signal_plateau_slow_growth_high_coverage():
    # two rounds of <2% growth AND coverage >=85 -> plateau
    hist = [_h(1000, 86), _h(1010, 87), _h(1018, 88)]
    assert loop_signal(hist) == "plateau"


def test_loop_signal_not_plateau_when_coverage_low():
    # slow growth but coverage <85 -> keep going
    hist = [_h(1000, 60), _h(1010, 61), _h(1018, 62)]
    assert loop_signal(hist) == "rising"


def test_loop_signal_insufficient_history_is_rising():
    assert loop_signal([]) == "rising"
    assert loop_signal([_h(10, 50)]) == "rising"


# ── industry-scoped estimate ─────────────────────────────────────────────────

def test_estimate_coverage_industry_scopes_list_a(tmp_path):
    cj = tmp_path / "companies.json"
    cj.write_text(json.dumps({"companies": [
        {"name": "HealthCo", "ats_type": "greenhouse", "slug": "healthco",
         "industries": ["health_informatics"]},
        {"name": "RoboCo", "ats_type": "greenhouse", "slug": "roboco",
         "industries": ["controls_engineering"]},
    ]}), encoding="utf-8")

    # list B overlaps only the health slice
    list_b = ["HealthCo", "SomeOtherHealthCo"]
    est = estimate_coverage_industry("health_informatics", list_b, user_json=cj)
    # list A is the health slice (HealthCo + hardcoded health registry); the
    # controls-only RoboCo must NOT be counted in list A's health identities.
    reg_health = get_registry(industry="health_informatics", user_json=cj)
    names = {e.name for e in reg_health}
    assert "HealthCo" in names and "RoboCo" not in names
    assert est.overlap >= 1                       # HealthCo recaptured


# ── history persistence round-trip ───────────────────────────────────────────

def test_record_and_load_history(tmp_path):
    reg = [CompanyEntry("A", "greenhouse", "a", []),
           CompanyEntry("B", "greenhouse", "b", [])]
    est = estimate_coverage(reg, ["A", "C"])      # overlap A -> defined
    p1 = H.record(est, "health_informatics", base=tmp_path, ts="20260630T000001Z")
    p2 = H.record(est, "health_informatics", base=tmp_path, ts="20260630T000002Z")
    assert p1 == p2                                # same industry file
    hist = H.load_history("health_informatics", base=tmp_path)
    assert len(hist) == 2
    assert hist[0]["ts"] == "20260630T000001Z"
    assert hist[0]["observed"] == est.observed
    assert hist[0]["industry"] == "health_informatics"


def test_history_slug_and_empty_industry(tmp_path):
    assert H.history_path("", base=tmp_path).name == "_all.jsonl"
    assert H.history_path("Health Informatics", base=tmp_path).name == "health-informatics.jsonl"


def test_record_serializes_undefined_estimate_as_null(tmp_path):
    # disjoint lists -> undefined estimate (nan); must serialize to valid JSON null
    est = estimate_coverage([CompanyEntry("A", "greenhouse", "a", [])], ["Z"])
    assert not est.defined
    H.record(est, "x", base=tmp_path, ts="20260630T000001Z")
    line = H.history_path("x", base=tmp_path).read_text(encoding="utf-8").strip()
    rec = json.loads(line)                         # would raise if NaN leaked in
    assert rec["n_hat"] is None and rec["coverage_pct"] is None
