"""Shared fixtures for the webui API tests.

``client`` — the receiver's Flask app (which mounts webui) as a TESTING
test_client, so the private ``/api/_test/job`` hook is live and no real socket
is opened (the autouse network guard in the top-level conftest allows loopback,
but the test_client never touches a socket at all).

``tmp_db`` — points ``tracker.db`` at a fresh tmp DB (the established fixture
pattern from tests/test_top_picks.py / tests/test_browser_receiver_track.py) so
inbox/tracker writes never touch real user data.
"""
import pytest

import webui  # noqa: F401 — ensure the package registers onto the app
import workspace
from scrape.browser_receiver import app as _app
from tracker import db


@pytest.fixture
def client():
    _app.config["TESTING"] = True
    return _app.test_client()


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    return db.DB_PATH


@pytest.fixture(autouse=True)
def _isolate_output_dir(tmp_path, monkeypatch):
    """Point ``workspace.output_dir`` at a per-test tmp dir so the inbox export
    route (which writes under ``output_dir()/rerank``) never touches the real
    project output folder, and each test's export/download is hermetic."""
    out = tmp_path / "ws_output"
    out.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(workspace, "output_dir", lambda slug=None: out)
    return out


@pytest.fixture(autouse=True)
def _reset_undo_buffer():
    """The inbox dismiss-undo buffer is a module-global (single-flight per
    process); clear it around every test so a stashed batch can't leak into an
    unrelated test's undo count."""
    from webui.api import inbox as _inbox
    _inbox._undo_batches.clear()
    yield
    _inbox._undo_batches.clear()
