"""AI-assisted setup (§6.3 / §6.7 / SB-2a): the BYO-AI onboarding path.

Covers the pure prompt/parse/apply functions in ui.ai_setup (no display / no
LLM / no network needed). The GUI dialog is a thin Toplevel over these and is
smoke-built in tests/ui/test_dialogs.py-style suites; the logic is here.
"""
import json

import pytest

import config
import workspace
import preferences
from ui import ai_setup


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "PREFERENCES_JSON", tmp_path / "preferences.json")
    monkeypatch.setattr(config, "PREFERENCES_MD", tmp_path / "preferences.md")
    monkeypatch.setattr(config, "COMPANIES_JSON", tmp_path / "companies.json")
    monkeypatch.setattr(workspace, "BASE_DIR", tmp_path)
    return tmp_path


# ── prompt generation ─────────────────────────────────────────────────────────
def test_setup_prompt_is_static_and_documents_vocab():
    p = ai_setup.build_setup_prompt()
    assert "```json" in p
    for key in ("field", "target_titles", "location", "salary_floor",
                "seniority", "radius_miles", "preferences_md", "remote_ok"):
        assert key in p
    # The canonical field vocabulary is enumerated so the AI can only pick valid
    # tokens (kills the free-text routing bug at the source).
    for tok in ("data analytics", "nursing", "warehouse", "consulting", "other"):
        assert tok in p


def test_setup_prompt_calls_no_llm_and_reads_nothing(isolated):
    # Pure/static: two calls are byte-identical and touch no disk.
    assert ai_setup.build_setup_prompt() == ai_setup.build_setup_prompt()


# ── strict parser: happy paths ────────────────────────────────────────────────
_GOOD = {
    "field": "Data Analytics",
    "target_titles": ["Data Analyst", "BI Analyst"],
    "location": "Phoenix, AZ",
    "remote_ok": True,
    "radius_miles": 40,
    "salary_floor": 85000,
    "seniority": "mid",
    "preferences_md": "I want data analyst roles. I love SQL. Avoid pure sales.",
}


def test_parse_setup_block_maps_to_wizard_answers():
    parsed = ai_setup.parse_setup_block("```json\n" + json.dumps(_GOOD) + "\n```")
    a = parsed["answers"]
    assert a["roles"] == ["Data Analyst", "BI Analyst"]
    assert a["location"] == "Phoenix, AZ"
    assert a["salary_min"] == 85000
    assert a["industry"] == "data analytics"    # canonical, space form
    assert a["level"] == "Mid"                   # seniority -> wizard level
    assert "SQL" in a["about"]
    assert parsed["extras"]["radius"] == 40
    assert parsed["extras"]["remote_only"] is False


def test_parse_tolerates_prose_around_the_block():
    text = ("Sure! Here is your setup:\n```json\n" + json.dumps(_GOOD)
            + "\n```\nHope that helps.")
    parsed = ai_setup.parse_setup_block(text)
    assert parsed["answers"]["industry"] == "data analytics"


def test_parse_remote_only_sets_remote_flags():
    block = dict(_GOOD, location="Remote")
    parsed = ai_setup.parse_setup_block(json.dumps(block))
    assert parsed["answers"]["location"] == "Remote"
    assert parsed["answers"]["remote_ok"] is True
    assert parsed["extras"]["remote_only"] is True


def test_parse_other_field_maps_to_empty_industry():
    block = dict(_GOOD, field="other")
    parsed = ai_setup.parse_setup_block(json.dumps(block))
    assert parsed["answers"]["industry"] == ""     # generic full reach
    assert parsed["extras"]["field_token"] == "other"


def test_parse_accepts_close_synonym_field_via_seed_profile():
    # "management consulting" isn't a bare canonical token but resolves to the
    # consulting seed profile, so it's tolerated (not rejected).
    block = dict(_GOOD, field="management consulting")
    parsed = ai_setup.parse_setup_block(json.dumps(block))
    assert parsed["answers"]["industry"] == "management consulting"


def test_parse_string_title_is_wrapped():
    block = dict(_GOOD, target_titles="Data Analyst")
    parsed = ai_setup.parse_setup_block(json.dumps(block))
    assert parsed["answers"]["roles"] == ["Data Analyst"]


