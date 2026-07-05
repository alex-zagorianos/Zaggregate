"""Insights route — GET /api/insights (read-only funnel + by_source + cadence).

Seeds a couple of applications through the real tracker.db API (so the route,
which reads the ACTIVE project DB via insights.compute, sees them) and asserts
the envelope carries all three views with the expected shape.
"""


def test_insights_empty_envelope(client, tmp_db):
    r = client.get("/api/insights")
    body = r.get_json()
    assert r.status_code == 200 and body["ok"] is True
    assert body["funnel"]["tracked"] == 0
    assert body["by_source"] == []
    # cadence always returns a full 8-week window, even empty.
    assert len(body["cadence"]["weeks"]) == 8
    assert body["cadence"]["target_min"] == 10
    assert body["cadence"]["target_max"] == 20


def test_insights_reflects_tracked_applications(client, tmp_db):
    from tracker import db

    # Two applied jobs (one advanced to interview), one still interested.
    a1 = db.add_job(title="Controls Engineer", company="Acme",
                    source="greenhouse", status="applied")
    db.add_job(title="Firmware Engineer", company="Globex",
               source="adzuna", status="applied")
    db.add_job(title="ME", company="Initech", source="manual",
               status="interested")
    # Advance a1 to interview (records a status_history transition).
    db.update_job(a1, status="interview")

    r = client.get("/api/insights")
    body = r.get_json()
    assert body["ok"] is True

    f = body["funnel"]
    assert f["tracked"] == 3
    assert f["applied"] == 2       # the two applied (interested one never applied)
    assert f["interview"] == 1     # a1 advanced

    # by_source: only sources with >=1 applied -> greenhouse + adzuna, not manual.
    srcs = {row["source"]: row for row in body["by_source"]}
    assert set(srcs) == {"greenhouse", "adzuna"}
    assert srcs["greenhouse"]["interviews"] == 1
    assert srcs["greenhouse"]["interview_rate"] == 1.0
    assert srcs["adzuna"]["interviews"] == 0
