"""C1: freshness presence-history format + repost/evergreen state machine.

Fixture-based (temp base_dir), no network. Covers:
  * old bare-list format reads compatibly (no crash, treated as first_seen=now)
  * new versioned {job_key: record} format round-trips
  * repost state machine: seen -> absent -> seen again => repost=True
  * evergreen: cumulative presence > 90 days => evergreen=True
  * a key present every run is neither repost nor evergreen (until 90d)
  * load_prev_keys / save_keys back-compat with the set-based callers
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

import search.freshness as freshness


@pytest.fixture
def base(tmp_path):
    return tmp_path / "freshness"


def _iso(dt):
    return dt.replace(microsecond=0).isoformat()


# -- format compatibility -----------------------------------------------------

def test_reads_old_bare_list_format(base, tmp_path):
    # Simulate an existing user's old file: a bare JSON list of keys.
    base.mkdir(parents=True)
    (base / "daily_test.json").write_text(json.dumps(["k1", "k2"]),
                                          encoding="utf-8")
    prev = freshness.load_prev_keys("daily:test", base_dir=base)
    assert prev == {"k1", "k2"}
    # repost_info must not crash and flags nothing (no history to read).
    info = freshness.repost_info("daily:test", base_dir=base)
    assert set(info) == {"k1", "k2"}
    assert all(not v["repost"] and not v["evergreen"] for v in info.values())


def test_missing_file_is_empty(base):
    assert freshness.load_prev_keys("daily:none", base_dir=base) == set()
    assert freshness.repost_info("daily:none", base_dir=base) == {}


def test_new_format_roundtrips(base):
    freshness.save_keys("daily:x", {"a", "b"}, base_dir=base)
    assert freshness.load_prev_keys("daily:x", base_dir=base) == {"a", "b"}
    raw = json.loads((freshness._path("daily:x", base)).read_text("utf-8"))
    assert raw["version"] == freshness.FORMAT_VERSION
    assert set(raw["keys"]) == {"a", "b"}


def test_save_keys_accepts_a_plain_list(base):
    # daily_run passes a set comprehension; be tolerant of any iterable.
    freshness.save_keys("daily:x", ["a", "a", "b"], base_dir=base)
    assert freshness.load_prev_keys("daily:x", base_dir=base) == {"a", "b"}


# -- repost state machine -----------------------------------------------------

def test_repost_seen_absent_seen(base):
    # Run 1: k present.
    freshness.save_keys("daily:r", {"k"}, base_dir=base)
    assert freshness.repost_info("daily:r", base_dir=base)["k"]["repost"] is False
    # Run 2: k ABSENT (different key present).
    freshness.save_keys("daily:r", {"other"}, base_dir=base)
    # Run 3: k present again -> repost.
    freshness.save_keys("daily:r", {"k"}, base_dir=base)
    info = freshness.repost_info("daily:r", base_dir=base)
    assert info["k"]["repost"] is True


def test_present_every_run_is_not_a_repost(base):
    for _ in range(4):
        freshness.save_keys("daily:c", {"k"}, base_dir=base)
    info = freshness.repost_info("daily:c", base_dir=base)
    assert info["k"]["repost"] is False


def test_evergreen_after_90_days(base):
    # Seed a record whose first_seen is >90 days ago and that's been seen twice.
    base.mkdir(parents=True)
    old = _iso(datetime.now(timezone.utc) - timedelta(days=120))
    now = _iso(datetime.now(timezone.utc))
    state = {"k": {"first_seen": old, "last_seen": now, "runs_present": 5,
                   "run_seq": 4, "was_absent": False}}
    (base / "daily_e.json").write_text(
        json.dumps({"version": freshness.FORMAT_VERSION, "keys": state}),
        encoding="utf-8")
    info = freshness.repost_info("daily:e", base_dir=base)
    assert info["k"]["evergreen"] is True


def test_fresh_key_is_not_evergreen(base):
    freshness.save_keys("daily:f", {"k"}, base_dir=base)
    info = freshness.repost_info("daily:f", base_dir=base)
    assert info["k"]["evergreen"] is False


def test_first_seen_preserved_across_runs(base):
    freshness.save_keys("daily:p", {"k"}, base_dir=base)
    first = freshness.repost_info("daily:p", base_dir=base)["k"]["first_seen"]
    freshness.save_keys("daily:p", {"k"}, base_dir=base)
    assert freshness.repost_info("daily:p", base_dir=base)["k"]["first_seen"] == first
