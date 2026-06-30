"""Per-source freshness delta (spec §5.6).

Persist each source's set of job_keys under USER_DATA_DIR/freshness/, so the
next run can surface only postings new since last time. job_key is WS-1's
stable cross-source identity.
"""
from __future__ import annotations
import json
from pathlib import Path

import config


def _dir(base_dir=None) -> Path:
    base = Path(base_dir) if base_dir is not None else Path(config.USER_DATA_DIR) / "freshness"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _path(source_id: str, base_dir=None) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in source_id)
    return _dir(base_dir) / f"{safe}.json"


def load_prev_keys(source_id: str, base_dir=None) -> set:
    p = _path(source_id, base_dir)
    if not p.exists():
        return set()
    try:
        return set(json.loads(p.read_text(encoding="utf-8")))
    except (ValueError, OSError):
        return set()


def save_keys(source_id: str, keys: set, base_dir=None) -> None:
    p = _path(source_id, base_dir)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(sorted(keys)), encoding="utf-8")
    tmp.replace(p)


def new_since_last(jobs: list, source_id: str, prev_keys: set) -> list:
    """Jobs whose job_key was not in the previous run's set for this source."""
    return [j for j in jobs if j.job_key not in prev_keys]
