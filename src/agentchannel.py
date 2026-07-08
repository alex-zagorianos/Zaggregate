r"""Scaffold the "point Claude Code here" folder for a Setup.exe install.

Goal: a non-technical user installs Zaggregate, opens **Claude Code** in
`Documents\Zaggregate`, and says *"run searches for these types of jobs"* — no repo
clone, no Python, no config. This module drops the folder that makes that work:

    Documents\Zaggregate\
        .mcp.json                     -> spawns the bundled Zaggregate-MCP.exe (stdio)
        AGENTS.md                     -> operator guide (Claude Code reads it each session)
        .claude\skills\find-jobs\SKILL.md  -> the detailed find-jobs workflow
        README.txt                    -> "open this folder in Claude Code and say 'find me jobs'"

`ensure_agent_folder()` is idempotent and frozen-only: it runs on app launch (the exe
scaffolds its own agent folder), rewrites `.mcp.json` each time (the exe path is the
source of truth), and never clobbers a user's edited `AGENTS.md`.

Drive model (Alex, 2026-07-08): STANDALONE — the MCP server opens the data folder
directly, so it works with the app closed. The guide therefore tells the user to treat
Claude Code as the primary surface and not to triage in the GUI *while* Claude runs
searches (one writer at a time). The "co-pilot on the open app" model is future work.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import config

AGENT_FOLDER_NAME = "Zaggregate"
MCP_EXE_NAME = "Zaggregate-MCP.exe"
MCP_SERVER_KEY = "zaggregate"


def documents_dir() -> Path:
    """The user's real Documents folder, honoring OneDrive Known-Folder-Move.

    Reads the resolved `Personal` path from the Shell Folders registry (Windows keeps
    it current when Documents is redirected to OneDrive); falls back to ~/Documents."""
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
        ) as key:
            val, _ = winreg.QueryValueEx(key, "Personal")
        if val:
            return Path(os.path.expandvars(val))
    except Exception:
        pass
    return Path(os.path.expanduser("~")) / "Documents"


def agent_dir() -> Path:
    return documents_dir() / AGENT_FOLDER_NAME


def _mcp_exe_path() -> Path:
    r"""Absolute path to the bundled companion exe (next to the running exe). Under a
    Velopack install this is `...\Zaggregate\current\Zaggregate-MCP.exe`, a path that
    stays valid across updates (Velopack keeps `current` as the live dir)."""
    return Path(sys.executable).parent / MCP_EXE_NAME


def _mcp_json(exe_path: Path) -> str:
    return json.dumps(
        {"mcpServers": {MCP_SERVER_KEY: {"command": str(exe_path), "args": []}}},
        indent=2,
    )


AGENTS_MD = """\
# Driving Zaggregate for a job seeker

You are connected to the **{key}** MCP server — a local job-search app running entirely
on this computer. **You are the ranker; the server does no AI of its own.** It exposes
tools to search job sources, read the inbox, score jobs, track applications, and tailor
resumes. Everything stays on this machine.

## The one rule
**Never apply to a job on the user's behalf.** You find, rank, and prep — the user
always clicks Submit themselves.

## When the user says "run searches for <kinds of jobs>"
1. `get_preferences` — read what they want + their background.
2. `search_jobs` with keywords from their request (and their location) — this fetches,
   filters, scores, and adds new postings to the inbox.
3. `list_inbox` (`compact=true`, `limit<=150`, page for big inboxes) — the postings to judge.
4. Score each 0-100 against their preferences AND background (90+ = apply today, 70-89
   strong, 50-69 stretch, <50 skip); pick the top ~10 and rank them 1..N.
5. `set_fit_scores` with `[{{"id","fit","rationale","rank"}}, ...]` — this fills their
   **Top Picks**.
6. Show the top matches best-first (title - company - location - fit - one-line why) and
   offer to `track_job` the good ones.

Then keep helping through the whole cycle: `track_job`, `list_applications`, `set_status`,
`followups_due`, `draft_followup_context`, `skill_gap`, `get_resume_prompt` /
`save_resume`. The detailed playbook is in **`.claude/skills/find-jobs/SKILL.md`**.

## If the Zaggregate app window is also open
The app and this server share the same local data, one writer at a time. So: drive the
search from here (Claude Code), and don't triage in the app window *while* you're running
a search. The open app won't refresh on its own — the user can reopen/refresh it to see
what you did. (A future version will let you drive the open app live.)
"""

README_TXT = """\
Zaggregate + Claude Code
========================

This folder connects Claude Code to your Zaggregate app so you can run your whole job
search by chatting.

1. Open Claude Code in THIS folder.
2. Say something like: "run searches for events and hospitality jobs near Cincinnati".
3. Claude searches, ranks the results to your preferences, and shows you the best ones -
   then it can track jobs, draft follow-ups, and tailor your resume, all on request.

Everything runs on your computer. Claude never applies to a job for you.

(Requires Claude Code with your own Claude plan. No Python or setup needed - the app
provides the tools.)
"""


def _skill_source() -> Path | None:
    """Locate the bundled find-jobs skill. Tried: the PyInstaller bundle root
    (config.DATA_DIR/claude-code, when app.spec bundles it) then the loose copy the
    packager drops next to the exe. None if neither is present."""
    for base in (config.DATA_DIR, Path(sys.executable).parent):
        p = base / "claude-code" / "skills" / "find-jobs" / "SKILL.md"
        if p.is_file():
            return p
    return None


def _write_if_missing(path: Path, content: str) -> None:
    if not path.exists():
        path.write_text(content, encoding="utf-8")


def _make_shortcut(target_dir: Path) -> None:
    """Best-effort Desktop shortcut to the agent folder so a non-technical user can
    find it. Never raises — a missing shortcut is cosmetic."""
    try:
        desktop = Path(os.path.join(os.path.expanduser("~"), "Desktop"))
        lnk = desktop / "Zaggregate for Claude Code.lnk"
        if lnk.exists():
            return
        ps = (
            "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
            "$s.TargetPath='{tgt}';$s.Save()"
        ).format(lnk=str(lnk), tgt=str(target_dir))
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            check=False, capture_output=True, timeout=15,
        )
    except Exception:
        pass


def ensure_agent_folder() -> Path | None:
    """Create/refresh `Documents\\Zaggregate` for the Claude Code channel. Frozen-only
    and never raises — a scaffolding hiccup must not stop the app from launching.

    Returns the folder path (or None when skipped/failed)."""
    if not config._is_frozen():
        return None
    try:
        folder = agent_dir()
        (folder / ".claude" / "skills" / "find-jobs").mkdir(parents=True, exist_ok=True)

        # .mcp.json: rewrite every launch — the installed exe path is authoritative.
        (folder / ".mcp.json").write_text(_mcp_json(_mcp_exe_path()), encoding="utf-8")

        # Guide + readme: write once so a user's edits survive later launches.
        _write_if_missing(folder / "AGENTS.md",
                          AGENTS_MD.format(key=MCP_SERVER_KEY))
        # Claude Code also reads CLAUDE.md; ship both names pointing at the same guide.
        _write_if_missing(folder / "CLAUDE.md",
                          AGENTS_MD.format(key=MCP_SERVER_KEY))
        _write_if_missing(folder / "README.txt", README_TXT)

        skill_src = _skill_source()
        skill_dst = folder / ".claude" / "skills" / "find-jobs" / "SKILL.md"
        if skill_src and not skill_dst.exists():
            shutil.copyfile(skill_src, skill_dst)

        _make_shortcut(folder)
        return folder
    except Exception:
        return None
