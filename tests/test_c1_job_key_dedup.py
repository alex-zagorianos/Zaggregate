"""C1: job_key dedup + cross-source coalescing + URL-less persistence.

Fixture-based, no network. Covers:
  * migration idempotence + the job_key column exists and is NULL-tolerant
  * cross-source coalescing: same posting via two URLs -> ONE row with alt_urls
  * NULL job_key never coalesces (old rows / no-coverage builds)
  * URL-less postings persist under a synthetic 'keyless:' norm_url and dedupe
    against themselves across runs
  * the review's regression: an overlap source (same posting from 'adzuna' and
    'careers' at different URLs) yields exactly ONE inbox row
  * per-company cap overflow reporting via overflow_out
"""
import json

import pytest

import tracker.db as db
from models import JobResult


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    return db.DB_PATH


def _job(url, title="Data Analyst", company="Acme Health",
         location="Cincinnati, OH", source="careers", description="",
         score=80):
    return JobResult(title=title, company=company, location=location,
                     salary_min=None, salary_max=None, description=description,
                     url=url, source_keyword="", created="2026-06-21",
                     source_api=source, score=score)


# -- migration ----------------------------------------------------------------

def test_migration_idempotent_and_adds_job_key(tmp_db):
    # init_db already ran in the fixture -> fast path returns False the 2nd time.
    assert db.init_db() is False
    with db.get_conn() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(inbox)")}
        assert "job_key" in cols
        idx = {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
        assert "idx_inbox_job_key" in idx


def test_null_job_key_never_coalesces(tmp_db):
    """A row with a NULL job_key (old row) must not swallow a later real posting
    that also can't resolve a key - NULL is 'no key', never a match."""
    # Insert two rows directly with NULL job_key and distinct norm_urls.
    with db.get_conn() as conn:
        for i in (1, 2):
            conn.execute(
                "INSERT INTO inbox (norm_url, title, company, date_added, job_key) "
                "VALUES (?,?,?,?,NULL)",
                (f"x.com/{i}", "Eng", "Acme", "2026-06-01"))
        conn.commit()
    assert db.inbox_count() == 2  # both kept; NULL keys did not merge


# -- cross-source coalescing --------------------------------------------------

def test_same_posting_two_urls_collapses_to_one_row_with_alt_urls(tmp_db):
    a = _job("https://boards.greenhouse.io/acme/jobs/1", source="careers",
             description="Full JD here.")
    b = _job("https://adzuna.example/ad/9", source="adzuna", description="")
    # Same title/company/location -> same job_key -> b coalesces into a.
    added = db.inbox_add_many([a, b])
    assert added == 1
    rows = db.inbox_all()
    assert len(rows) == 1
    row = rows[0]
    # earlier (a's) description is kept; alt_urls records b's URL.
    assert row["description"] == "Full JD here."
    extras = json.loads(row["extras"] or "{}")
    assert db.normalize_url(b.url) in extras.get("alt_urls", [])


def test_coalesce_fills_missing_description(tmp_db):
    # a has NO description, b (coalesced) does -> the merged row gains b's text.
    a = _job("https://a/1", source="careers", description="")
    b = _job("https://b/2", source="adzuna", description="Great role.")
    db.inbox_add_many([a, b])
    row = db.inbox_all()[0]
    assert row["description"] == "Great role."


def test_cross_run_coalescing(tmp_db):
    # First run inserts the posting; a later run seeing it via a new URL merges.
    db.inbox_add_many([_job("https://a/1", source="careers",
                            description="JD")])
    added = db.inbox_add_many([_job("https://b/2", source="adzuna",
                                    description="")])
    assert added == 0
    assert db.inbox_count() == 1
    extras = json.loads(db.inbox_all()[0]["extras"] or "{}")
    assert "b/2" in extras.get("alt_urls", [""])[0]


def test_same_run_two_sources_one_row(tmp_db):
    # Both surfaced in ONE batch (same run) -> still one row.
    jobs = [_job("https://a/1", source="careers"),
            _job("https://b/2", source="adzuna")]
    added = db.inbox_add_many(jobs)
    assert added == 1
    assert db.inbox_count() == 1


def test_distinct_postings_not_merged(tmp_db):
    # Different titles -> different job_keys -> two rows.
    added = db.inbox_add_many([
        _job("https://a/1", title="Data Analyst"),
        _job("https://b/2", title="Nurse Practitioner"),
    ])
    assert added == 2


# -- the review's demanded regression -----------------------------------------

def test_overlap_source_regression_exactly_one_row(tmp_db):
    """Review: with an overlap source simulated (same posting from 'adzuna' and
    'careers' with different URLs), the inbox gains EXACTLY one row."""
    posting_a = _job("https://careers.acme.com/job/42", source="careers",
                     title="Registered Nurse", company="Acme Health",
                     location="Cincinnati, OH")
    posting_b = _job("https://www.adzuna.com/details/9988", source="adzuna",
                     title="Registered Nurse", company="Acme Health",
                     location="Cincinnati, OH")
    before = db.inbox_count()
    db.inbox_add_many([posting_a, posting_b])
    assert db.inbox_count() - before == 1


# -- URL-less persistence -----------------------------------------------------

def test_urlless_posting_persists_and_self_dedupes(tmp_db):
    j1 = _job("", title="Welder", company="Metals Co", location="Dayton, OH")
    added = db.inbox_add_many([j1])
    assert added == 1
    row = db.inbox_all()[0]
    assert row["norm_url"].startswith("keyless:")
    # A second run seeing the same URL-less posting must NOT double-insert.
    j2 = _job("", title="Welder", company="Metals Co", location="Dayton, OH")
    added2 = db.inbox_add_many([j2])
    assert added2 == 0
    assert db.inbox_count() == 1


def test_urlless_distinct_cities_not_merged(tmp_db):
    # Same title+company, different city -> distinct keyless identity -> 2 rows
    # (mirrors the engine's dedup contract).
    added = db.inbox_add_many([
        _job("", title="Director", company="Acme", location="Cincinnati, OH"),
        _job("", title="Director", company="Acme", location="Columbus, OH"),
    ])
    assert added == 2


def test_urlless_identity_matches_engine(tmp_db):
    """The inbox's synthetic norm_url must be 'keyless:' + the SAME identity the
    search engine dedups on, so the two layers agree."""
    from search.search_engine import keyless_identity
    j = _job("", title="Machinist", company="Tool Co", location="Remote")
    db.inbox_add_many([j])
    row = db.inbox_all()[0]
    assert row["norm_url"] == "keyless:" + keyless_identity(j)


# -- per-company cap overflow reporting ---------------------------------------

def test_cap_overflow_reported(tmp_db):
    overflow: dict = {}
    jobs = [_job(f"https://a/{i}", title=f"Eng {i}", company="BigCo")
            for i in range(5)]
    added = db.inbox_add_many(jobs, per_company_cap=2, overflow_out=overflow)
    assert added == 2
    assert overflow.get("BigCo") == 3   # 5 offered, 2 capped in, 3 overflow


def test_cap_overflow_empty_when_under_cap(tmp_db):
    overflow: dict = {}
    db.inbox_add_many([_job("https://a/1", title="Eng 1", company="BigCo")],
                      per_company_cap=5, overflow_out=overflow)
    assert overflow == {}


def test_cap_overflow_out_param_optional(tmp_db):
    # Existing callers that pass no overflow_out still get an int and don't crash.
    n = db.inbox_add_many([_job("https://a/1", title="Eng 1")],
                          per_company_cap=2)
    assert n == 1


def test_run_record_carries_capped_sibling_key(tmp_db):
    """C1 #6 storage contract: cap overflow rides the runs.source_counts JSON as a
    reserved '__capped__' sibling - no schema change, survives a round-trip."""
    run_id = db.record_run_start(project="p")
    source_counts = {"careers": 12, "adzuna": 3, "__capped__": {"BigCo": 9}}
    db.record_run_finish(run_id, "ok", source_counts=source_counts)
    last = db.get_last_run(project="p")
    got = json.loads(last["source_counts"])
    assert got["careers"] == 12
    assert got["__capped__"] == {"BigCo": 9}
