"""Contacts/referral CRM (TASK C) — manual networking capture on the project DB."""
import pytest

import tracker.db as db


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    return db.DB_PATH


def test_init_sets_user_version_4_and_second_init_is_noop(tmp_db):
    assert db.init_db() is True     # first call migrates -> current
    with db.get_conn() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == db.SCHEMA_VERSION
    assert db.init_db() is False    # already current -> fast-path skip


def test_add_and_list_contacts_newest_first(tmp_db):
    db.init_db()
    a = db.add_contact("Jane Recruiter", role="Recruiter", email="jane@acme.com",
                       company="Acme", note="met at meetup")
    b = db.add_contact("Bob Hiring", role="EM", linkedin="in/bob", company="Globex")
    assert isinstance(a, int) and isinstance(b, int) and a != b

    rows = db.list_contacts()
    assert len(rows) == 2
    # newest first -> the second insert (Bob) leads
    assert rows[0]["name"] == "Bob Hiring"
    assert rows[1]["name"] == "Jane Recruiter"
    jane = rows[1]
    assert jane["role"] == "Recruiter"
    assert jane["email"] == "jane@acme.com"
    assert jane["company"] == "Acme"
    assert jane["note"] == "met at meetup"
    assert jane["linkedin"] == ""      # default
    assert jane["app_id"] is None      # default
    assert jane["created"]             # stamped


def test_add_contact_defaults(tmp_db):
    db.init_db()
    cid = db.add_contact("Minimal")
    row = next(r for r in db.list_contacts() if r["id"] == cid)
    assert row["name"] == "Minimal"
    for col in ("role", "email", "linkedin", "company", "last_contacted", "note"):
        assert row[col] == ""
    assert row["app_id"] is None


def test_contacts_for_company_case_insensitive(tmp_db):
    db.init_db()
    db.add_contact("Jane", company="Acme Corp")
    db.add_contact("Bob", company="Globex")
    db.add_contact("Sue", company="acme corp")

    acme = db.contacts_for_company("ACME CORP")
    names = {c["name"] for c in acme}
    assert names == {"Jane", "Sue"}
    assert all(c["company"].lower() == "acme corp" for c in acme)
    assert db.contacts_for_company("Nope") == []


def test_delete_contact(tmp_db):
    db.init_db()
    a = db.add_contact("Jane", company="Acme")
    b = db.add_contact("Bob", company="Acme")
    db.delete_contact(a)
    remaining = db.list_contacts()
    assert [r["id"] for r in remaining] == [b]
    assert remaining[0]["name"] == "Bob"


def test_contact_app_id_links_to_application(tmp_db):
    db.init_db()
    job_id = db.add_job("Controls Eng", "Acme")
    cid = db.add_contact("Jane", company="Acme", app_id=job_id)
    row = next(r for r in db.list_contacts() if r["id"] == cid)
    assert row["app_id"] == job_id
