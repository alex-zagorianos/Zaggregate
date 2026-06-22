from __future__ import annotations
from dataclasses import dataclass
from coverage import entity

try:
    from rapidfuzz import fuzz as _rf_fuzz
    _HAVE_RF = True
except ImportError:
    _HAVE_RF = False

_MATCH_THRESHOLD = 85.0

@dataclass
class Cluster:
    job_key: str
    canonical: "JobResult"  # noqa: F821
    members: list
    source_ids: set

def _source_id(job) -> str:
    return getattr(job, "source_api", None) or getattr(job, "source_keyword", None) or ""

def _block_key(job) -> tuple:
    nt = entity.normalize_title(getattr(job, "title", "") or "")
    nl = entity.normalize_location(getattr(job, "location", "") or "")
    return (entity.canonicalize_company(getattr(job, "company", "") or ""), nt.soc_code, entity.location_token(nl))

def _pair_matches(a, b) -> bool:
    ta, tb = (getattr(a, "title", "") or ""), (getattr(b, "title", "") or "")
    ca, cb = (getattr(a, "company", "") or ""), (getattr(b, "company", "") or "")
    if not _HAVE_RF:
        return entity.title_core(ta) == entity.title_core(tb) and \
            entity.canonicalize_company(ca) == entity.canonicalize_company(cb)
    combined = 0.6 * _rf_fuzz.token_set_ratio(ta, tb) + 0.4 * _rf_fuzz.WRatio(ca, cb)
    return combined >= _MATCH_THRESHOLD

class _UnionFind:
    def __init__(self, n: int):
        self.p = list(range(n))
    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x
    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)

def resolve(jobs: list) -> list[Cluster]:
    if not jobs:
        return []
    blocks: dict[tuple, list[int]] = {}
    for i, j in enumerate(jobs):
        blocks.setdefault(_block_key(j), []).append(i)
    uf = _UnionFind(len(jobs))
    for idxs in blocks.values():
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                if _pair_matches(jobs[idxs[a]], jobs[idxs[b]]):
                    uf.union(idxs[a], idxs[b])
    groups: dict[int, list[int]] = {}
    for i in range(len(jobs)):
        groups.setdefault(uf.find(i), []).append(i)
    clusters: list[Cluster] = []
    for members_idx in groups.values():
        members = [jobs[i] for i in sorted(members_idx)]
        canonical = members[0]
        clusters.append(Cluster(job_key=canonical.job_key, canonical=canonical,
                                 members=members, source_ids={_source_id(m) for m in members}))
    clusters.sort(key=lambda c: c.job_key)
    return clusters
