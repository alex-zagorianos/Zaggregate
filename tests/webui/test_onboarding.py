"""Onboarding API — wizard round-trip + AI express-lane, over the web (Phase 5).

The load-bearing test is the ROUND-TRIP: POST /api/onboarding must write the SAME
files the tk wizard writes. We assert the on-disk shape against a GOLDEN produced
by calling the Tk-free core (build_preferences / _search_config) directly — so the
web path and the tk path can never drift.
"""
import json

import pytest

import config
import workspace
import preferences
from ui import setup_wizard_core as wizard


_LOOPBACK = "http://127.0.0.1:5002"
_EXT_ORIGIN = "chrome-extension://abcdefghijklmnop"


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Point the whole on-disk contract at a tmp data dir (mirrors the ai_setup
    test fixture) so onboarding writes never touch real user data."""
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "PREFERENCES_JSON", tmp_path / "preferences.json")
    monkeypatch.setattr(config, "PREFERENCES_MD", tmp_path / "preferences.md")
    monkeypatch.setattr(config, "COMPANIES_JSON", tmp_path / "companies.json")
    monkeypatch.setattr(workspace, "BASE_DIR", tmp_path)
    return tmp_path


# ── GET /api/onboarding (read prefill) ────────────────────────────────────────
def test_onboarding_state_fresh(client, isolated):
    body = client.get("/api/onboarding").get_json()
    assert body["ok"] is True
    assert body["onboarded"] is False          # no .onboarded marker yet
    pf = body["prefill"]
    for k in ("roles", "location", "remote_ok", "salary_min", "about",
              "industry", "level"):
        assert k in pf


def test_onboarding_state_reflects_existing(client, isolated):
    # Seed a contract, then the prefill should echo it (parity with the tk wizard
    # re-opening on an already-configured project).
    wizard.apply({"roles": ["Nurse", "RN"], "location": "Boston, MA",
                  "remote_ok": False, "salary_min": 70000, "industry": "nursing",
                  "about": "ICU experience"})
    body = client.get("/api/onboarding").get_json()
    assert body["onboarded"] is True
    assert body["prefill"]["roles"] == "Nurse, RN"
    assert body["prefill"]["location"] == "Boston, MA"
    assert body["prefill"]["remote_ok"] is False
    assert body["prefill"]["industry"] == "nursing"


# ── POST /api/onboarding (the load-bearing round-trip) ────────────────────────
def test_onboarding_apply_writes_golden_contract(client, isolated):
    answers_payload = {
        "roles": "Data Analyst, BI Analyst",     # comma string, as the tk box gives
        "location": "Phoenix, AZ",
        "remote_ok": True,
        "salary_min": 85000,
        "industry": "data analytics",
        "level": "Mid",
        "about": "I love SQL. Avoid pure sales.",
    }
    resp = client.post("/api/onboarding", json=answers_payload,
                       headers={"Origin": _LOOPBACK})
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True, "onboarded": True,
                               "resume_restructured": False,
                               "industry_detected": ""}

    # GOLDEN: what the tk wizard's pure core would produce from the same answers.
    golden_answers = {
        "roles": ["Data Analyst", "BI Analyst"], "location": "Phoenix, AZ",
        "remote_ok": True, "salary_min": 85000, "industry": "data analytics",
        "level": "Mid", "about": "I love SQL. Avoid pure sales.",
    }
    golden_prefs = wizard.build_preferences(golden_answers)

    loaded = preferences.load()
    # preferences.load() normalizes/augments the stored hard block (adds
    # employment_types / remote_regions_ok defaults), so assert the golden fields
    # are a SUBSET — every key build_preferences wrote must round-trip identically.
    for k, v in golden_prefs["hard"].items():
        assert loaded["hard"][k] == v, k
    assert loaded["hard"]["target_roles"] == ["Data Analyst", "BI Analyst"]
    assert loaded["hard"]["salary_min"] == 85000
    # profile_md carries the About section verbatim.
    assert "I love SQL" in loaded["profile_md"]

    # Search config matches _search_config's output (keywords/location/industry +
    # rubric-read seniority keys from the level).
    cfg = workspace.load_config()
    golden_cfg = wizard._search_config(golden_answers)
    for key in ("keywords", "location", "industry", "seniority_target"):
        assert cfg.get(key) == golden_cfg.get(key)
    assert cfg["keywords"] == ["Data Analyst", "BI Analyst"]
    assert cfg["industry"] == "data analytics"
    assert cfg["seniority_target"] == "mid"

    # Marker written.
    assert wizard.is_onboarded() is True


def test_onboarding_apply_blank_industry_derived_like_tk(client, isolated):
    # The divergence guard: a web user who lists roles but leaves the industry box
    # blank must get the SAME auto-derived non-generic field the tk wizard's
    # _finish() produces (setup_wizard.py L628), instead of silent generic/eng
    # routing. Golden = the wizard core's own _derive_industry on identical input.
    golden_industry = wizard._derive_industry("", ["Registered Nurse"])
    assert golden_industry and "nurse" in golden_industry.lower()  # sanity

    resp = client.post("/api/onboarding",
                       json={"roles": "Registered Nurse", "location": "Boston, MA",
                             "industry": ""},              # blank, as the common case
                       headers={"Origin": _LOOPBACK})
    assert resp.status_code == 200
    body = resp.get_json()
    # The derived field is echoed for the "Field detected" UI notice...
    assert body["industry_detected"] == golden_industry
    # ...AND persisted to the search config so industry-specific source routing
    # (Muse/Jobicy) + registry tuning turn on — parity with the tk path.
    cfg = workspace.load_config()
    assert cfg["industry"] == golden_industry
    assert cfg["industry"].lower() != "generic"


def test_onboarding_apply_explicit_industry_not_overridden(client, isolated):
    # An explicitly-typed field is never clobbered by derivation (byte-identical to
    # the tk _derive_industry("<set>", ...) -> "" short-circuit).
    resp = client.post("/api/onboarding",
                       json={"roles": "Registered Nurse", "location": "Boston, MA",
                             "industry": "health informatics"},
                       headers={"Origin": _LOOPBACK})
    assert resp.status_code == 200
    assert resp.get_json()["industry_detected"] == ""
    assert workspace.load_config()["industry"] == "health informatics"


def test_onboarding_apply_eng_role_blank_industry_stays_generic(client, isolated):
    # Alex's eng path must stay byte-identical: an engineering role with a blank
    # field must NOT get a field prefilled (mirrors test_derive_industry_eng_role).
    resp = client.post("/api/onboarding",
                       json={"roles": "Controls Engineer", "location": "Toledo, OH",
                             "industry": ""},
                       headers={"Origin": _LOOPBACK})
    assert resp.status_code == 200
    assert resp.get_json()["industry_detected"] == ""
    # No industry key was written (blank stays blank -> generic full reach).
    assert not workspace.load_config().get("industry")


def test_onboarding_apply_salary_freetext_parsed(client, isolated):
    # A free-text hourly salary is parsed exactly as the tk salary box does.
    resp = client.post("/api/onboarding",
                       json={"roles": "Welder", "location": "Toledo, OH",
                             "salary_min": "22/hr"},
                       headers={"Origin": _LOOPBACK})
    assert resp.status_code == 200
    loaded = preferences.load()
    assert loaded["hard"]["salary_min"] == wizard.parse_salary_input("22/hr")
    assert loaded["hard"]["salary_min"] == 22 * 2080


def test_onboarding_apply_structures_resume(client, isolated):
    resp = client.post("/api/onboarding",
                       json={"roles": "Nurse", "location": "Boston, MA",
                             "resume_text": "Jane Doe\njane@x.com\n"
                                            "Worked at a hospital for 5 years."},
                       headers={"Origin": _LOOPBACK})
    assert resp.status_code == 200
    assert resp.get_json()["resume_restructured"] is True
    # experience.md was written with headings the parser accepts.
    exp = workspace.experience_file()
    assert exp.exists()
    assert "## " in exp.read_text(encoding="utf-8")


def test_onboarding_apply_headerless_403(client, isolated):
    resp = client.post("/api/onboarding", json={"roles": "x"})   # no Origin
    assert resp.status_code == 403
    assert resp.get_json() == {"ok": False, "error": "forbidden origin"}
    assert wizard.is_onboarded() is False           # nothing written


def test_onboarding_apply_foreign_origin_403(client, isolated):
    resp = client.post("/api/onboarding", json={"roles": "x"},
                       headers={"Origin": "https://evil.example.com"})
    assert resp.status_code == 403
    assert wizard.is_onboarded() is False


# ── resume-structure preview ──────────────────────────────────────────────────
def test_resume_structure_preview(client, isolated):
    resp = client.post("/api/onboarding/resume-structure",
                       json={"text": "EXPERIENCE\nDid things.\nEDUCATION\nBS"},
                       headers={"Origin": _EXT_ORIGIN})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["restructured"] is True
    # At least one recognizable heading was promoted (the core's alias table
    # decides which; EDUCATION is a canonical section it recognizes).
    assert "## EDUCATION" in body["markdown"]
    # It's a PREVIEW — nothing was written to disk.
    assert not workspace.experience_file().exists()


def test_resume_structure_blank_is_noop(client, isolated):
    resp = client.post("/api/onboarding/resume-structure", json={"text": ""},
                       headers={"Origin": _EXT_ORIGIN})
    body = resp.get_json()
    assert body["markdown"] == ""
    assert body["restructured"] is False


def test_resume_structure_headerless_403(client, isolated):
    resp = client.post("/api/onboarding/resume-structure", json={"text": "x"})
    assert resp.status_code == 403


# ── salary-parse (read) ───────────────────────────────────────────────────────
@pytest.mark.parametrize("text,annual,kind", [
    ("90000", 90000, "annual"),
    ("$90,000", 90000, "annual"),
    ("90k", 90000, "annual"),
    ("18/hr", 18 * 2080, "hourly"),
    ("$18.50 per hour", int(round(18.5 * 2080)), "hourly"),
    ("18", 18 * 2080, "hourly"),          # bare small number -> annualized hourly
    ("", None, "none"),
    ("nope", None, "none"),
])
def test_salary_parse(client, text, annual, kind):
    body = client.post("/api/onboarding/salary-parse",
                       json={"text": text}).get_json()
    assert body["ok"] is True
    assert body["annual"] == annual
    assert body["kind"] == kind


def test_salary_parse_needs_no_origin(client):
    # READ-only: a header-less GET-context POST is fine (no side effect).
    resp = client.post("/api/onboarding/salary-parse", json={"text": "80k"})
    assert resp.status_code == 200


# ── AI express-lane ───────────────────────────────────────────────────────────
_GOOD_BLOCK = {
    "field": "data analytics",
    "target_titles": ["Data Analyst", "BI Analyst"],
    "location": "Phoenix, AZ",
    "remote_ok": True,
    "radius_miles": 40,
    "salary_floor": 85000,
    "seniority": "mid",
    "preferences_md": "I want data analyst roles. I love SQL. Avoid pure sales.",
}


def test_ai_setup_prompt_static(client):
    body = client.get("/api/ai-setup/prompt").get_json()
    assert body["ok"] is True
    assert "```json" in body["prompt"]
    # P1 (search-discovery-plan §5): the flat target_titles ask was replaced by
    # a tiered, uncapped keywords object.
    assert "keywords" in body["prompt"]


def test_ai_setup_prompt_full_flag_serves_combined(client):
    """`?full=1` serves the combined config+seeds prompt (S40 AI-first setup) —
    the SAME string build_full_setup_prompt() returns — so the wizard's inline
    express lane and the Search-tab dialog get both contracts in one paste. The
    default (no flag) stays the config-only prompt (compat)."""
    from ui.ai_setup import build_setup_prompt, build_full_setup_prompt

    full = client.get("/api/ai-setup/prompt?full=1").get_json()
    assert full["ok"] is True
    assert full["prompt"] == build_full_setup_prompt()
    # Both contracts present: the config json block AND the seeds fence.
    assert "```json" in full["prompt"]
    assert "keywords" in full["prompt"]
    assert "```seeds" in full["prompt"]

    # Default (no flag) is unchanged — the config-only prompt, no seeds fence.
    default = client.get("/api/ai-setup/prompt").get_json()
    assert default["prompt"] == build_setup_prompt()
    assert "```seeds" not in default["prompt"]


def test_ai_setup_apply_happy(client, isolated):
    resp = client.post("/api/ai-setup/apply",
                       json={"text": json.dumps(_GOOD_BLOCK)},
                       headers={"Origin": _LOOPBACK})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["applied"]["field"] == "data analytics"
    assert body["applied"]["radius"] == 40
    # Same contract the manual wizard writes.
    cfg = workspace.load_config()
    assert cfg["keywords"] == ["Data Analyst", "BI Analyst"]
    assert cfg["industry"] == "data analytics"
    assert wizard.is_onboarded() is True


def test_ai_setup_apply_bad_block_400_no_write(client, isolated):
    resp = client.post("/api/ai-setup/apply", json={"text": "garbage not json"},
                       headers={"Origin": _LOOPBACK})
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False
    # No partial apply, no onboarded marker.
    assert wizard.is_onboarded() is False
    assert not config.PREFERENCES_JSON.exists()


def test_ai_setup_apply_headerless_403(client, isolated):
    resp = client.post("/api/ai-setup/apply",
                       json={"text": json.dumps(_GOOD_BLOCK)})   # no Origin
    assert resp.status_code == 403
    assert wizard.is_onboarded() is False


# ── AI-first setup: POST /api/ai-setup/apply-full (S40 B1) ────────────────────
# The combined reply = the config block + a ```seeds block. One paste applies the
# config synchronously AND (autorun default) chains an exclusive first_run job:
# phase 1 seeds companies, phase 2 runs the daily ingest via the SHARED helper.
import pytest as _pytest        # local alias so the fixtures below read cleanly

from webui.api import runs as runs_mod
from webui.jobs import runner


_SEEDS = ("```seeds\n"
          "Acme | https://boards.greenhouse.io/acme\n"
          "Beta Corp | https://jobs.lever.co/beta\n"
          "```")
_FULL_REPLY = "```json\n" + json.dumps(_GOOD_BLOCK) + "\n```\n\n" + _SEEDS


@_pytest.fixture
def _reset_runner():
    """Clear the shared runner singleton around each apply-full test so a held or
    leaked first_run job can't carry the exclusive mutex into the next test
    (mirrors tests/webui/test_runs_daily.py's fixture)."""
    with runner._lock:
        runner._jobs.clear()
        runner._active.clear()
        runner._exclusive_active = None
    yield
    with runner._lock:
        runner._jobs.clear()
        runner._active.clear()
        runner._exclusive_active = None


@_pytest.fixture
def _first_run_slug(monkeypatch):
    """Pin a known active slug and force the FIRST-run state (no last_run.json) so
    the chained job takes the quick-pass path deterministically."""
    import applog
    monkeypatch.setattr(workspace, "active_slug", lambda: "projA")
    monkeypatch.setattr(workspace, "registry_active_slug", lambda: "projA")
    monkeypatch.setattr(applog, "last_run_info", lambda slug=None: None)


def _wait_job(client, job_id, timeout=3.0):
    from tests.webui.conftest import wait_until

    def _check():
        snap = client.get(f"/api/jobs/{job_id}").get_json()
        return snap if snap.get("status") in ("done", "failed") else None
    return wait_until(_check, timeout=timeout,
                      message=f"first_run job {job_id} never finished")


def test_apply_full_applies_config_and_starts_job(client, isolated,
                                                  _reset_runner, _first_run_slug,
                                                  monkeypatch):
    # Fake the ingest seam (both routes share it) and the live probe so no network
    # is touched; assert the config applied synchronously AND the job ran both
    # phases (seed line logged, then the ingest).
    seen = {}

    def fake_ingest(slug, *, on_line=None, cancel=None, max_pages=None,
                    min_score=None):
        seen.update(slug=slug, max_pages=max_pages)
        on_line("[Adzuna] 5 results")
        return 0
    monkeypatch.setattr(runs_mod, "_daily_ingest", fake_ingest)
    # Offline probe: greenhouse/lever boards land unverified (no network needed).
    resp = client.post("/api/ai-setup/apply-full",
                       json={"text": _FULL_REPLY},
                       headers={"Origin": _LOOPBACK})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    # applied has the SAME shape as /ai-setup/apply.
    assert body["applied"]["field"] == "data analytics"
    assert body["applied"]["radius"] == 40
    assert body["seed_count"] == 2
    assert body["job_id"]                       # a job was started
    assert "job_error" not in body
    # Config was written synchronously (same contract as the manual wizard).
    cfg = workspace.load_config()
    assert cfg["keywords"] == ["Data Analyst", "BI Analyst"]
    assert wizard.is_onboarded() is True
    # The chained job ran: first-run quick pass forwarded max_pages=1 to the ingest.
    snap = _wait_job(client, body["job_id"])
    assert snap["status"] == "done"
    assert seen == {"slug": "projA", "max_pages": 1}
    log = " ".join(snap.get("lines_tail") or [])
    assert "Seeding 2 starter companies" in log      # phase 1
    assert "First run: quick pass" in log            # phase 2 quick pass
    assert "[Adzuna] 5 results" in log               # phase 2 ingest


def test_apply_full_no_config_400_no_job(client, isolated, _reset_runner,
                                         _first_run_slug, monkeypatch):
    # Seeds ALONE do not onboard: a reply with only a seeds block is a 400 with the
    # same human-message contract as /ai-setup/apply — and NO job starts.
    def boom(*a, **k):
        raise AssertionError("ingest started despite missing config")
    monkeypatch.setattr(runs_mod, "_daily_ingest", boom)
    resp = client.post("/api/ai-setup/apply-full",
                       json={"text": _SEEDS},            # seeds only, no json
                       headers={"Origin": _LOOPBACK})
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False
    assert wizard.is_onboarded() is False
    assert not config.PREFERENCES_JSON.exists()
    # No job leaked into the runner.
    with runner._lock:
        assert runner._exclusive_active is None


def test_apply_full_autorun_false_applies_but_no_job(client, isolated,
                                                     _reset_runner,
                                                     _first_run_slug, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("ingest started despite autorun=false")
    monkeypatch.setattr(runs_mod, "_daily_ingest", boom)
    resp = client.post("/api/ai-setup/apply-full",
                       json={"text": _FULL_REPLY, "autorun": False},
                       headers={"Origin": _LOOPBACK})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["applied"]["field"] == "data analytics"
    assert body["seed_count"] == 2
    assert body["job_id"] is None
    # Config still applied.
    assert wizard.is_onboarded() is True
    with runner._lock:
        assert runner._exclusive_active is None


def test_apply_full_conflict_shape_still_ok(client, isolated, _reset_runner,
                                            _first_run_slug, monkeypatch):
    # An engine job already holding the exclusive slot -> the config still applies
    # but the search can't start: ok:true, job_id:null, job_error set.
    from webui.jobs import JobConflict

    def raise_conflict(*a, **k):
        raise JobConflict("existing-job-123", same_gate=False)
    monkeypatch.setattr(runner, "start", raise_conflict)
    resp = client.post("/api/ai-setup/apply-full",
                       json={"text": _FULL_REPLY},
                       headers={"Origin": _LOOPBACK})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["applied"]["field"] == "data analytics"
    assert body["seed_count"] == 2
    assert body["job_id"] is None
    assert body["job_error"] == "another run is in progress"
    # The config WAS applied despite the conflict.
    assert wizard.is_onboarded() is True


def test_apply_full_config_only_reply_starts_job_with_zero_seeds(
        client, isolated, _reset_runner, _first_run_slug, monkeypatch):
    # A reply with a config block but NO seeds still onboards + runs (config-only
    # degrade, inclusion over precision). Phase 1 is skipped; phase 2 runs.
    def fake_ingest(slug, *, on_line=None, cancel=None, max_pages=None,
                    min_score=None):
        on_line("ingest ran")
        return 0
    monkeypatch.setattr(runs_mod, "_daily_ingest", fake_ingest)
    resp = client.post("/api/ai-setup/apply-full",
                       json={"text": "```json\n" + json.dumps(_GOOD_BLOCK) + "\n```"},
                       headers={"Origin": _LOOPBACK})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["seed_count"] == 0
    assert body["job_id"]
    snap = _wait_job(client, body["job_id"])
    assert snap["status"] == "done"
    log = " ".join(snap.get("lines_tail") or [])
    assert "Seeding" not in log            # phase 1 skipped (no seeds)
    assert "ingest ran" in log             # phase 2 ran


def test_apply_full_headerless_403(client, isolated):
    resp = client.post("/api/ai-setup/apply-full",
                       json={"text": _FULL_REPLY})       # no Origin
    assert resp.status_code == 403
    assert resp.get_json() == {"ok": False, "error": "forbidden origin"}
    assert wizard.is_onboarded() is False


def test_apply_full_foreign_origin_403(client, isolated):
    resp = client.post("/api/ai-setup/apply-full",
                       json={"text": _FULL_REPLY},
                       headers={"Origin": "https://evil.example.com"})
    assert resp.status_code == 403
    assert wizard.is_onboarded() is False


# ── per-project onboarding marker (scenario finding #5) ───────────────────────
def test_onboarded_marker_is_per_project(tmp_path, monkeypatch):
    """The wizard-completion marker is scoped to the PROJECT's data dir, not one
    installation-wide root file. Onboarding project A must NOT make a brand-new
    project B report onboarded:true (B was never wizard-configured). Migration:
    the root/'default' project keeps using the legacy root marker path."""
    # Two isolated project dirs under a tmp root; drive project_dir directly so the
    # test doesn't depend on the live registry.
    dirs = {"proj-a": tmp_path / "projects" / "proj-a",
            "proj-b": tmp_path / "projects" / "proj-b",
            "default": tmp_path}   # root/'default' -> USER_DATA_DIR (migration parity)
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)
    monkeypatch.setattr(workspace, "project_dir",
                        lambda slug=None: dirs.get(slug, tmp_path))

    # Fresh: nothing onboarded anywhere.
    assert wizard.is_onboarded("proj-a") is False
    assert wizard.is_onboarded("proj-b") is False

    # Onboard A only.
    wizard.mark_onboarded("proj-a")
    assert wizard.is_onboarded("proj-a") is True
    # B is untouched — the bug was a global marker flipping B to true too.
    assert wizard.is_onboarded("proj-b") is False

    # The marker really lives in A's dir, not the root.
    assert (dirs["proj-a"] / ".onboarded").exists()
    assert not (tmp_path / ".onboarded").exists()


def test_onboarded_marker_default_slug_uses_root_path(tmp_path, monkeypatch):
    """Migration guard: the 'default' slug resolves to USER_DATA_DIR, so a legacy
    single-project install's root .onboarded keeps marking it onboarded."""
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)
    monkeypatch.setattr(workspace, "project_dir",
                        lambda slug=None: tmp_path)   # default -> root
    (tmp_path / ".onboarded").write_text("ok\n", encoding="utf-8")   # legacy marker
    assert wizard.is_onboarded("default") is True
    assert wizard._marker_path("default") == tmp_path / ".onboarded"


