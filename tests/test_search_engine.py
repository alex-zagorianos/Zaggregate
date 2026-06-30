from datetime import datetime, timezone

from search.search_engine import SearchEngine, _location_score, _parse_created
from models import JobResult


def _job(created="", location="", title="t", company="c", url=""):
    return JobResult(
        title=title, company=company, location=location, salary_min=None,
        salary_max=None, description="", url=url, source_keyword="k",
        created=created, job_id="", source_api="adzuna",
    )


# ── date parsing / sort ───────────────────────────────────────────────────────

def test_parse_created_handles_mixed_formats():
    z = _parse_created("2026-06-01T12:00:00Z")        # Z suffix
    offset = _parse_created("2026-06-01T08:00:00-05:00")  # offset == 13:00 UTC
    date_only = _parse_created("2026-05-30")
    assert z < offset                                  # 12:00Z before 13:00Z
    assert date_only < z
    assert _parse_created("").tzinfo is not None       # empty sinks to epoch, still aware


def test_full_search_sorts_by_date_descending():
    class Stub:
        def __init__(self, jobs): self._jobs = jobs
        def search_and_parse(self, keyword, location, salary_min, page):
            return self._jobs if page == 1 else []

    older = _job(created="2026-05-01", url="u1", title="Older", company="A")
    newer = _job(created="2026-06-01T00:00:00Z", url="u2", title="Newer", company="B")
    eng = SearchEngine([Stub([older, newer])])
    out = eng.run_full_search(["k"], max_pages_per_keyword=1, sort_by="date")
    assert [j.url for j in out] == ["u2", "u1"]


# ── dedup ─────────────────────────────────────────────────────────────────────

def test_dedup_collapses_same_url_across_location_variants():
    # identity_key is URL-primary: the SAME posting harvested with differing
    # location strings ("", "Remote", "Cincinnati, OH" vs "Ohio") collapses.
    eng = SearchEngine([])
    a = _job(title="Eng", company="Acme", location="Cincinnati, OH",
             url="https://acme.com/jobs/42")
    b = _job(title="Eng", company="Acme", location="Ohio",
             url="https://acme.com/jobs/42?utm_source=foo")
    assert len(eng._deduplicate([a, b])) == 1


def test_dedup_keeps_distinct_reqs_at_different_urls():
    # Same title/company/location but DIFFERENT URLs are distinct reqs and must
    # NOT merge (the old dedup_key wrongly collapsed them to one).
    eng = SearchEngine([])
    a = _job(title="Eng", company="Acme", location="Cincinnati", url="x")
    b = _job(title="Eng", company="Acme", location="Cincinnati", url="y")
    assert len(eng._deduplicate([a, b])) == 2


def test_dedup_url_less_jobs_fall_back_to_title_company():
    # No URL on either -> identity_key falls back to title|company (no location),
    # so location-only variants of the same posting still collapse.
    eng = SearchEngine([])
    a = _job(title="Eng", company="Acme", location="Cincinnati", url="")
    b = _job(title="Eng", company="Acme", location="Remote", url="")
    assert len(eng._deduplicate([a, b])) == 1


# ── location score ──────────────────────────────────────────────────────────

def test_location_score_prefers_match():
    assert _location_score("Cincinnati, OH", "Cincinnati") > _location_score("Austin, TX", "Cincinnati")


def test_location_score_remote_credited_when_remote_ok():
    # Remote is first-class: an acceptable-remote role gets full location credit
    # (not 0), so it ranks fairly when the user is open to remote.
    assert _location_score("Remote", "Cincinnati") == 3            # default remote_ok=True
    assert _location_score("Remote", "Cincinnati", remote_ok=True) == 3


def test_location_score_remote_zero_when_remote_not_ok():
    # Local-only users (remote_ok=False) still score a remote-only role 0.
    assert _location_score("Remote", "Cincinnati", remote_ok=False) == 0


def test_location_score_hybrid_unaffected_by_remote_flag():
    # A hybrid "Cincinnati, OH - Remote" matches the metro token regardless.
    assert _location_score("Cincinnati, OH - Remote", "Cincinnati", remote_ok=False) > 0


def test_state_map_covers_previously_missing_states():
    # TRACK-6: full 50-state + DC map. Oregon/Maine were unscored before.
    from search.search_engine import _STATE_ABBREVS
    assert _STATE_ABBREVS["oregon"] == "or"
    assert _STATE_ABBREVS["maine"] == "me"
    assert len(_STATE_ABBREVS) == 51  # 50 states + DC
    # full-name target now resolves to the abbrev in the job location
    assert _location_score("Portland, OR", "Oregon") > 0
