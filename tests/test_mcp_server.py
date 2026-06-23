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


def test_list_inbox_limit_zero_returns_all_with_rank(monkeypatch):
    rows = [{"id": i, "title": "T", "company": "C", "fit": -1, "score": 70,
             "extras": ('{"rank":1,"rec_batch":"B"}' if i == 1 else "")}
            for i in (1, 2, 3)]
    monkeypatch.setattr(mcp_server.db, "inbox_all", lambda: rows)
    out = mcp_server.list_inbox(limit=0, unscored_only=False)
    assert len(out) == 3
    by_id = {r["id"]: r for r in out}
    assert by_id[1]["rank"] == 1 and by_id[2]["rank"] == -1
    assert all(r["job_key"] for r in out)


def test_set_fit_scores_persists_rank(monkeypatch):
    fits, patches = [], []
    monkeypatch.setattr(mcp_server.db, "inbox_set_fit",
                        lambda i, f, r: fits.append((i, f, r)))
    monkeypatch.setattr(mcp_server.db, "inbox_merge_extras",
                        lambda i, p: patches.append((i, p)))
    out = mcp_server.set_fit_scores([
        {"id": 1, "fit": 90, "rationale": "x", "rank": 1},
        {"id": 2, "fit": 80, "rationale": "y"},   # no rank -> no merge
    ])
    assert out["applied"] == 2
    assert len(patches) == 1 and patches[0][0] == 1
    assert patches[0][1]["rank"] == 1 and patches[0][1]["rec_batch"]
