"""Insights units over the tracker tables (temp-db, read-only aggregation).

Covers the three B6 views on a hand-built fixture DB spanning multiple sources,
funnel stages, real status transitions, and interview rounds:
  * funnel()   — tracked/applied/interview/offer/accepted counts + rates + ghosted
  * by_source()— per source applied/interviews/interview_rate; >=1-applied only;
                 blank-source -> 'unknown' bucketing
  * cadence()  — weekly buckets from date_applied, current week, streak, avg

Plus the empty-db graceful path and the interview_rounds-folds-into-interview
behavior (a booked round counts as reaching interview even without a status move).
"""
import sqlite3
from datetime import date

import insights


# ── fixture builders ──────────────────────────────────────────────────────────

def _build(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE applications ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " title TEXT, company TEXT, location TEXT, url TEXT,"
        " salary_text TEXT, source TEXT, status TEXT,"
        " date_added TEXT, date_applied TEXT, notes TEXT)"
    )
    conn.execute(
        "CREATE TABLE status_history ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " job_id INTEGER, old_status TEXT, new_status TEXT, changed_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE interview_rounds ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " app_id INTEGER, round_no INTEGER, kind TEXT, scheduled_at TEXT,"
        " interviewer TEXT, notes TEXT, outcome TEXT)"
    )
    return conn


def _add_app(conn, job_id, status, source="manual",
             date_added="2026-06-01", date_applied=""):
    conn.execute(
        "INSERT INTO applications (id, title, company, location, url, "
        "salary_text, source, status, date_added, date_applied, notes) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (job_id, f"Job {job_id}", f"Co{job_id}", "Remote", f"http://x/{job_id}",
         "", source, status, date_added, date_applied, ""),
    )


def _hist(conn, job_id, transitions):
    for old, new, ts in transitions:
        conn.execute(
            "INSERT INTO status_history (job_id, old_status, new_status, changed_at) "
            "VALUES (?,?,?,?)",
            (job_id, old, new, ts),
        )


def _round(conn, app_id, kind="phone"):
    conn.execute(
        "INSERT INTO interview_rounds (app_id, round_no, kind) VALUES (?,?,?)",
        (app_id, 1, kind),
    )


def _seed(db_path):
    conn = _build(db_path)
    # Job 1: reached offer (full funnel), greenhouse.
    _add_app(conn, 1, "offer", source="greenhouse", date_applied="2026-06-02")
    _hist(conn, 1, [
        ("interested", "applied", "2026-06-02T00:00:00+00:00"),
        ("applied", "phone_screen", "2026-06-04T00:00:00+00:00"),
        ("phone_screen", "interview", "2026-06-06T00:00:00+00:00"),
        ("interview", "offer", "2026-06-08T00:00:00+00:00"),
    ])
    # Job 2: reached interview, greenhouse.
    _add_app(conn, 2, "interview", source="greenhouse", date_applied="2026-06-02")
    _hist(conn, 2, [
        ("interested", "applied", "2026-06-02T00:00:00+00:00"),
        ("applied", "phone_screen", "2026-06-08T00:00:00+00:00"),
        ("phone_screen", "interview", "2026-06-10T00:00:00+00:00"),
    ])
    # Job 3: only phone_screen, adzuna (NOT interview).
    _add_app(conn, 3, "phone_screen", source="adzuna", date_applied="2026-06-02")
    _hist(conn, 3, [
        ("interested", "applied", "2026-06-02T00:00:00+00:00"),
        ("applied", "phone_screen", "2026-06-06T00:00:00+00:00"),
    ])
    # Job 4: applied only, adzuna.
    _add_app(conn, 4, "applied", source="adzuna", date_applied="2026-06-03")
    _hist(conn, 4, [("interested", "applied", "2026-06-02T00:00:00+00:00")])
    # Job 5: currently rejected, but passed applied+phone_screen, lever.
    _add_app(conn, 5, "rejected", source="lever", date_applied="2026-06-02")
    _hist(conn, 5, [
        ("interested", "applied", "2026-06-02T00:00:00+00:00"),
        ("applied", "phone_screen", "2026-06-10T00:00:00+00:00"),
        ("phone_screen", "rejected", "2026-06-12T00:00:00+00:00"),
    ])
    # Job 6: interested only, no history, manual. (never applied)
    _add_app(conn, 6, "interested", source="manual", date_added="2026-05-20")
    # Job 7: ghosted terminal, adzuna (applied, then employer went silent).
    _add_app(conn, 7, "ghosted", source="adzuna", date_applied="2026-06-01")
    _hist(conn, 7, [
        ("interested", "applied", "2026-06-01T00:00:00+00:00"),
        ("applied", "ghosted", "2026-06-25T00:00:00+00:00"),
    ])
    conn.commit()
    return conn


