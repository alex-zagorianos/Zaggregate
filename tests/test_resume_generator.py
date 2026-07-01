import types

import pytest

import resume.generator as gen
from resume.generator import (
    ResumeGenerationError,
    _build_system,
    generate_resume_and_cover_letter,
)
from resume.experience_parser import load_experience


@pytest.fixture(autouse=True)
def _experience_fixture(tmp_path, monkeypatch):
    """These tests exercise the generator, not the user's personal experience.md
    (gitignored — absent in fresh clones and worktrees). Point the default
    experience file at a minimal valid fixture so the suite never depends on
    personal data being present on disk."""
    exp = tmp_path / "experience.md"
    exp.write_text(
        "## CONTACT\nAlex Example - a@b.c\n\n"
        "## TECHNICAL SKILLS\nPython\n\n"
        "## WORK EXPERIENCE\nEngineer at Acme (2020-2025)\n",
        encoding="utf-8",
    )
    import resume.experience_parser as ep
    monkeypatch.setattr(ep.workspace, "experience_file", lambda: exp)


# ── prompt assembly ───────────────────────────────────────────────────────────

def test_system_blocks_have_cached_corpus():
    blocks = _build_system(load_experience())
    assert len(blocks) == 2
    # The static corpus (last block) carries the cache breakpoint.
    assert blocks[-1].get("cache_control") == {"type": "ephemeral"}
    assert "CANDIDATE EXPERIENCE" in blocks[-1]["text"]


def test_tool_schema_matches_docx_keys():
    required = gen.RESUME_TOOL["input_schema"]["required"]
    assert set(required) == {
        "contact", "summary", "skills", "experience", "education", "cover_letter"
    }


# ── error guards (no API call) ────────────────────────────────────────────────

def test_missing_key_raises(monkeypatch):
    monkeypatch.setattr(gen, "ANTHROPIC_API_KEY", "")
    with pytest.raises(ResumeGenerationError, match="ANTHROPIC_API_KEY"):
        generate_resume_and_cover_letter("some posting")


def test_empty_posting_raises(monkeypatch):
    monkeypatch.setattr(gen, "ANTHROPIC_API_KEY", "sk-test")
    with pytest.raises(ResumeGenerationError, match="empty"):
        generate_resume_and_cover_letter("   ")


# ── happy path (mocked SDK) ───────────────────────────────────────────────────

class _FakeBlock:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _FakeMessages:
    def __init__(self, message):
        self._message = message
        self.captured = {}

    def create(self, **kwargs):
        self.captured.update(kwargs)
        return self._message


class _FakeClient:
    def __init__(self, message):
        self.messages = _FakeMessages(message)


def test_returns_tool_input(monkeypatch):
    payload = {
        "contact": {"name": "Alex", "email": "a@b.c", "phone": "1", "location": "Cincinnati, OH"},
        "summary": "s", "skills": ["x"],
        "experience": [{"company": "Acme", "title": "Eng", "bullets": ["b"]}],
        "education": [{"institution": "NCSU", "degree": "BSME"}],
        "cover_letter": "para1\n\npara2",
    }
    msg = types.SimpleNamespace(
        stop_reason="tool_use",
        content=[_FakeBlock(type="tool_use", name="emit_resume", input=payload)],
    )
    fake = _FakeClient(msg)
    monkeypatch.setattr(gen, "ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(gen.anthropic, "Anthropic",
                        lambda api_key, base_url=None: fake)

    out = generate_resume_and_cover_letter("Controls Engineer at Acme")
    assert out == payload
    # forced structured output + posting in the user turn only
    assert fake.messages.captured["tool_choice"] == {"type": "tool", "name": "emit_resume"}
    assert "Controls Engineer" in fake.messages.captured["messages"][0]["content"]


def test_max_tokens_raises(monkeypatch):
    msg = types.SimpleNamespace(stop_reason="max_tokens", content=[])
    monkeypatch.setattr(gen, "ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(gen.anthropic, "Anthropic",
                        lambda api_key, base_url=None: _FakeClient(msg))
    with pytest.raises(ResumeGenerationError, match="token limit"):
        generate_resume_and_cover_letter("posting")