# ── strict parser: error paths (actionable, never partial-apply) ──────────────
@pytest.mark.parametrize("text,needle", [
    ("", "Nothing pasted"),
    ("no json in here at all", "valid JSON config block"),
    ('["not","an","object"]', "must be a JSON object"),
])
def test_parse_bad_input_raises_actionable(text, needle):
    with pytest.raises(ai_setup.SetupBlockError) as ei:
        ai_setup.parse_setup_block(text)
    assert needle in str(ei.value)


def test_parse_unknown_field_lists_the_vocabulary():
    block = dict(_GOOD, field="quantum astrology")
    with pytest.raises(ai_setup.SetupBlockError) as ei:
        ai_setup.parse_setup_block(json.dumps(block))
    msg = str(ei.value)
    assert "Unknown field" in msg and "nursing" in msg   # vocab listed


def test_parse_missing_field_is_actionable():
    block = {k: v for k, v in _GOOD.items() if k != "field"}
    with pytest.raises(ai_setup.SetupBlockError) as ei:
        ai_setup.parse_setup_block(json.dumps(block))
    assert "missing a 'field'" in str(ei.value)


def test_parse_empty_titles_raises():
    block = dict(_GOOD, target_titles=[])
    with pytest.raises(ai_setup.SetupBlockError):
        ai_setup.parse_setup_block(json.dumps(block))


def test_parse_bad_salary_raises():
    block = dict(_GOOD, salary_floor="lots")
    with pytest.raises(ai_setup.SetupBlockError):
        ai_setup.parse_setup_block(json.dumps(block))


def test_parse_bad_seniority_raises():
    block = dict(_GOOD, seniority="wizard-supreme")
    with pytest.raises(ai_setup.SetupBlockError):
        ai_setup.parse_setup_block(json.dumps(block))


def test_parse_blank_optional_fields_are_permissive():
    # salary_floor 0 -> None (no floor); radius 0 -> None; blank seniority -> ''.
    block = dict(_GOOD, salary_floor=0, radius_miles=0, seniority="")
    parsed = ai_setup.parse_setup_block(json.dumps(block))
    assert parsed["answers"]["salary_min"] is None
    assert parsed["extras"]["radius"] is None
    assert parsed["answers"]["level"] == ""


# ── apply_setup: writes the same contract as the wizard ───────────────────────
def test_apply_setup_writes_preferences_and_config(isolated):
    summary = ai_setup.apply_setup(json.dumps(_GOOD))
    loaded = preferences.load()
    assert loaded["hard"]["target_roles"] == ["Data Analyst", "BI Analyst"]
    assert loaded["hard"]["salary_min"] == 85000
    assert "SQL" in loaded["profile_md"]
    cfg = workspace.load_config()
    assert cfg["industry"] == "data analytics"
    assert cfg["keywords"] == ["Data Analyst", "BI Analyst"]
    assert cfg["radius"] == 40
    assert cfg["seniority_target"] == "mid"       # from _level_to_config
    assert summary["field"] == "data analytics"
    assert summary["radius"] == 40


def test_apply_setup_marks_onboarded(isolated):
    from ui import setup_wizard
    assert setup_wizard.is_onboarded() is False
    ai_setup.apply_setup(json.dumps(_GOOD))
    assert setup_wizard.is_onboarded() is True


def test_apply_setup_can_skip_onboarded(isolated):
    from ui import setup_wizard
    ai_setup.apply_setup(json.dumps(_GOOD), mark_onboarded=False)
    assert setup_wizard.is_onboarded() is False


def test_apply_setup_does_not_apply_on_bad_block(isolated):
    from ui import setup_wizard
    with pytest.raises(ai_setup.SetupBlockError):
        ai_setup.apply_setup("garbage not json")
    # Nothing was written (no partial apply, no onboarded marker).
    assert setup_wizard.is_onboarded() is False
    assert not config.PREFERENCES_JSON.exists()


def test_apply_setup_matches_wizard_contract_shape(isolated):
    # The AI path and the wizard must produce the SAME preferences hard-keys.
    from ui import setup_wizard
    ai_setup.apply_setup(json.dumps(_GOOD))
    ai_hard = json.loads(config.PREFERENCES_JSON.read_text(encoding="utf-8"))
    # Fresh dir for the wizard write.
    wiz = setup_wizard.build_preferences({
        "roles": ["Data Analyst", "BI Analyst"], "location": "Phoenix, AZ",
        "remote_ok": True, "salary_min": 85000, "about": "x"})
    # Every wizard hard key is present in the AI-written contract.
    for k in wiz["hard"]:
        assert k in ai_hard


