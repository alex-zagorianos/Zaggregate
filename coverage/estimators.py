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
