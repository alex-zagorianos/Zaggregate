"""Chunked + compact export (C2 / review P4 item 2).

  * chunk_size splits the CSV into ranking_export_01.csv, _02, ... and each holds
    at most chunk_size rows; every job_key still appears exactly once across them.
  * compact=True replaces the long description_excerpt with the facts summary,
    shrinking the file materially.
  * a subset (one chunk) still imports cleanly by job_key (no import change).
"""
import csv

import pytest

from rerank.export import export_inbox
from rerank import schema
from rerank.import_ import import_scores


def _rows(n, desc):
    return [{"id": i, "title": f"Engineer {i}", "company": f"Co{i}",
             "location": "Cincinnati, OH", "salary_text": "$120k",
             "url": f"https://x/{i}", "score": 70, "fit": -1,
             "description": desc} for i in range(1, n + 1)]


def _read(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def test_chunk_splits_into_numbered_files(tmp_path):
    paths = export_inbox(_rows(5, "x"), tmp_path, fmt="csv", chunk_size=2)
    csvs = paths["csvs"]
    assert len(csvs) == 3                      # 2 + 2 + 1
    names = sorted(p.name for p in csvs)
    assert names == ["ranking_export_01.csv", "ranking_export_02.csv",
                     "ranking_export_03.csv"]
    # No single ranking_export.csv when split.
    assert not (tmp_path / "ranking_export.csv").exists()
    # Every job_key appears exactly once across all chunks.
    keys = [r["job_key"] for p in csvs for r in _read(p)]
    assert len(keys) == 5 and len(set(keys)) == 5


def test_chunk_size_none_writes_single_file(tmp_path):
    paths = export_inbox(_rows(3, "x"), tmp_path, fmt="csv", chunk_size=None)
    assert len(paths["csvs"]) == 1
    assert (tmp_path / "ranking_export.csv").exists()


def test_chunk_size_larger_than_inbox_single_file(tmp_path):
    paths = export_inbox(_rows(3, "x"), tmp_path, fmt="csv", chunk_size=100)
    assert len(paths["csvs"]) == 1
    assert (tmp_path / "ranking_export.csv").exists()


def test_compact_shrinks_the_export(tmp_path):
    long_desc = ("We need a controls engineer with PLC, SCADA, motion control, "
                 "C++, Python. " * 40)
    full = export_inbox(_rows(4, long_desc), tmp_path / "full", fmt="csv")
    comp = export_inbox(_rows(4, long_desc), tmp_path / "comp", fmt="csv",
                        compact=True)
    full_len = full["csv"].read_text(encoding="utf-8-sig").__len__()
    comp_len = comp["csv"].read_text(encoding="utf-8-sig").__len__()
    assert comp_len < full_len                 # facts summary is much smaller
    # Same columns/rows/keys — only description_excerpt content changed.
    full_rows, comp_rows = _read(full["csv"]), _read(comp["csv"])
    assert [r["job_key"] for r in full_rows] == [r["job_key"] for r in comp_rows]
    assert len(comp_rows) == 4


def test_compact_and_chunk_together(tmp_path):
    paths = export_inbox(_rows(5, "controls engineer PLC " * 30), tmp_path,
                         fmt="csv", chunk_size=2, compact=True)
    assert len(paths["csvs"]) == 3
    keys = [r["job_key"] for p in paths["csvs"] for r in _read(p)]
    assert len(set(keys)) == 5


def test_subset_chunk_imports_by_job_key(tmp_path):
    """A single chunk answered on its own re-ranks exactly its rows via job_key —
    import needs no change to handle a subset."""
    rows = _rows(4, "x")
    paths = export_inbox(rows, tmp_path, fmt="csv", chunk_size=2)
    first_chunk = paths["csvs"][0]
    exported = _read(first_chunk)               # 2 rows
    assert len(exported) == 2

    # The user fills new_fit on just this chunk and hands it back.
    ret = tmp_path / "answered.csv"
    with ret.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=schema.RERANK_CSV_COLUMNS)
        w.writeheader()
        for r in exported:
            r["new_fit"] = "88"
            r["fit_rationale"] = "good"
            w.writerow(r)

    # The join is by job_key (the CSV carries no id); map each to a synthetic id.
    rows_by_key = {r["job_key"]: {"id": idx + 1, "fit": -1}
                   for idx, r in enumerate(exported)}
    applied = []
    res = import_scores(ret, rows_by_key, policy="overwrite",
                        _apply=lambda u, *, source="file_import": (
                            applied.extend(u) or len(u)))
    assert res.matched == 2 and res.updated == 2 and res.unmatched == []
    assert all(u["new_fit"] == 88 for u in applied)
