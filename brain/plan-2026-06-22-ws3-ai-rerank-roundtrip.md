# WS-3 AI Re-rank Round-trip — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the AI tailoring layer a clean, model-agnostic **file round-trip** — export the inbox as `.csv` + `.md` + a versioned `prompt.md`; the user hands those to any AI; the app imports the returned CSV/JSON, validates the `job_key` join, snapshots prior state to `score_history`, and re-ranks the inbox. Undo reverts the last re-rank. The existing bridge/API/MCP ranking routes are refactored behind a `Ranker` protocol with **no behavior change** (characterization-tested first).

**Architecture:** A new `rerank/` package (sibling of `search/`, `scrape/`, `match/`, `tracker/`, `coverage/`) holds the column contract + versioned prompt (`schema.py`), export (`export.py`), and tolerant import (`import_.py`). `ranker.py` grows a `Ranker` Protocol + `FileRanker`, with the existing bridge/API extracted into `BridgeRanker`/`ApiRanker` behind characterization tests. `tracker/db.py` bumps schema v2→v3 (adds `score_history` table + `inbox.extras` TEXT column), routes `inbox_set_fit` through a history snapshot, and adds `inbox_undo_last_rerank`. `mcp_server.py` gains `export_inbox`/`import_scores` tools; `gui.py` `InboxTab` gains Export/Import/Undo controls. The cross-source join key is WS-1's **`JobResult.job_key`** (sha1 16-hex `cached_property`) **when WS-1 has landed it**; today's `models.py` has only `identity_key`/`dedup_key` (no `job_key`, no `functools`/`cached_property`), so WS-3 reads the key via `getattr(job, "job_key", None) or job.identity_key` and never assumes `job_key` already exists. WS-3 must NOT add `job_key` to `models.py` (that is WS-1 Task 5 / out-of-scope here).

**Tech Stack:** Python 3.11, pytest (`py -m pytest <path> -v`, Windows `py` launcher), stdlib `csv`/`json`/`hashlib`/`re`/`sqlite3`/`shutil`/`io`/`dataclasses`/`typing`/`pathlib`/`datetime`. The round-trip is stdlib-only. (`rapidfuzz` is named in the spec for a deferred fuzzy fallback that THIS plan does not implement — no WS-3 task imports it.)

## Global Constraints

- **Test runner:** `py -m pytest <path> -v`. The suite must stay green; this plan adds ~30–35 test functions. Do not hard-code a suite-wide count — recount at build time.
- **No new REQUIRED deps, and no optional dep is actually used.** The round-trip is stdlib-only across every task in this plan. `rapidfuzz` is referenced by the spec only for a deferred opt-in fuzzy fallback that this plan does NOT build, so **no WS-3 module imports `rapidfuzz`** and `rerank/` never import-fails on its absence by construction. (It is NOT in `requirements.txt` today; the WS-1 plan that would add it has not landed.)
- **`job_key` is the join key (pinned by WS-1):** when WS-1 has landed, `JobResult.job_key` is a `functools.cached_property` returning a 16-hex sha1, itself falling back to `identity_key` on `ImportError`. **VERIFIED against the real codebase: `job_key` does NOT exist on `JobResult` yet** — today's `models.py` (read at plan-review time) defines only `dedup_key` (md5) and `identity_key` (md5), and has no `functools`/`cached_property` import. WS-1 (`brain/plan-2026-06-22-ws1-coverage-foundations.md`, Task 5) adds it; WS-3 must NOT add it (out-of-scope: do not touch `models.py`). Therefore WS-3 reads the key defensively as **`getattr(job, "job_key", None) or job.identity_key`** everywhere — preferring `job_key` when WS-1 has landed, else `identity_key` (which exists today). Both are deterministic and applied on BOTH the export and import sides, so the round-trip join is internally consistent under either key. **Do not redefine `job_key`** — read it off `JobResult`/rows via the getattr fallback. This makes `rerank/` build-able and testable standalone, before or after WS-1.
- **Tolerant import is mandatory:** accept CSV **or** JSON; strip a UTF-8 BOM; repair trailing commas (reuse `claude_bridge._strip_trailing_commas` / `_extract_json`); tolerate locale decimal commas in `new_fit`/`new_rank`; clamp `new_fit` to 0–100; reorder/extra/missing columns OK; a missing/rewritten `job_key` → reported in `unmatched`, never silently dropped.
- **CSV formula-injection guard:** every string cell written to the export CSV passes through the same guard as `search/report_csv._csv_safe` (prefix a leading `= + - @ \t \r` with `'`). Do not re-implement a weaker guard.
- **Prompt anchors are pinned:** `PROMPT_TEMPLATE` references the user's `preferences.md` (read via `preferences.load()["profile_md"]`) verbatim and reuses `claude_bridge._FIT_INSTRUCTIONS` so the file route gives identical scoring guidance to the bridge/API routes. `PROMPT_VERSION = "1"`.
- **DB migration safety:** bump `SCHEMA_VERSION` 2→3. The migration creates `score_history` and ALTERs `inbox` to add `extras TEXT DEFAULT ''`, gated on `PRAGMA user_version` exactly like the existing pattern. **Back up `tracker.db` (copy to `tracker.db.bak-v<old>`) before any v2→v3 ALTER**, and test the migration on a populated fixture DB (rows survive).
- **`inbox_set_fit` writes a `score_history` row BEFORE the UPDATE** (mirrors the `status_history` precedent in `update_job`). Signature stays `inbox_set_fit(inbox_id, fit, why)` plus a new optional `source` kwarg defaulting to `"manual"`.
- **No behavior change to existing ranker routes:** `ranker.build_request`, `ranker.parse_response`, `ranker.gate`, `ranker.rank_via_api`, `ranker.build_profile`, `ranker.has_api_key`, `ranker.api_key` must keep working with identical outputs. Characterization tests pin them BEFORE extraction.
- **TDD + frequent commits:** each task = failing test → run-to-fail → minimal impl → run-to-pass → conventional-commit.

## Setup (deps to pip install)

**No pip install is required for WS-3.** Every task below is **stdlib-only** (`csv`/`json`/`hashlib`/`re`/`sqlite3`/`shutil`/`io`/`dataclasses`/`typing`/`pathlib`/`datetime`). The repo's existing `requirements.txt` (`anthropic`, `pytest`, etc.) already covers the imports the characterization tests touch (`anthropic` is monkeypatched, never really called).

`rapidfuzz` is mentioned in the spec only for an **opt-in fuzzy `job_key` fallback that this plan does NOT implement** (it is a documented follow-up — see Self-Review). No task in this plan imports `rapidfuzz`, so do not `pip install` it and do not gate any task on it. (Note: `rapidfuzz` is NOT currently in `requirements.txt`; the WS-1 plan that would add it has not landed.) The strict-`job_key`-join + `unmatched` report is the complete WS-3 behavior; unmatched rows are reported, never silently dropped, with or without `rapidfuzz`.

Do NOT add anything to `requirements.txt` in this workstream (WS-3 adds no required deps).

## Out of scope for the executor (do NOT touch)

- Any file outside `rerank/`, `tests/rerank/`, `tests/fixtures/rerank/`, and the five explicitly-modified files (`ranker.py`, `tracker/db.py`, `tracker/service.py`, `mcp_server.py`, `gui.py`).
- Do NOT modify `models.py`, `coverage/`, `claude_bridge.py`, `search/`, `config.py`, `preferences.py`, or any `brain/` doc.
- Do NOT change the meaning/output of any existing `ranker.py` function, `mcp_server.py` tool, or `tracker/db.py` function beyond what each task specifies.
- Do NOT delete `normalize_url`, `identity_key`, `dedup_key`, `fit_token`, `status_history`, or any existing column.
- **Do NOT run any git commands and do NOT commit.** A parallel build is in progress; moving git refs would abort it. The commit STEP in each task documents the conventional-commit message the executor would use — when running under this plan, treat the commit step as a no-op marker (write the files, run the tests, move on).
- Do NOT `git push`, change git config, or merge branches under any circumstance.
- Do NOT auto-apply scores anywhere (unchanged app philosophy): import writes to the inbox only after an explicit call.
- Stay strictly within the tasks below, in order.

## Frozen Shared Interfaces

Every task uses these EXACT names/signatures. Internal helpers/tests are task-local.

```
# rerank/schema.py
RERANK_CSV_COLUMNS = ["job_key","title","company","location","salary","url",
    "local_score","current_fit","description_excerpt","new_fit","new_rank",
    "fit_rationale","tags"]
PROMPT_VERSION = "1"
PROMPT_TEMPLATE: str          # anchors to preferences.md + reuses claude_bridge._FIT_INSTRUCTIONS
OUT_COLUMNS  = [...]          # the subset the app fills (out)
IN_COLUMNS   = ["new_fit","new_rank","fit_rationale","tags"]   # the subset the AI fills (in)
csv_safe(value) -> object     # formula-injection guard (parity with report_csv._csv_safe)
row_from_inbox(r: dict) -> dict   # inbox-row dict -> RERANK_CSV_COLUMNS dict (string cells)
build_prompt(profile_md: str) -> str

# rerank/export.py
export_inbox(rows: list[dict], out_dir, *, fmt: str = "both") -> dict
    # returns {"csv": Path, "md": Path, "prompt": Path}; fmt in {"both","csv","md"}

# rerank/import_.py
@dataclass
class ImportResult:
    matched: int
    unmatched: list      # list of dicts: the returned rows whose job_key didn't join
    updated: int
    skipped: int
    errors: list         # list of str: per-row parse/validation problems
import_scores(path, rows_by_key: dict, *, policy: str = "overwrite") -> ImportResult
    # policy in {"overwrite","keep_existing","add_only"}
    # rows_by_key: {job_key -> inbox-row dict (must carry "id" and "fit")}
    # tolerant CSV+JSON parse; BOM strip; locale commas; clamp new_fit 0-100;
    # validate job_key join; writes via tracker.service.apply_rerank_scores

# ranker.py (ADD; existing module fns unchanged)
class Ranker(typing.Protocol):
    def build_request(self, jobs, prefs=None, experience_summary=None) -> str: ...
    def parse_response(self, text: str, jobs) -> list: ...
class BridgeRanker: ...     # wraps the existing build_request/parse_response
class ApiRanker: ...        # wraps rank_via_api
class FileRanker: ...       # export -> (user fills file) -> import; build_request==export prompt
                            # FileRanker.export(rows, out_dir, fmt="both") -> dict
                            # FileRanker.import_(path, rows_by_key, policy="overwrite") -> ImportResult

# tracker/db.py (MODIFY)
SCHEMA_VERSION = 3
# v3 migration: + table score_history(id, inbox_id, job_key, old_fit, new_fit, old_score, source, ts)
#               + column inbox.extras TEXT DEFAULT ''   ; backs up tracker.db before ALTER
inbox_set_fit(inbox_id, fit, why, source="manual")   # writes a score_history row BEFORE the UPDATE
inbox_set_extras(inbox_id, extras: str)              # write the extras JSON blob
inbox_undo_last_rerank(scope) -> int                 # revert the newest re-rank batch; returns rows restored
                                                     # scope: a source string (e.g. "file_import") or "any"

# tracker/service.py (ADD)
inbox_rows_by_key() -> dict                          # {job_key -> inbox-row dict} for the join
apply_rerank_scores(updates: list[dict], *, source="file_import") -> int
    # updates: [{"id","new_fit","fit_rationale","extras"?}, ...]; returns rows updated
undo_last_rerank(scope="file_import") -> int

# mcp_server.py (ADD tools)
@mcp.tool() export_inbox(out_dir: str, fmt: str = "both") -> dict
@mcp.tool() import_scores(path: str, policy: str = "overwrite") -> dict

# gui.py InboxTab (ADD)
# buttons: "Export for AI", "Import scores" (file picker + merge-policy dropdown + dry-run preview),
#          "Undo last re-rank"
```

