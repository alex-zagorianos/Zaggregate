"""Append-only history of company-registry coverage estimates (plan P4).

Each capture-recapture round appends one JSON line to
``cache/coverage/registry/<industry>.jsonl`` so ``loop_signal`` can decide when a
loop-until-dry acquisition run has converged (rising -> plateau -> dry). Mirrors
coverage/report.persist's jsonl-append shape; the clock is injectable so tests
are deterministic (and to satisfy the no-implicit-now discipline).
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path


def _slug(industry: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (industry or "").strip().lower()).strip("-")
    return s or "_all"


def history_path(industry: str, *, base=None) -> Path:
    if base is None:
        from config import CACHE_DIR as base
    return Path(base) / "coverage" / "registry" / f"{_slug(industry)}.jsonl"


def _num(x):
    """nan/inf -> None (valid JSON, and loop_signal treats missing as undefined)."""
    try:
        return None if x is None or math.isnan(x) or math.isinf(x) else x
    except TypeError:
        return None


def estimate_to_record(estimate, industry, *, ts=None, extra=None) -> dict:
    ts = ts or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    ci = estimate.ci95 if estimate.defined else (None, None)
    rec = {
        "ts": ts,
        "industry": industry or "",
        "n1": estimate.n1,
        "n2": estimate.n2,
        "overlap": estimate.overlap,
        "observed": estimate.observed,
        "n_hat": _num(estimate.n_hat),
        "coverage_pct": _num(estimate.coverage_pct),
        "ci95": [_num(ci[0]), _num(ci[1])],
    }
    if extra:
        rec.update(extra)
    return rec


def record(estimate, industry, *, base=None, ts=None, extra=None) -> Path:
    """Append one estimate to the industry's history jsonl; returns the path."""
    path = history_path(industry, base=base)
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = estimate_to_record(estimate, industry, ts=ts, extra=extra)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    return path


def load_history(industry: str, *, base=None) -> list[dict]:
    path = history_path(industry, base=base)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
