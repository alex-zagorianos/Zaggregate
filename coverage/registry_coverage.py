"""Measure how complete the company registry is — capture-recapture on two
INDEPENDENT company lists.

The standing worry with a hand-/LLM-grown registry is that its completeness is
unmeasurable: "are we finding as many of the relevant employers as we can?"
Capture-recapture answers it with a number. Treat two independently-built company
lists as two capture occasions; the size of their overlap reveals the size of the
unseen population:

    N̂  = (n1+1)(n2+1)/(m+1) - 1        (Chapman — bias-corrected Lincoln-Petersen)
    coverage = observed_union / N̂

VALIDITY DEPENDS ON INDEPENDENCE of the two lists.
  GOOD pairs (genuinely independent):
    - current registry  vs.  a Common-Crawl ATS harvest   (our curation vs. web archive)
    - current registry  vs.  a firmographic export         (PDL / AtoZ / library DB)
  BAD pair (correlated → N̂ inflated, coverage looks better than reality):
    - registry vs. the LLM enumerator seeded from the registry's own gaps.

The two lists must also share ONE identity space (both names, or both domains),
or the overlap is spuriously zero. `coverage.estimators.chapman` does the math.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from coverage.entity import canonicalize_company
from coverage.estimators import chapman


def name_identity(item) -> str:
    """Canonical company NAME identity (the default, since ATS registry entries
    carry a name but not always a domain). Accepts a CompanyEntry or a string."""
    name = getattr(item, "name", None)
    raw = name if name is not None else str(item or "")
    return canonicalize_company(raw)


def domain_identity(item) -> str:
    """Registrable-domain identity, for comparing two domain/URL-based lists.
    A CompanyEntry's ``slug`` is only a domain for the 'direct' (full-URL) type;
    ATS slugs have no domain, so those collapse to '' and are ignored."""
    from discover.enumerate import normalize_domain
    slug = getattr(item, "slug", None)
    raw = slug if slug is not None else str(item or "")
    return normalize_domain(raw)


@dataclass
class CoverageEstimate:
    n1: int                 # distinct identities in list A
    n2: int                 # distinct identities in list B
    overlap: int            # identities in BOTH (recaptures, m)
    observed: int           # union — what we've actually seen
    n_hat: float            # estimated true population (nan if undefined)
    ci95: tuple             # 95% CI on n_hat
    coverage_pct: float     # observed / n_hat * 100, capped at 100 (nan if undefined)

    @property
    def defined(self) -> bool:
        return not math.isnan(self.n_hat)

    def summary(self, *, label_a: str = "list A", label_b: str = "list B") -> str:
        lines = [
            "Company-registry coverage (capture-recapture)",
            f"  {label_a:<22} n1 = {self.n1}",
            f"  {label_b:<22} n2 = {self.n2}",
            f"  overlap (m)            = {self.overlap}",
            f"  observed (union)       = {self.observed}",
        ]
        if not self.defined:
            lines.append("  estimate               = UNDEFINED (no overlap — lists "
                         "may be disjoint, too small, or not in the same identity space)")
            return "\n".join(lines)
        lo, hi = self.ci95
        lines += [
            f"  estimated universe N̂   = {self.n_hat:.0f}  (95% CI {lo:.0f}–{hi:.0f})",
            f"  estimated coverage     = {self.coverage_pct:.1f}%  "
            f"(~{max(0, round(self.n_hat) - self.observed)} employers still unseen)",
        ]
        return "\n".join(lines)


def estimate_coverage_industry(industry, list_b, *, user_json=None,
                               key=name_identity) -> CoverageEstimate:
    """Capture-recapture with list A scoped to one industry's registry slice.

    list A = get_registry(industry=industry); list B = an INDEPENDENT list (a
    dataset/host harvest — never the LLM enumerator). Empty/None industry = the
    whole registry (same as estimate_coverage over get_registry())."""
    from scrape.company_registry import get_registry
    registry = get_registry(industry=industry or None, user_json=user_json)
    return estimate_coverage(registry, list_b, key=key)


def loop_signal(history, *, plateau_growth: float = 0.02,
                plateau_cov: float = 85.0) -> str:
    """Convergence verdict for a loop-until-dry acquisition run, from an ordered
    coverage history (oldest→newest; each entry has 'observed' + 'coverage_pct').

    - 'dry'      the last round added NO new companies (union flat) → exhausted.
    - 'plateau'  union grew <plateau_growth for the last TWO rounds AND estimated
                 coverage ≥ plateau_cov% → good enough, stop.
    - 'rising'   still climbing (or not enough data yet) → keep going.
    """
    hist = [h for h in (history or []) if h.get("observed") is not None]
    if len(hist) < 2:
        return "rising"
    last, prev = hist[-1], hist[-2]
    if last["observed"] <= prev["observed"]:
        return "dry"

    def _growth(a, b):
        return (a["observed"] - b["observed"]) / b["observed"] if b["observed"] else 0.0

    g1 = _growth(last, prev)
    cov = last.get("coverage_pct")
    if len(hist) >= 3:
        g2 = _growth(prev, hist[-3])
        if (g1 < plateau_growth and g2 < plateau_growth
                and cov is not None and cov >= plateau_cov):
            return "plateau"
    return "rising"


def estimate_coverage(list_a, list_b, *, key=name_identity) -> CoverageEstimate:
    """Capture-recapture estimate of the true company universe from two lists.

    `key` maps each item to a comparable identity (default: canonical name; pass
    `domain_identity` for two domain/URL lists). Empty identities are dropped.
    Returns a CoverageEstimate; if the lists don't overlap the estimate is
    undefined (n_hat = nan) and only the observed counts are meaningful.
    """
    a = {k for k in (key(x) for x in list_a) if k}
    b = {k for k in (key(x) for x in list_b) if k}
    n1, n2 = len(a), len(b)
    m = len(a & b)
    observed = len(a | b)
    if m == 0:
        nan = float("nan")
        return CoverageEstimate(n1, n2, 0, observed, nan, (nan, nan), nan)
    res = chapman(n1, n2, m)
    cov = min(100.0, observed / res.n_hat * 100) if res.n_hat > 0 else float("nan")
    return CoverageEstimate(n1, n2, m, observed, res.n_hat, res.ci95, cov)