## File Structure

```
rerank/                              # NEW package
  __init__.py · schema.py · export.py · import_.py
ranker.py                            # MODIFY — add Ranker protocol + Bridge/Api/FileRanker
tracker/db.py                        # MODIFY — SCHEMA_VERSION 3, score_history, inbox.extras, undo
tracker/service.py                   # MODIFY — inbox_rows_by_key, apply_rerank_scores, undo_last_rerank
mcp_server.py                        # MODIFY — export_inbox / import_scores tools
gui.py                               # MODIFY — InboxTab Export/Import/Undo controls
tests/rerank/                        # NEW — one test module per rerank concern
  __init__.py · test_schema.py · test_export.py · test_import.py
  test_ranker_characterization.py · test_ranker_protocol.py
  test_db_migration_v3.py · test_service_rerank.py · test_roundtrip.py
  test_mcp_rerank.py
tests/fixtures/rerank/               # NEW — populated v2 DB fixture for the migration test
  v2_populated.sql
```

---

### Task 1 — `rerank/` package skeleton + the column/prompt contract (`schema.py`)

**Files:** Create `rerank/__init__.py`, `rerank/schema.py`, `tests/rerank/__init__.py`, `tests/rerank/test_schema.py`

**Interfaces — Produces:** `RERANK_CSV_COLUMNS`, `PROMPT_VERSION`, `PROMPT_TEMPLATE`, `OUT_COLUMNS`, `IN_COLUMNS`, `csv_safe`, `row_from_inbox`, `build_prompt` (consumed by `export.py`, `import_.py`, `ranker.FileRanker`). **Consumes:** `claude_bridge._FIT_INSTRUCTIONS`, `preferences.load`.

- [ ] **Step 1:** Create `rerank/__init__.py` (empty package marker; do **not** import submodules at package top, so importing `rerank.schema` stays light and never pulls tkinter/anthropic).

- [ ] **Step 2: Write the failing test** `tests/rerank/test_schema.py`:

```python
from rerank import schema


def test_columns_frozen_exact_order():
    assert schema.RERANK_CSV_COLUMNS == [
        "job_key", "title", "company", "location", "salary", "url",
        "local_score", "current_fit", "description_excerpt",
        "new_fit", "new_rank", "fit_rationale", "tags",
    ]


def test_in_out_partition():
    assert schema.IN_COLUMNS == ["new_fit", "new_rank", "fit_rationale", "tags"]
    # every column is either out-context or an AI-filled in-column
    assert set(schema.OUT_COLUMNS) | set(schema.IN_COLUMNS) == set(schema.RERANK_CSV_COLUMNS)
    assert set(schema.OUT_COLUMNS) & set(schema.IN_COLUMNS) == set()


def test_prompt_version_is_one():
    assert schema.PROMPT_VERSION == "1"


def test_csv_safe_neutralizes_formula_chars():
    assert schema.csv_safe("=HYPERLINK(1)") == "'=HYPERLINK(1)"
    assert schema.csv_safe("@SUM(A1)") == "'@SUM(A1)"
    assert schema.csv_safe("-2+3") == "'-2+3"
    assert schema.csv_safe("plain") == "plain"
    assert schema.csv_safe(7) == 7  # non-strings pass through


def test_row_from_inbox_maps_and_carries_job_key():
    r = {"id": 5, "title": "Software Developer", "company": "Acme",
         "location": "Cincinnati, OH", "salary_text": "$120k", "url": "https://x/1",
         "score": 70, "fit": -1, "description": "build motion control " * 200}
    out = schema.row_from_inbox(r)
    assert set(out.keys()) == set(schema.RERANK_CSV_COLUMNS)
    assert out["local_score"] == 70
    assert out["current_fit"] == -1
    assert out["new_fit"] == ""  # AI-filled columns start blank
    assert len(out["description_excerpt"]) <= 1200
    assert out["job_key"]  # non-empty join key derived from the row


def test_build_prompt_anchors_to_preferences_and_fit_instructions(monkeypatch):
    import preferences
    monkeypatch.setattr(preferences, "load",
                        lambda: {"profile_md": "I want controls + embedded roles.", "hard": {}})
    p = schema.build_prompt("I want controls + embedded roles.")
    assert "controls + embedded" in p
    assert "Scoring guide" in p          # reused from claude_bridge._FIT_INSTRUCTIONS
    assert "new_fit" in p and "job_key" in p
    assert "version 1" in p.lower()
```

- [ ] **Step 2b: Run to fail** `py -m pytest tests/rerank/test_schema.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement** `rerank/schema.py`:

```python
"""The round-trip file contract (WS-3).

Defines the CSV column order carried between the app and the user's AI, the
versioned prompt template (anchored to preferences.md + the same fit-scoring
guide the bridge/API routes use), and the formula-injection guard. job_key is
the WS-1 cross-source join key and MUST echo back unchanged.
"""
from __future__ import annotations

import re

# Carrier column order. Reordering breaks golden-file tests — change deliberately.
RERANK_CSV_COLUMNS = [
    "job_key", "title", "company", "location", "salary", "url",
    "local_score", "current_fit", "description_excerpt",
    "new_fit", "new_rank", "fit_rationale", "tags",
]
# The AI fills these in; everything else is read-only context the app emits.
IN_COLUMNS = ["new_fit", "new_rank", "fit_rationale", "tags"]
OUT_COLUMNS = [c for c in RERANK_CSV_COLUMNS if c not in IN_COLUMNS]

PROMPT_VERSION = "1"
_DESC_LIMIT = 1200

_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value):
    """Formula-injection guard (parity with search.report_csv._csv_safe): a
    string starting with = + - @ or a control char is prefixed with a single
    quote so spreadsheets don't execute it. Non-strings pass through."""
    if isinstance(value, str) and value and value[0] in _DANGEROUS:
        return "'" + value
    return value


def _job_key_for_row(r: dict) -> str:
    """The WS-1 join key for an inbox row. Build a JobResult and read its
    cached job_key (added by WS-1; itself falls back to identity_key when the
    coverage package is absent), so export/import share one definition with the
    rest of the app. **WS-1 may not have landed yet** — the real models.py today
    has only identity_key/dedup_key, no job_key — so fall back to identity_key
    when JobResult has no job_key attribute. Both are deterministic and used on
    BOTH the export and import sides, so the round-trip join stays consistent
    whichever key is in effect."""
    from models import JobResult
    j = JobResult(
        title=r.get("title", "") or "", company=r.get("company", "") or "",
        location=r.get("location", "") or "", salary_min=None, salary_max=None,
        description=r.get("description", "") or "", url=r.get("url", "") or "",
        source_keyword="", created=r.get("created", "") or "",
        source_api=r.get("source", "") or "",
    )
    # getattr fallback: job_key (WS-1, 16-hex sha1) when present, else the
    # existing identity_key (32-hex md5). Never AttributeError on today's models.
    return getattr(j, "job_key", None) or j.identity_key


def row_from_inbox(r: dict) -> dict:
    """Map an inbox-row dict (tracker.db.inbox_all shape) into a full
    RERANK_CSV_COLUMNS dict. AI-filled columns start blank."""
    desc = re.sub(r"\s+", " ", (r.get("description", "") or "")).strip()[:_DESC_LIMIT]
    return {
        "job_key": _job_key_for_row(r),
        "title": r.get("title", "") or "",
        "company": r.get("company", "") or "",
        "location": r.get("location", "") or "",
        "salary": r.get("salary_text", "") or "",
        "url": r.get("url", "") or "",
        "local_score": r.get("score", -1),
        "current_fit": r.get("fit", -1),
        "description_excerpt": desc,
        "new_fit": "",
        "new_rank": "",
        "fit_rationale": "",
        "tags": "",
    }


