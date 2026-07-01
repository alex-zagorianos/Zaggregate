"""Export the inbox as the round-trip trio: ranking_export.csv (the carrier the
AI fills), ranking_export.md (human-readable), and prompt.md (versioned).

Two knobs for fitting a free chatbot's context window (C2 / review P4):
  * chunk_size  — split the CSV into ranking_export_01.csv, _02, ... of at most
                  chunk_size rows each. The AI answers each file separately;
                  job_key joins them back on import (import needs no change).
  * compact     — replace the long description_excerpt with the S21 one-line
                  facts summary (match.facts.facts_summary), shrinking a ~215K-
                  token full export to ~15-30K. Same column contract, so a
                  compact export imports identically.
"""
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


def _fit_preference() -> str:
    try:
        import preferences
        return (preferences.load() or {}).get("fit_preference", "") or ""
    except Exception:
        return ""


def _facts_excerpt(r: dict) -> str:
    """The S21 one-line facts summary for an inbox row (compact mode), reusing
    the SAME match.facts seam tracker/service.py feeds the bridge. Best-effort:
    on any failure fall back to the plain description excerpt so a row never
    exports blank."""
    try:
        from models import JobResult
        from match.facts import facts_for, facts_summary
        j = JobResult(
            title=r.get("title", "") or "", company=r.get("company", "") or "",
            location=r.get("location", "") or "", salary_min=None, salary_max=None,
            description=r.get("description", "") or "", url=r.get("url", "") or "",
            source_keyword="", created=r.get("created", "") or "",
            source_api=r.get("source", "") or "")
        return facts_summary(facts_for(j))
    except Exception:
        return ""


def _mapped_row(r: dict, *, compact: bool) -> dict:
    """RERANK_CSV_COLUMNS dict for one inbox row. In compact mode the long
    description_excerpt is replaced by the facts summary (~15x smaller)."""
    mapped = schema.row_from_inbox(r)
    if compact:
        facts = _facts_excerpt(r)
        if facts:
            mapped["description_excerpt"] = facts
    return mapped


def _write_csv(out: Path, rows: list[dict], *, compact: bool = False) -> Path:
    # utf-8-sig: Excel opens it without mojibake; the importer strips the BOM.
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=schema.RERANK_CSV_COLUMNS)
        w.writeheader()
        for r in rows:
            mapped = _mapped_row(r, compact=compact)
            w.writerow({k: schema.csv_safe(v) for k, v in mapped.items()})
    return out


def _chunk(rows: list[dict], chunk_size: int) -> list[list[dict]]:
    """Split rows into chunks of at most chunk_size. chunk_size<=0 => one chunk
    (no split)."""
    if not chunk_size or chunk_size <= 0 or len(rows) <= chunk_size:
        return [rows]
    return [rows[i:i + chunk_size] for i in range(0, len(rows), chunk_size)]


def _write_md(out: Path, rows: list[dict], *, compact: bool = False) -> Path:
    lines = ["# Inbox export for AI re-ranking", "",
             "Fill `new_fit` (0-100), optional `new_rank`, and `fit_rationale` "
             "for each row in `ranking_export.csv`. Leave `job_key` unchanged.",
             "",
             "| job_key | title | company | location | salary | local_score | current_fit |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    detail = ["", "## Job details", ""]
    for r in rows:
        m = _mapped_row(r, compact=compact)
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


def export_inbox(rows: list[dict], out_dir, *, fmt: str = "both",
                 chunk_size: int | None = None, compact: bool = False) -> dict:
    """Write the export trio under out_dir. fmt in {"both","csv","md"}; the CSV
    and the versioned prompt are always written (the CSV is the carrier, the
    prompt is the instructions); fmt only toggles the human-readable MD.

    chunk_size (C2): when set and the inbox exceeds it, the CSV is split into
    ranking_export_01.csv, _02, ... (<= chunk_size rows each) so each file fits a
    free chatbot's window; the AI answers each separately and job_key joins them
    back on import. None / 0 / a size >= len(rows) writes the single
    ranking_export.csv (byte-compatible with the old behavior).

    compact (C2): replace the long description_excerpt with the one-line facts
    summary (~15x smaller). Same columns, so a compact export imports identically.

    Returns {"csv": Path, "csvs": [Path,...], "md": Path (when written),
    "prompt": Path}. "csv" is the first chunk (back-compat single-file callers);
    "csvs" is the full list."""
    base = Path(out_dir)
    base.mkdir(parents=True, exist_ok=True)
    paths: dict = {}
    chunks = _chunk(list(rows), chunk_size or 0)
    csv_paths: list[Path] = []
    if len(chunks) == 1:
        csv_paths.append(_write_csv(base / "ranking_export.csv", chunks[0],
                                    compact=compact))
    else:
        for i, chunk in enumerate(chunks, 1):
            csv_paths.append(_write_csv(base / f"ranking_export_{i:02d}.csv", chunk,
                                        compact=compact))
    paths["csv"] = csv_paths[0]
    paths["csvs"] = csv_paths
    if fmt in ("both", "md"):
        paths["md"] = _write_md(base / "ranking_export.md", list(rows), compact=compact)
    prompt = base / "prompt.md"
    prompt.write_text(schema.build_prompt(_profile_md(), _fit_preference()),
                      encoding="utf-8")
    paths["prompt"] = prompt
    return paths
