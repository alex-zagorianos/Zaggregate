"""SEARCH-5: _normalize_location must return the caller's location verbatim
(trimmed only) and never append a state. Calling it unbound with ``self=None``
proves it doesn't touch instance state."""
from search.usajobs_client import USAJobsClient

norm = USAJobsClient._normalize_location


def test_comma_less_location_unchanged():
    assert norm(None, "Austin") == "Austin"


def test_remote_not_rewritten_to_state():
    assert norm(None, "Remote") == "Remote"


def test_location_with_comma_kept_as_is():
    assert norm(None, "Cincinnati, OH") == "Cincinnati, OH"


def test_whitespace_stripped():
    assert norm(None, "  Denver  ") == "Denver"