# ── funnel ────────────────────────────────────────────────────────────────────

def test_funnel_counts(tmp_path):
    conn = _seed(tmp_path / "t.db")
    f = insights.funnel(conn)
    assert f["tracked"] == 7
    # applied: jobs 1-5 + 7 (job 6 never applied) = 6
    assert f["applied"] == 6
    # interview reach: jobs 1,2 (job 3 only phone_screen, not interview)
    assert f["interview"] == 2
    assert f["offer"] == 1
    assert f["accepted"] == 0
    assert f["ghosted"] == 1  # job 7 current status


def test_funnel_rates(tmp_path):
    conn = _seed(tmp_path / "t.db")
    f = insights.funnel(conn)
    # applied(6)/tracked(7)
    assert f["applied_rate"] == round(6 / 7, 4)
    # interview(2)/applied(6)
    assert f["interview_rate"] == round(2 / 6, 4)
    # offer(1)/interview(2)
    assert f["offer_rate"] == 0.5
    # accepted(0)/offer(1)
    assert f["accepted_rate"] == 0.0


def test_interview_round_folds_into_interview(tmp_path):
    """A booked interview round counts as reaching interview even when the row's
    status was never advanced past applied."""
    conn = _build(tmp_path / "r.db")
    _add_app(conn, 1, "applied", source="lever", date_applied="2026-06-10")
    _hist(conn, 1, [("interested", "applied", "2026-06-10T00:00:00+00:00")])
    _round(conn, 1, kind="phone")  # a scheduled round, status still 'applied'
    conn.commit()
    f = insights.funnel(conn)
    assert f["applied"] == 1
    assert f["interview"] == 1  # round pulled it into interview reach
    # and by_source reflects it too
    rows = {r["source"]: r for r in insights.by_source(conn)}
    assert rows["lever"]["interviews"] == 1
    assert rows["lever"]["interview_rate"] == 1.0


# ── by_source ─────────────────────────────────────────────────────────────────

def test_by_source_only_applied_sources_and_rates(tmp_path):
    conn = _seed(tmp_path / "t.db")
    rows = {r["source"]: r for r in insights.by_source(conn)}
    # 'manual' had only job 6 (interested, never applied) -> dropped entirely.
    assert "manual" not in rows
    # greenhouse: 2 applied, 2 interviews -> 1.0
    assert rows["greenhouse"]["applied"] == 2
    assert rows["greenhouse"]["interviews"] == 2
    assert rows["greenhouse"]["interview_rate"] == 1.0
    assert rows["greenhouse"]["low_n"] is True
    # adzuna: jobs 3,4,7 applied (3), 0 interviews
    assert rows["adzuna"]["applied"] == 3
    assert rows["adzuna"]["interviews"] == 0
    assert rows["adzuna"]["interview_rate"] == 0.0
    # lever: job 5 applied (1), 0 interviews
    assert rows["lever"]["applied"] == 1
    # sorted applied desc, then name: adzuna(3), greenhouse(2), lever(1)
    order = [r["source"] for r in insights.by_source(conn)]
    assert order == ["adzuna", "greenhouse", "lever"]


def test_by_source_blank_source_bucketed_unknown(tmp_path):
    conn = _build(tmp_path / "u.db")
    _add_app(conn, 1, "applied", source="", date_applied="2026-06-10")
    _hist(conn, 1, [("interested", "applied", "2026-06-10T00:00:00+00:00")])
    conn.commit()
    rows = {r["source"]: r for r in insights.by_source(conn)}
    assert "unknown" in rows
    assert rows["unknown"]["applied"] == 1


