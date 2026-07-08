"""keyword_pool CRUD (Search Discovery spine) + the v8 schema migration."""
import pytest

from tracker import db
from search.discovery import pool


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    return tmp_path


def test_keyword_pool_table_created_at_v8(tmp_db):
    with db.get_conn() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 8
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(keyword_pool)")}
    assert {"term", "tier", "source", "status", "yield_count", "activated_at"} <= cols


def test_upsert_inserts_new_counts_only_new(tmp_db):
    n = pool.upsert_terms([
        {"term": "Diesel Mechanic", "tier": "core", "source": "onet"},
        {"term": "Fleet Technician", "tier": "adjacent", "source": "related_soc"},
    ])
    assert n == 2
    # re-proposing the same two + one new -> only the new one is counted
    n2 = pool.upsert_terms([
        {"term": "Diesel Mechanic", "tier": "core", "source": "onet"},
        {"term": "Field Service Tech", "tier": "exploratory", "source": "related_soc"},
    ])
    assert n2 == 1
    assert len(pool.get_pool()) == 3


def test_upsert_dedupes_within_batch_and_skips_bad_rows(tmp_db):
    n = pool.upsert_terms([
        {"term": "Welder", "tier": "core", "source": "onet"},
        {"term": "Welder", "tier": "core", "source": "onet"},   # dup in batch
        {"term": "", "tier": "core", "source": "onet"},          # blank
        {"term": "X", "tier": "bogus", "source": "onet"},        # bad tier
        {"term": "Y", "tier": "core", "source": ""},             # blank source
    ])
    assert n == 1
    assert [r["term"] for r in pool.get_pool()] == ["Welder"]


def test_upsert_never_downgrades_active_term(tmp_db):
    pool.upsert_terms([{"term": "Machinist", "tier": "core", "source": "onet"}])
    pool.set_status("Machinist", "active")
    # a later re-propose as a plain suggestion must NOT revert it
    pool.upsert_terms([{"term": "Machinist", "tier": "core", "source": "onet",
                        "status": "suggested"}])
    row = pool.get_term("Machinist")
    assert row["status"] == "active"
    assert row["activated_at"] is not None


def test_active_terms_and_status_roundtrip(tmp_db):
    pool.upsert_terms([{"term": "CNC Operator", "tier": "core", "source": "onet"}])
    assert pool.active_terms() == []
    assert pool.set_status("CNC Operator", "active") is True
    assert pool.active_terms() == ["CNC Operator"]
    pool.set_status("CNC Operator", "inactive")
    assert pool.active_terms() == []
    assert pool.set_status("Nonexistent", "active") is False


def test_set_yield_records_count(tmp_db):
    pool.upsert_terms([{"term": "Assembler", "tier": "core", "source": "onet"}])
    assert pool.set_yield("Assembler", 42, "adzuna:us-oh-cincinnati") is True
    row = pool.get_term("Assembler")
    assert row["yield_count"] == 42
    assert row["yield_source"] == "adzuna:us-oh-cincinnati"
    assert row["yield_date"] is not None


def test_prune_suggestions_never_touches_active(tmp_db):
    pool.upsert_terms([
        {"term": "Old Suggestion", "tier": "exploratory", "source": "ai"},
        {"term": "Chosen Term", "tier": "core", "source": "onet"},
    ])
    pool.set_status("Chosen Term", "active")
    # backdate both rows well past the TTL
    with db.get_conn() as conn:
        conn.execute("UPDATE keyword_pool SET last_seen='2000-01-01T00:00:00+00:00'")
        conn.commit()
    removed = pool.prune_suggestions(ttl_days=90)
    assert removed == 1
    remaining = [r["term"] for r in pool.get_pool()]
    assert remaining == ["Chosen Term"]  # active survived despite being ancient


def test_get_pool_filters(tmp_db):
    pool.upsert_terms([
        {"term": "A", "tier": "core", "source": "onet"},
        {"term": "B", "tier": "adjacent", "source": "related_soc"},
    ])
    pool.set_status("A", "active")
    assert [r["term"] for r in pool.get_pool(status="active")] == ["A"]
    assert [r["term"] for r in pool.get_pool(tier="adjacent")] == ["B"]
