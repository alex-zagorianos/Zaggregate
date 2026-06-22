from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
from coverage.entity import normalize_title
from coverage.resolve import resolve

ReferenceProvider = Callable[[str, list], list]

@dataclass
class ReferenceResult:
    per_soc: dict
    cov_proxy_weighted: float | None

def _soc_of_cluster(cluster) -> str:
    return normalize_title(getattr(cluster.canonical, "title", "") or "").soc_code

def reference_coverage(area: str, soc_groups: list, our_clusters: list, provider, weights: dict | None) -> ReferenceResult:
    if provider is None:
        return ReferenceResult(per_soc={}, cov_proxy_weighted=None)
    ref_clusters = resolve(provider(area, soc_groups))
    if not ref_clusters:
        return ReferenceResult(per_soc={}, cov_proxy_weighted=None)
    our_keys = {c.job_key for c in our_clusters}
    ref_by_soc: dict[str, list] = {}
    for rc in ref_clusters:
        ref_by_soc.setdefault(_soc_of_cluster(rc), []).append(rc)
    per_soc: dict[str, dict] = {}
    for g, clusters in ref_by_soc.items():
        d_g = len(clusters)
        n_g = sum(1 for rc in clusters if rc.job_key in our_keys)
        per_soc[g] = {"D_g": d_g, "N_g": n_g, "cov_proxy_g": (n_g / d_g) if d_g else None}
    present = {g: v for g, v in per_soc.items() if v["D_g"] > 0}
    if not present:
        return ReferenceResult(per_soc=per_soc, cov_proxy_weighted=None)
    w = weights or {}
    num = sum(w.get(g, 1.0) * v["cov_proxy_g"] for g, v in present.items())
    den = sum(w.get(g, 1.0) for g in present)
    return ReferenceResult(per_soc=per_soc, cov_proxy_weighted=(num / den) if den else None)
