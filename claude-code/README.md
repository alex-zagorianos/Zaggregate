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

## Bring your own AI (any provider)

The app is provider-agnostic. Beyond the copy-paste bridge (works with any
chatbot) and Claude Code (this channel), the direct-API route can point at ANY
Anthropic-compatible endpoint:

- Leave the base URL blank (default) to use Anthropic's own API with your key.
- Set a **Base URL** in the desktop app under **Tools -> Connect your AI**, or
  the `ANTHROPIC_BASE_URL` env var, to route the SAME calls to a local or
  third-party model:
  - **Ollama** (v0.14+) exposes a native Anthropic endpoint — e.g.
    `http://localhost:11434`. Fully offline, no key needed by Anthropic.
  - **GLM (Z.ai)**, **DeepSeek**, and **Kimi** all ship Anthropic-compatible
    endpoints — set the base URL to theirs and your key in the key box.

This one setting covers the ranker, the GUI auto-rank, resume/cover generation,
company enumeration, and industry-profile enrichment (all five AI call sites).

> Note: OpenAI/Gemini/LM-Studio use the OpenAI chat-completions shape, not the
> Anthropic message shape, so a full OpenAI-compat adapter (provider enum +
> request translation) is **future work** — not yet wired here. Use Ollama's
> native Anthropic endpoint, or one of the Anthropic-compatible providers above,
> in the meantime.
