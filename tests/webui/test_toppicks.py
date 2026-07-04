"""/api/toppicks — rows shape against a seeded tmp DB, limit semantics, extras parse."""
from models import JobResult
from tracker import db, service


def _job(url, title="Software Developer", company="Acme"):
    return JobResult(title=title, company=company, location="Cincinnati, OH",
                     salary_min=None, salary_max=None, description="controls",
                     url=url, source_keyword="", created="2026-06-21",
                     source_api="adzuna", score=70)


def _seed_ranked(n=3):
    """Inbox n rows and stamp a shortlist rank (1..n) under one rec_batch."""
    db.inbox_add_many([_job(f"https://x/{i}", chr(65 + i)) for i in range(n)])
    rows = db.inbox_all()
    b = service.new_rec_batch()
    for i, r in enumerate(rows):
        db.inbox_merge_extras(r["id"], service.rank_patch(i + 1, b))
    return rows


def test_toppicks_empty_when_unranked(client, tmp_db):
    db.inbox_add_many([_job("https://x/1")])
    body = client.get("/api/toppicks").get_json()
    assert body == {"ok": True, "rows": []}


def test_toppicks_rows_shape(client, tmp_db):
    _seed_ranked(3)
    body = client.get("/api/toppicks").get_json()
    assert body["ok"] is True
    rows = body["rows"]
    assert len(rows) == 3
    # Ordered by rank ascending.
    assert [r["rank"] for r in rows] == [1, 2, 3]
    # Engine columns pass through; extras is a PARSED object (not a JSON string).
    first = rows[0]
    assert first["title"] and first["company"] and first["url"]
    assert isinstance(first["extras"], dict)
    assert first["extras"]["rank"] == 1 and first["extras"]["rec_batch"]


def test_toppicks_limit_default_10(client, tmp_db):
    _seed_ranked(12)
    rows = client.get("/api/toppicks").get_json()["rows"]
    assert len(rows) == 10


def test_toppicks_limit_all(client, tmp_db):
    _seed_ranked(12)
    for q in ("all", "0"):
        rows = client.get(f"/api/toppicks?limit={q}").get_json()["rows"]
        assert len(rows) == 12, q


def test_toppicks_limit_explicit(client, tmp_db):
    _seed_ranked(5)
    rows = client.get("/api/toppicks?limit=2").get_json()["rows"]
    assert len(rows) == 2


def test_toppicks_limit_junk_falls_back_to_default(client, tmp_db):
    _seed_ranked(12)
    rows = client.get("/api/toppicks?limit=notanumber").get_json()["rows"]
    assert len(rows) == 10
