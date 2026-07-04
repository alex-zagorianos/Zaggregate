# CLAUDE.md — Zaggregate (ZAG0005 Job-Program)

Python wide-net job aggregator + match-scoring + BYO-AI re-rank + resume gen + application tracker. tkinter GUI (`py gui.py`), MCP server (`mcp_server.py`), browser extension (`browser_ext/`, MV3).

## Session open

Read the newest `docs/handoffs/handoff_*.md` first, then `brain/_index.md`. Handoffs moved to `docs/handoffs/` in the S31 reorg — not repo root.

## Python — critical

- **Always `py -3.12`** — NEVER bare `python` or `uv`. A `uv run python` hook redirects to an empty ephemeral 3.11; the real env is global 3.12 (pytest 8.3.5).
- Tests: `py -3.12 -m pytest` — full suite expected green (~2195 as of S32).
- Deps beyond `.env`: `ttkbootstrap rapidfuzz cleanco defusedxml pywebview` (pip-installed globally; pywebview powers `--desktop` and is optional at runtime — missing → browser-mode fallback).

## Git discipline

- **PUSH HELD by default** — never push without Alex's explicit go. Commit locally freely.
- User data is gitignored (`projects/`, `tracker.db`, `preferences.*`, `config_dad/user_config`). `companies.json` IS tracked (ships as starter registry).
- Test projects: `gu-*` / `gs-*` / `test-*` slugs — disposable, currently kept pending Alex.

## Design philosophy (Alex, S35)

**Inclusion over precision: get as many potential jobs in front of the user as
possible — the USER does the final dropping.** Never add a filter that can
silently over-drop; when ambiguous, keep the job. Prefer down-ranking to
dropping, and showing to down-ranking. Only cut what's clearly stated as
unwanted (explicit dealbreaker token, hard salary floor, ToS-blocked source) or
completely unrelated. Trade-offs + accepted gaps live in `docs/KNOWN_ISSUES.md`.

## Gotchas

- **Never run two project-touching processes at once** — `current_db_path` reads the global `active` project; concurrent daily_runs corrupted inbox routing before the S27 pin. `daily_run --project X` flips the GLOBAL active project.
- `scripts/setup_lanes.py`: RUN it, never import it (import executes and rewrites projects.json).
- Rescore must pass ALL scoring levers — S32's rescore-drift bug erased new levers same-run; parity tests must be lever-tripping.
- Windows FileCache: keys with `:` are NTFS ADS — sanitized since S30; keep new cache keys filename-safe.
- Scoring changes: Alex's eng daily run must stay byte-identical unless he approves a delta (verified per wave).

## Docs

Per-session brain docs in `brain/` (plans, reviews, findings). Canonical status: `brain/project-status.md`.

**Brain-update rule (Alex, S34): after EVERY large batch change and at every
session finalization**, update all three brain surfaces before closing out:
`brain/project-status.md` (prepend the session entry), `_index.md` (status
paragraph + Core Documents table + Open list), and a `docs/handoffs/handoff_*`
narrative. The graphify graph self-maintains via the post-commit watcher hook
(verify `graphify-out/graph.json` mtime advanced after your last commit — the
rebuild log is `~/.cache/graphify-rebuild.log`); only run `graphify update .`
manually if the watcher didn't fire.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:

- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
