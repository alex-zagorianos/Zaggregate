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