def build_prompt(profile_md: str) -> str:
    """The versioned re-rank prompt: the same scoring guide the bridge/API use,
    plus the user's preferences profile, plus explicit round-trip instructions
    (fill new_fit/new_rank/fit_rationale; leave job_key untouched)."""
    from claude_bridge import _FIT_INSTRUCTIONS, DEFAULT_FIT_PREFERENCE
    guide = _FIT_INSTRUCTIONS.replace("__PREFERENCE__", DEFAULT_FIT_PREFERENCE.strip())
    cols = ", ".join(RERANK_CSV_COLUMNS)
    return "\n".join([
        f"# Job re-rank request (prompt version {PROMPT_VERSION})",
        "",
        "You are re-ranking the candidate's job inbox. Read the candidate "
        "profile below, then score EVERY row in the attached CSV "
        "(`ranking_export.csv`).",
        "",
        "## How to return your answer",
        f"Return the SAME CSV with these columns filled in: {', '.join(IN_COLUMNS)}.",
        "- `new_fit`: integer 0-100 (the scoring guide below).",
        "- `new_rank`: optional integer ordering within the batch (1 = best).",
        "- `fit_rationale`: one short line (why / red flags).",
        "- `tags`: optional free dimensions, comma-separated.",
        "**Leave `job_key` EXACTLY as given** — it is how scores are matched "
        "back; do not edit, reorder its characters, or drop the column. "
        "Returning JSON (a list of objects with these keys) is also accepted.",
        "",
        "## Scoring guide",
        guide,
        "",
        "## Candidate profile (from preferences.md)",
        (profile_md or "(no profile provided)").strip(),
        "",
        f"## CSV columns, in order\n{cols}",
    ])


# Module-level convenience: the default prompt rendered against the user's live
# preferences.md. Built lazily so importing schema.py never reads the data dir.
class _LazyPromptTemplate(str):
    pass


def _render_default_prompt() -> str:
    try:
        import preferences
        profile = (preferences.load() or {}).get("profile_md", "") or ""
    except Exception:
        profile = ""
    return build_prompt(profile)


PROMPT_TEMPLATE = _render_default_prompt()
```

- [ ] **Step 4: Run** `py -m pytest tests/rerank/test_schema.py -v` → PASS.
- [ ] **Step 5: Commit** (no-op under this plan; see Out-of-scope) — message: `feat(rerank): round-trip column contract + versioned prompt anchored to preferences + fit guide`

### Task 2 — `rerank/export.py` — write CSV + MD + prompt trio

**Files:** Create `rerank/export.py`, `tests/rerank/test_export.py`

**Interfaces — Produces:** `export_inbox(rows, out_dir, *, fmt="both") -> {"csv","md","prompt"}` (consumed by `ranker.FileRanker`, `mcp_server.export_inbox`, GUI). **Consumes:** `rerank.schema.*`, `preferences.load`.

- [ ] **Step 1: Write the failing test** `tests/rerank/test_export.py`:

```python
import csv
from rerank.export import export_inbox
from rerank import schema


def _rows():
    return [
        {"id": 1, "title": "Software Developer", "company": "Acme",
         "location": "Cincinnati, OH", "salary_text": "$120k", "url": "https://x/1",
         "score": 70, "fit": -1, "description": "build motion control systems"},
        {"id": 2, "title": "=cmd|' /C calc'!A0", "company": "Beta",
         "location": "Remote", "salary_text": "", "url": "https://x/2",
         "score": 55, "fit": 80, "description": "controls + plc"},
    ]


def test_export_both_writes_trio(tmp_path, monkeypatch):
    import preferences
    monkeypatch.setattr(preferences, "load", lambda: {"profile_md": "controls roles", "hard": {}})
    paths = export_inbox(_rows(), tmp_path, fmt="both")
    assert set(paths) == {"csv", "md", "prompt"}
    for p in paths.values():
        assert p.exists() and p.read_text(encoding="utf-8").strip()


def test_export_csv_header_and_join_key(tmp_path):
    paths = export_inbox(_rows(), tmp_path, fmt="csv")
    with paths["csv"].open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == schema.RERANK_CSV_COLUMNS
        rows = list(reader)
    assert len(rows) == 2
    assert all(r["job_key"] for r in rows)           # join key present per row
    assert rows[0]["new_fit"] == ""                  # AI columns blank on export


def test_export_csv_guards_formula_injection(tmp_path):
    paths = export_inbox(_rows(), tmp_path, fmt="csv")
    text = paths["csv"].read_text(encoding="utf-8-sig")
    assert "'=cmd" in text                            # leading = neutralized


def test_export_md_is_human_readable(tmp_path):
    paths = export_inbox(_rows(), tmp_path, fmt="md")
    md = paths["md"].read_text(encoding="utf-8")
    assert "Software Developer" in md and "| job_key" in md


def test_export_csv_only_skips_md(tmp_path):
    paths = export_inbox(_rows(), tmp_path, fmt="csv")
    assert "md" not in paths and "csv" in paths and "prompt" in paths
```

- [ ] **Step 2: Run to fail** → FAIL.

- [ ] **Step 3: Implement** `rerank/export.py`:

```python
"""Export the inbox as the round-trip trio: ranking_export.csv (the carrier the
AI fills), ranking_export.md (human-readable), and prompt.md (versioned)."""
from __future__ import annotations

import csv
from pathlib import Path

from rerank import schema


def _profile_md() -> str:
    try:
        import preferences
        return (preferences.load() or {}).get("profile_md", "") or ""
    except Exception:
        return ""


def _write_csv(out: Path, rows: list[dict]) -> Path:
    # utf-8-sig: Excel opens it without mojibake; the importer strips the BOM.
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=schema.RERANK_CSV_COLUMNS)
        w.writeheader()
        for r in rows:
            mapped = schema.row_from_inbox(r)
            w.writerow({k: schema.csv_safe(v) for k, v in mapped.items()})
    return out


