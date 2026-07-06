from __future__ import annotations
from pathlib import Path
import config
from coverage import report as _report
from coverage.estimators import (chao2, chapman, good_turing, jackknife1,
                                 jackknife2, loglinear, loglinear_ci)
from coverage.independence import collapse_sources
from coverage.jolts import jolts_gate
from coverage.reference import reference_coverage
from coverage.report import CoverageReport
from coverage.resolve import resolve

_WEIGHTS = {"cov_cr": 0.5, "cov_proxy_weighted": 0.3, "c_hat": 0.2}

def _clamp_fraction(observed: int, n_hat) -> float | None:
    if n_hat is None or n_hat <= 0:
        return None
    return max(0.0, min(1.0, observed / n_hat))

def _composite(cov_cr, cov_proxy_weighted, c_hat) -> float:
    legs = {"cov_cr": cov_cr, "cov_proxy_weighted": cov_proxy_weighted, "c_hat": c_hat}
    present = {k: v for k, v in legs.items() if v is not None}
    if not present:
        return 0.0
    num = sum(_WEIGHTS[k] * v for k, v in present.items())
    den = sum(_WEIGHTS[k] for k in present)
    return 100.0 * (num / den)

def run_benchmark(jobs: list, area: str, soc_groups: list, *, window: str = "", provider=None,
                  jolts_key: str | None = None, weights: dict | None = None, out_dir=None) -> CoverageReport:
    clusters = resolve(jobs)
    n_clusters, n_raw = len(clusters), len(jobs)
    paths_used: dict = {}

    # Collapse correlated sources to INDEPENDENCE FAMILIES before any capture-
    # recapture math (serpapi+jsearch = one Google-Jobs meta-source): counting
    # them as two independent captures inflates overlap and the estimate.
    membership = [collapse_sources(c.source_ids) for c in clusters]
    source_counts: dict[str, int] = {}
    for ms in membership:
        for s in ms:
            source_counts[s] = source_counts.get(s, 0) + 1
    sources = sorted(source_counts, key=lambda s: source_counts[s], reverse=True)
    t = len(sources)                                   # independent sample count
    f1 = sum(1 for ms in membership if len(ms) == 1)   # incidence singletons (Q1)
    f2 = sum(1 for ms in membership if len(ms) == 2)   # incidence doubletons (Q2)

    cov_cr = cov_cr_ci = cov_upper = c_hat = None
    jackknife: dict | None = None
    if t >= 3:
        # Bootstrap CI around the log-linear point estimate (was a bare float).
        point, lo, hi = loglinear_ci(membership)
        cov_cr = _clamp_fraction(n_clusters, point)
        cov_cr_ci = (_clamp_fraction(n_clusters, hi), _clamp_fraction(n_clusters, lo))
        paths_used["cr"] = "loglinear+bootstrap"
    elif t == 2:
        a, b = sources[0], sources[1]
        m = sum(1 for ms in membership if a in ms and b in ms)
        res = chapman(source_counts[a], source_counts[b], m)
        cov_cr = _clamp_fraction(n_clusters, res.n_hat)
        cov_cr_ci = (_clamp_fraction(n_clusters, res.ci95[1]), _clamp_fraction(n_clusters, res.ci95[0]))
        paths_used["cr"] = "chapman"
    else:
        paths_used["cr"] = "insufficient_sources"

    if n_clusters:
        # Incidence-based Chao2 (with the (t-1)/t finite-sample correction) is the
        # correct richness ceiling for presence/absence-across-sources data; the
        # old chao1(f1, f2, ...) call fed incidence counts to an abundance formula.
        cov_upper = chao2(f1, f2, n_clusters, t)
        c_hat = good_turing(f1, n_raw)
        # Two assumption-light cross-checks so no single estimator is trusted alone.
        jackknife = {"jack1": jackknife1(f1, n_clusters, t),
                     "jack2": jackknife2(f1, f2, n_clusters, t)}
    paths_used["cov_upper"] = "chao2"
    paths_used["source_families"] = sources

    ref = reference_coverage(area, soc_groups, clusters, provider, weights)
    paths_used["reference"] = "provider" if provider is not None else "skip"
    jolts = jolts_gate(area, None, n_clusters, api_key=jolts_key)
    paths_used["jolts"] = jolts.verdict

    rpt = CoverageReport(
        scope_hash=_report.scope_hash(area, window, ",".join(soc_groups), sources),
        area=area, window=window, soc_grouping=",".join(soc_groups), source_ids=sources,
        composite_score=_composite(cov_cr, ref.cov_proxy_weighted, c_hat),
        cov_cr=cov_cr, cov_cr_ci=cov_cr_ci, cov_upper=cov_upper, c_hat=c_hat,
        cov_proxy_weighted=ref.cov_proxy_weighted, jolts_verdict=jolts.verdict,
        dedup_f1=None, per_soc=ref.per_soc, n_clusters=n_clusters, n_raw=n_raw, paths_used=paths_used,
        jackknife=jackknife, cov_upper_method="chao2", source_families=sources,
    )
    base = Path(out_dir) if out_dir is not None else Path(config.USER_DATA_DIR) / "coverage"
    _report.persist(rpt, base)
    return rpt
