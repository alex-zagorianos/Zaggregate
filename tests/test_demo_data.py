"""Bundled sample inbox (plan §6.1) — pure loader + retire/show state.

Headless: no Tk, no DB. Proves the demo rows load in the Inbox row shape, are
clearly marked read-only, span the personas with a visible Score-vs-Fit split,
and that the show/retire lifecycle hides them once a real inbox exists.
"""
import json

import demo_data


def test_demo_rows_load_and_are_marked_readonly():
    rows = demo_data.demo_inbox_rows()
    assert 18 <= len(rows) <= 25, "expected ~20 sample rows"
    for r in rows:
        assert r["is_demo"] is True
        assert r["source"] == demo_data.DEMO_SOURCE
        assert r["id"] < 0                       # never collides with a real id
        # every key the Inbox renderer/detail-pane reads is present
        for k in ("score", "fit", "title", "company", "location",
                  "salary_text", "board_count", "description", "fit_why"):
            assert k in r


def test_demo_rows_show_score_vs_fit_split():
    """The whole point of the sample inbox is to demonstrate Score != Fit. At
    least a few rows must have a Score that diverges from the AI Fit grade."""
    rows = demo_data.demo_inbox_rows()
    diverging = [r for r in rows if abs(r["score"] - r["fit"]) >= 10]
    assert len(diverging) >= 3, "sample inbox should showcase Score-vs-Fit gaps"
    # Scores/fits are in the valid 0-100 band.
    for r in rows:
        assert 0 <= r["score"] <= 100
        assert 0 <= r["fit"] <= 100


def test_demo_rows_span_personas():
    rows = demo_data.demo_inbox_rows()
    blob = " ".join((r["title"] + " " + r["company"]).lower() for r in rows)
    for needle in ("software", "nurse", "mechanical", "controls", "data",
                   "consult", "marketing", "warehouse", "teacher", "account"):
        assert needle in blob, f"no sample row covers {needle!r}"
    # Locations are varied (not all one metro).
    assert len({r["location"] for r in rows}) >= 6


def test_demo_rows_have_varied_locations_including_remote():
    rows = demo_data.demo_inbox_rows()
    locs = " ".join(r["location"].lower() for r in rows)
    assert "remote" in locs


def test_bad_file_yields_empty(tmp_path):
    bad = tmp_path / "nope.json"
    assert demo_data.demo_inbox_rows(bad) == []
    bad.write_text("{ not json", encoding="utf-8")
    assert demo_data.demo_inbox_rows(bad) == []
    # a dict without "rows" -> []
    (tmp_path / "empty.json").write_text(json.dumps({"foo": 1}), encoding="utf-8")
    assert demo_data.demo_inbox_rows(tmp_path / "empty.json") == []


def test_show_and_retire_lifecycle(tmp_path):
    # Fresh machine, empty real inbox -> show the demo.
    assert demo_data.should_show_demo(tmp_path, real_inbox_count=0) is True
    assert demo_data.is_demo_retired(tmp_path) is False
    # A real inbox exists -> never show (and caller should retire).
    assert demo_data.should_show_demo(tmp_path, real_inbox_count=5) is False
    # Once retired, it stays hidden even with an empty inbox.
    demo_data.retire_demo(tmp_path)
    assert demo_data.is_demo_retired(tmp_path) is True
    assert demo_data.should_show_demo(tmp_path, real_inbox_count=0) is False
    # retire is idempotent.
    demo_data.retire_demo(tmp_path)
    assert demo_data.is_demo_retired(tmp_path) is True