def _write_md(out: Path, rows: list[dict]) -> Path:
    lines = ["# Inbox export for AI re-ranking", "",
             "Fill `new_fit` (0-100), optional `new_rank`, and `fit_rationale` "
             "for each row in `ranking_export.csv`. Leave `job_key` unchanged.",
             "",
             "| job_key | title | company | location | salary | local_score | current_fit |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    detail = ["", "## Job details", ""]
    for r in rows:
        m = schema.row_from_inbox(r)
        def cell(x):
            return str(x).replace("|", "\\|").replace("\n", " ")
        lines.append("| " + " | ".join(cell(m[c]) for c in
                     ("job_key", "title", "company", "location", "salary",
                      "local_score", "current_fit")) + " |")
        detail += [f"### {cell(m['title'])} — {cell(m['company'])}",
                   f"- job_key: `{m['job_key']}`",
                   f"- url: {m['url']}",
                   f"- {cell(m['description_excerpt'])}", ""]
    out.write_text("\n".join(lines + detail), encoding="utf-8")
    return out


def export_inbox(rows: list[dict], out_dir, *, fmt: str = "both") -> dict:
    """Write the export trio under out_dir. fmt in {"both","csv","md"}; the CSV
    and the versioned prompt are always written (the CSV is the carrier and the
    prompt is the instructions); fmt only toggles the human-readable MD.
    Returns {"csv": Path, "md": Path (when written), "prompt": Path}."""
    base = Path(out_dir)
    base.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    paths["csv"] = _write_csv(base / "ranking_export.csv", rows)
    if fmt in ("both", "md"):
        paths["md"] = _write_md(base / "ranking_export.md", rows)
    prompt = base / "prompt.md"
    prompt.write_text(schema.build_prompt(_profile_md()), encoding="utf-8")
    paths["prompt"] = prompt
    return paths
```

- [ ] **Step 4: Run** `py -m pytest tests/rerank/test_export.py -v` → PASS.
- [ ] **Step 5: Commit** (no-op marker) — message: `feat(rerank): export inbox to csv+md+prompt trio keyed by job_key (injection-guarded)`

### Task 3 — `rerank/import_.py` — tolerant CSV/JSON parse + job_key validation

**Files:** Create `rerank/import_.py`, `tests/rerank/test_import.py`

**Interfaces — Produces:** `ImportResult`, `import_scores(path, rows_by_key, *, policy="overwrite") -> ImportResult` (consumed by `ranker.FileRanker`, `mcp_server.import_scores`, GUI). **Consumes:** `claude_bridge._extract_json`/`_strip_trailing_commas`, `rerank.schema`, `tracker.service.apply_rerank_scores`. Note: this task introduces `import_scores` with the **parse + join + merge** logic but defers the DB write to `tracker.service.apply_rerank_scores` (Task 6); to keep this task self-contained and TDD-runnable now, `import_scores` accepts the join map `rows_by_key` directly and calls a small injectable writer (`_apply`) that defaults to `tracker.service.apply_rerank_scores` — tests pass a fake writer.

- [ ] **Step 1: Write the failing test** `tests/rerank/test_import.py`:

```python
from rerank.import_ import import_scores, ImportResult


def _rows_by_key():
    # job_key -> inbox row dict (must carry id + fit)
    return {
        "k1": {"id": 1, "fit": -1, "title": "Software Developer", "company": "Acme"},
        "k2": {"id": 2, "fit": 50, "title": "Controls Eng", "company": "Beta"},
    }


def _capture():
    seen = {}
    def writer(updates, *, source="file_import"):
        seen["updates"] = updates
        seen["source"] = source
        return len(updates)
    return seen, writer


def _write_csv(tmp_path, body, bom=False):
    p = tmp_path / "ret.csv"
    text = body
    if bom:
        text = "﻿" + text
    p.write_text(text, encoding="utf-8")
    return p


def test_import_csv_overwrite(tmp_path):
    seen, writer = _capture()
    body = ("job_key,new_fit,new_rank,fit_rationale,tags\n"
            "k1,88,1,great fit,plc\n"
            "k2,30,2,weak,\n")
    res = import_scores(_write_csv(tmp_path, body), _rows_by_key(),
                        policy="overwrite", _apply=writer)
    assert isinstance(res, ImportResult)
    assert res.matched == 2 and res.updated == 2 and res.unmatched == []
    ids = {u["id"]: u["new_fit"] for u in seen["updates"]}
    assert ids == {1: 88, 2: 30}


def test_import_strips_bom_and_clamps(tmp_path):
    seen, writer = _capture()
    body = "job_key,new_fit,fit_rationale\nk1,150,too high\n"
    res = import_scores(_write_csv(tmp_path, body, bom=True), _rows_by_key(),
                        _apply=writer)
    assert res.updated == 1
    assert seen["updates"][0]["new_fit"] == 100   # clamped


def test_import_locale_comma_decimal(tmp_path):
    seen, writer = _capture()
    body = 'job_key,new_fit\nk1,"88,0"\n'
    res = import_scores(_write_csv(tmp_path, body), _rows_by_key(), _apply=writer)
    assert res.updated == 1 and seen["updates"][0]["new_fit"] == 88


def test_import_unmatched_job_key_reported_not_dropped(tmp_path):
    seen, writer = _capture()
    body = "job_key,new_fit\nNOPE,90\nk1,70\n"
    res = import_scores(_write_csv(tmp_path, body), _rows_by_key(), _apply=writer)
    assert res.updated == 1
    assert len(res.unmatched) == 1 and res.unmatched[0]["job_key"] == "NOPE"


def test_import_keep_existing_skips_already_scored(tmp_path):
    seen, writer = _capture()
    body = "job_key,new_fit\nk1,88\nk2,99\n"
    res = import_scores(_write_csv(tmp_path, body), _rows_by_key(),
                        policy="keep_existing", _apply=writer)
    # k2 already has fit=50 -> kept; only k1 (fit=-1) updated
    assert res.updated == 1 and res.skipped == 1
    assert seen["updates"][0]["id"] == 1


def test_import_add_only_skips_already_scored(tmp_path):
    seen, writer = _capture()
    body = "job_key,new_fit\nk1,88\nk2,99\n"
    res = import_scores(_write_csv(tmp_path, body), _rows_by_key(),
                        policy="add_only", _apply=writer)
    assert res.updated == 1 and seen["updates"][0]["id"] == 1


def test_import_json_input(tmp_path):
    seen, writer = _capture()
    p = tmp_path / "ret.json"
    p.write_text('[{"job_key":"k1","new_fit":77,"fit_rationale":"ok"},]',
                 encoding="utf-8")  # note the tolerated trailing comma
    res = import_scores(p, _rows_by_key(), _apply=writer)
    assert res.updated == 1 and seen["updates"][0]["new_fit"] == 77


def test_import_bad_fit_recorded_as_error(tmp_path):
    seen, writer = _capture()
    body = "job_key,new_fit\nk1,notanumber\n"
    res = import_scores(_write_csv(tmp_path, body), _rows_by_key(), _apply=writer)
    assert res.updated == 0 and res.errors
```

- [ ] **Step 2: Run to fail** → FAIL.

- [ ] **Step 3: Implement** `rerank/import_.py`:

```python
"""Tolerant import of an AI-returned re-rank file (CSV or JSON).

Validates the WS-1 job_key join (unmatched rows are REPORTED, never silently
dropped), clamps new_fit to 0-100, tolerates Excel artifacts (UTF-8 BOM, locale
decimal commas, trailing commas in JSON, reordered/extra columns), applies the
chosen merge policy, then hands the survivors to a writer (default:
tracker.service.apply_rerank_scores) that snapshots to score_history.
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field

_POLICIES = ("overwrite", "keep_existing", "add_only")


@dataclass
class ImportResult:
    matched: int = 0
    unmatched: list = field(default_factory=list)
    updated: int = 0
    skipped: int = 0
    errors: list = field(default_factory=list)


def _default_apply(updates, *, source="file_import"):
    from tracker import service
    return service.apply_rerank_scores(updates, source=source)


def _read_text(path) -> str:
    raw = open(path, "r", encoding="utf-8-sig").read()  # utf-8-sig strips a BOM
    return raw


def _coerce_int(value):
    """Tolerant int: locale decimal comma ('88,0'), stray spaces, floats."""
    if value is None:
        raise ValueError("missing")
    s = str(value).strip().strip('"').replace(" ", "")
    if not s:
        raise ValueError("blank")
    s = s.replace(",", ".")          # locale decimal comma -> dot
    return int(round(float(s)))


def _clamp_fit(value) -> int:
    return max(0, min(100, _coerce_int(value)))


def _parse_records(text: str) -> tuple[list[dict], list[str]]:
    """Return (records, errors). Each record is a dict with at least job_key."""
    errors: list[str] = []
    stripped = text.lstrip()
    if stripped[:1] in ("[", "{"):
        from claude_bridge import _extract_json
        try:
            data = json.loads(_extract_json(text, prefer="array"))
        except json.JSONDecodeError as e:
            return [], [f"JSON parse failed: {e}"]
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return [], ["Expected a JSON array of score objects."]
        return [d for d in data if isinstance(d, dict)], errors
    # CSV path
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "job_key" not in [
            (h or "").strip().lstrip("﻿") for h in reader.fieldnames]:
        return [], ["CSV is missing the required job_key column."]
    records = []
    for raw in reader:
        records.append({(k or "").strip().lstrip("﻿"): v for k, v in raw.items()})
    return records, errors


def import_scores(path, rows_by_key: dict, *, policy: str = "overwrite",
                  _apply=None) -> ImportResult:
    if policy not in _POLICIES:
        raise ValueError(f"policy must be one of {_POLICIES}, got {policy!r}")
    apply = _apply or _default_apply
    res = ImportResult()
    records, parse_errors = _parse_records(_read_text(path))
    res.errors.extend(parse_errors)

    updates: list[dict] = []
    for rec in records:
        key = (rec.get("job_key") or "").strip()
        if not key:
            res.errors.append("row with missing/blank job_key")
            continue
        row = rows_by_key.get(key)
        if row is None:
            res.unmatched.append({"job_key": key, **{k: rec.get(k) for k in
                                  ("new_fit", "fit_rationale")}})
            continue
        res.matched += 1
        current_fit = int(row.get("fit", -1) or -1)
        already_scored = current_fit >= 0
        if policy in ("keep_existing", "add_only") and already_scored:
            res.skipped += 1
            continue
        try:
            new_fit = _clamp_fit(rec.get("new_fit"))
        except (ValueError, TypeError):
            res.errors.append(f"{key}: bad new_fit {rec.get('new_fit')!r}")
            continue
        update = {"id": row["id"], "new_fit": new_fit,
                  "fit_rationale": str(rec.get("fit_rationale", "") or "").strip()}
        extras = {k: rec.get(k) for k in ("new_rank", "tags")
                  if str(rec.get(k, "") or "").strip()}
        if extras:
            update["extras"] = json.dumps(extras)
        updates.append(update)

    res.updated = apply(updates, source="file_import") if updates else 0
    return res
```

- [ ] **Step 4: Run** `py -m pytest tests/rerank/test_import.py -v` → PASS.
- [ ] **Step 5: Commit** (no-op marker) — message: `feat(rerank): tolerant CSV/JSON import — job_key join, clamp, BOM/locale, merge policies`

### Task 4 — Characterize the existing ranker routes BEFORE refactor

**Files:** Create `tests/rerank/test_ranker_characterization.py`

**Interfaces — Consumes:** existing `ranker.build_request`, `ranker.parse_response`, `ranker.gate`, `ranker.build_profile`, `ranker.rank_via_api`. Produces no code — this is the safety net pinned before Task 5 touches `ranker.py` (spec R2).

- [ ] **Step 1: Write the characterization test** `tests/rerank/test_ranker_characterization.py` (these MUST pass against the CURRENT, unmodified `ranker.py`):

```python
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
        Anthropic=lambda api_key=None: types.SimpleNamespace(
            messages=types.SimpleNamespace(create=fake_create)))
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic)
    monkeypatch.setattr(ranker, "api_key", lambda: "sk-test")
    out = ranker.rank_via_api(jobs, prefs={"profile_md": "controls", "hard": {}},
                              experience_summary="C++")
    assert out[0][1] == 88
    assert "controls" in captured["messages"][0]["content"]
```

- [ ] **Step 2: Run** `py -m pytest tests/rerank/test_ranker_characterization.py -v` → **PASS NOW** (against the unmodified module). If any fails, STOP — the characterization baseline is wrong; fix the test to match current behavior, do not change `ranker.py`.
- [ ] **Step 3: Commit** (no-op marker) — message: `test(rerank): characterize bridge/API ranker routes before protocol extraction`

### Task 5 — `ranker.py` — add `Ranker` Protocol + Bridge/Api/FileRanker (no behavior change)

**Files:** Modify `ranker.py`; Test `tests/rerank/test_ranker_protocol.py`

**Interfaces — Produces:** `Ranker` Protocol, `BridgeRanker`, `ApiRanker`, `FileRanker`. **Consumes:** existing module fns (unchanged), `rerank.export.export_inbox`, `rerank.import_.import_scores`. The existing module-level functions (`build_request`, `parse_response`, `gate`, `rank_via_api`, ...) stay exactly as-is; the classes are thin wrappers over them, so the characterization tests (Task 4) keep passing.

- [ ] **Step 1: Write the failing test** `tests/rerank/test_ranker_protocol.py`:

```python
import ranker
import models


def _job(title="Controls Engineer", url="https://x.co/1"):
    return models.JobResult(title=title, company="Acme", location="Cincinnati, OH",
                            salary_min=100000, salary_max=None, description="C++",
                            url=url, source_keyword="", created="", source_api="t")


def test_bridge_ranker_delegates_to_module_fns():
    r = ranker.BridgeRanker()
    prefs = {"profile_md": "controls roles", "hard": {}}
    assert r.build_request([_job()], prefs=prefs, experience_summary="C++") == \
        ranker.build_request([_job()], prefs=prefs, experience_summary="C++")


def test_api_ranker_build_request_matches_bridge():
    prefs = {"profile_md": "controls roles", "hard": {}}
    a, b = ranker.ApiRanker(), ranker.BridgeRanker()
    assert a.build_request([_job()], prefs=prefs) == b.build_request([_job()], prefs=prefs)


def test_all_rankers_satisfy_protocol():
    for r in (ranker.BridgeRanker(), ranker.ApiRanker(), ranker.FileRanker()):
        assert isinstance(r, ranker.Ranker)        # runtime_checkable Protocol


def test_file_ranker_build_request_is_export_prompt(monkeypatch):
    import preferences
    monkeypatch.setattr(preferences, "load", lambda: {"profile_md": "controls roles", "hard": {}})
    from rerank import schema
    fr = ranker.FileRanker()
    # FileRanker.build_request renders the versioned export prompt (job_key/new_fit present)
    req = fr.build_request([_job()])
    assert "job_key" in req and "new_fit" in req


def test_file_ranker_export_and_import_roundtrip(tmp_path):
    fr = ranker.FileRanker()
    rows = [{"id": 1, "title": "Software Developer", "company": "Acme",
             "location": "Cincinnati, OH", "salary_text": "$120k", "url": "https://x/1",
             "score": 70, "fit": -1, "description": "controls"}]
    paths = fr.export(rows, tmp_path)
    assert paths["csv"].exists()
    # build a returned CSV that fills new_fit for the exported job_key
    import csv
    with paths["csv"].open(encoding="utf-8-sig", newline="") as f:
        key = next(csv.DictReader(f))["job_key"]
    ret = tmp_path / "ret.csv"
    ret.write_text(f"job_key,new_fit\n{key},91\n", encoding="utf-8")
    captured = {}
    res = fr.import_(ret, {key: {"id": 1, "fit": -1}},
                     _apply=lambda u, *, source="file_import": captured.setdefault("u", u) or len(u))
    assert res.updated == 1 and captured["u"][0]["new_fit"] == 91
```

- [ ] **Step 2: Run to fail** → FAIL (`BridgeRanker`/`ApiRanker`/`FileRanker`/`Ranker` missing).

- [ ] **Step 3: Implement** — append to `ranker.py` (do NOT alter the existing functions above; only ADD below them). First add `import typing` at the top of the file alongside the existing `import config` line. Then append:

```python
# ── Ranker protocol (WS-3) ────────────────────────────────────────────────────
# The three routes (bridge / API / file) share one shape so callers can pick a
# route without forking logic. The classes are thin wrappers over the module
# functions above — no behavior change (characterization-tested first).


@typing.runtime_checkable
class Ranker(typing.Protocol):
    """A ranking route: build one prompt, parse one reply into
    [(job, fit_score, rationale)]."""

    def build_request(self, jobs, prefs=None, experience_summary=None) -> str: ...

    def parse_response(self, text: str, jobs) -> list: ...


class BridgeRanker:
    """Clipboard bridge route: build_request -> user pastes into claude.ai ->
    pastes the reply back -> parse_response. Delegates to the module functions."""

    def build_request(self, jobs, prefs=None, experience_summary=None) -> str:
        return build_request(jobs, prefs, experience_summary)

    def parse_response(self, text: str, jobs) -> list:
        return parse_response(text, jobs)


class ApiRanker:
    """Auto API route: same prompt + parser as the bridge, executed via the
    Anthropic API (when a key is configured)."""

    def build_request(self, jobs, prefs=None, experience_summary=None) -> str:
        return build_request(jobs, prefs, experience_summary)

    def parse_response(self, text: str, jobs) -> list:
        return parse_response(text, jobs)

    def rank(self, jobs, prefs=None, experience_summary=None, model=None) -> list:
        return rank_via_api(jobs, prefs, experience_summary, model)


class FileRanker:
    """File round-trip route: export the inbox to a CSV/MD/prompt trio, the user
    hands it to any AI, then import the returned CSV/JSON. build_request renders
    the versioned export prompt so this route gives identical guidance."""

    def build_request(self, jobs, prefs=None, experience_summary=None) -> str:
        from rerank import schema
        if prefs is not None and prefs.get("profile_md") is not None:
            profile = prefs.get("profile_md") or ""
        else:
            import preferences as _prefs_mod
            profile = (_prefs_mod.load() or {}).get("profile_md", "") or ""
        return schema.build_prompt(profile)

    def parse_response(self, text: str, jobs) -> list:
        # The file route resolves scores by job_key via import_scores, not by the
        # bridge token; parse_response is unused for files. Kept for the Protocol.
        raise NotImplementedError(
            "FileRanker scores are applied by import_(); use export()/import_().")

    def export(self, rows, out_dir, *, fmt: str = "both") -> dict:
        from rerank.export import export_inbox
        return export_inbox(rows, out_dir, fmt=fmt)

    def import_(self, path, rows_by_key, *, policy: str = "overwrite", _apply=None):
        from rerank.import_ import import_scores
        return import_scores(path, rows_by_key, policy=policy, _apply=_apply)
```

- [ ] **Step 4: Run** `py -m pytest tests/rerank/test_ranker_protocol.py tests/rerank/test_ranker_characterization.py tests/test_ranker.py -v` → ALL PASS (protocol added AND existing behavior intact).
- [ ] **Step 5: Commit** (no-op marker) — message: `feat(ranker): Ranker protocol + Bridge/Api/FileRanker wrappers (no behavior change)`

### Task 6 — `tracker/db.py` — schema v3 (score_history + inbox.extras), history-on-set-fit, undo

**Files:** Modify `tracker/db.py`; Create `tests/fixtures/rerank/v2_populated.sql`, `tests/rerank/test_db_migration_v3.py`

**Interfaces — Produces:** `inbox_set_fit(inbox_id, fit, why, source="manual")` (history-writing), `inbox_set_extras`, `inbox_undo_last_rerank(scope) -> int`, schema v3. **Consumes:** the join key via the row's stored fields — `getattr(JobResult, "job_key", None) or JobResult.identity_key` (the history-write computes a key for each `score_history` row from the inbox row's title/company/location/url; `job_key` does not exist on `models.py` yet, so this falls back to `identity_key` until WS-1 lands).

- [ ] **Step 1: Create the populated v2 fixture** `tests/fixtures/rerank/v2_populated.sql` (a minimal v2 schema with one inbox row + `user_version=2`, so the test can prove a v2→v3 migration preserves data):

```sql
PRAGMA user_version = 2;
CREATE TABLE applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL, company TEXT NOT NULL, location TEXT DEFAULT '',
    url TEXT DEFAULT '', salary_text TEXT DEFAULT '', source TEXT DEFAULT 'manual',
    status TEXT DEFAULT 'interested', date_added TEXT NOT NULL,
    date_applied TEXT DEFAULT '', notes TEXT DEFAULT ''
);
CREATE TABLE inbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    norm_url TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL, company TEXT NOT NULL, location TEXT DEFAULT '',
    url TEXT DEFAULT '', salary_text TEXT DEFAULT '', description TEXT DEFAULT '',
    source TEXT DEFAULT '', score INTEGER DEFAULT -1, score_notes TEXT DEFAULT '',
    fit INTEGER DEFAULT -1, fit_why TEXT DEFAULT '', created TEXT DEFAULT '',
    date_added TEXT NOT NULL, board_count INTEGER DEFAULT -1
);
INSERT INTO inbox (norm_url, title, company, location, url, salary_text,
    description, source, score, fit, created, date_added)
VALUES ('x.co/1', 'Software Developer', 'Acme', 'Cincinnati, OH',
    'https://x.co/1', '$120k', 'controls', 'adzuna', 70, -1,
    '2026-06-20', '2026-06-20');
```

- [ ] **Step 2: Write the failing test** `tests/rerank/test_db_migration_v3.py`:

```python
import sqlite3
import pytest
from pathlib import Path

import tracker.db as db

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "rerank" / "v2_populated.sql"


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    return db.DB_PATH


@pytest.fixture
def v2_db(tmp_db):
    conn = sqlite3.connect(str(tmp_db))
    conn.executescript(FIXTURE.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    return tmp_db


def test_schema_version_is_three():
    assert db.SCHEMA_VERSION == 3


def test_v2_to_v3_migrates_and_preserves_rows(v2_db):
    assert db.init_db() is True               # migration ran
    with db.get_conn() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(inbox)")}
        assert "extras" in cols
        tables = {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "score_history" in tables
        row = conn.execute("SELECT title FROM inbox WHERE id=1").fetchone()
        assert row["title"] == "Software Developer"      # data survived


def test_migration_backs_up_db(v2_db, tmp_path):
    db.init_db()
    backups = list(tmp_path.glob("tracker.db.bak-v*"))
    assert backups, "expected a pre-migration backup"


def test_init_db_idempotent_at_v3(tmp_db):
    assert db.init_db() is True
    assert db.init_db() is False              # fast path at v3


def test_inbox_set_fit_writes_history_before_update(tmp_db):
    db.init_db()
    iid = db.inbox_add_many([_inbox_job()])  # see helper below
    rows = db.inbox_all()
    inbox_id = rows[0]["id"]
    db.inbox_set_fit(inbox_id, 88, "great", source="file_import")
    with db.get_conn() as conn:
        h = conn.execute(
            "SELECT old_fit, new_fit, source FROM score_history WHERE inbox_id=?",
            (inbox_id,)).fetchone()
        cur = conn.execute("SELECT fit FROM inbox WHERE id=?", (inbox_id,)).fetchone()
    assert h["old_fit"] == -1 and h["new_fit"] == 88 and h["source"] == "file_import"
    assert cur["fit"] == 88


def test_undo_last_rerank_reverts(tmp_db):
    db.init_db()
    db.inbox_add_many([_inbox_job()])
    inbox_id = db.inbox_all()[0]["id"]
    db.inbox_set_fit(inbox_id, 88, "great", source="file_import")
    restored = db.inbox_undo_last_rerank("file_import")
    assert restored == 1
    with db.get_conn() as conn:
        assert conn.execute("SELECT fit FROM inbox WHERE id=?",
                            (inbox_id,)).fetchone()["fit"] == -1


def _inbox_job():
    from models import JobResult
    return JobResult(title="Controls Engineer", company="Beta",
                     location="Cincinnati, OH", salary_min=None, salary_max=None,
                     description="plc", url="https://x.co/9", source_keyword="",
                     created="2026-06-21", source_api="adzuna", score=60)
```

- [ ] **Step 3: Run to fail** → FAIL (`SCHEMA_VERSION` still 2; no `score_history`; `inbox_set_fit` has no `source`/history; no `inbox_undo_last_rerank`).

- [ ] **Step 4: Implement** in `tracker/db.py`:

  4a. Bump the constant. Replace:

  ```python
  SCHEMA_VERSION = 2
  ```

  with:

  ```python
  SCHEMA_VERSION = 3
  ```

  4b. Add a backup + the new schema objects inside `init_db()`. In the migration branch (after `if conn.execute("PRAGMA user_version")... == SCHEMA_VERSION: return False`), **before** the `CREATE TABLE IF NOT EXISTS applications` statement, insert a backup of the existing DB when it is below v3:

  ```python
        old_version = conn.execute("PRAGMA user_version").fetchone()[0]
        if old_version and old_version < SCHEMA_VERSION:
            import shutil
            src = current_db_path()
            try:
                shutil.copy2(str(src), str(src) + f".bak-v{old_version}")
            except OSError:
                pass  # backup is best-effort; never block the migration
  ```

  Then, just before the existing `conn.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)` line, add the v3 objects (the `inbox.extras` column via the same probe-and-ALTER pattern already used for `board_count`, and the `score_history` table):

  ```python
        # v3 (WS-3): round-trip extras blob + score-change audit/undo log.
        inbox_existing_v3 = {r["name"] for r in conn.execute("PRAGMA table_info(inbox)")}
        if "extras" not in inbox_existing_v3:
            conn.execute("ALTER TABLE inbox ADD COLUMN extras TEXT DEFAULT ''")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS score_history (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                inbox_id  INTEGER NOT NULL,
                job_key   TEXT DEFAULT '',
                old_fit   INTEGER,
                new_fit   INTEGER,
                old_score INTEGER,
                source    TEXT DEFAULT '',
                ts        TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_score_history_inbox "
                     "ON score_history(inbox_id)")
  ```

  Note: the existing `board_count` ALTER block already extends `inbox`; the new `extras` ALTER must run on every migration to v3, so it lives in its own probe (above) rather than the v2 block.

  4c. Replace the existing `inbox_set_fit` with the history-writing version:

  ```python
  def inbox_set_fit(inbox_id: int, fit: int, why: str, source: str = "manual"):
      """Set an inbox row's fit + why. Snapshots the prior fit/score to
      score_history BEFORE the UPDATE (mirrors the status_history precedent), so
      a re-rank can be undone and before/after diffed. `source` tags the change
      ('manual', 'file_import', ...)."""
      from datetime import datetime, timezone
      def _job_key_of(row) -> str:
          try:
              from models import JobResult
              j = JobResult(title=row["title"], company=row["company"],
                            location=row["location"], salary_min=None, salary_max=None,
                            description="", url=row["url"] or "", source_keyword="",
                            created="", source_api=row["source"] or "")
              # job_key when WS-1 has landed it; else the existing identity_key.
              # Never AttributeError on today's models.py (job_key not present yet).
              return getattr(j, "job_key", None) or j.identity_key
          except Exception:
              return ""
      with get_conn() as conn:
          row = conn.execute(
              "SELECT title, company, location, url, source, fit, score "
              "FROM inbox WHERE id=?", (inbox_id,)).fetchone()
          if row is not None:
              conn.execute(
                  "INSERT INTO score_history "
                  "(inbox_id, job_key, old_fit, new_fit, old_score, source, ts) "
                  "VALUES (?,?,?,?,?,?,?)",
                  (inbox_id, _job_key_of(row), row["fit"], fit, row["score"],
                   source, datetime.now(timezone.utc).isoformat()))
          conn.execute("UPDATE inbox SET fit=?, fit_why=? WHERE id=?",
                       (fit, why, inbox_id))
          conn.commit()


  def inbox_set_extras(inbox_id: int, extras: str):
      """Write the round-trip extras JSON blob (new_rank/tags/...) onto an inbox
      row. No history row (extras are additive context, not a scored change)."""
      with get_conn() as conn:
          conn.execute("UPDATE inbox SET extras=? WHERE id=?", (extras or "", inbox_id))
          conn.commit()


  def inbox_undo_last_rerank(scope: str) -> int:
      """Revert the most recent re-rank batch: restore each inbox row's fit to the
      old_fit recorded in the newest score_history timestamp group for `scope`
      ('any' = ignore source). Deletes the reverted history rows. Returns rows
      restored."""
      with get_conn() as conn:
          if scope == "any":
              row = conn.execute("SELECT MAX(ts) AS ts FROM score_history").fetchone()
          else:
              row = conn.execute(
                  "SELECT MAX(ts) AS ts FROM score_history WHERE source=?",
                  (scope,)).fetchone()
          last_ts = row["ts"] if row else None
          if not last_ts:
              return 0
          if scope == "any":
              hist = conn.execute(
                  "SELECT id, inbox_id, old_fit FROM score_history WHERE ts=?",
                  (last_ts,)).fetchall()
          else:
              hist = conn.execute(
                  "SELECT id, inbox_id, old_fit FROM score_history "
                  "WHERE ts=? AND source=?", (last_ts, scope)).fetchall()
          restored = 0
          for h in hist:
              conn.execute("UPDATE inbox SET fit=? WHERE id=?",
                           (h["old_fit"], h["inbox_id"]))
              conn.execute("DELETE FROM score_history WHERE id=?", (h["id"],))
              restored += 1
          conn.commit()
          return restored
  ```

- [ ] **Step 5: Run** `py -m pytest tests/rerank/test_db_migration_v3.py tests/test_tracker_db.py tests/test_status_history.py -v` → ALL PASS (v3 migration works AND existing tracker/db + status-history tests still green). Note: the existing `tests/test_tracker_db.py::test_init_db_gated_on_user_version` asserts `init_db()` returns True then False — with `SCHEMA_VERSION` now 3 it still holds (fresh DB starts at user_version 0).
- [ ] **Step 6: Commit** (no-op marker) — message: `feat(tracker): schema v3 — score_history + inbox.extras; history-on-set-fit; undo; pre-migrate backup`

### Task 7 — `tracker/service.py` — join map + apply-rerank + undo verbs

**Files:** Modify `tracker/service.py`; Test `tests/rerank/test_service_rerank.py`

**Interfaces — Produces:** `inbox_rows_by_key() -> dict`, `apply_rerank_scores(updates, *, source="file_import") -> int`, `undo_last_rerank(scope="file_import") -> int`. **Consumes:** `db.inbox_all`, `db.inbox_set_fit`, `db.inbox_set_extras`, `db.inbox_undo_last_rerank`, `rerank.schema._job_key_for_row`.

- [ ] **Step 1: Write the failing test** `tests/rerank/test_service_rerank.py`:

```python
import pytest
import tracker.db as db
from tracker import service
from models import JobResult


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    return db.DB_PATH


def _job(url, title="Software Developer", company="Acme"):
    return JobResult(title=title, company=company, location="Cincinnati, OH",
                     salary_min=None, salary_max=None, description="controls",
                     url=url, source_keyword="", created="2026-06-21",
                     source_api="adzuna", score=70)


def test_inbox_rows_by_key_keys_by_job_key(tmp_db):
    db.inbox_add_many([_job("https://x.co/1")])
    m = service.inbox_rows_by_key()
    assert len(m) == 1
    (key, row), = m.items()
    assert key and "id" in row and "fit" in row


def test_apply_rerank_scores_writes_fit_and_history(tmp_db):
    db.inbox_add_many([_job("https://x.co/1")])
    iid = db.inbox_all()[0]["id"]
    n = service.apply_rerank_scores(
        [{"id": iid, "new_fit": 91, "fit_rationale": "strong"}], source="file_import")
    assert n == 1
    row = db.inbox_all()[0]
    assert row["fit"] == 91 and row["fit_why"] == "strong"
    with db.get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM score_history WHERE source='file_import'"
                            ).fetchone()[0] == 1


def test_apply_rerank_scores_persists_extras(tmp_db):
    db.inbox_add_many([_job("https://x.co/1")])
    iid = db.inbox_all()[0]["id"]
    service.apply_rerank_scores(
        [{"id": iid, "new_fit": 80, "fit_rationale": "ok", "extras": '{"tags":"plc"}'}])
    with db.get_conn() as conn:
        assert conn.execute("SELECT extras FROM inbox WHERE id=?",
                            (iid,)).fetchone()["extras"] == '{"tags":"plc"}'


def test_undo_last_rerank_reverts(tmp_db):
    db.inbox_add_many([_job("https://x.co/1")])
    iid = db.inbox_all()[0]["id"]
    service.apply_rerank_scores([{"id": iid, "new_fit": 91, "fit_rationale": "x"}])
    assert service.undo_last_rerank("file_import") == 1
    assert db.inbox_all()[0]["fit"] == -1
```

- [ ] **Step 2: Run to fail** → FAIL.

- [ ] **Step 3: Implement** — append to `tracker/service.py` (after the existing `set_inbox_fit` function, inside the inbox-triage section):

```python
# ── Re-rank round-trip (WS-3) ─────────────────────────────────────────────────

def inbox_rows_by_key() -> dict:
    """{job_key -> inbox-row dict} for the file round-trip join. The key is the
    WS-1 cross-source identity when present, else JobResult.identity_key (the
    _job_key_for_row helper does `getattr(j, "job_key", None) or j.identity_key`,
    so this works before OR after WS-1 lands). On a key collision the first row
    wins (round-robin order is stable)."""
    from rerank.schema import _job_key_for_row
    out: dict = {}
    for r in db.inbox_all():
        key = _job_key_for_row(r)
        out.setdefault(key, r)
    return out


def apply_rerank_scores(updates: list[dict], *, source: str = "file_import") -> int:
    """Write imported re-rank scores back to the inbox: new_fit -> fit,
    fit_rationale -> fit_why (via inbox_set_fit, which snapshots score_history),
    and the optional extras JSON blob -> inbox.extras. Returns rows updated."""
    applied = 0
    for u in updates:
        try:
            inbox_id = int(u["id"])
            fit = max(0, min(100, int(u["new_fit"])))
        except (KeyError, TypeError, ValueError):
            continue
        db.inbox_set_fit(inbox_id, fit, str(u.get("fit_rationale", "") or ""),
                         source=source)
        extras = u.get("extras")
        if extras:
            db.inbox_set_extras(inbox_id, str(extras))
        applied += 1
    return applied


def undo_last_rerank(scope: str = "file_import") -> int:
    """Revert the most recent re-rank batch (by source scope). Returns rows
    restored. scope='any' ignores the source tag."""
    return db.inbox_undo_last_rerank(scope)
```

- [ ] **Step 4: Run** `py -m pytest tests/rerank/test_service_rerank.py tests/test_tracker_service.py -v` → ALL PASS.
- [ ] **Step 5: Commit** (no-op marker) — message: `feat(tracker): service verbs — inbox_rows_by_key, apply_rerank_scores, undo_last_rerank`

### Task 8 — End-to-end round-trip test (export → simulate AI → import → re-rank)

**Files:** Create `tests/rerank/test_roundtrip.py`

**Interfaces — Consumes:** the full `export_inbox` → `import_scores` → `apply_rerank_scores` → inbox path on a real temp DB (spec §8 round-trip property test). Produces no code.

- [ ] **Step 1: Write the test** `tests/rerank/test_roundtrip.py`:

```python
import csv
import json
import pytest

import tracker.db as db
from tracker import service
from rerank.export import export_inbox
from rerank.import_ import import_scores
from models import JobResult


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    return db.DB_PATH


def _seed():
    db.inbox_add_many([
        JobResult(title="Software Developer", company="Acme", location="Cincinnati, OH",
                  salary_min=None, salary_max=None, description="controls",
                  url="https://x.co/1", source_keyword="", created="2026-06-21",
                  source_api="adzuna", score=70),
        JobResult(title="Controls Engineer", company="Beta", location="Cincinnati, OH",
                  salary_min=None, salary_max=None, description="plc", url="https://x.co/2",
                  source_keyword="", created="2026-06-21", source_api="themuse", score=55),
    ])


def _fill_csv(export_csv, returned_csv, scores: dict):
    """Read the exported CSV, fill new_fit per job_key from `scores`, write a
    returned CSV — simulates the user's AI filling in the carrier."""
    with export_csv.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    with returned_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["job_key", "new_fit", "fit_rationale"])
        w.writeheader()
        for r in rows:
            w.writerow({"job_key": r["job_key"],
                        "new_fit": scores.get(r["job_key"], ""),
                        "fit_rationale": "scored by AI"})