# ── S36b: legacy-config inference (configured project ≠ re-gated wizard) ──────

def test_configured_project_without_marker_counts_as_onboarded(tmp_path, monkeypatch):
    """A project configured BEFORE the per-project marker existed (config.json
    with keywords, no .onboarded file) must report onboarded:true — and the
    marker self-heals so the inference runs once."""
    import json
    from ui import setup_wizard_core as core
    import workspace

    proj = tmp_path / "legacy-proj"
    proj.mkdir()
    (proj / "config.json").write_text(
        json.dumps({"keywords": ["controls engineer"], "location": "Cincinnati"}),
        encoding="utf-8")
    monkeypatch.setattr(workspace, "project_dir", lambda slug=None: proj)
    monkeypatch.setattr(workspace, "load_config",
                        lambda slug=None: json.loads(
                            (proj / "config.json").read_text(encoding="utf-8")))

    assert not (proj / ".onboarded").exists()
    assert core.is_onboarded() is True
    # Pure inference — a READ never writes the marker.
    assert not (proj / ".onboarded").exists()


def test_unconfigured_project_still_gates(tmp_path, monkeypatch):
    from ui import setup_wizard_core as core
    import workspace

    proj = tmp_path / "fresh-proj"
    proj.mkdir()
    monkeypatch.setattr(workspace, "project_dir", lambda slug=None: proj)
    monkeypatch.setattr(workspace, "load_config", lambda slug=None: {})
    assert core.is_onboarded() is False
    assert not (proj / ".onboarded").exists()


def test_mid_wizard_sentinel_suppresses_inference_until_finish(tmp_path, monkeypatch):
    """AI mid-wizard paste (apply_setup mark_onboarded=False) saves a keyword
    config; the sentinel keeps the gate CLOSED until mark_onboarded, which
    clears it (review-confirmed follow-up to the legacy-config inference)."""
    import json
    from ui import setup_wizard_core as core
    import workspace

    proj = tmp_path / "midwizard"
    proj.mkdir()
    (proj / "config.json").write_text(
        json.dumps({"keywords": ["nurse"]}), encoding="utf-8")
    monkeypatch.setattr(workspace, "project_dir", lambda slug=None: proj)
    monkeypatch.setattr(workspace, "load_config",
                        lambda slug=None: json.loads(
                            (proj / "config.json").read_text(encoding="utf-8")))

    assert core.is_onboarded() is True          # legacy inference
    core.mark_wizard_in_progress()
    assert core.is_onboarded() is False         # sentinel wins over inference
    core.mark_onboarded()
    assert core.is_onboarded() is True          # finished: marker set…
    assert not (proj / ".wizard-in-progress").exists()   # …sentinel cleared