# ── company seeding prompt (§6.7 / SB-2a) — careers-page URLs ONLY ────────────
def test_seed_prompt_asks_for_careers_urls_only():
    p = ai_setup.build_seed_prompt("nurse", "Boise, ID")
    low = p.lower()
    assert "careers" in low
    assert "Name |" in p or "| https" in p
    # It explicitly steers AWAY from slug/tenant guessing (the coin-flip).
    assert "slug" in low or "tenant" in low
    assert "nurse" in p and "Boise" in p


def test_seed_prompt_is_safe_with_blank_field_and_metro():
    p = ai_setup.build_seed_prompt("", "")
    assert "my field" in p and "my area" in p


# ── apply_seed_lines: detect + P0-6 gate (offline, probe skipped) ─────────────
def test_apply_seed_lines_gates_on_probe(isolated):
    lines = (
        "Acme | https://boards.greenhouse.io/acme\n"      # ATS: needs probe
        "Direct Co | https://directco.com/careers/\n"     # direct: verified-manual
    )
    # probe=False: the greenhouse board is never confirmed live -> unverified;
    # the direct page is user-supplied-exact -> verified.
    res = ai_setup.apply_seed_lines(lines, industry="engineering", probe=False)
    assert res["parsed"] == 2
    kinds = {v["name"]: v["verdict"] for v in res["verdicts"]}
    assert kinds["Direct Co"] == "direct"
    assert kinds["Acme"] == "unreachable"
    # Both saved; the unverified one is flagged so it's excluded from scraping.
    saved = json.loads(config.COMPANIES_JSON.read_text(encoding="utf-8"))
    by_name = {c["name"]: c for c in saved["companies"] if "_example" not in c}
    assert by_name["Acme"]["extra"]["unverified"] is True
    assert "extra" not in by_name["Direct Co"] or not by_name["Direct Co"].get("extra")


def test_apply_seed_lines_workday_detects_as_cxs(isolated):
    # Wave-1: a myworkdayjobs careers URL now detects as workday_cxs.
    lines = "St Luke's | https://stlukes.wd5.myworkdayjobs.com/en-US/External\n"
    res = ai_setup.apply_seed_lines(lines, industry="nursing", probe=False)
    v = res["verdicts"][0]
    assert v["ats_type"] == "workday_cxs"


def test_apply_seed_lines_live_probe_verifies(isolated, monkeypatch):
    # Stub the probe so a "live" verdict path is exercised without network.
    from scrape import ats_detect
    monkeypatch.setattr(ats_detect, "probe_count", lambda e: 12)
    lines = "Acme | https://boards.greenhouse.io/acme\n"
    res = ai_setup.apply_seed_lines(lines, industry="engineering", probe=True)
    v = res["verdicts"][0]
    assert v["verdict"] == "live" and v["count"] == 12
    assert res["verified"] == 1 and res["unverified"] == 0


# ── P0-6 verdict fix: walled workday_cxs is UNREACHABLE, live-empty is VERIFIED ─
def test_apply_seed_lines_workday_cxs_walled_is_unreachable(isolated, monkeypatch):
    # The exact smoke-test defect: a 422-walled Workday tenant (FedEx/AutoZone/
    # Nike) must be flagged-unverified (unreachable), NOT saved as "live (0 open
    # jobs)". probe_board returns reachable=False for a walled tenant.
    from scrape import ats_detect
    monkeypatch.setattr(ats_detect, "probe_board",
                        lambda e: ats_detect.ProbeResult(None, False))
    lines = "FedEx | https://fedex.wd5.myworkdayjobs.com/en-US/careers\n"
    res = ai_setup.apply_seed_lines(lines, industry="warehouse logistics", probe=True)
    v = res["verdicts"][0]
    assert v["ats_type"] == "workday_cxs"
    assert v["verdict"] == "unreachable"
    assert res["verified"] == 0 and res["unverified"] == 1
    # Saved but flagged so it's excluded from scraping (re-verify upgrade applies).
    saved = json.loads(config.COMPANIES_JSON.read_text(encoding="utf-8"))
    by_name = {c["name"]: c for c in saved["companies"] if "_example" not in c}
    assert by_name["FedEx"]["extra"]["unverified"] is True


