from models import JobResult
from geo.filter import (
    filter_to_metro, classify, location_visible,
    LOCATION_MODES, DEFAULT_LOCATION_MODE,
)

def _j(location, title="Engineer"):
    return JobResult(title=title, company="C", location=location, salary_min=None, salary_max=None,
                     description="", url="", source_keyword="kw", created="2026-06-22", source_api="s")

def test_keeps_metro_match():
    jobs = [_j("Cincinnati, OH"), _j("San Francisco, CA")]
    out = filter_to_metro(jobs, "Cincinnati, OH")
    assert [j.location for j in out] == ["Cincinnati, OH"]

def test_keeps_unknown_location():
    out = filter_to_metro([_j("")], "Cincinnati, OH")
    assert len(out) == 1  # empty location kept (don't over-cut)

def test_remote_region_us_keeps_us_remote_drops_global():
    jobs = [_j("Remote - US"), _j("Remote - Worldwide")]
    out = filter_to_metro(jobs, "Cincinnati, OH", remote_region="us")
    locs = [j.location for j in out]
    assert "Remote - US" in locs
    assert "Remote - Worldwide" not in locs

def test_no_remote_region_keeps_all_remote():
    jobs = [_j("Remote - Worldwide")]
    assert len(filter_to_metro(jobs, "Cincinnati, OH")) == 1


# ── classify() — agnostic location bucketing for the Inbox view-filter ──────────
def test_classify_local_remote_elsewhere_unknown():
    assert classify("Cincinnati, OH", "Engineer", "Cincinnati, OH") == "local"
    assert classify("Remote - US", "Engineer", "Cincinnati, OH") == "remote"
    assert classify("San Francisco, CA", "Engineer", "Cincinnati, OH") == "elsewhere"
    assert classify("", "Engineer", "Cincinnati, OH") == "unknown"


def test_classify_is_agnostic_across_metros():
    # Same code, different home areas — no Cincinnati special-casing.
    assert classify("Austin, TX", "Dev", "Austin, TX") == "local"
    assert classify("Austin, TX", "Dev", "Seattle, WA") == "elsewhere"
    assert classify("Seattle, WA", "Dev", "Seattle, WA") == "local"
    assert classify("Cincinnati, OH", "Dev", "Seattle, WA") == "elsewhere"


def test_classify_metro_match_wins_over_remote_tag():
    # A hybrid "City - Remote" posting counts as local (metro match wins).
    assert classify("Cincinnati, OH - Remote", "Engineer", "Cincinnati, OH") == "local"


def test_classify_remote_not_ok_is_elsewhere():
    assert classify("Remote - US", "E", "Cincinnati, OH", remote_ok=False) == "elsewhere"
    # ...but a local job is still local even when remote isn't wanted.
    assert classify("Cincinnati, OH", "E", "Cincinnati, OH", remote_ok=False) == "local"


# ── location_visible() — the predicate the Inbox Location dropdown applies ───────
def test_visible_local_plus_remote_keeps_local_remote_unknown():
    A, m = "Cincinnati, OH", "Local + remote"
    assert location_visible("Cincinnati, OH", "E", A, m)
    assert location_visible("Remote - US", "E", A, m)
    assert location_visible("", "E", A, m)              # unknown kept (don't over-cut)
    assert not location_visible("Austin, TX", "E", A, m)


def test_visible_local_only_hides_remote_keeps_unknown():
    A, m = "Cincinnati, OH", "Local only"
    assert location_visible("Cincinnati, OH", "E", A, m)
    assert not location_visible("Remote - US", "E", A, m)
    assert location_visible("", "E", A, m)
    assert not location_visible("Austin, TX", "E", A, m)


def test_visible_all_locations_shows_everything():
    A, m = "Cincinnati, OH", "All locations"
    for loc in ("Cincinnati, OH", "Remote - US", "Austin, TX", ""):
        assert location_visible(loc, "E", A, m)


def test_visible_unknown_mode_fails_open_to_all_locations():
    # A garbage/unknown mode (typo'd query param, outdated frontend enum) must
    # behave as "All locations", NEVER as the strictest local view (inclusion
    # over precision — scenario finding MINOR-1).
    A = "Cincinnati, OH"
    for m in ("NotARealMode", "local only", "LOCAL_ONLY", "", None):
        for loc in ("Cincinnati, OH", "Remote - US", "Austin, TX", ""):
            assert location_visible(loc, "E", A, m), (m, loc)


def test_default_mode_is_local_plus_remote():
    assert DEFAULT_LOCATION_MODE == "Local + remote"
    assert DEFAULT_LOCATION_MODE in LOCATION_MODES
    assert len(LOCATION_MODES) == 3
