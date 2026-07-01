import sys
import types

import claude_bridge as bridge
import models
import preferences
import ranker


def _job(title="Controls Engineer", company="Acme", location="Cincinnati, OH",
         salary_min=100000, url="https://x.co/1"):
    return models.JobResult(
        title=title, company=company, location=location,
        salary_min=salary_min, salary_max=None, description="C++ motion control",
        url=url, source_keyword="", created="", source_api="test",
    )


# ── profile + request ─────────────────────────────────────────────────────────

def test_build_profile_combines_prefs_and_background():
    prefs = {"profile_md": "I want controls + embedded roles.", "hard": {}}
    prof = ranker.build_profile(prefs, experience_summary="Skills: C++17, STM32")
    assert "controls + embedded" in prof
    assert "C++17" in prof


def test_build_profile_tolerates_empty():
    prof = ranker.build_profile({"profile_md": "", "hard": {}}, experience_summary="")
    assert isinstance(prof, str) and prof  # non-empty sentinel, never blank


def test_build_request_includes_prefs_and_jobs():
    prefs = {"profile_md": "I want controls + embedded roles.", "hard": {}}
    req = ranker.build_request([_job()], prefs=prefs, experience_summary="Skills: C++")
    assert "controls + embedded" in req
    assert "Controls Engineer" in req
    assert "Acme" in req


# ── parse ─────────────────────────────────────────────────────────────────────

def test_parse_response_maps_scores_by_token():
    jobs = [_job(url="https://x.co/1"), _job(title="SWE", url="https://x.co/2")]
    t0, t1 = bridge.fit_token(jobs[0]), bridge.fit_token(jobs[1])
    reply = (f'[{{"i":1,"token":"{t0}","fit":90,"why":"great"}},'
             f'{{"i":2,"token":"{t1}","fit":40,"why":"meh"}}]')
    out = ranker.parse_response(reply, jobs)
    assert len(out) == 2
    assert out[0][1] == 90
    assert out[1][1] == 40
    assert out[0][0] is jobs[0]


# ── gate ──────────────────────────────────────────────────────────────────────

def test_gate_applies_hard_filter():
    jobs = [_job(salary_min=70000), _job(salary_min=120000)]
    prefs = {"profile_md": "", "hard": {**preferences._DEFAULT_HARD, "salary_min": 90000}}
    out = ranker.gate(jobs, prefs)
    assert len(out) == 1
    assert out[0].salary_min == 120000


# ── API key detection ─────────────────────────────────────────────────────────

def test_api_key_from_secrets_file(tmp_path, monkeypatch):
    monkeypatch.setattr(ranker.config, "ANTHROPIC_API_KEY", None)
    monkeypatch.setattr(ranker.config, "SECRETS_DIR", tmp_path)
    assert ranker.has_api_key() is False
    (tmp_path / "anthropic_key").write_text("sk-ant-xyz\n", encoding="utf-8")
    assert ranker.has_api_key() is True
    assert ranker.api_key() == "sk-ant-xyz"


def test_api_key_env_takes_precedence(tmp_path, monkeypatch):
    monkeypatch.setattr(ranker.config, "ANTHROPIC_API_KEY", "sk-env")
    monkeypatch.setattr(ranker.config, "SECRETS_DIR", tmp_path)
    (tmp_path / "anthropic_key").write_text("sk-file", encoding="utf-8")
    assert ranker.api_key() == "sk-env"


# ── API ranking (mocked) ──────────────────────────────────────────────────────

def test_rank_via_api_runs_prompt_and_parses(monkeypatch):
    jobs = [_job(url="https://x.co/1")]
    tok = bridge.fit_token(jobs[0])
    reply = f'[{{"i":1,"token":"{tok}","fit":88,"why":"fits"}}]'

    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        block = types.SimpleNamespace(type="text", text=reply)
        return types.SimpleNamespace(content=[block])

    fake_anthropic = types.SimpleNamespace(
        Anthropic=lambda api_key=None: types.SimpleNamespace(
            messages=types.SimpleNamespace(create=fake_create)))
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic)
    monkeypatch.setattr(ranker, "api_key", lambda: "sk-test")

    out = ranker.rank_via_api(jobs, prefs={"profile_md": "controls", "hard": {}},
                              experience_summary="C++")
    assert out[0][1] == 88
    assert "controls" in captured["messages"][0]["content"]  # preferences in prompt


def test_rank_via_api_without_key_raises(monkeypatch):
    monkeypatch.setattr(ranker, "api_key", lambda: None)
    try:
        ranker.rank_via_api([_job()])
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass


# ── _facts_profile (item 25: persisted onet_soc_code) ────────────────────────

def test_facts_profile_returns_soc_code_from_explicit_cfg():
    industry, skill_terms, soc_code = ranker._facts_profile(
        {"industry": "health_informatics", "onet_soc_code": "29-1141.00"})
    assert soc_code == "29-1141.00"
    assert industry == "health_informatics"


def test_facts_profile_soc_code_none_when_absent():
    industry, skill_terms, soc_code = ranker._facts_profile({"industry": "health_informatics"})
    assert soc_code is None


def test_facts_profile_soc_code_none_for_eng_default():
    industry, skill_terms, soc_code = ranker._facts_profile({})
    assert soc_code is None
    assert industry == ""


def test_facts_profile_cfg_none_falls_back_to_active_config(monkeypatch):
    """The pre-existing cfg=None -> active-project-config fallback (the GUI's
    'Ask AI to rank' buttons call through with no cfg) must keep working, and
    must surface onet_soc_code from that fallback too."""
    import workspace
    monkeypatch.setattr(workspace, "load_config",
                        lambda: {"industry": "health_informatics", "onet_soc_code": "29-1141.00"})
    industry, skill_terms, soc_code = ranker._facts_profile(None)
    assert industry == "health_informatics"
    assert soc_code == "29-1141.00"


def test_build_compact_request_soc_code_separates_facts_cache(tmp_path, monkeypatch):
    """End-to-end: two projects with the SAME industry text but a DIFFERENT
    persisted SOC code must not share a facts-cache entry (item 25's whole
    point) -- verified through the real build_compact_request path, not just
    match.facts directly."""
    from match import facts as F
    monkeypatch.setattr(F, "_cache_dir", lambda: tmp_path)
    jobs = [_job("Health Informatics Analyst", url="https://x.co/hia")]
    jobs[0].description = "clinical informatics EHR analytics"
    prefs = {"profile_md": "", "hard": {}}
    ranker.build_compact_request(jobs, prefs=prefs,
                                 cfg={"industry": "health_informatics",
                                      "onet_soc_code": "29-1141.00"})
    ranker.build_compact_request(jobs, prefs=prefs,
                                 cfg={"industry": "health_informatics",
                                      "onet_soc_code": "15-1211.00"})
    files = list(tmp_path.glob(f"{jobs[0].job_key}*"))
    assert len(files) == 2
