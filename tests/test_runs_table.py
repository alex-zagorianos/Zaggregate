"""HEALTH BEACON: the runs table + record_run_start/finish/get_last_run."""
import pytest

import tracker.db as db


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    return db.DB_PATH


def test_start_then_finish_transitions(tmp_db):
    rid = db.record_run_start("controls-cincinnati")
    row = db.get_last_run("controls-cincinnati")
    assert row["id"] == rid
    assert row["status"] == "running"
    assert row["started_at"]            # timestamp set
    assert row["finished_at"] == ""     # not finished yet

    db.record_run_finish(rid, "ok", source_counts={"greenhouse": 4, "lever": 1})
    row = db.get_last_run("controls-cincinnati")
    assert row["status"] == "ok"
    assert row["finished_at"]
    assert '"greenhouse": 4' in row["source_counts"]


def test_get_last_run_returns_latest(tmp_db):
    db.record_run_finish(db.record_run_start("p"), "ok")
    r2 = db.record_run_start("p")
    last = db.get_last_run("p")
    assert last["id"] == r2
    # overall (no project arg) also returns the most recent row
    assert db.get_last_run()["id"] == r2


def test_get_last_run_none_when_empty(tmp_db):
    assert db.get_last_run("nobody") is None


def test_failed_status_persists_error(tmp_db):
    rid = db.record_run_start("p")
    tb = "Traceback (most recent call last):\n  RuntimeError: boom"
    db.record_run_finish(rid, "failed", error=tb)
    row = db.get_last_run("p")
    assert row["status"] == "failed"
    assert "RuntimeError: boom" in row["error"]


def test_get_last_run_signature_default():
    """GUI reads get_last_run(project: str|None=None) with no arg."""
    import inspect
    sig = inspect.signature(db.get_last_run)
    assert list(sig.parameters) == ["project"]
    assert sig.parameters["project"].default is None


def test_zero_status_when_nothing_new(tmp_db):
    rid = db.record_run_start("p")
    db.record_run_finish(rid, "zero", source_counts={"greenhouse": 0})
    assert db.get_last_run("p")["status"] == "zero"
