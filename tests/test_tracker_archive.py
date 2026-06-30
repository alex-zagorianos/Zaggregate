"""Archive = soft-delete: hidden from normal tracker views/counts, recoverable,
still deduped against search, with permanent delete reachable only from archive."""
import pytest

import tracker.db as db


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    return db.DB_PATH


def test_archive_hides_from_default_views_and_counts(tmp_db):
    a = db.add_job("Controls Engineer", "Acme", url="https://x/1", status="applied")
    db.add_job("Automation Engineer", "Beta", url="https://x/2", status="interested")
    db.archive_job(a)

    assert {j["title"] for j in db.get_all()} == {"Automation Engineer"}
    assert all(j["id"] != a for j in db.get_all("applied"))

    counts = db.get_counts()
    assert counts["all"] == 1            # archived excluded from total
    assert counts["applied"] == 0
    assert counts["archived"] == 1


def test_archived_filter_returns_only_archived(tmp_db):
    a = db.add_job("Controls Engineer", "Acme", url="https://x/1")
    db.add_job("Automation Engineer", "Beta", url="https://x/2")
    db.archive_job(a)
    arch = db.get_all("archived")
    assert len(arch) == 1 and arch[0]["id"] == a


def test_unarchive_restores(tmp_db):
    a = db.add_job("Controls Engineer", "Acme", status="applied")
    db.archive_job(a)
    assert db.get_counts()["archived"] == 1
    db.unarchive_job(a)
    counts = db.get_counts()
    assert counts["archived"] == 0 and counts["applied"] == 1
    assert any(j["id"] == a for j in db.get_all())


def test_archived_job_still_deduped(tmp_db):
    a = db.add_job("Eng", "Acme", url="https://x.com/tracked/9")
    db.archive_job(a)
    assert db.normalize_url("https://x.com/tracked/9") in db.tracked_urls()


def test_delete_is_permanent(tmp_db):
    a = db.add_job("Eng", "Acme")
    db.delete_job(a)
    assert db.get_job(a) is None
    assert db.get_counts()["all"] == 0
