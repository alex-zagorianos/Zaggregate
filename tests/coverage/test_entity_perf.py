"""normalize_title perf hardening (efficiency item): lru_cache the function, hoist
the O*NET key list into a cached loader, and pass score_cutoff to extractOne. These
are pure-function optimizations -- behavior must be IDENTICAL, verified here without
any timing assertion."""
from coverage import entity as E


def test_normalize_title_is_cached_and_stable():
    a = E.normalize_title("Senior Software Developer")
    b = E.normalize_title("Senior Software Developer")
    # lru_cache -> same object identity on repeat calls, and stable fields.
    assert a is b
    assert a.soc_code.startswith("15-1252")
    assert a.seniority and "senior" in a.seniority


def test_onet_keys_matches_table_keys():
    # The hoisted key list must be exactly the table's keys (no drift).
    assert E._onet_keys() == list(E._onet().keys())


def test_known_exact_match_unchanged():
    # An exact alt-title key resolves at confidence 1.0 (unchanged by the cache).
    nt = E.normalize_title("Senior Software Developer")
    assert nt.confidence == 1.0
    assert nt.soc_code.startswith("15-1252")


def test_unmatched_title_returns_placeholder():
    nt = E.normalize_title("zxqw blorp")
    assert nt.soc_code == "00-0000"
    assert nt.confidence == 0.0


def test_fuzzy_still_resolves_near_match():
    # A slight variant of a real title should still fuzzy-resolve above the floor
    # (the score_cutoff only rejects BELOW-floor matches, which were rejected before).
    nt = E.normalize_title("Software Developers")  # plural of a canonical alt title
    assert nt.soc_code != "00-0000"
    assert nt.confidence >= E._CONF_FLOOR