def test_csv_roundtrip_reranks_inbox(tmp_db, tmp_path):
    _seed()
    rows = db.inbox_all()
    paths = export_inbox(rows, tmp_path / "out", fmt="both")
    keys = [r["job_key"] for r in (
        __import__("rerank.schema", fromlist=["row_from_inbox"]).row_from_inbox(x)
        for x in rows)]
    scores = {keys[0]: 95, keys[1]: 40}
    ret = tmp_path / "returned.csv"
    _fill_csv(paths["csv"], ret, scores)
    res = import_scores(ret, service.inbox_rows_by_key(), policy="overwrite")
    assert res.matched == 2 and res.updated == 2 and res.unmatched == []
    by_title = {r["title"]: r["fit"] for r in db.inbox_all()}
    assert by_title["Software Developer"] == 95
    assert by_title["Controls Engineer"] == 40


def test_json_roundtrip_reranks_inbox(tmp_db, tmp_path):
    _seed()
    keys = list(service.inbox_rows_by_key().keys())
    ret = tmp_path / "returned.json"
    ret.write_text(json.dumps([{"job_key": keys[0], "new_fit": 88,
                                "fit_rationale": "great"}]), encoding="utf-8")
    res = import_scores(ret, service.inbox_rows_by_key())
    assert res.updated == 1


