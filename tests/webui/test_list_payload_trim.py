"""List-context serializers (inbox_row_list / app_row_list) drop ``description``
from LIST responses (inbox, board, applications, queue, toppicks) — the frontend
list views never render a preview, so the field is dead weight on every page load.
DETAIL routes (inbox detail, single application) must keep the full field.
"""
from models import JobResult
from tracker import db, service


_LOOPBACK = "http://127.0.0.1:5002"
_DESC = "We are looking for a fantastic engineer to join our fantastic team."


def _job(url, title="Software Developer", company="Acme", description=_DESC):
    return JobResult(title=title, company=company, location="Cincinnati, OH",
                     salary_min=None, salary_max=None, description=description,
                     url=url, source_keyword="", created="2026-06-21",
                     source_api="adzuna", score=70)


def _seed_inbox_row(url="https://x/1") -> int:
    db.inbox_add_many([_job(url)])
    return db.inbox_all()[0]["id"]


def _seed_app(**extra) -> int:
    fields = dict(title="Software Developer", company="Acme", location="Remote",
                  url=extra.pop("url", "https://x/app/1"), salary_text="",
                  source="manual", status=extra.pop("status", "interested"),
                  description=extra.pop("description", _DESC))
    fields.update(extra)
    return service.add_manual_job(**fields)


# ── /api/inbox list ────────────────────────────────────────────────────────────

def test_inbox_list_drops_description(client, tmp_db):
    _seed_inbox_row()
    body = client.get("/api/inbox").get_json()
    rows = body["rows"]
    assert len(rows) == 1
    assert "description" not in rows[0]


def test_inbox_detail_keeps_description(client, tmp_db):
    inbox_id = _seed_inbox_row()
    body = client.get(f"/api/inbox/{inbox_id}/detail").get_json()
    assert body["ok"] is True
    # The nested row keeps the full engine column...
    assert body["row"].get("description") == _DESC
    # ...and the route's own preview field is still produced.
    assert "description_preview" in body
    assert body["description_preview"]


# ── /api/board ──────────────────────────────────────────────────────────────────

def test_board_drops_description(client, tmp_db):
    a = _seed_app()
    service.set_status(a, "applied")
    body = client.get("/api/board").get_json()
    by_status = {c["status"]: c for c in body["columns"]}
    card = by_status["applied"]["cards"][0]
    assert "description" not in card


# ── /api/applications list ───────────────────────────────────────────────────────

def test_applications_list_drops_description(client, tmp_db):
    _seed_app()
    rows = client.get("/api/applications").get_json()["rows"]
    assert len(rows) == 1
    assert "description" not in rows[0]


def test_application_detail_keeps_description(client, tmp_db):
    a = _seed_app()
    body = client.get(f"/api/applications/{a}").get_json()
    assert body["ok"] is True
    assert body["job"].get("description") == _DESC


# ── /api/queue list ──────────────────────────────────────────────────────────────

def test_queue_list_drops_description(client, tmp_db):
    _seed_app()
    rows = client.get("/api/queue").get_json()["rows"]
    assert len(rows) == 1
    assert "description" not in rows[0]


def test_queue_resume_prompt_still_reads_description(client, tmp_db):
    """The resume-prompt route fetches the job fresh via service.get_job (not
    through the list serializer), so trimming the LIST payload must not starve it
    of the description it needs to build the prompt."""
    a = _seed_app()
    resp = client.get(f"/api/queue/{a}/resume-prompt")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert _DESC in body["prompt"]


# ── /api/toppicks ────────────────────────────────────────────────────────────────

def test_toppicks_drops_description(client, tmp_db):
    db.inbox_add_many([_job("https://x/top/1")])
    rows = db.inbox_all()
    b = service.new_rec_batch()
    db.inbox_merge_extras(rows[0]["id"], service.rank_patch(1, b))
    body = client.get("/api/toppicks").get_json()
    assert len(body["rows"]) == 1
    assert "description" not in body["rows"][0]


# ── ghost badge on inbox list rows (B7 item 1/2) ─────────────────────────────────

def _old_job(url, days_ago):
    """An inbox row whose ``created`` is ``days_ago`` days back, so the ghost age
    signal fires deterministically (>45 stale, 30-45 aging)."""
    from datetime import datetime, timedelta, timezone
    created = (datetime.now(timezone.utc) - timedelta(days=days_ago)).date().isoformat()
    return JobResult(title="Software Developer", company="Acme",
                     location="Cincinnati, OH", salary_min=90000, salary_max=None,
                     description=_DESC, url=url, source_keyword="",
                     created=created, source_api="adzuna", score=70)


def test_inbox_list_row_carries_ghost_badge(client, tmp_db):
    """Every list row gains a ``ghost`` badge {level, reasons} from ghost_score."""
    db.inbox_add_many([_job("https://x/g1")])
    row = client.get("/api/inbox").get_json()["rows"][0]
    assert "ghost" in row
    assert set(row["ghost"]) == {"level", "reasons"}
    assert row["ghost"]["level"] in ("fresh", "aging", "stale", "unknown")
    assert isinstance(row["ghost"]["reasons"], list)


def test_inbox_list_flags_a_stale_row_with_reasons(client, tmp_db):
    """A 60-day-old posting comes back level 'stale' with an age reason surfaced
    (longevity — from the existing ghost_score signals, no new mechanism)."""
    db.inbox_add_many([_old_job("https://x/stale", days_ago=60)])
    row = client.get("/api/inbox").get_json()["rows"][0]
    assert row["ghost"]["level"] == "stale"
    assert any("60d" in r or "stale" in r for r in row["ghost"]["reasons"])


def test_inbox_list_flags_aging_row(client, tmp_db):
    """A ~35-day-old posting reads 'aging' (30-45 day band)."""
    db.inbox_add_many([_old_job("https://x/aging", days_ago=35)])
    row = client.get("/api/inbox").get_json()["rows"][0]
    assert row["ghost"]["level"] == "aging"


def test_ghost_badge_never_hides_rows(client, tmp_db):
    """The badge only ANNOTATES — a stale row is still returned in the list (the
    opt-in hide_stale filter stays the only hiding mechanism)."""
    db.inbox_add_many([_old_job("https://x/keep", days_ago=90)])
    rows = client.get("/api/inbox").get_json()["rows"]
    assert len(rows) == 1  # present despite being stale


def test_ghost_badge_reasons_capped(client, tmp_db):
    """Reasons are capped so the tooltip stays short (<=4)."""
    db.inbox_add_many([_old_job("https://x/cap", days_ago=90)])
    row = client.get("/api/inbox").get_json()["rows"][0]
    assert len(row["ghost"]["reasons"]) <= 4
