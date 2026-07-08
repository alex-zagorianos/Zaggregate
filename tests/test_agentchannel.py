"""Tests for src/agentchannel.py — the Documents\\Zaggregate Claude Code scaffold.

Everything is mocked to a tmp dir; no real Documents folder, registry, powershell, or
frozen exe is touched.
"""
import json
import sys

import pytest

import config
import agentchannel


@pytest.fixture
def frozen_agent(monkeypatch, tmp_path):
    """Simulate a frozen install: Documents -> tmp, exe -> tmp, no shortcut, a fake
    bundled skill. Returns (agent_dir, exe_path)."""
    docs = tmp_path / "Documents"
    docs.mkdir()
    install = tmp_path / "install" / "current"
    install.mkdir(parents=True)
    exe = install / "JobProgram.exe"
    exe.write_text("", encoding="utf-8")

    # a fake bundled skill next to the exe
    skill = install / "claude-code" / "skills" / "find-jobs" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# find-jobs skill\n", encoding="utf-8")

    monkeypatch.setattr(config, "_is_frozen", lambda: True)
    monkeypatch.setattr(agentchannel, "documents_dir", lambda: docs)
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.setattr(agentchannel, "_make_shortcut", lambda d: None)  # no powershell
    return docs / "Zaggregate", exe


def test_skipped_when_not_frozen(monkeypatch):
    monkeypatch.setattr(config, "_is_frozen", lambda: False)
    assert agentchannel.ensure_agent_folder() is None


def test_scaffolds_the_full_folder(frozen_agent):
    agent_dir, exe = frozen_agent
    result = agentchannel.ensure_agent_folder()
    assert result == agent_dir
    assert (agent_dir / ".mcp.json").is_file()
    assert (agent_dir / "AGENTS.md").is_file()
    assert (agent_dir / "CLAUDE.md").is_file()      # both names, same guide
    assert (agent_dir / "README.txt").is_file()
    assert (agent_dir / ".claude" / "skills" / "find-jobs" / "SKILL.md").is_file()


def test_mcp_json_points_at_the_companion_exe(frozen_agent):
    agent_dir, exe = frozen_agent
    agentchannel.ensure_agent_folder()
    cfg = json.loads((agent_dir / ".mcp.json").read_text(encoding="utf-8"))
    cmd = cfg["mcpServers"]["zaggregate"]["command"]
    # companion sits next to the running exe, named Zaggregate-MCP.exe
    assert cmd == str(exe.parent / "Zaggregate-MCP.exe")
    assert cfg["mcpServers"]["zaggregate"]["args"] == []


def test_agents_md_has_the_golden_rule_and_caveat(frozen_agent):
    agent_dir, _ = frozen_agent
    agentchannel.ensure_agent_folder()
    guide = (agent_dir / "AGENTS.md").read_text(encoding="utf-8")
    assert "Never apply" in guide                      # never-apply rule
    assert "one writer at a time" in guide             # standalone concurrency caveat
    assert "search_jobs" in guide and "set_fit_scores" in guide


def test_idempotent_and_preserves_user_edits(frozen_agent):
    agent_dir, exe = frozen_agent
    agentchannel.ensure_agent_folder()
    # user edits the guide
    (agent_dir / "AGENTS.md").write_text("MY EDITS", encoding="utf-8")
    # a later launch must not clobber it...
    agentchannel.ensure_agent_folder()
    assert (agent_dir / "AGENTS.md").read_text(encoding="utf-8") == "MY EDITS"
    # ...but .mcp.json is always refreshed to the authoritative exe path
    cfg = json.loads((agent_dir / ".mcp.json").read_text(encoding="utf-8"))
    assert cfg["mcpServers"]["zaggregate"]["command"] == str(
        exe.parent / "Zaggregate-MCP.exe")


def test_never_raises_on_failure(monkeypatch, tmp_path):
    """A scaffolding error must degrade to None, never propagate into startup."""
    monkeypatch.setattr(config, "_is_frozen", lambda: True)

    def _boom():
        raise OSError("no documents")

    monkeypatch.setattr(agentchannel, "documents_dir", _boom)
    assert agentchannel.ensure_agent_folder() is None


def test_documents_dir_falls_back_without_registry(monkeypatch):
    """If the Shell Folders lookup fails, fall back to ~/Documents rather than raise."""
    import builtins
    real_import = builtins.__import__

    def _no_winreg(name, *a, **k):
        if name == "winreg":
            raise ImportError("no winreg")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _no_winreg)
    got = agentchannel.documents_dir()
    assert got.name == "Documents"
