import sys
import types
import ranker
import claude_bridge as bridge
import models


def _job(title="Controls Engineer", company="Acme", url="https://x.co/1"):
    return models.JobResult(title=title, company=company, location="Cincinnati, OH",
                            salary_min=100000, salary_max=None,
                            description="C++ motion control", url=url,
                            source_keyword="", created="", source_api="test")


def test_build_request_unchanged_contract():
    prefs = {"profile_md": "I want controls + embedded roles.", "hard": {}}
    req = ranker.build_request([_job()], prefs=prefs, experience_summary="Skills: C++")
    assert "controls + embedded" in req
    assert "Controls Engineer" in req and "Acme" in req


def test_parse_response_maps_by_token():
    jobs = [_job(url="https://x.co/1"), _job(title="SWE", url="https://x.co/2")]
    t0, t1 = bridge.fit_token(jobs[0]), bridge.fit_token(jobs[1])
    reply = (f'[{{"i":1,"token":"{t0}","fit":90,"why":"great"}},'
             f'{{"i":2,"token":"{t1}","fit":40,"why":"meh"}}]')
    out = ranker.parse_response(reply, jobs)
    assert [s for _, s, _ in out] == [90, 40]
    assert out[0][0] is jobs[0]


def test_gate_applies_hard_filter():
    import preferences
    jobs = [_job(), models.JobResult(title="X", company="Y", location="",
            salary_min=70000, salary_max=None, description="", url="https://x.co/3",
            source_keyword="", created="", source_api="t")]
    prefs = {"profile_md": "", "hard": {**preferences._DEFAULT_HARD, "salary_min": 90000}}
    out = ranker.gate(jobs, prefs)
    assert len(out) == 1 and out[0].salary_min == 100000


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
        Anthropic=lambda api_key=None, base_url=None: types.SimpleNamespace(
            messages=types.SimpleNamespace(create=fake_create)))
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic)
    monkeypatch.setattr(ranker, "api_key", lambda: "sk-test")
    out = ranker.rank_via_api(jobs, prefs={"profile_md": "controls", "hard": {}},
                              experience_summary="C++")
    assert out[0][1] == 88
    assert "controls" in captured["messages"][0]["content"]
