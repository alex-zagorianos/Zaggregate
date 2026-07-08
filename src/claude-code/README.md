# Zaggregate — Claude Code channel

Run your whole job search by chatting with Claude Code: it searches, ranks the results
to your preferences, tracks applications, and tailors resumes — using **your own Claude
plan**, entirely on your computer. No API key, no copy-pasting.

## Packaged app (Setup.exe) — the zero-setup way

If you installed Zaggregate with **Setup.exe**, there's nothing to clone or install:

1. Open **Claude Code** in the **`Documents\Zaggregate`** folder the app made for you
   (there's a "Zaggregate for Claude Code" shortcut on your Desktop).
2. Say **"find me jobs"** — or, e.g., _"run searches for events and hospitality jobs near
   Cincinnati."_

That folder already contains everything Claude Code needs: a `.mcp.json` pointed at the
bundled `Zaggregate-MCP.exe`, an `AGENTS.md` guide, and the `find-jobs` skill. The server
runs from inside the installed app — no Python, no repo, no config.

> Your first searches get richer once you add the free source API keys in the app
> (**Connect job sources**); the keyless sources work out of the box.

## From source (developers)

Running from a clone instead of the packaged app:

1. `pip install -r requirements-mcp.txt` (the `mcp` SDK).
2. Copy this folder's `.mcp.json` into the repo root (the server lives at
   `src/mcp_server.py`), or merge its `mcpServers.zaggregate` entry into an existing one.
   > macOS/Linux: change the command from `py` to `python3`.
3. Copy `skills/find-jobs/` into `.claude/skills/` (or your global `~/.claude/skills/`).
4. Run `claude` in the repo root and say **"find me jobs"** (or `/find-jobs`).

## How it works

The `zaggregate` MCP server is a thin, LOCAL data layer over the job-search engine.
Claude Code calls `get_preferences` → `search_jobs` → `list_inbox` → ranks the postings
against your preferences itself → `set_fit_scores` → `track_job` — plus the whole
application cycle (status, follow-ups, resume tailoring). The server does no AI; your
Claude plan does the thinking, and nothing leaves your machine.

**Tools:** `get_preferences`, `search_jobs`, `list_inbox`, `set_fit_scores`, `track_job`,
`dismiss_job`, `export_inbox`, `import_scores`, `seed_companies`, `list_applications`,
`get_application`, `set_status`, `set_follow_up`, `followups_due`, `funnel`,
`draft_followup_context`, `skill_gap`, `get_resume_prompt`, `save_resume`.

> Heads up: the app and the MCP server share the same local data, one writer at a time.
> Drive the search from Claude Code and don't triage in the app window _while_ Claude is
> running a search (the open window won't refresh on its own). A future version will let
> Claude drive the open app live.

## Using other MCP clients

`Zaggregate-MCP.exe` (packaged) or `py src/mcp_server.py` (source) is a standard **stdio**
MCP server — nothing is Claude-Code-specific. Any MCP client (Claude Desktop, Cursor, or
your own SDK client) can launch it and call the tools above. It's a pure local data layer
over your data folder; the client's model does the ranking and drafting.

## Bring your own AI (any provider)

The app is provider-agnostic. Beyond the copy-paste bridge (works with any chatbot) and
Claude Code (this channel), the direct-API route can point at ANY Anthropic-compatible
endpoint:

- Leave the base URL blank (default) to use Anthropic's own API with your key.
- Set a **Base URL** in the desktop app under **Tools -> Connect your AI**, or the
  `ANTHROPIC_BASE_URL` env var, to route the SAME calls to a local or third-party model:
  - **Ollama** (v0.14+) exposes a native Anthropic endpoint — e.g.
    `http://localhost:11434`. Fully offline, no key needed by Anthropic.
  - **GLM (Z.ai)**, **DeepSeek**, and **Kimi** all ship Anthropic-compatible endpoints —
    set the base URL to theirs and your key in the key box.

This one setting covers the ranker, the GUI auto-rank, resume/cover generation, company
enumeration, and industry-profile enrichment (all five AI call sites).

> Note: OpenAI/Gemini/LM-Studio use the OpenAI chat-completions shape, not the Anthropic
> message shape, so a full OpenAI-compat adapter (provider enum + request translation) is
> **future work** — not yet wired here. Use Ollama's native Anthropic endpoint, or one of
> the Anthropic-compatible providers above, in the meantime.
