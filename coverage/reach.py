"""Job-level reach certification for a real search run.

This is the capstone that answers Alex's standing question — "have we found
90-100% of the relevant jobs?" — with an honest, defensible number instead of a
vibe. It uses the ONE thing a multi-source search already gives us for free: the
set of INDEPENDENT sources that found each posting. Capture-recapture turns the
cross-source overlap into an estimate of the unseen population.

Pipeline (all from the RAW, pre-dedup results of a run):
  raw jobs --resolve--> clusters (each carries the sources that found it)
           --collapse--> independence families (serpapi+jsearch = one)
           --estimate--> N_hat (CR: log-linear >=3 families / Chapman 2),
                         Chao2 ceiling, Good-Turing sample completeness,
                         jackknife cross-checks
           --> coverage% with a bootstrap/analytic 95% CI, an unseen count, and
               an HONEST 'cannot certify' fallback when there aren't >=2
               independent families (matching CoverageEstimate.defined's spirit).

Design invariants: read-only (changes what's reported, never what's fetched),
best-effort (never raises into the run), stdlib + the existing coverage/ package.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import config
from coverage.estimators import (chao2, chapman, good_turing, jackknife1,
                                 jackknife2, loglinear_ci)
from coverage.independence import collapse_sources
from coverage.resolve import resolve


@dataclass
class ReachEstimate:
    area: str
    industry: str
    n_raw: int                 # raw postings observed across all sources
    n_distinct: int            # distinct postings after cross-source resolution
    n_families: int            # independent source families (capture occasions)
    families: list             # the family ids, most-productive first
    per_family: dict           # family -> distinct postings it contributed
    f1: int                    # postings seen by exactly ONE family (singletons)
    f2: int                    # postings seen by exactly TWO families
    method: str                # 'loglinear+bootstrap' | 'chapman' | 'insufficient'
    n_hat: float | None        # estimated true universe (distinct postings)
    n_hat_ci: tuple | None     # 95% CI on n_hat
    coverage_pct: float | None # n_distinct / n_hat * 100 (capped 100)
    coverage_ci: tuple | None  # 95% CI on coverage_pct
    unseen: int | None         # estimated distinct postings still unseen
    chao2: float | None        # incidence richness ceiling (cross-check)
    completeness: float | None # Good-Turing sample completeness (assumption-light)
    jack1: float | None
    jack2: float | None
    certifiable: bool          # True only with >=2 independent families + defined N̂
    message: str               # human-readable honesty note
    ts: str = ""

    def summary_line(self) -> str:
        """One-line log/badge string. Never a bare percentage — always qualified
        by the CI, the source-family count, and the raw->distinct funnel."""
        scope = " / ".join(x for x in (self.area, self.industry) if x) or "all"
        if not self.certifiable or self.coverage_pct is None:
            comp = (f" (sample completeness ~{self.completeness*100:.0f}% by Good-Turing)"
                    if self.completeness is not None else "")
            return (f"Reach [{scope}]: cannot certify a coverage % — {self.message}. "
                    f"{self.n_raw} raw -> {self.n_distinct} distinct from "
                    f"{self.n_families} independent source famil"
                    f"{'y' if self.n_families == 1 else 'ies'}{comp}.")
        lo, hi = self.coverage_ci or (self.coverage_pct, self.coverage_pct)
        return (f"Reach [{scope}]: seeing ~{self.coverage_pct:.0f}% "
                f"(95% CI {lo:.0f}-{hi:.0f}%) of the reachable universe — "
                f"~{self.unseen} of ~{round(self.n_hat)} estimated postings still "
                f"unseen (from {self.n_families} independent source families, "
                f"{self.n_raw} raw -> {self.n_distinct} distinct).")

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("n_hat_ci", "coverage_ci"):
            if d.get(k) is not None:
                d[k] = list(d[k])
        return d


def _cap_cov(observed: int, n_hat) -> float | None:
    if not n_hat or n_hat <= 0 or (isinstance(n_hat, float) and math.isnan(n_hat)):
        return None
    return min(100.0, observed / n_hat * 100.0)


def estimate_reach(raw_results, *, area: str = "", industry: str = "") -> ReachEstimate:
    """Estimate job-level reach from the RAW (pre-dedup) results of a search run.

    Pass the raw list (SearchEngine.last_raw_results), NOT the deduped one — dedup
    discards the cross-source membership the estimate depends on.
    """
    jobs = list(raw_results or [])
    n_raw = len(jobs)
    clusters = resolve(jobs)
    n_distinct = len(clusters)

    membership = [collapse_sources(c.source_ids) for c in clusters]
    per_family: dict[str, int] = {}
    for ms in membership:
        for fam in ms:
            per_family[fam] = per_family.get(fam, 0) + 1
    families = sorted(per_family, key=lambda s: per_family[s], reverse=True)
    t = len(families)
    f1 = sum(1 for ms in membership if len(ms) == 1)
    f2 = sum(1 for ms in membership if len(ms) == 2)

    completeness = good_turing(f1, n_raw) if n_raw else None
    ceiling = chao2(f1, f2, n_distinct, t) if n_distinct else None
    jack1 = jackknife1(f1, n_distinct, t) if n_distinct else None
    jack2 = jackknife2(f1, f2, n_distinct, t) if n_distinct else None

    n_hat = n_hat_ci = coverage_pct = coverage_ci = unseen = None
    certifiable = False
    if t >= 3:
        point, lo, hi = loglinear_ci(membership)
        n_hat = point
        n_hat_ci = (lo, hi)
        method = "loglinear+bootstrap"
        certifiable = point > 0
    elif t == 2:
        a, b = families[0], families[1]
        m = sum(1 for ms in membership if a in ms and b in ms)
        res = chapman(per_family[a], per_family[b], m)
        n_hat = res.n_hat
        n_hat_ci = res.ci95
        method = "chapman"
        certifiable = m > 0 and not math.isnan(res.n_hat)
    else:
        method = "insufficient"

    if certifiable and n_hat and n_hat > 0:
        coverage_pct = _cap_cov(n_distinct, n_hat)
        if n_hat_ci:
            lo_n, hi_n = n_hat_ci
            # bigger N̂ -> lower coverage, so the CI flips.
            coverage_ci = (_cap_cov(n_distinct, hi_n), _cap_cov(n_distinct, lo_n))
        unseen = max(0, round(n_hat) - n_distinct)
        message = f"log-linear over {t} independent source families" if t >= 3 \
            else "Chapman capture-recapture over 2 independent source families"
    elif t < 2:
        message = (f"need >=2 independent source families (have {t}) — a single "
                   f"source can't reveal what it's missing")
    else:
        message = ("no cross-source overlap — families may be disjoint (each "
                   "covering a different slice), so the universe can't be sized")

    return ReachEstimate(
        area=area, industry=industry, n_raw=n_raw, n_distinct=n_distinct,
        n_families=t, families=families, per_family=per_family, f1=f1, f2=f2,
        method=method, n_hat=n_hat, n_hat_ci=n_hat_ci, coverage_pct=coverage_pct,
        coverage_ci=coverage_ci, unseen=unseen, chao2=ceiling,
        completeness=completeness, jack1=jack1, jack2=jack2,
        certifiable=certifiable, message=message,
        ts=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    )


def _reach_dir() -> Path:
    return Path(config.USER_DATA_DIR) / "coverage" / "reach"


def persist_reach(est: ReachEstimate, *, project: str = "") -> Path:
    """Append the estimate to a per-project JSONL history and write a 'latest'
    snapshot the GUI/CLI can read. Best-effort; returns the latest path."""
    base = _reach_dir()
    base.mkdir(parents=True, exist_ok=True)
    slug = (project or "root").replace("/", "_").replace("\\", "_")
    payload = {**est.to_dict(), "project": slug}
    with (base / f"{slug}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")
    latest = base / f"{slug}.latest.json"
    latest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return latest


def load_latest(project: str = "") -> dict | None:
    """Most recent persisted reach snapshot for a project, or None."""
    slug = (project or "root").replace("/", "_").replace("\\", "_")
    p = _reach_dir() / f"{slug}.latest.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


if __name__ == "__main__":  # pragma: no cover - thin CLI
    import argparse
    import workspace
    ap = argparse.ArgumentParser(description="Show the latest reach estimate.")
    ap.add_argument("--project", default=None)
    args = ap.parse_args()
    proj = args.project or workspace.active_slug() or "root"
    snap = load_latest(proj)
    if not snap:
        print(f"No reach estimate yet for '{proj}'. Run a daily_run first "
              f"(it computes and persists one).")
    else:
        print(json.dumps(snap, indent=2))
