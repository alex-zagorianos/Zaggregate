"""Tk-free source-health classifier core (S36 extraction from SearchTab).

Proves (a) the pure helpers work without importing tkinter, and (b) the tk
``SearchTab`` staticmethods now DELEGATE to this core (re-export parity), so the tk
tab and the web Search job classify source health identically. The delegation check
imports SearchTab lazily and skips if Tk isn't importable headless.
"""
import pytest

from ui import tab_search_core as core


# ── pure helpers (no Tk) ──────────────────────────────────────────────────────

def test_class_is_keyless_skipped_prefix_match():
    assert core.class_is_keyless_skipped("JoobleClient", ["jooble"]) is True
    assert core.class_is_keyless_skipped("AdzunaClient", ["jooble"]) is False
    assert core.class_is_keyless_skipped("", []) is False


def test_progress_line_keyless_vs_count():
    assert "needs a free key" in core.progress_line("JoobleClient", 3, 8, 0, True)
    assert core.progress_line("AdzunaClient", 1, 8, 12, False).endswith("(12)")


@pytest.mark.parametrize("row,expected", [
    ({"skipped_keyless": True}, "keyless"),
    ({"ok": True, "count": 5, "error": ""}, "ok"),
    ({"ok": True, "count": 0, "error": ""}, "ok"),                 # clean empty = ok
    ({"ok": True, "count": 5, "error": "some keyword 500"}, "ok"),  # had rows -> ok
    ({"ok": False, "count": 0, "error": "429 rate limit"}, "throttled"),
    ({"ok": False, "count": 0, "error": "401 auth"}, "keyless"),
    ({"ok": False, "count": 0, "error": "boom"}, "failed"),
])
def test_source_status(row, expected):
    assert core.source_status(row) == expected


def test_health_summary_line_counts():
    rows = [{"ok": True, "count": 5}, {"skipped_keyless": True},
            {"ok": False, "count": 0, "error": "429"},
            {"ok": False, "count": 0, "error": "boom"}]
    line = core.health_summary_line(rows)
    assert line == ("Sources: 1 ok, 1 skipped (no key), 1 throttled, 1 failed  "
                    "(details)")


def test_health_summary_line_empty():
    assert core.health_summary_line([]) == ""


def test_health_details_text():
    rows = [{"source": "Bee", "ok": True, "count": 3},
            {"source": "Ant", "skipped_keyless": True},
            {"source": "Cat", "ok": False, "error": "boom"}]
    txt = core.health_details_text(rows)
    # sorted by source lower: Ant, Bee, Cat
    assert txt.splitlines() == [
        "Ant: skipped — needs a free key",
        "Bee: 3 result(s)",
        "Cat: FAILED — boom",
    ]


# ── tk re-export parity ───────────────────────────────────────────────────────

def test_searchtab_delegates_to_core():
    """The tk SearchTab staticmethods must BE the core functions (re-export), so a
    palette/logic change in the core propagates to the tk tab with no drift."""
    try:
        from ui.tab_search import SearchTab
    except Exception:  # pragma: no cover - headless Tk import guard
        pytest.skip("tkinter not importable headless")
    assert SearchTab._class_is_keyless_skipped("JoobleClient", ["jooble"]) is True
    assert SearchTab._health_summary_line([{"ok": True, "count": 1}]) == \
        core.health_summary_line([{"ok": True, "count": 1}])
    assert SearchTab._health_details_text([{"source": "A", "ok": True, "count": 2}]) == \
        core.health_details_text([{"source": "A", "ok": True, "count": 2}])
    assert SearchTab._progress_line("AdzunaClient", 1, 3, 4, False) == \
        core.progress_line("AdzunaClient", 1, 3, 4, False)
