"""Provider-agnostic base_url plumbing (C2 / review P4).

A fake `anthropic` module records every `Anthropic(...)` constructor call so we
can assert base_url is threaded through at ALL FIVE AI call sites:
  ranker.rank_via_api, gui._call_prompt_via_api, resume/generator.py,
  discover/enumerate.py, industry_profile.py.

None of these hit the network — the fake client returns canned text/tool blocks.
"""
import sys
import types

import pytest

import config
import claude_bridge as bridge
import models


def _fake_anthropic(calls, *, reply_text="[]", tool_input=None):
    """Build a fake `anthropic` module. Records constructor kwargs into `calls`.
    messages.create returns a text block (reply_text) and, if tool_input is
    given, a tool_use block named emit_resume (for the resume generator)."""
    def make_client(**kwargs):
        calls.append(kwargs)
        blocks = [types.SimpleNamespace(type="text", text=reply_text)]
        if tool_input is not None:
            blocks.append(types.SimpleNamespace(
                type="tool_use", name="emit_resume", input=tool_input))

        def create(**_kw):
            return types.SimpleNamespace(content=blocks, stop_reason="end_turn")
        return types.SimpleNamespace(
            messages=types.SimpleNamespace(create=create))

    ns = types.SimpleNamespace(Anthropic=make_client)
    # generator.py catches anthropic.AuthenticationError/RateLimitError/APIError
    ns.AuthenticationError = type("AuthenticationError", (Exception,), {})
    ns.RateLimitError = type("RateLimitError", (Exception,), {})
    ns.APIError = type("APIError", (Exception,), {})
    return ns


def _job(url="https://x.co/1"):
    return models.JobResult(
        title="Controls Engineer", company="Acme", location="Cincinnati, OH",
        salary_min=100000, salary_max=None, description="C++ motion control",
        url=url, source_keyword="", created="", source_api="test")


# ── base_url resolution ───────────────────────────────────────────────────────

def test_anthropic_base_url_none_when_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path)
    assert config.anthropic_base_url() is None


def test_anthropic_base_url_env_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://env:1")
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path)
    (tmp_path / "base_url").write_text("http://secret:2", encoding="utf-8")
    assert config.anthropic_base_url() == "http://env:1"


def test_anthropic_base_url_secret_fallback(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path)
    (tmp_path / "base_url").write_text("  http://localhost:11434  \n", encoding="utf-8")
    assert config.anthropic_base_url() == "http://localhost:11434"


def test_anthropic_base_url_blank_secret_is_none(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path)
    (tmp_path / "base_url").write_text("   \n", encoding="utf-8")
    assert config.anthropic_base_url() is None


# ── site 1: ranker.rank_via_api ───────────────────────────────────────────────

def test_ranker_passes_base_url(monkeypatch):
    import ranker
    jobs = [_job()]
    tok = bridge.fit_token(jobs[0])
    calls = []
    monkeypatch.setitem(sys.modules, "anthropic",
                        _fake_anthropic(calls, reply_text=f'[{{"token":"{tok}","fit":80}}]'))
    monkeypatch.setattr(ranker, "api_key", lambda: "sk-test")
    monkeypatch.setattr(config, "anthropic_base_url", lambda: "http://ollama:11434")
    ranker.rank_via_api(jobs, prefs={"profile_md": "", "hard": {}}, experience_summary="")
    assert calls and calls[0]["base_url"] == "http://ollama:11434"
    assert calls[0]["api_key"] == "sk-test"


# ── site 2: gui._call_prompt_via_api ──────────────────────────────────────────

def test_gui_call_prompt_passes_base_url(monkeypatch):
    gui = pytest.importorskip("gui")
    calls = []
    monkeypatch.setitem(sys.modules, "anthropic", _fake_anthropic(calls, reply_text="hi"))
    monkeypatch.setattr(gui._ranker_mod, "api_key", lambda: "sk-test")
    monkeypatch.setattr(config, "anthropic_base_url", lambda: "http://glm:8080")
    out = gui._call_prompt_via_api("rank these")
    assert out == "hi"
    assert calls and calls[0]["base_url"] == "http://glm:8080"


# ── site 3: resume/generator.py ───────────────────────────────────────────────

def test_resume_generator_passes_base_url(monkeypatch):
    from resume import generator
    calls = []
    tool_input = {"contact": {"name": "N", "email": "e", "phone": "p", "location": "l"},
                  "summary": "s", "skills": ["a"],
                  "experience": [{"company": "c", "title": "t", "bullets": ["b"]}],
                  "education": [{"institution": "i", "degree": "d"}],
                  "cover_letter": "cl"}
    fake = _fake_anthropic(calls, tool_input=tool_input)
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    monkeypatch.setattr(generator, "anthropic", fake)  # module bound it at import
    monkeypatch.setattr(generator, "ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(generator, "load_experience", lambda: {})
    monkeypatch.setattr(config, "anthropic_base_url", lambda: "http://deepseek:9000")
    data = generator.generate_resume_and_cover_letter("Some job posting")
    assert data["summary"] == "s"
    assert calls and calls[0]["base_url"] == "http://deepseek:9000"


# ── site 4: discover/enumerate.py ─────────────────────────────────────────────

def test_enumerate_passes_base_url(monkeypatch):
    from discover import enumerate as enum
    calls = []
    monkeypatch.setitem(sys.modules, "anthropic", _fake_anthropic(calls, reply_text="[]"))
    import ranker
    monkeypatch.setattr(ranker, "api_key", lambda: "sk-test")
    monkeypatch.setattr(config, "anthropic_base_url", lambda: "http://kimi:7000")
    enum.enumerate_via_api("Cincinnati", ["engineering"], angles=["angle one"])
    assert calls and calls[0]["base_url"] == "http://kimi:7000"


# ── site 5: industry_profile.py (base_url + fast-model constant) ──────────────

def test_industry_profile_passes_base_url_and_fast_model(monkeypatch, tmp_path):
    import industry_profile
    calls = []
    created_models = []

    def make_client(**kwargs):
        calls.append(kwargs)

        def create(**kw):
            created_models.append(kw.get("model"))
            block = types.SimpleNamespace(type="text",
                                          text='{"muse_categories":[],"jobicy_industry":null,'
                                               '"query_synonyms":[],"title_terms":[]}')
            return types.SimpleNamespace(content=[block])
        return types.SimpleNamespace(messages=types.SimpleNamespace(create=create))

    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=make_client))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(config, "anthropic_base_url", lambda: "http://ollama:11434")
    monkeypatch.setattr(config, "ANTHROPIC_FAST_MODEL", "my-fast-model")
    monkeypatch.setattr(industry_profile, "_user_json_path", lambda: tmp_path / "ip.json")
    industry_profile.enrich_via_ai("underwater basket weaving")
    assert calls and calls[0]["base_url"] == "http://ollama:11434"
    assert created_models == ["my-fast-model"]