def test_apply_seed_lines_workday_cxs_live_empty_is_verified(isolated, monkeypatch):
    # A genuinely-live Workday board with 0 open jobs is REACHABLE -> verified
    # (live, 0 open jobs), NOT flagged unverified.
    from scrape import ats_detect
    monkeypatch.setattr(ats_detect, "probe_board",
                        lambda e: ats_detect.ProbeResult(0, True))
    lines = "LiveCo | https://liveco.wd1.myworkdayjobs.com/en-US/External\n"
    res = ai_setup.apply_seed_lines(lines, industry="engineering", probe=True)
    v = res["verdicts"][0]
    assert v["verdict"] == "live" and v["count"] == 0
    assert res["verified"] == 1 and res["unverified"] == 0
    saved = json.loads(config.COMPANIES_JSON.read_text(encoding="utf-8"))
    by_name = {c["name"]: c for c in saved["companies"] if "_example" not in c}
    assert "extra" not in by_name["LiveCo"] or not by_name["LiveCo"].get("extra")


def test_apply_seed_lines_skips_already_registered(isolated, monkeypatch):
    from scrape import company_registry
    from scrape.company_registry import CompanyEntry
    monkeypatch.setattr(
        company_registry, "get_registry",
        lambda *a, **k: [CompanyEntry("Acme", "greenhouse", "acme")])
    lines = "Acme | https://boards.greenhouse.io/acme\n"
    res = ai_setup.apply_seed_lines(lines, probe=False)
    assert res["verdicts"][0]["verdict"] == "skipped"
    assert res["skipped"] == 1 and res["added"] == 0


def test_apply_seed_lines_empty_is_noop(isolated):
    res = ai_setup.apply_seed_lines("   \n  \n", probe=False)
    assert res["parsed"] == 0 and res["added"] == 0 and res["verdicts"] == []


# ── P0-6 re-verify: a previously-unverified board is upgraded on a live re-seed ─
def test_apply_seed_lines_reverifies_unverified_board(isolated, monkeypatch):
    from scrape import ats_detect
    from scrape.company_registry import get_registry
    # First seed offline: the greenhouse board is unreachable -> flagged-unverified.
    ai_setup.apply_seed_lines("Acme | https://boards.greenhouse.io/acme\n",
                              industry="engineering", probe=False)
    assert "Acme" not in {c.name for c in get_registry(user_json=config.COMPANIES_JSON)}

    # Re-seed with a live probe: it now verifies -> the stored flag is cleared
    # and the board re-enters the scraped registry (NOT reported as 'skipped').
    monkeypatch.setattr(ats_detect, "probe_count", lambda e: 9)
    res = ai_setup.apply_seed_lines("Acme | https://boards.greenhouse.io/acme\n",
                                    industry="engineering", probe=True)
    v = res["verdicts"][0]
    assert v["verdict"] == "live"
    assert res["added"] == 1
    assert "Acme" in {c.name for c in get_registry(user_json=config.COMPANIES_JSON)}


# ── ToS/aggregator guard: blocked hosts are rejected, never saved ─────────────
@pytest.mark.parametrize("url", [
    "https://www.governmentjobs.com/careers/cincinnati",   # NEOGOV
    "https://acme.applitrack.com/district/onlineapp/",      # Frontline/AppliTrack
    "https://www.indeed.com/cmp/acme/jobs",                 # aggregator
    "https://www.linkedin.com/company/acme/jobs",           # aggregator
])
def test_apply_seed_lines_rejects_tos_blocked_hosts(isolated, url):
    res = ai_setup.apply_seed_lines(f"Acme | {url}\n", industry="engineering",
                                    probe=False)
    assert res["rejected"] == 1
    assert res["added"] == 0
    v = res["verdicts"][0]
    assert v["verdict"] == "rejected"
    # Nothing persisted for a blocked host.
    assert not config.COMPANIES_JSON.exists() or "Acme" not in {
        c["name"] for c in json.loads(config.COMPANIES_JSON.read_text(encoding="utf-8"))
        .get("companies", []) if "_example" not in c}


def test_apply_seed_lines_allows_legit_direct_page(isolated):
    # A normal company careers page (not a blocked host) still saves as 'direct'.
    res = ai_setup.apply_seed_lines("Direct Co | https://directco.com/careers/\n",
                                    industry="engineering", probe=False)
    assert res["rejected"] == 0
    assert {v["verdict"] for v in res["verdicts"]} == {"direct"}
