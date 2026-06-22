from __future__ import annotations
from pathlib import Path
import config
from coverage import report as _report
from coverage.estimators import chao1, chapman, good_turing, loglinear
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

    membership = [frozenset(c.source_ids) for c in clusters]
    source_counts: dict[str, int] = {}
    for ms in membership:
        for s in ms:
            source_counts[s] = source_counts.get(s, 0) + 1
    sources = sorted(source_counts, key=lambda s: source_counts[s], reverse=True)
    f1 = sum(1 for ms in membership if len(ms) == 1)
    f2 = sum(1 for ms in membership if len(ms) == 2)

    cov_cr = cov_cr_ci = cov_upper = c_hat = None
    if len(sources) >= 3:
        cov_cr = _clamp_fraction(n_clusters, loglinear(membership))
        paths_used["cr"] = "loglinear"
    elif len(sources) == 2:
        a, b = sources[0], sources[1]
        m = sum(1 for ms in membership if a in ms and b in ms)
        res = chapman(source_counts[a], source_counts[b], m)
        cov_cr = _clamp_fraction(n_clusters, res.n_hat)
        cov_cr_ci = (_clamp_fraction(n_clusters, res.ci95[1]), _clamp_fraction(n_clusters, res.ci95[0]))
        paths_used["cr"] = "chapman"
    else:
        paths_used["cr"] = "insufficient_sources"

    if n_clusters:
        cov_upper = chao1(f1, f2, n_clusters)
        c_hat = good_turing(f1, n_raw)

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
    )
    base = Path(out_dir) if out_dir is not None else Path(config.USER_DATA_DIR) / "coverage"
    _report.persist(rpt, base)
    return rpt
