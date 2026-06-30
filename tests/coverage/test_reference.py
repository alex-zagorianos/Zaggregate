from models import JobResult
from coverage.reference import reference_coverage
from coverage.resolve import resolve

def _j(title, company="Acme", location="Cincinnati, OH", source="ref"):
    return JobResult(title=title, company=company, location=location, salary_min=None, salary_max=None,
                     description="", url="", source_keyword="kw", created="2026-06-22", source_api=source)

def test_none_provider_returns_none():
    assert reference_coverage("A", ["15-1252.00"], [], None, None).cov_proxy_weighted is None

def test_perfect_overlap_proxy_one():
    ours = resolve([_j("Software Developer", source="ours")])
    provider = lambda area, groups: [_j("Software Developer")]
    assert reference_coverage("A", ["15-1252.00"], ours, provider, None).cov_proxy_weighted == 1.0

def test_partial_overlap():
    ours = resolve([_j("Software Developer", source="ours")])
    provider = lambda area, groups: [_j("Software Developer"), _j("Mechanical Engineer")]
    cov = reference_coverage("A", [], ours, provider, None).cov_proxy_weighted
    assert 0 < cov < 1
