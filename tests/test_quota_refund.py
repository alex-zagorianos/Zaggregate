"""SEARCH-6: quota refund.

(a) MonthlyQuota.decrement restores remaining(), never drops below the real
    count, and is a no-op on a stale month.
(b) JSearchClient refunds the reservation when the request fails so a failed
    call doesn't permanently burn the 200/month tier.
"""
import pytest

from search.http_util import MonthlyQuota


# ── (a) MonthlyQuota.decrement ───────────────────────────────────────────────

def test_decrement_restores_remaining(tmp_path):
    q = MonthlyQuota(tmp_path / "usage.json", limit=200)
    before = q.remaining()
    assert q.try_increment() is True
    assert q.remaining() == before - 1
    q.decrement()
    assert q.remaining() == before  # reservation refunded


def test_decrement_never_below_real_count(tmp_path):
    q = MonthlyQuota(tmp_path / "usage.json", limit=10)
    q.try_increment(2)            # real count = 2
    q.decrement(5)                # would go negative -> clamp at 0
    assert q.remaining() == 10
    # And a subsequent increment still works from the floor, not a negative.
    assert q.try_increment() is True
    assert q.remaining() == 9


def test_decrement_stale_month_is_noop(tmp_path, monkeypatch):
    path = tmp_path / "usage.json"
    q = MonthlyQuota(path, limit=5)
    monkeypatch.setattr(q, "_this_month", lambda: "2026-05")
    q.try_increment(3)            # count = 3 stored under 2026-05

    # Now "this month" rolls over; the stored file is stale.
    monkeypatch.setattr(q, "_this_month", lambda: "2026-06")
    q.decrement(2)               # must not touch the stale 2026-05 file

    # Roll back to the stored month and confirm the count was untouched.
    monkeypatch.setattr(q, "_this_month", lambda: "2026-05")
    assert q.remaining() == 2    # still 5 - 3, decrement did nothing


# ── (b) JSearchClient refunds on a failed request ────────────────────────────

class _BoomSession:
    """Stand-in requests.Session whose GET always blows up."""

    def get(self, *args, **kwargs):
        raise RuntimeError("network down")


def _make_client(tmp_path):
    from search.jsearch_client import JSearchClient

    client = JSearchClient(api_key="test", cache_dir=tmp_path, cache_enabled=False)
    client.session = _BoomSession()
    # Don't actually sleep in the rate limiter during the test.
    client.limiter.acquire = lambda: None
    return client


def test_jsearch_refunds_quota_on_failed_request(tmp_path):
    client = _make_client(tmp_path)
    before = client.quota.remaining()

    with pytest.raises(RuntimeError):
        client.search("controls engineer", "Cincinnati, OH")

    # The reservation taken before the request must be given back.
    assert client.quota.remaining() == before


def test_jsearch_no_quota_leak_across_failures(tmp_path):
    client = _make_client(tmp_path)
    before = client.quota.remaining()
    for _ in range(5):
        with pytest.raises(RuntimeError):
            client.search("k", "Cincinnati, OH")
    assert client.quota.remaining() == before  # five failures, zero net spend
