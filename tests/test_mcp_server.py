import pytest

pytest.importorskip("mcp")  # server needs the MCP SDK; skip where absent

import mcp_server


def test_server_and_tools_exist():
    assert mcp_server.mcp is not None
    for name in ("get_preferences", "search_jobs", "list_inbox",
                 "set_fit_scores", "track_job", "dismiss_job"):
        assert callable(getattr(mcp_server, name))


def test_get_preferences_shape(monkeypatch):
    monkeypatch.setattr(mcp_server.prefs_mod, "load",
                        lambda: {"profile_md": "controls roles",
                                 "hard": {"salary_min": 90000}})
    out = mcp_server.get_preferences()
    assert out["profile_md"] == "controls roles"
    assert out["hard_filters"]["salary_min"] == 90000


def test_set_fit_scores_applies_and_clamps(monkeypatch):
    applied = []
    monkeypatch.setattr(mcp_server.db, "inbox_set_fit",
                        lambda i, f, r: applied.append((i, f, r)))
    out = mcp_server.set_fit_scores([
        {"id": 1, "fit": 88, "rationale": "great"},
        {"id": 2, "fit": 150, "rationale": "clamp"},   # clamps to 100
        {"fit": 50},                                    # no id -> skipped
    ])
    assert out["applied"] == 2
    assert applied[0] == (1, 88, "great")
    assert applied[1][1] == 100


def test_list_inbox_filters_unscored(monkeypatch):
    rows = [
        {"id": 1, "title": "A", "company": "X", "fit": -1, "score": 70},
        {"id": 2, "title": "B", "company": "Y", "fit": 80, "score": 60},
    ]
    monkeypatch.setattr(mcp_server.db, "inbox_all", lambda: rows)
    assert [r["id"] for r in mcp_server.list_inbox(unscored_only=True)] == [1]
    assert {r["id"] for r in mcp_server.list_inbox(unscored_only=False)} == {1, 2}