def test_double_import_is_idempotent_on_fit(tmp_db, tmp_path):
    _seed()
    keys = list(service.inbox_rows_by_key().keys())
    ret = tmp_path / "r.csv"
    ret.write_text(f"job_key,new_fit\n{keys[0]},77\n", encoding="utf-8")
    import_scores(ret, service.inbox_rows_by_key())
    import_scores(ret, service.inbox_rows_by_key())  # re-import same file
    fits = {r["job_key"]: r["fit"] for r in
            (dict(rr, job_key=k) for k, rr in service.inbox_rows_by_key().items())}
    # fit is the same value after the second import (idempotent beyond a history row)
    target_row = service.inbox_rows_by_key()[keys[0]]
    assert target_row["fit"] == 77
    with db.get_conn() as conn:
        # two history rows (one per import) prove the audit log grew, fit unchanged
        assert conn.execute("SELECT COUNT(*) FROM score_history").fetchone()[0] == 2


def test_undo_after_import_reverts(tmp_db, tmp_path):
    _seed()
    keys = list(service.inbox_rows_by_key().keys())
    ret = tmp_path / "r.csv"
    ret.write_text(f"job_key,new_fit\n{keys[0]},77\n{keys[1]},66\n", encoding="utf-8")
    import_scores(ret, service.inbox_rows_by_key())
    assert service.undo_last_rerank("file_import") == 2
    assert all(r["fit"] == -1 for r in db.inbox_all())
