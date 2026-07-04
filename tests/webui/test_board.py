"""Kanban board API — /api/board shape, column order, card augmentation.

Asserts the board groups tracked applications into COLUMNS (in db.STATUSES order),
that each card carries days_in_stage / days_label / forward_targets, and that
forward_targets is correct for both a progression stage and a terminal stage (no
targets). Read-only route — no origin gate to exercise here.
"""
from tracker import db, service
from ui import kanban_core


def _add(title="Software Developer", company="Acme", **extra) -> int:
    return service.add_manual_job(title=title, company=company, **extra)


def test_board_empty_has_all_columns(client, tmp_db):
    resp = client.get("/api/board")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    statuses = [c["status"] for c in body["columns"]]
    # Column order == db.STATUSES order (== kanban_core.COLUMNS).
    assert statuses == kanban_core.COLUMNS
    assert statuses == db.STATUSES
    # Every column present, all empty.
    assert all(c["cards"] == [] for c in body["columns"])


def test_board_column_labels(client, tmp_db):
    body = client.get("/api/board").get_json()
    by_status = {c["status"]: c for c in body["columns"]}
    assert by_status["phone_screen"]["label"] == db.STATUS_LABELS["phone_screen"]


def test_board_places_card_in_its_column(client, tmp_db):
    a = _add(company="Acme")
    service.set_status(a, "interview")
    body = client.get("/api/board").get_json()
    by_status = {c["status"]: c for c in body["columns"]}
    assert [card["id"] for card in by_status["interview"]["cards"]] == [a]
    # Not lingering in its original column.
    assert by_status["interested"]["cards"] == []


def test_board_card_has_days_and_forward_targets(client, tmp_db):
    a = _add(company="Acme")
    service.set_status(a, "applied")
    body = client.get("/api/board").get_json()
    by_status = {c["status"]: c for c in body["columns"]}
    card = by_status["applied"]["cards"][0]
    # days_in_stage present (an int or None) + a matching label.
    assert "days_in_stage" in card
    assert "days_label" in card
    # forward_targets for a progression stage: immediate next step first.
    assert card["forward_targets"] == kanban_core.forward_targets("applied")
    assert card["forward_targets"][0] == "phone_screen"


def test_board_terminal_stage_has_no_forward_targets(client, tmp_db):
    a = _add(company="Acme")
    service.set_status(a, "rejected")
    body = client.get("/api/board").get_json()
    by_status = {c["status"]: c for c in body["columns"]}
    card = by_status["rejected"]["cards"][0]
    assert card["forward_targets"] == []        # terminal -> no advance offered


def test_board_days_in_stage_is_present_int(client, tmp_db):
    # A freshly-added 'applied' row (stamped today) reads 0 days in stage.
    a = _add(company="Acme")
    service.set_status(a, "applied")
    body = client.get("/api/board").get_json()
    by_status = {c["status"]: c for c in body["columns"]}
    card = by_status["applied"]["cards"][0]
    assert isinstance(card["days_in_stage"], int)
    assert card["days_in_stage"] == 0
    assert card["days_label"] == "today"


def test_board_drops_archived_rows(client, tmp_db):
    a = _add(company="Acme")
    service.archive_job(a)
    body = client.get("/api/board").get_json()
    # No card for the archived app anywhere on the board.
    all_ids = [card["id"] for c in body["columns"] for card in c["cards"]]
    assert a not in all_ids
