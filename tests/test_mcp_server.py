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

    def fake_set_fit(i, f, r, source="manual", batch=""):
        applied.append((i, f, r, source, batch))
        return True   # row landed

    monkeypatch.setattr(mcp_server.db, "inbox_set_fit", fake_set_fit)
    out = mcp_server.set_fit_scores([
        {"id": 1, "fit": 88, "rationale": "great"},
        {"id": 2, "fit": 150, "rationale": "clamp"},   # clamps to 100
        {"fit": 50},                                    # no id -> skipped
    ])
    assert out["applied"] == 2
    assert out["missed"] == 0
    assert applied[0][:3] == (1, 88, "great")
    assert applied[0][3] == "mcp"                       # tagged source
    assert applied[0][4] and applied[0][4] == applied[1][4]  # ONE shared batch
    assert applied[1][1] == 100


def test_set_fit_scores_phantom_id_not_counted(monkeypatch):
    """A nonexistent id must NOT count as applied (phantom-applied fix): the
    real inbox_set_fit returns False for a missing row."""
    def fake_set_fit(i, f, r, source="manual", batch=""):
        return i == 1   # only id 1 exists

    monkeypatch.setattr(mcp_server.db, "inbox_set_fit", fake_set_fit)
    merged = []
    monkeypatch.setattr(mcp_server.db, "inbox_merge_extras",
                        lambda i, p: merged.append(i))
    out = mcp_server.set_fit_scores([
        {"id": 1, "fit": 80, "rationale": "real", "rank": 1},
        {"id": 999, "fit": 70, "rationale": "phantom", "rank": 2},
    ])
    assert out["applied"] == 1 and out["missed"] == 1
    assert merged == [1]                                # no rank write for phantom


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
                        lambda i, f, r, source="manual", batch="": (
                            fits.append((i, f, r)) or True))
    monkeypatch.setattr(mcp_server.db, "inbox_merge_extras",
                        lambda i, p: patches.append((i, p)))
    out = mcp_server.set_fit_scores([
        {"id": 1, "fit": 90, "rationale": "x", "rank": 1},
        {"id": 2, "fit": 80, "rationale": "y"},   # no rank -> no merge
    ])
    assert out["applied"] == 2
    assert len(patches) == 1 and patches[0][0] == 1
    assert patches[0][1]["rank"] == 1 and patches[0][1]["rec_batch"]


# ── A3: startup project pin (S27 concurrency class) ───────────────────────────
def test_main_pins_active_project_at_startup(monkeypatch):
    """A long-lived MCP session must pin the active project ONCE at startup so a
    later GUI switch can't redirect its writes to another project."""
    pinned = {}
    monkeypatch.setattr(mcp_server.userdata, "bootstrap", lambda: None)
    monkeypatch.setattr(mcp_server.db, "init_db", lambda: None)
    monkeypatch.setattr(mcp_server.mcp, "run", lambda: None)
    monkeypatch.setattr(mcp_server.workspace, "active_slug", lambda: "controls")
    monkeypatch.setattr(mcp_server.workspace, "pin_active",
                        lambda s: pinned.setdefault("slug", s))
    mcp_server.main([])                    # no --project -> pin whatever's active
    assert pinned["slug"] == "controls"


def test_main_pins_explicit_project(monkeypatch):
    pinned = {}
    monkeypatch.setattr(mcp_server.userdata, "bootstrap", lambda: None)
    monkeypatch.setattr(mcp_server.db, "init_db", lambda: None)
    monkeypatch.setattr(mcp_server.mcp, "run", lambda: None)
    monkeypatch.setattr(mcp_server.workspace, "list_projects",
                        lambda: [{"slug": "dad"}, {"slug": "controls"}])
    monkeypatch.setattr(mcp_server.workspace, "pin_active",
                        lambda s: pinned.setdefault("slug", s))
    mcp_server.main(["--project", "dad"])
    assert pinned["slug"] == "dad"


def test_main_rejects_unknown_project(monkeypatch):
    monkeypatch.setattr(mcp_server.userdata, "bootstrap", lambda: None)
    monkeypatch.setattr(mcp_server.workspace, "list_projects",
                        lambda: [{"slug": "controls"}])
    monkeypatch.setattr(mcp_server.mcp, "run", lambda: pytest.fail("must not serve"))
    with pytest.raises(SystemExit):
        mcp_server.main(["--project", "nope"])
