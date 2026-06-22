from models import JobResult
from geo.filter import filter_to_metro

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
