"""Capture-recapture company-coverage estimate (coverage/registry_coverage.py)."""
import math

from coverage.registry_coverage import (domain_identity, estimate_coverage,
                                        name_identity)


def test_chapman_estimate_basic():
    # n1=4, n2=4, m=2  ->  N̂ = (5*5)/(2+1) - 1 = 7.33; observed union = 6.
    a = ["Alpha", "Beta", "Gamma", "Delta"]
    b = ["Gamma", "Delta", "Epsilon", "Zeta"]
    est = estimate_coverage(a, b)
    assert (est.n1, est.n2, est.overlap, est.observed) == (4, 4, 2, 6)
    assert est.defined
    assert 7.0 <= est.n_hat <= 7.7
    assert 78 <= est.coverage_pct <= 86
    lo, hi = est.ci95
    assert lo <= est.n_hat <= hi


def test_undefined_when_no_overlap():
    est = estimate_coverage(["a", "b"], ["c", "d"])
    assert est.overlap == 0
    assert not est.defined
    assert math.isnan(est.n_hat) and math.isnan(est.coverage_pct)


def test_name_identity_canonicalizes_and_dedupes():
    # Formatting variants of one company collapse to a single identity, so the
    # overlap count reflects real companies, not punctuation.
    a = ["Acme, Inc.", "Acme Inc"]
    est = estimate_coverage(a, ["Acme Inc"])
    assert est.n1 == 1 and est.overlap == 1


def test_company_entry_uses_name():
    from scrape.company_registry import CompanyEntry
    e = CompanyEntry("Acme Corp", "greenhouse", "acme", [])
    assert name_identity(e) == name_identity("Acme Corp")


def test_domain_identity_normalizes_urls():
    assert domain_identity("https://www.acme.com/careers") == domain_identity("acme.com")
    est = estimate_coverage(["https://www.acme.com/careers"], ["acme.com"],
                            key=domain_identity)
    assert est.overlap == 1


def test_summary_renders_without_error():
    est = estimate_coverage(["A", "B", "C"], ["B", "C", "D"])
    text = est.summary(label_a="registry", label_b="harvest")
    assert "coverage" in text.lower()
