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
    assert set(paths) == {"csv", "csvs", "md", "prompt"}
    for k, p in paths.items():
        if k == "csvs":
            assert p == [paths["csv"]]  # single-file export: one chunk
            continue
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
