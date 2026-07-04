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
        ci = self.coverage_ci
        if not ci or ci[0] is None or ci[1] is None:
            lo, hi = self.coverage_pct, self.coverage_pct
        else:
            lo, hi = ci
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
    # Jobs seen by >=2 families = actual recaptures. With ZERO recaptures the
    # capture-recapture estimate is meaningless (loglinear's naive fallback then
    # returns exactly n_distinct -> a false 100%), so certification requires
    # overlap for EVERY branch, mirroring the t==2 m>0 check.
    n_overlap = sum(1 for ms in membership if len(ms) >= 2)

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
        # Require real overlap: 3 disjoint families (n_overlap==0) make loglinear
        # degenerate to n_distinct -> a bogus 100%. Route those to "cannot certify".
        certifiable = point > 0 and n_overlap > 0
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
            # bigger N̂ -> lower coverage, so the CI flips. A non-positive N̂ bound
            # (the analytic Chapman Wald CI often has a negative lower bound when m
            # is small) means N̂ <= observed on that end -> ~100% coverage; NEVER
            # leave a None in the CI (it crashed summary_line's %-formatting).
            ci_low = _cap_cov(n_distinct, hi_n)     # big N̂ -> low coverage bound
            ci_high = _cap_cov(n_distinct, lo_n)    # small/neg N̂ -> high coverage bound
            coverage_ci = (ci_low if ci_low is not None else coverage_pct,
                           ci_high if ci_high is not None else 100.0)
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


def _serpapi_key_present() -> bool:
    """True if a SerpApi key is configured (env or secrets). Used to decide
    whether the non-certifiable badge should suggest adding one — the reach probe
    that unlocks certification needs it. Best-effort; False on any error."""
    try:
        import config
        key = config.SERPAPI_KEY or config.read_secret("serpapi_key")
        return bool(key)
    except Exception:
        return False


# The two headline free keys that most widen LOCAL reach (plan §6.8 / coverage
# monopoly finding). Named in the actionable badge when they're missing.
_HEADLINE_LOCAL_KEYS = ("Adzuna", "CareerOneStop")


def _missing_headline_keys() -> list[str]:
    """Which of the headline local-reach keys (Adzuna, CareerOneStop) are NOT
    connected. Best-effort ([] on any error) so the badge never crashes the GUI."""
    try:
        from ui.setup_wizard import connected_source_labels
        connected = set(connected_source_labels())
    except Exception:
        return []
    return [k for k in _HEADLINE_LOCAL_KEYS if k not in connected]


def _badge_industry(industry: str | None) -> str:
    """Resolve the industry for badge copy: the caller's explicit value, else the
    ACTIVE project's config (per-request/per-refresh — never cached at import, so
    a project switch changes the copy). Best-effort '' on any error; '' counts as
    knowledge work downstream, which keeps the historical copy."""
    if industry is not None:
        return industry
    try:
        import workspace
        return (workspace.load_config() or {}).get("industry") or ""
    except Exception:
        return ""


def badge_reason(snap: dict | None, industry: str | None = None) -> str | None:
    """The single actionable reason a reach badge is weak, or None when it's fine.

    Returns a short "…because <keys> aren't connected — Connect a free key" note
    when reach is low/uncertifiable AND a headline local key (Adzuna/CareerOneStop)
    is missing. This is what turns the honest-but-dead-end badge into an actionable
    one (§6.8 / Pattern 4a): the GUI shows it as a clickable "[Connect a free key]"
    that opens the keys dialog. None when the estimate is certifiable or nothing
    actionable is missing.

    The "mostly remote/tech jobs" clause only applies to knowledge-work fields —
    a nurse/teacher/trades project (where tech sources were already gated off)
    gets neutral "coverage is uncertain" copy instead (S36 scenario MINOR-4).
    `industry` defaults to the active project's config."""
    if snap is None:
        # No run yet — still worth nudging if the headline keys are missing.
        missing = _missing_headline_keys()
    elif snap.get("certifiable") and snap.get("coverage_pct") is not None:
        return None
    else:
        missing = _missing_headline_keys()
    if not missing:
        return None
    try:
        from search.keyword_strategy import is_knowledge_work
        knowledge = is_knowledge_work(_badge_industry(industry))
    except Exception:
        knowledge = True  # copy nuance must never break the badge
    lead = ("mostly remote/tech jobs" if knowledge else "coverage is uncertain")
    return (f"{lead} because {' + '.join(missing)} "
            f"{'is' if len(missing) == 1 else 'are'} not connected")


def badge_line(snap: dict | None) -> str:
    """One-line reach badge from a persisted snapshot dict (see load_latest) —
    for the GUI/CLI. Blank when there's no snapshot; a qualified percentage only
    when the estimate is certifiable, else an honest 'not yet certifiable'.

    When NOT certifiable and no SerpApi key is configured, the badge names the
    single action that unlocks certification — a SerpApi key (its Google-Jobs
    probe gives capture-recapture the cross-source overlap it needs). With a key
    already present the hint is omitted (adding one wouldn't help)."""
    if not snap:
        return ""
    nd, nf = snap.get("n_distinct"), snap.get("n_families")
    cov, ci = snap.get("coverage_pct"), snap.get("coverage_ci")
    if snap.get("certifiable") and cov is not None:
        s = f"Reach ~{cov:.0f}%"
        if (isinstance(ci, (list, tuple)) and len(ci) == 2
                and ci[0] is not None and ci[1] is not None):
            s += f" ({ci[0]:.0f}–{ci[1]:.0f}%)"
        return s + f" · {nd} distinct / {nf} src families"
    base = f"Reach: not yet certifiable · {nd} distinct / {nf} src families"
    if not _serpapi_key_present():
        base += " · add a SerpApi key in Settings to certify coverage"
    return base


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
