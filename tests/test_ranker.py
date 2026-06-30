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
