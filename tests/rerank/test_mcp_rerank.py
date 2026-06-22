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
