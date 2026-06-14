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

def test_dedup_collapses_same_title_company_location():
    eng = SearchEngine([])
    a = _job(title="Eng", company="Acme", location="Cincinnati", url="x")
    b = _job(title="Eng", company="Acme", location="Cincinnati", url="y")
    assert len(eng._deduplicate([a, b])) == 1


# ── location score ──────────────────────────────────────────────────────────

def test_location_score_prefers_match():
    assert _location_score("Cincinnati, OH", "Cincinnati") > _location_score("Austin, TX", "Cincinnati")


def test_location_score_remote_zero_for_local_search():
    assert _location_score("Remote", "Cincinnati") == 0
