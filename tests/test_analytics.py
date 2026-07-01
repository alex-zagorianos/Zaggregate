"""Funnel analytics over the tracker tables (temp-db, pure SQL aggregation).

Mirrors tests/test_inbox_health.py's temp-db seeding: build the two tables by
hand, seed rows spanning the funnel plus a couple of real status transitions,
then assert the stage rollup, a known conversion rate, response rate, a median
day-delta, and the per-source breakdown (including a low_n flag).
"""
import sqlite3

from tracker.analytics import funnel, by_source


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
    return conn


def _add_app(conn, job_id, status, source="manual", date_added="2026-06-01"):
    conn.execute(
        "INSERT INTO applications (id, title, company, location, url, "
        "salary_text, source, status, date_added, date_applied, notes) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (job_id, f"Job {job_id}", f"Co{job_id}", "Remote", f"http://x/{job_id}",
         "", source, status, date_added, "", ""),
    )


def _hist(conn, job_id, transitions):
    """transitions = list of (old, new, changed_at_iso)."""
    for old, new, ts in transitions:
        conn.execute(
            "INSERT INTO status_history (job_id, old_status, new_status, changed_at) "
            "VALUES (?,?,?,?)",
            (job_id, old, new, ts),
        )


def _seed(db_path):
    conn = _build(db_path)
    # Job 1: reached offer (full funnel). applied->phone in 2 days, phone->reject n/a.
    _add_app(conn, 1, "offer", source="greenhouse")
    _hist(conn, 1, [
        ("interested", "applied", "2026-06-02T00:00:00+00:00"),
        ("applied", "phone_screen", "2026-06-04T00:00:00+00:00"),   # 2-day response
        ("phone_screen", "interview", "2026-06-06T00:00:00+00:00"),
        ("interview", "offer", "2026-06-08T00:00:00+00:00"),
    ])
    # Job 2: reached interview. applied->phone in 6 days.
    _add_app(conn, 2, "interview", source="greenhouse")
    _hist(conn, 2, [
        ("interested", "applied", "2026-06-02T00:00:00+00:00"),
        ("applied", "phone_screen", "2026-06-08T00:00:00+00:00"),   # 6-day response
        ("phone_screen", "interview", "2026-06-10T00:00:00+00:00"),
    ])
    # Job 3: reached phone_screen.
    _add_app(conn, 3, "phone_screen", source="adzuna")
    _hist(conn, 3, [
        ("interested", "applied", "2026-06-02T00:00:00+00:00"),
        ("applied", "phone_screen", "2026-06-06T00:00:00+00:00"),   # 4-day response
    ])
    # Job 4: applied only, no further progress.
    _add_app(conn, 4, "applied", source="adzuna")
    _hist(conn, 4, [
        ("interested", "applied", "2026-06-02T00:00:00+00:00"),
    ])
    # Job 5: currently rejected, but passed through applied + phone_screen first.
    _add_app(conn, 5, "rejected", source="lever")
    _hist(conn, 5, [
        ("interested", "applied", "2026-06-02T00:00:00+00:00"),
        ("applied", "phone_screen", "2026-06-10T00:00:00+00:00"),   # 8-day response
        ("phone_screen", "rejected", "2026-06-12T00:00:00+00:00"),  # 10-day reject
    ])
    # Job 6: interested only, no history (defensive: zero transitions).
    _add_app(conn, 6, "interested", source="manual", date_added="2026-05-20")
    conn.commit()
    return conn


def test_counts_and_total(tmp_path):
    conn = _seed(tmp_path / "t.db")
    f = funnel(conn)
    assert f["total_tracked"] == 6
    assert f["counts"]["offer"] == 1
    assert f["counts"]["interview"] == 1
    assert f["counts"]["phone_screen"] == 1
    assert f["counts"]["applied"] == 1
    assert f["counts"]["rejected"] == 1
    assert f["counts"]["interested"] == 1
    # earliest date_added across the table
    assert f["tracked_since"] == "2026-05-20"