# ── cadence ───────────────────────────────────────────────────────────────────

def test_cadence_weekly_buckets_and_current_week(tmp_path):
    conn = _build(tmp_path / "c.db")
    # today anchored to a known Monday-week so bucketing is deterministic.
    today = date(2026, 6, 24)  # a Wednesday; ISO week starts Mon 2026-06-22
    # 3 applications in the current week, 2 the week before.
    for i, d in enumerate(["2026-06-22", "2026-06-23", "2026-06-24"]):
        _add_app(conn, i + 1, "applied", source="a", date_applied=d)
    for i, d in enumerate(["2026-06-16", "2026-06-18"]):
        _add_app(conn, 100 + i, "applied", source="a", date_applied=d)
    conn.commit()
    c = insights.cadence(conn, weeks=8, today=today)
    assert len(c["weeks"]) == 8
    assert c["weeks"][-1]["current"] is True
    assert c["weeks"][-1]["count"] == 3
    assert c["weeks"][-2]["count"] == 2
    assert c["current_week"] == 3
    # streak: current week (3) + prior week (2) both >=1 -> 2
    assert c["streak"] == 2
    # avg over 8 weeks = 5 total / 8
    assert c["per_week_avg"] == round(5 / 8, 2)
    assert c["target_min"] == 10 and c["target_max"] == 20


def test_cadence_streak_breaks_on_empty_current_week(tmp_path):
    conn = _build(tmp_path / "c2.db")
    today = date(2026, 6, 24)
    # applications only in a prior week, nothing this week -> streak 0.
    _add_app(conn, 1, "applied", source="a", date_applied="2026-06-15")
    conn.commit()
    c = insights.cadence(conn, weeks=8, today=today)
    assert c["current_week"] == 0
    assert c["streak"] == 0


def test_cadence_ignores_unapplied_rows(tmp_path):
    conn = _build(tmp_path / "c3.db")
    today = date(2026, 6, 24)
    # An 'interested' row with no date_applied must not count toward cadence.
    _add_app(conn, 1, "interested", source="a", date_applied="")
    conn.commit()
    c = insights.cadence(conn, weeks=8, today=today)
    assert c["current_week"] == 0
    assert sum(w["count"] for w in c["weeks"]) == 0


# ── empty / defensive ─────────────────────────────────────────────────────────

def test_empty_db_is_graceful(tmp_path):
    conn = _build(tmp_path / "empty.db")
    conn.commit()
    f = insights.funnel(conn)
    assert f["tracked"] == 0
    assert f["applied"] == 0 and f["interview"] == 0 and f["ghosted"] == 0
    assert f["applied_rate"] == 0.0 and f["interview_rate"] == 0.0
    assert insights.by_source(conn) == []
    c = insights.cadence(conn, weeks=8, today=date(2026, 6, 24))
    assert len(c["weeks"]) == 8
    assert c["current_week"] == 0 and c["streak"] == 0
    assert c["per_week_avg"] == 0.0


def test_missing_interview_rounds_table_does_not_crash(tmp_path):
    """A DB without the interview_rounds table still computes (older schemas)."""
    conn = sqlite3.connect(str(tmp_path / "no_rounds.db"))
    conn.execute(
        "CREATE TABLE applications ("
        " id INTEGER PRIMARY KEY, title TEXT, company TEXT, location TEXT,"
        " url TEXT, salary_text TEXT, source TEXT, status TEXT,"
        " date_added TEXT, date_applied TEXT, notes TEXT)"
    )
    conn.execute(
        "CREATE TABLE status_history ("
        " id INTEGER PRIMARY KEY, job_id INTEGER, old_status TEXT,"
        " new_status TEXT, changed_at TEXT)"
    )
    _add_app(conn, 1, "interview", source="manual", date_applied="2026-06-10")
    conn.commit()
    f = insights.funnel(conn)
    assert f["interview"] == 1  # status-based reach still works
    assert insights.by_source(conn)[0]["applied"] == 1
