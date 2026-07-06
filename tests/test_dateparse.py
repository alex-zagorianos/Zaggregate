"""Parity proof for dateparse.parse_flex_iso (finding #9).

search.freshness._parse_iso, search.search_engine._parse_created, and
match.ghost._parse_created all used to inline the identical tolerance loop
(only their not-found SENTINEL differed: None vs an _EPOCH datetime). This
asserts the shared helper's raw output is byte-identical to that legacy loop
across valid ISO strings, datetimes-with-tz, junk, and empty input, and that
each of the three call sites still produces its OWN historical sentinel/shape.
"""
from datetime import datetime, timezone

from dateparse import parse_flex_iso

_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


def _legacy_loop(value):
    """The exact loop all three modules used to inline."""
    if not value:
        return None
    s = value.strip().replace("Z", "+00:00")
    for candidate in (s, s[:19], s[:10]):
        try:
            dt = datetime.fromisoformat(candidate)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


FIXTURES = [
    "2026-07-05T10:30:00Z",
    "2026-07-05T10:30:00+00:00",
    "2026-07-05T10:30:00-05:00",
    "2026-07-05T10:30:00",
    "2026-07-05",
    "2026-07-05T10:30:00.123456Z",
    "not-a-date",
    "",
    "   ",
    "2026-13-99",  # invalid month/day
    "2026-07-05T10:30:00.123456+02:00",
]


def test_parity_matches_legacy_loop_on_fixture_battery():
    for raw in FIXTURES:
        assert parse_flex_iso(raw) == _legacy_loop(raw), f"mismatch for {raw!r}"


def test_none_and_empty_return_none():
    assert parse_flex_iso(None) is None
    assert parse_flex_iso("") is None


def test_naive_result_assumed_utc():
    dt = parse_flex_iso("2026-07-05T10:30:00")
    assert dt.tzinfo is not None
    assert dt.utcoffset().total_seconds() == 0


def test_z_suffix_normalized_to_utc_offset():
    a = parse_flex_iso("2026-07-05T10:30:00Z")
    b = parse_flex_iso("2026-07-05T10:30:00+00:00")
    assert a == b


# ── call-site parity: each module's own sentinel/guard is unchanged ───────────

def test_freshness_parse_iso_returns_none_sentinel():
    from search.freshness import _parse_iso
    assert _parse_iso(None) is None
    assert _parse_iso("") is None
    assert _parse_iso("garbage") is None
    assert _parse_iso(123) is None  # non-str guarded -> None, not a raise
    dt = _parse_iso("2026-07-05T10:30:00Z")
    assert dt == parse_flex_iso("2026-07-05T10:30:00Z")


def test_search_engine_parse_created_returns_epoch_sentinel():
    from search.search_engine import _parse_created, _EPOCH
    assert _EPOCH == _EPOCH  # sanity: module constant still present
    assert _parse_created("") == _EPOCH
    assert _parse_created("garbage") == _EPOCH
    assert _parse_created(None) == _EPOCH
    dt = _parse_created("2026-07-05T10:30:00Z")
    assert dt == parse_flex_iso("2026-07-05T10:30:00Z")


def test_ghost_parse_created_returns_epoch_sentinel_and_guards_non_str():
    from match.ghost import _parse_created, _EPOCH
    assert _parse_created("") == _EPOCH
    assert _parse_created("garbage") == _EPOCH
    assert _parse_created(None) == _EPOCH
    assert _parse_created(12345) == _EPOCH  # non-str guarded -> epoch, not a raise
    dt = _parse_created("2026-07-05T10:30:00Z")
    assert dt == parse_flex_iso("2026-07-05T10:30:00Z")


def test_ghost_stays_stdlib_only_no_search_import_chain():
    """match.ghost's own docstring promises it stays free of any search/scraper
    import chain; dateparse must not reintroduce that coupling."""
    import ast
    import inspect
    import dateparse as _dateparse_mod
    src = inspect.getsource(_dateparse_mod)
    tree = ast.parse(src)
    imported_names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_names.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_names.append(node.module)
    assert all(not name.startswith(("search", "scrape", "match"))
               for name in imported_names), imported_names