def test_stage_counts_at_least(tmp_path):
    conn = _seed(tmp_path / "t.db")
    f = funnel(conn)
    stages = {s["stage"]: s["count"] for s in f["stage_counts"]}
    # ordering preserved (D1: 'accepted' is the success terminal at the tail)
    assert [s["stage"] for s in f["stage_counts"]] == [
        "interested", "applied", "phone_screen", "interview", "offer", "accepted"
    ]
    # reached interested: all 6
    assert stages["interested"] == 6
    # reached applied: jobs 1-5 (job 6 never applied)
    assert stages["applied"] == 5
    # reached phone_screen: jobs 1,2,3,5 (4 stuck at applied, 6 at interested)
    assert stages["phone_screen"] == 4
    # reached interview: jobs 1,2
    assert stages["interview"] == 2
    # reached offer: job 1
    assert stages["offer"] == 1


def test_conversions(tmp_path):
    conn = _seed(tmp_path / "t.db")
    f = funnel(conn)
    conv = {(c["from"], c["to"]): c["rate"] for c in f["conversions"]}
    # applied(5) -> phone_screen(4) = 0.8
    assert conv[("applied", "phone_screen")] == 0.8
    # phone_screen(4) -> interview(2) = 0.5
    assert conv[("phone_screen", "interview")] == 0.5
    # interview(2) -> offer(1) = 0.5
    assert conv[("interview", "offer")] == 0.5
    # interested(6) -> applied(5)
    assert conv[("interested", "applied")] == round(5 / 6, 4)


def test_response_rate(tmp_path):
    conn = _seed(tmp_path / "t.db")
    f = funnel(conn)
    # share of APPLIED (5) that reached >= phone_screen (4) = 0.8
    assert f["response_rate"] == 0.8


def test_median_days_to_response(tmp_path):
    conn = _seed(tmp_path / "t.db")
    f = funnel(conn)
    # applied->first phone_screen deltas: 2, 6, 4, 8 days -> median = 5.0
    assert f["median_days_to_response"] == 5.0


def test_median_days_to_rejection(tmp_path):
    conn = _seed(tmp_path / "t.db")
    f = funnel(conn)
    # only job 5 rejected: applied 06-02 -> rejected 06-12 = 10 days
    assert f["median_days_to_rejection"] == 10.0


def test_by_source(tmp_path):
    conn = _seed(tmp_path / "t.db")
    rows = {r["source"]: r for r in by_source(conn)}
    # greenhouse: jobs 1,2 both applied, both interview+ -> response 1.0
    gh = rows["greenhouse"]
    assert gh["applied"] == 2
    assert gh["interview_plus"] == 2
    assert gh["interview_rate"] == 1.0  # D1: renamed from response_rate
    assert gh["low_n"] is True          # <5
    # adzuna: jobs 3 (phone),4 (applied) -> 2 applied, 1 interview_plus? no.
    az = rows["adzuna"]
    assert az["applied"] == 2
    assert az["interview_plus"] == 0    # neither reached interview
    # lever: job 5 rejected but passed through phone_screen (applied=1, no interview)
    lev = rows["lever"]
    assert lev["applied"] == 1
    assert lev["interview_plus"] == 0
    assert lev["low_n"] is True


def test_empty_db_is_graceful(tmp_path):
    conn = _build(tmp_path / "empty.db")
    conn.commit()
    f = funnel(conn)
    assert f["total_tracked"] == 0
    assert f["tracked_since"] is None
    assert f["response_rate"] == 0.0
    assert f["median_days_to_response"] is None
    assert f["median_days_to_rejection"] is None
    # every stage present at 0, no divide-by-zero in conversions
    assert all(s["count"] == 0 for s in f["stage_counts"])
    assert all(c["rate"] == 0.0 for c in f["conversions"])
    assert by_source(conn) == []


def test_missing_history_table_does_not_crash(tmp_path):
    """Defensive: applications present but no status_history table at all."""
    conn = sqlite3.connect(str(tmp_path / "no_hist.db"))
    conn.execute(
        "CREATE TABLE applications ("
        " id INTEGER PRIMARY KEY, title TEXT, company TEXT, location TEXT,"
        " url TEXT, salary_text TEXT, source TEXT, status TEXT,"
        " date_added TEXT, date_applied TEXT, notes TEXT)"
    )
    _add_app(conn, 1, "applied", source="manual")
    conn.commit()
    f = funnel(conn)
    # current-status fallback still places job 1 at >= applied
    stages = {s["stage"]: s["count"] for s in f["stage_counts"]}
    assert stages["applied"] == 1
    assert f["median_days_to_response"] is None     # no history to measure
    src = by_source(conn)
    assert src[0]["applied"] == 1
