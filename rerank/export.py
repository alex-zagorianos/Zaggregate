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
