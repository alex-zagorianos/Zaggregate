"""Corpus mining (search-discovery-plan.md §4.2, Phase 5): mine_corpus() +
corpus_title_counts(), gated behind discovery_enabled, plus the generic
cached_titles() accessor on SingleFeedClient. Fully offline."""
import json

import pytest

from search.discovery import mine, pool
from search.single_feed_client import SingleFeedClient
from tracker import db


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    return tmp_path


def _insert_inbox(conn, title, n=1):
    for i in range(n):
        conn.execute(
            "INSERT INTO inbox (norm_url, title, company, date_added) "
            "VALUES (?,?,?,?)",
            (f"http://example.com/{title}/{i}", title, "ACME", "2026-01-01"))


def _insert_application(conn, title, n=1):
    for i in range(n):
        conn.execute(
            "INSERT INTO applications (title, company, date_added) "
            "VALUES (?,?,?)",
            (title, "ACME", "2026-01-01"))


# --------------------------------------------------------------------------
# mine_corpus gating
# --------------------------------------------------------------------------

def test_mine_corpus_noop_when_disabled(tmp_db, monkeypatch):
    with db.get_conn() as conn:
        _insert_inbox(conn, "Diesel Mechanic", n=3)
        conn.commit()

    # explicit enabled=False
    result = mine.mine_corpus(enabled=False)
    assert result == {"mined": 0, "upserted": 0, "skipped": True, "reason": "disabled"}
    assert pool.get_pool() == []

    # enabled=None falls through to cfg.get('discovery_enabled', False); with
    # discovery_enabled unset (empty cfg) this must also skip.
    monkeypatch.setattr(mine.workspace, "load_config", lambda *a, **k: {})
    result2 = mine.mine_corpus(enabled=None)
    assert result2 == {"mined": 0, "upserted": 0, "skipped": True, "reason": "disabled"}
    assert pool.get_pool() == []


def test_mine_corpus_upserts_frequent_titles(tmp_db, monkeypatch):
    # Isolate this test from whatever the real single-feed clients' on-disk
    # caches happen to contain on this machine — the SQL scan is what's under
    # test here; the feed-cache union is covered separately.
    monkeypatch.setattr(mine, "_feed_cache_titles", lambda: [])

    with db.get_conn() as conn:
        _insert_inbox(conn, "Diesel Mechanic", n=3)       # frequent
        _insert_inbox(conn, "Fleet Technician", n=1)       # below min_count
        _insert_application(conn, "Diesel Mechanic", n=1)  # +1, still frequent
        conn.commit()

    result = mine.mine_corpus(enabled=True, min_count=2)
    assert result["skipped"] is False
    assert result["reason"] == ""
    assert result["upserted"] == 1  # only "Diesel Mechanic" clears min_count
    assert result["mined"] == 2     # 2 distinct titles considered

    pool_terms = {r["term"]: r for r in pool.get_pool()}
    assert "Diesel Mechanic" in pool_terms
    assert "Fleet Technician" not in pool_terms
    row = pool_terms["Diesel Mechanic"]
    assert row["tier"] == "adjacent"
    assert row["source"] == "corpus"
    assert row["status"] == "suggested"

    # re-running must not re-count as newly upserted (upsert_terms only counts
    # NEW rows) but should not error either.
    result2 = mine.mine_corpus(enabled=True, min_count=2)
    assert result2["skipped"] is False
    assert result2["upserted"] == 0


# --------------------------------------------------------------------------
# corpus_title_counts (pure read)
# --------------------------------------------------------------------------

def test_corpus_title_counts_frequency(tmp_db):
    with db.get_conn() as conn:
        _insert_inbox(conn, "Machinist", n=2)
        _insert_application(conn, "Machinist", n=1)  # total 3
        _insert_inbox(conn, "Welder", n=1)             # total 1, below min_count
        conn.commit()

    counts = dict(mine.corpus_title_counts(min_count=2))
    assert counts["Machinist"] == 3
    assert "Welder" not in counts


# --------------------------------------------------------------------------
# cached_titles() generic extraction (SingleFeedClient base)
# --------------------------------------------------------------------------

class _StubFeedClient(SingleFeedClient):
    """Minimal concrete subclass — JobAPIClient's search()/parse_results() are
    abstract, so a bare SingleFeedClient can't be instantiated directly."""
    cache_subdir = "stubfeed_test"
    rate_limit = 5

    def search(self, keyword, location, salary_min, page):
        return {}

    def parse_results(self, raw, source_keyword):
        return []


def test_cached_titles_generic_extraction(tmp_path):
    client = _StubFeedClient(cache_dir=tmp_path / "populated")
    (client.cache.dir / "a.json").write_text(
        json.dumps({"jobs": [{"title": "Foo Bar", "company": "X"},
                              {"title": "Baz Qux"}]}),
        encoding="utf-8")
    (client.cache.dir / "b.json").write_text(
        json.dumps([{"title": "Direct List Title"}]), encoding="utf-8")

    titles = client.cached_titles()
    assert set(titles) == {"Foo Bar", "Baz Qux", "Direct List Title"}

    # An opaque cache shape (no 'title' fields anywhere) yields [].
    opaque_client = _StubFeedClient(cache_dir=tmp_path / "opaque")
    (opaque_client.cache.dir / "c.json").write_text(
        json.dumps({"data": "blob", "meta": [1, 2, 3]}), encoding="utf-8")
    assert opaque_client.cached_titles() == []

    # An empty/never-fetched cache also yields [], never raises.
    empty_client = _StubFeedClient(cache_dir=tmp_path / "empty")
    assert empty_client.cached_titles() == []
