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
