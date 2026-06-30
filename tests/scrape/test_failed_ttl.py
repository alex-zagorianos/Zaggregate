"""The dead-URL negative cache ("_FAILED" markers) lives on the longer
FAILED_TTL_HOURS window, so a known-dead board is skipped for ~a week instead of
being re-probed at full request timeout on every daily run."""
import os
import time

from scrape.cache_helpers import is_failed, mark_failed, read_cache, read_failed


def test_failed_marker_survives_past_content_ttl(tmp_path):
    f = tmp_path / "direct_abc_FAILED.json"
    mark_failed(f)
    # Age it to 48h: past the 24h content TTL, still within the 168h failed TTL.
    old = time.time() - 48 * 3600
    os.utime(f, (old, old))
    assert read_cache(f) is None            # content TTL would have expired it
    assert is_failed(read_failed(f))         # but the failed marker is still live


def test_failed_marker_expires_after_failed_ttl(tmp_path):
    f = tmp_path / "direct_abc_FAILED.json"
    mark_failed(f)
    old = time.time() - 200 * 3600           # older than FAILED_TTL_HOURS (168)
    os.utime(f, (old, old))
    assert read_failed(f) is None


def test_fresh_marker_read_either_way(tmp_path):
    f = tmp_path / "workday_x_FAILED.json"
    mark_failed(f)
    assert is_failed(read_failed(f))
    assert is_failed(read_cache(f))          # fresh -> visible under both TTLs
