from __future__ import annotations
import itertools, math
from dataclasses import dataclass

try:
    import statsmodels.api as _sm  # noqa: F401
    _HAVE_SM = True
except ImportError:
    _HAVE_SM = False

@dataclass
class ChapmanResult:
    n_hat: float
    var: float
    ci95: tuple

def chapman(n1: int, n2: int, m: int) -> ChapmanResult:
    n_hat = (n1 + 1) * (n2 + 1) / (m + 1) - 1
    var = ((n1 + 1) * (n2 + 1) * (n1 - m) * (n2 - m)) / ((m + 1) ** 2 * (m + 2))
    half = 1.96 * math.sqrt(var) if var > 0 else 0.0
    return ChapmanResult(n_hat=n_hat, var=var, ci95=(n_hat - half, n_hat + half))

def chao1(f1: int, f2: int, s_obs: int) -> float:
    return s_obs + (f1 * (f1 - 1)) / (2 * (f2 + 1))


def chao2(q1: int, q2: int, s_obs: int, t: int) -> float:
    """Incidence-based Chao2 richness estimate with the (t-1)/t finite-sample
    correction, for capture data expressed as SAMPLE incidence:

        q1 = species (jobs) found in exactly ONE sample (source)
        q2 = species found in exactly TWO samples
        s_obs = observed richness (distinct jobs seen)
        t = number of samples (independent sources)

    This is the correct estimator when the "captures" are presence/absence across
    sources (our case), where the abundance-based chao1 is a mislabel. The
    correction factor collapses to chao1's form as t -> inf; with t < 2 it is
    undefined, so we fall back to the uncorrected bias-corrected form.
    """
    corr = (t - 1) / t if t and t >= 2 else 1.0
    return s_obs + corr * (q1 * (q1 - 1)) / (2 * (q2 + 1))


def jackknife1(q1: int, s_obs: int, t: int) -> float:
    """First-order incidence jackknife richness estimate. Degenerates to s_obs
    for a single sample (no unseen-class information)."""
    if not t or t <= 1:
        return float(s_obs)
    return s_obs + q1 * (t - 1) / t


def jackknife2(q1: int, q2: int, s_obs: int, t: int) -> float:
    """Second-order incidence jackknife richness estimate. Needs t >= 3;
    degenerates to s_obs below that (the (t-2) terms vanish/are undefined)."""
    if not t or t <= 2:
        return float(s_obs)
    return s_obs + q1 * (2 * t - 3) / t - q2 * (t - 2) ** 2 / (t * (t - 1))


def loglinear_ci(membership: list, *, n_boot: int = 200, alpha: float = 0.05,
                 seed: int = 1234567) -> tuple:
    """Nonparametric percentile bootstrap CI around ``loglinear`` — which
    otherwise returns a bare point estimate with no variance. Resamples the
    per-job source-membership list with replacement ``n_boot`` times and takes
    the (alpha/2, 1-alpha/2) percentiles of the recomputed estimates.

    Returns ``(point, lo, hi)``. Deterministic given ``seed`` (so tests and
    persisted reports are reproducible). Failed resamples are skipped; if none
    survive, the CI collapses to the point estimate.
    """
    import random
    point = loglinear(membership) if membership else 0.0
    n = len(membership)
    if n == 0 or n_boot <= 0:
        return point, point, point
    rng = random.Random(seed)
    ests: list[float] = []
    for _ in range(n_boot):
        sample = [membership[rng.randrange(n)] for _ in range(n)]
        try:
            ests.append(loglinear(sample))
        except Exception:
            continue
    if not ests:
        return point, point, point
    ests.sort()
    lo = ests[int((alpha / 2) * len(ests))]
    hi = ests[min(len(ests) - 1, int((1 - alpha / 2) * len(ests)))]
    return point, lo, hi

def good_turing(f1: int, n: int) -> float:
    if n <= 0:
        return 0.0
    return 1.0 - (f1 / n)

def loglinear(membership: list) -> float:
    sources = sorted({s for fs in membership for s in fs})
    if _HAVE_SM and len(sources) >= 3:
        return _loglinear_glm(membership, sources)
    estimates: list[float] = []
    for a, b in itertools.combinations(sources, 2):
        n1 = sum(1 for fs in membership if a in fs)
        n2 = sum(1 for fs in membership if b in fs)
        m = sum(1 for fs in membership if a in fs and b in fs)
        if m > 0:
            estimates.append(chapman(n1, n2, m).n_hat)
    return sum(estimates) / len(estimates) if estimates else float(len(membership))

def _loglinear_glm(membership: list, sources: list) -> float:
    import numpy as np
    import statsmodels.api as sm
    cells: dict[tuple, int] = {}
    for fs in membership:
        pattern = tuple(1 if s in fs else 0 for s in sources)
        cells[pattern] = cells.get(pattern, 0) + 1
    rows = [p for p in cells if any(p)]
    y = np.array([cells[p] for p in rows], dtype=float)
    X = sm.add_constant(np.array(rows, dtype=float), has_constant="add")
    model = sm.GLM(y, X, family=sm.families.Poisson()).fit()
    zero = sm.add_constant(np.zeros((1, len(sources))), has_constant="add")
    return len(membership) + float(model.predict(zero)[0])
