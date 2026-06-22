# JobScout — Claude Code channel

Drive your job search from Claude Code: it searches, then ranks your inbox to your
preferences using **your own Claude Code plan** — no API key, no copy-pasting.

## Setup

1. `pip install -r requirements-mcp.txt` (installs the `mcp` SDK the server needs).
2. Copy this folder's `.mcp.json` into the JobScout project folder (next to
   `mcp_server.py`), or merge its `mcpServers.jobscout` entry into an existing one.
3. Copy `skills/find-jobs/` into `.claude/skills/` in that folder (or into your
   global `~/.claude/skills/`).
4. Fill in `data/preferences.md` (what you want, plain English) and
   `data/experience.md` (your background).
5. Run `claude` in the folder and say **"find me jobs"** (or invoke `/find-jobs`).

> macOS/Linux: change the `.mcp.json` command from `py` to `python3`.

## How it works

The `jobscout` MCP server is a thin, local data layer over the job-search engine.
Claude Code calls `get_preferences` → `search_jobs` → `list_inbox` → ranks the
postings against your preferences itself → `set_fit_scores` → `track_job`. Nothing
leaves your machine except your own Claude Code session; everything is stored in
your `data/` folder.

Tools: `get_preferences`, `search_jobs`, `list_inbox`, `set_fit_scores`,
`track_job`, `dismiss_job`.
