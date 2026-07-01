"""Per-source freshness delta + repost/evergreen detection (spec sec 5.6, C1).

Persist each source's job_keys under USER_DATA_DIR/freshness/, so the next run
can surface only postings new since last time. job_key is WS-1's stable
cross-source identity.

C1 upgrade: the on-disk format is no longer a bare SET of keys overwritten each
run (which retained no history). It is now a VERSIONED map

    {"version": 2, "keys": {job_key: {"first_seen": iso, "last_seen": iso,
                                       "runs_present": int, "run_seq": int,
                                       "was_absent": bool}}}

that keeps just enough per-key presence history to answer:
  (a) seen -> absent for >=1 run -> seen again  => REPOST
  (b) cumulative presence spanning > 90 days     => EVERGREEN

The OLD bare-list format is still READ compatibly (every old key is treated as
first_seen=now with no history), so an existing user's files never crash.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

import config

FORMAT_VERSION = 2
EVERGREEN_DAYS = 90  # cumulative presence longer than this = evergreen listing


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_iso(value):
    """Parse an ISO datetime (aware) or return None. Tolerant of a bare date."""
    if not value or not isinstance(value, str):
        return None
    s = value.strip().replace("Z", "+00:00")
    for candidate in (s, s[:19], s[:10]):
        try:
            dt = datetime.fromisoformat(candidate)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _dir(base_dir=None) -> Path:
    base = Path(base_dir) if base_dir is not None else Path(config.USER_DATA_DIR) / "freshness"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _path(source_id: str, base_dir=None) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in source_id)
    return _dir(base_dir) / f"{safe}.json"


def _load_state(source_id: str, base_dir=None) -> dict:
    """Read the per-source presence map, tolerant of the OLD bare-list format.

    Returns {job_key: record} where record has first_seen/last_seen/runs_present/
    run_seq/was_absent. An old bare list is upgraded in-memory: each key becomes a
    single-run record first_seen=now (we have no prior history to reconstruct)."""
    p = _path(source_id, base_dir)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    now = _now_iso()
    # Old format: a bare JSON list (or set-serialized-as-list) of job_keys.
    if isinstance(data, list):
        return {k: {"first_seen": now, "last_seen": now, "runs_present": 1,
                    "run_seq": 0, "was_absent": False}
                for k in data if isinstance(k, str)}
    # New format: {"version": N, "keys": {...}}.
    if isinstance(data, dict):
        keys = data.get("keys")
        if isinstance(keys, dict):
            out = {}
            for k, rec in keys.items():
                if isinstance(rec, dict):
                    out[k] = rec
                else:  # a stray non-dict value -> treat as a bare presence
                    out[k] = {"first_seen": now, "last_seen": now,
                              "runs_present": 1, "run_seq": 0, "was_absent": False}
            return out
        # A dict that isn't our envelope (e.g. an old {key: iso} experiment):
        # treat its keys as present-now records.
        return {k: {"first_seen": (v if isinstance(v, str) else now),
                    "last_seen": now, "runs_present": 1, "run_seq": 0,
                    "was_absent": False}
                for k, v in data.items() if isinstance(k, str)}
    return {}


def _write_state(source_id: str, state: dict, base_dir=None) -> None:
    p = _path(source_id, base_dir)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"version": FORMAT_VERSION, "keys": state},
                              separators=(",", ":")),
                   encoding="utf-8")
    tmp.replace(p)


# -- Public API (back-compat with the old set-based callers) -------------------

def load_prev_keys(source_id: str, base_dir=None) -> set:
    """The set of job_keys present at the END of the previous run (back-compat:
    daily_run reads this to mark is_new). Reads either format."""
    return set(_load_state(source_id, base_dir).keys())


def save_keys(source_id: str, keys, base_dir=None) -> None:
    """Advance the freshness baseline to THIS run's found `keys`, updating the
    per-key presence history in place so repost_info() can classify next time.

    History transitions for each key:
      * new this run                 -> first_seen=now, runs_present=1, seq++
      * present last run, present now -> last_seen=now, runs_present++, seq++
      * ABSENT last run, present now  -> was_absent stays True across the gap and
                                         is what repost_info reads as a REPOST
    A key present LAST run but absent NOW is retained (we don't forget it) with
    was_absent=True bumped, so a later reappearance is detectable as a repost.
    """
    keys = set(keys)
    state = _load_state(source_id, base_dir)
    now = _now_iso()
    # Bump a monotonic run counter so "absent for >=1 run" is countable even when
    # two runs share a wall-clock second.
    max_seq = max((int(r.get("run_seq", 0)) for r in state.values()), default=-1)
    this_seq = max_seq + 1
    for k in keys:
        rec = state.get(k)
        if rec is None:
            state[k] = {"first_seen": now, "last_seen": now, "runs_present": 1,
                        "run_seq": this_seq, "was_absent": False}
        else:
            prev_seq = int(rec.get("run_seq", this_seq))
            # A gap of >=1 run since we last saw this key = it went absent and came
            # back: mark it a repost. (prev_seq is the last run it was PRESENT.)
            if this_seq - prev_seq > 1:
                rec["was_absent"] = True
            rec["last_seen"] = now
            rec["runs_present"] = int(rec.get("runs_present", 0)) + 1
            rec["run_seq"] = this_seq
    # Keys present before but NOT this run: keep them (history), flag the gap so a
    # future reappearance is a repost. We DON'T advance their run_seq (they weren't
    # present), which is exactly what lets the gap-detection above fire.
    for k, rec in state.items():
        if k not in keys:
            rec["was_absent"] = True
    _write_state(source_id, state, base_dir)


def new_since_last(jobs: list, source_id: str, prev_keys: set) -> list:
    """Jobs whose job_key was not in the previous run's set for this source."""
    return [j for j in jobs if j.job_key not in prev_keys]


def repost_info(source_id: str, base_dir=None) -> dict:
    """Per-key repost/evergreen classification read off the persisted history:

        {job_key: {"first_seen": iso, "repost": bool, "evergreen": bool}}

    repost   = the key was seen, went absent for >=1 run, then reappeared.
    evergreen = cumulative presence spans > EVERGREEN_DAYS (a perpetual req).

    Safe on the old bare-list format (no history -> nothing flagged) and on a
    missing file (empty dict). Read-only; never writes."""
    state = _load_state(source_id, base_dir)
    now = datetime.now(timezone.utc)
    out: dict = {}
    for k, rec in state.items():
        first = _parse_iso(rec.get("first_seen"))
        last = _parse_iso(rec.get("last_seen")) or first
        evergreen = bool(first and last and (last - first).days > EVERGREEN_DAYS)
        # Also treat a key first seen > EVERGREEN_DAYS ago and still present as
        # evergreen even if last_seen wasn't bumped this exact run.
        if not evergreen and first and (now - first).days > EVERGREEN_DAYS \
                and int(rec.get("runs_present", 0)) > 1:
            evergreen = True
        out[k] = {
            "first_seen": rec.get("first_seen", ""),
            "repost": bool(rec.get("was_absent", False)),
            "evergreen": evergreen,
        }
    return out