```

- [ ] **Step 2: Run** `py -m pytest tests/rerank/test_roundtrip.py -v` → PASS.
- [ ] **Step 3: Commit** (no-op marker) — message: `test(rerank): end-to-end CSV/JSON round-trip, idempotency, and undo on a temp DB`

### Task 9 — MCP bulk tools (`mcp_server.py`) — `export_inbox` / `import_scores`

**Files:** Modify `mcp_server.py`; Test `tests/rerank/test_mcp_rerank.py`

**Interfaces — Produces:** `@mcp.tool() export_inbox(out_dir, fmt="both")`, `@mcp.tool() import_scores(path, policy="overwrite")`. **Consumes:** `rerank.export.export_inbox`, `rerank.import_.import_scores`, `tracker.service.inbox_rows_by_key`, `db.inbox_all`.

- [ ] **Step 1: Write the failing test** `tests/rerank/test_mcp_rerank.py`:

```python
import pytest
pytest.importorskip("mcp")

import mcp_server


def test_rerank_tools_exist():
    for name in ("export_inbox", "import_scores"):
        assert callable(getattr(mcp_server, name))


def test_export_inbox_tool_writes_trio(tmp_path, monkeypatch):
    rows = [{"id": 1, "title": "Software Developer", "company": "Acme",
             "location": "Cincinnati, OH", "salary_text": "$120k", "url": "https://x/1",
             "score": 70, "fit": -1, "description": "controls"}]
    monkeypatch.setattr(mcp_server.db, "inbox_all", lambda: rows)
    import preferences
    monkeypatch.setattr(preferences, "load", lambda: {"profile_md": "controls", "hard": {}})
    out = mcp_server.export_inbox(str(tmp_path), fmt="both")
    assert (tmp_path / "ranking_export.csv").exists()
    assert out["csv"].endswith("ranking_export.csv")
    assert "prompt" in out


def test_import_scores_tool_returns_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_server.service, "inbox_rows_by_key",
                        lambda: {"k1": {"id": 1, "fit": -1}})
    applied = {}
    monkeypatch.setattr(mcp_server.service, "apply_rerank_scores",
                        lambda updates, *, source="file_import": applied.update(
                            {"u": updates}) or len(updates))
    p = tmp_path / "ret.csv"
    p.write_text("job_key,new_fit\nk1,84\n", encoding="utf-8")
    out = mcp_server.import_scores(str(p), policy="overwrite")
    assert out["updated"] == 1 and out["matched"] == 1 and out["unmatched"] == []
    assert applied["u"][0]["new_fit"] == 84
```

- [ ] **Step 2: Run to fail** → FAIL.

- [ ] **Step 3: Implement** in `mcp_server.py`:

  3a. Add the service import near the existing imports (after `from tracker import db`):

  ```python
  from tracker import service
  ```

  3b. Add the two tools (after the existing `dismiss_job` tool, before `def main()`):

  ```python
  @mcp.tool()
  def export_inbox(out_dir: str, fmt: str = "both") -> dict:
      """Export the current inbox as the round-trip trio (ranking_export.csv +
      ranking_export.md + a versioned prompt.md) under out_dir, each row keyed by
      the stable job_key. Hand the CSV + prompt to any AI; it fills new_fit/
      new_rank/fit_rationale and you call import_scores with the returned file.
      fmt in {"both","csv","md"}. Returns the written paths as strings."""
      from rerank.export import export_inbox as _export
      paths = _export(db.inbox_all(), out_dir, fmt=fmt)
      return {k: str(v) for k, v in paths.items()}

  @mcp.tool()
  def import_scores(path: str, policy: str = "overwrite") -> dict:
      """Import an AI-returned re-rank file (CSV or JSON) and re-rank the inbox.
      Validates the job_key join (unmatched rows are reported, never dropped),
      clamps new_fit to 0-100, snapshots prior scores to score_history (undoable),
      and applies the merge policy. policy in {"overwrite","keep_existing",
      "add_only"}. Returns {matched, updated, skipped, unmatched, errors}."""
      from rerank.import_ import import_scores as _import
      res = _import(path, service.inbox_rows_by_key(), policy=policy)
      return {"matched": res.matched, "updated": res.updated,
              "skipped": res.skipped, "unmatched": res.unmatched,
              "errors": res.errors}
  ```

- [ ] **Step 4: Run** `py -m pytest tests/rerank/test_mcp_rerank.py tests/test_mcp_server.py -v` → ALL PASS (new tools work AND the existing MCP tests still green).
- [ ] **Step 5: Commit** (no-op marker) — message: `feat(mcp): export_inbox / import_scores bulk round-trip tools`

### Task 10 — GUI InboxTab controls (Export for AI / Import scores / Undo last re-rank)

**Files:** Modify `gui.py` (`InboxTab`)

**Interfaces — Consumes:** `rerank.export.export_inbox`, `rerank.import_.import_scores`, `tracker.service.inbox_rows_by_key`, `tracker.service.undo_last_rerank`. No new test file (the GUI tkinter layer is not unit-tested in this suite — `tests/` has no GUI test module; the logic these buttons call is fully covered by Tasks 2, 3, 7, 8). This task wires the buttons to the already-tested service/rerank functions.

- [ ] **Step 1:** Add imports near the top of `gui.py`, alongside the existing `from tkinter import ttk, messagebox, simpledialog`:

  ```python
  from tkinter import filedialog
  ```

  and after the existing `from config import DEFAULT_LOCATION`:

  ```python
  from config import OUTPUT_DIR
  ```

- [ ] **Step 2:** In `InboxTab._build`, in the `abar` button bar (after the existing "Paste Fit Results" button block, before `self._status = tk.Label(...)`), add the three controls:

  ```python
          tk.Button(abar, text="Export for AI", bg="#2d4a2d", fg=WHITE,
                    font=("Segoe UI", 9), relief="flat", padx=10, pady=3,
                    command=self._export_for_ai).pack(side="left", padx=(16, 2))
          tk.Button(abar, text="Import scores", bg="#2d4a2d", fg=WHITE,
                    font=("Segoe UI", 9), relief="flat", padx=10, pady=3,
                    command=self._import_scores).pack(side="left", padx=2)
          self._merge_policy = tk.StringVar(value="overwrite")
          ttk.Combobox(abar, textvariable=self._merge_policy, state="readonly",
                       width=13, values=["overwrite", "keep_existing", "add_only"]
                       ).pack(side="left", padx=2)
          tk.Button(abar, text="Undo last re-rank", bg=WHITE, fg="#555",
                    font=("Segoe UI", 9), relief="flat", padx=10, pady=3,
                    command=self._undo_rerank).pack(side="left", padx=2)
  ```

- [ ] **Step 3:** Add the three handler methods to `InboxTab` (place them after the existing `_paste_fit` method; if the exact insertion point is unclear, add them immediately before `def refresh(self):`). They reuse the already-tested `rerank`/`service` functions:

  ```python
      def _export_for_ai(self):
          """Write the round-trip trio (csv+md+prompt) for the current inbox to a
          timestamped folder under OUTPUT_DIR/rerank, then open the folder."""
          from datetime import datetime
          from rerank.export import export_inbox
          rows = list(self._all)
          if not rows:
              messagebox.showinfo("Nothing to export", "The inbox is empty.")
              return
          stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
          out_dir = Path(OUTPUT_DIR) / "rerank" / stamp
          try:
              paths = export_inbox(rows, out_dir, fmt="both")
          except Exception as e:
              messagebox.showerror("Export failed", str(e))
              return
          set_status(self._status,
                     f"Exported {len(rows)} rows -> {out_dir}", "info")
          try:
              subprocess.Popen(["explorer", str(out_dir)])
          except Exception:
              pass

      def _import_scores(self):
          """Pick an AI-returned CSV/JSON, show a dry-run preview of matched/
          unmatched, and on confirm apply with the selected merge policy."""
          from rerank.import_ import import_scores
          path = filedialog.askopenfilename(
              title="Import AI scores",
              filetypes=[("CSV or JSON", "*.csv *.json"), ("All files", "*.*")])
          if not path:
              return
          policy = self._merge_policy.get()
          rows_by_key = tracker_service.inbox_rows_by_key()
          # Dry-run preview: a no-op apply so nothing is written yet.
          preview = import_scores(path, rows_by_key, policy=policy,
                                  _apply=lambda u, *, source="file_import": len(u))
          msg = (f"Matched {preview.matched}, would update {preview.updated}, "
                 f"skip {preview.skipped}, unmatched {len(preview.unmatched)}.\n"
                 f"Policy: {policy}. Apply now?")
          if preview.errors:
              msg += f"\n{len(preview.errors)} row error(s) will be skipped."
          if not messagebox.askyesno("Import preview", msg, parent=self):
              return
          res = import_scores(path, rows_by_key, policy=policy)  # real apply
          set_status(self._status,
                     f"Re-ranked {res.updated} (skipped {res.skipped}, "
                     f"unmatched {len(res.unmatched)}).", "info")
          self.refresh()

      def _undo_rerank(self):
          """Revert the most recent file-import re-rank batch via score_history."""
          n = tracker_service.undo_last_rerank("file_import")
          set_status(self._status,
                     f"Undid last re-rank: restored {n} row(s)." if n else
                     "No re-rank to undo.", "muted" if n else "info")
          self.refresh()
  ```

  Note: `set_status`, `Path`, `subprocess`, `messagebox`, `tracker_service`, `OUTPUT_DIR`, and `filedialog` are all in scope (the first three already imported/used in `gui.py`; the latter three added in Steps 1–2).

- [ ] **Step 4: Verify the module still imports** (no GUI test exists; prove the edit didn't break import and the new methods are present). Run:
  ```bash
  py -c "import ast,sys; src=open('gui.py',encoding='utf-8').read(); ast.parse(src); assert '_export_for_ai' in src and '_import_scores' in src and '_undo_rerank' in src; print('gui.py parses + handlers present')"
  ```
  Expected output: `gui.py parses + handlers present`. (Importing `gui` directly would require a display; the AST/parse check is the headless-safe gate.)
- [ ] **Step 5: Commit** (no-op marker) — message: `feat(gui): InboxTab Export for AI / Import scores (preview + merge policy) / Undo last re-rank`

### Task 11 — Full-suite green gate

**Files:** none (verification task)

- [ ] **Step 1: Run the rerank unit suite** `py -m pytest tests/rerank -q` → all green.
- [ ] **Step 2: Run the full suite** `py -m pytest -q` → all green (including the ranker-refactor characterization tests from Task 4, the v2→v3 DB migration from Task 6, and the pre-existing `tests/test_ranker.py`, `tests/test_tracker_db.py`, `tests/test_tracker_service.py`, `tests/test_mcp_server.py`, `tests/test_status_history.py`, `tests/test_csv_injection.py`).
- [ ] **Step 3:** If any pre-existing test regressed, the refactor changed behavior — STOP and fix the implementation (NOT the pre-existing test) until the suite is green. The characterization tests (Task 4) are the contract; the existing route functions must remain output-identical.
- [ ] **Step 4: Commit** (no-op marker) — message: `test(rerank): full-suite green gate for WS-3 round-trip`

---

## Self-Review

- **Spec coverage:** dual-format export trio keyed by `job_key` (Tasks 1–2) ✓; tolerant CSV/JSON import with BOM/locale/clamp + `job_key` join + merge policies (Task 3) ✓; `Ranker` protocol + Bridge/Api/FileRanker behind characterization tests (Tasks 4–5) ✓; DB v3 (`score_history` + `inbox.extras`), history-on-set-fit, undo, pre-migrate backup, populated-fixture migration test (Task 6) ✓; service join/apply/undo verbs (Task 7) ✓; end-to-end round-trip + idempotency + undo (Task 8) ✓; MCP `export_inbox`/`import_scores` (Task 9) ✓; GUI Export/Import(preview+policy)/Undo (Task 10) ✓; full-suite gate (Task 11) ✓.
- **Frozen contract:** `RERANK_CSV_COLUMNS`/`PROMPT_VERSION`/`PROMPT_TEMPLATE` (Task 1), `export_inbox` (Task 2), `ImportResult`/`import_scores` (Task 3), `Ranker`/`FileRanker` (Task 5), `SCHEMA_VERSION 3`/`score_history`/`inbox.extras`/`inbox_set_fit(...source)`/`inbox_undo_last_rerank` (Task 6), MCP tools (Task 9), GUI controls (Task 10) — all match the assignment names/signatures.
- **Grounded in real code (re-verified against the live tree at review):** `claude_bridge._FIT_INSTRUCTIONS`/`DEFAULT_FIT_PREFERENCE`/`_extract_json`/`_strip_trailing_commas`/`fit_token` (verified present), `search.report_csv._csv_safe` guard — guards on `("=","+","-","@","\t","\r")`, exact parity with `schema.csv_safe` (verified), `tracker.db.SCHEMA_VERSION == 2`/`init_db` gated migration + `board_count` inbox-ALTER pattern + `current_db_path()` + `status_history` precedent in `update_job` (verified), `inbox` columns `fit`/`fit_why`/`score`/`score_notes`/`description`/`salary_text`/`board_count` (verified), `tracker.service` inbox verbs (`inbox_all`/`set_inbox_fit`/`jobs_from_rows`) + `JobResult` field order incl. required `created` (verified — `title,company,location,salary_min,salary_max,description,url,source_keyword,created,job_id="",source_api="",score=-1,...`), `mcp_server` tool style + `db`/`prefs_mod` imports + tools `set_fit_scores`/`dismiss_job` (verified), `config.OUTPUT_DIR`/`SECRETS_DIR`/`ANTHROPIC_MODEL` (verified), `gui.py InboxTab` (class line ~651, local `abar` bar lines ~787–812, "Paste Fit Results" button, `_paste_fit`, `self._status`, `self._all`, `set_status`, `tracker_service`, `Path`, `subprocess`, `DARK`/`WHITE` all in scope; `filedialog`/`OUTPUT_DIR` added by Task 10) (verified), existing suite files named in the Verify steps (`tests/test_ranker.py`, `tests/test_tracker_db.py` incl. `test_init_db_gated_on_user_version`, `tests/test_tracker_service.py`, `tests/test_mcp_server.py`, `tests/test_status_history.py`, `tests/test_csv_injection.py`) all exist (verified).
- **⚠️ Cross-workstream dependency, NOT yet in the tree:** `JobResult.job_key` — the cross-source join key this whole workstream pivots on — **does NOT exist on `models.py` today** (only `dedup_key`/`identity_key`; WS-1 Task 5 adds `job_key`). WS-3 is out-of-scope for `models.py`, so all key reads use `getattr(job, "job_key", None) or job.identity_key` (fixed in `schema._job_key_for_row` and `db.inbox_set_fit._job_key_of`). This lets WS-3 build/test standalone whether WS-1 lands first or not; when WS-1 lands, the same code automatically prefers the 16-hex `job_key`. There is no `coverage/` package and no `functools` import in `models.py` at review time — do not assume either.
- **Optional dep handling:** `rapidfuzz` is the only optional dep; `rerank/` is stdlib-only and never import-fails without it (the fuzzy `job_key` fallback in spec §7 is left as an opt-in follow-up — see below).
- **Could not fully ground:** spec §7's **fuzzy fallback** (rapidfuzz on title+company behind a confirm) for rewritten/missing `job_key` rows — the frozen contract specifies only the strict `job_key` join + an `unmatched` report, so this plan reports unmatched rows (never drops them) and leaves the opt-in fuzzy re-match as a documented follow-up rather than inventing a signature not in the contract. Spec §6's "stale-fit on preferences.md change" flag is likewise out of the frozen contract and deferred (the prompt is already re-rendered from live `preferences.md` on every export, so a stale export self-heals on re-export).
- **Known follow-ups (not blockers):** opt-in fuzzy `job_key` re-match for unmatched rows; stale-fit visual flag in the InboxTab; surfacing `score_history` as a before/after diff view; a GUI smoke harness (none exists in `tests/` today).
