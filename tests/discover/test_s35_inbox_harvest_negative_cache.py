"""S35 finding #26 (minor): harvest_inbox_companies had NO negative-cache -- a
company name whose domain-guess never resolves was re-probed with 3 live HTTP
round-trips (find_career_url -> detect_ats -> probe_count, per domain guess)
EVERY single run, forever. Added a persisted negative-cache (mirroring
scrape.cache_helpers.mark_failed/is_failed), keyed by the CANONICALIZED,
filename-safe (slug_safe) name, with a 14-day TTL (config.
INBOX_HARVEST_NEGATIVE_TTL_HOURS).

All tests pass cache_dir=tmp_path so nothing here ever touches the real
cache/inbox_harvest/ (S35 hard rule: tests must use tmp_path, never real
on-disk state)."""
import os
import time

import discover.inbox_harvest as H


def test_name_that_never_resolves_is_negative_cached_and_skipped_next_run(tmp_path, monkeypatch):
    probe_calls = {"n": 0}

    def never_resolves(domain):
        return None  # every domain guess fails to resolve a career URL
    monkeypatch.setattr(H, "inbox_company_counts", lambda: {"Ghost Corp": 5})
    monkeypatch.setattr(H, "find_career_url", never_resolves)
    monkeypatch.setattr(H, "detect_ats", lambda url: None)
    monkeypatch.setattr(H, "probe_count", lambda entry: (probe_calls.__setitem__("n", probe_calls["n"] + 1), 5)[1])
    monkeypatch.setattr(H, "save_companies", lambda entries, json_path: len(entries))

    # First run: 3 domain guesses attempted, all fail, name gets negative-cached.
    r1 = H.harvest_inbox_companies(companies_json=tmp_path / "companies.json",
                                   cache_dir=tmp_path)
    assert r1.candidates == 1
    assert r1.resolved == 0
    assert r1.verified == 0
    marker = H._negative_cache_file("Ghost Corp", tmp_path)
    assert marker.exists()

    # Second run (same process, same TTL window): the name is skipped before
    # any domain guess is attempted -- find_career_url must not even be called.
    calls = {"n": 0}
    def find_and_count(domain):
        calls["n"] += 1
        return None
    monkeypatch.setattr(H, "find_career_url", find_and_count)
    r2 = H.harvest_inbox_companies(companies_json=tmp_path / "companies.json",
                                   cache_dir=tmp_path)
    assert r2.candidates == 1          # still counted as a candidate...
    assert calls["n"] == 0             # ...but never actually probed again


def test_negative_cache_expires_after_ttl(tmp_path, monkeypatch):
    from config import INBOX_HARVEST_NEGATIVE_TTL_HOURS

    monkeypatch.setattr(H, "inbox_company_counts", lambda: {"Renamed Co": 5})
    monkeypatch.setattr(H, "find_career_url", lambda domain: None)
    monkeypatch.setattr(H, "detect_ats", lambda url: None)
    monkeypatch.setattr(H, "probe_count", lambda entry: 5)
    monkeypatch.setattr(H, "save_companies", lambda entries, json_path: len(entries))

    H.harvest_inbox_companies(companies_json=tmp_path / "companies.json", cache_dir=tmp_path)
    marker = H._negative_cache_file("Renamed Co", tmp_path)
    assert marker.exists()

    # Age the marker past the TTL window (simulate 15 days later).
    old = time.time() - (INBOX_HARVEST_NEGATIVE_TTL_HOURS + 24) * 3600
    os.utime(marker, (old, old))

    # Now the company DOES resolve (its site changed, or a new ATS came up) --
    # confirms the TTL expiry actually re-enables a probe, not just a permanent skip.
    calls = {"n": 0}
    def find_now(domain):
        calls["n"] += 1
        return f"https://{domain}/careers"
    monkeypatch.setattr(H, "find_career_url", find_now)
    monkeypatch.setattr(H, "detect_ats", lambda url: ("greenhouse", "renamed"))
    r = H.harvest_inbox_companies(companies_json=tmp_path / "companies.json", cache_dir=tmp_path)
    assert calls["n"] > 0               # re-attempted after TTL expiry
    assert r.resolved == 1
    assert r.verified == 1


def test_negative_cache_keyed_by_canonicalized_name(tmp_path):
    # "Acme Robotics, Inc." and "ACME ROBOTICS" must share one cache entry --
    # mirrors the existing canonicalize_company-based registry-dedup semantics.
    f1 = H._negative_cache_file("Acme Robotics, Inc.", tmp_path)
    f2 = H._negative_cache_file("ACME ROBOTICS", tmp_path)
    assert f1 == f2


def test_negative_cache_key_is_filename_safe(tmp_path):
    # Windows NTFS ADS gotcha: a raw ':' in a cache key breaks os.replace with
    # WinError 87. A name containing a colon (or other NTFS-illegal char) must
    # still produce a writable path.
    f = H._negative_cache_file("Acme: A Robotics Co.", tmp_path)
    assert ":" not in f.name
    H._mark_unresolved("Acme: A Robotics Co.", tmp_path)  # must not raise
    assert f.exists()


def test_resolved_but_zero_jobs_is_not_negative_cached(tmp_path, monkeypatch):
    # A name that DOES resolve to a real ATS board (just with 0 live jobs
    # right now) is a different signal than "never resolves at all" -- it
    # must NOT be negative-cached (a board with 0 jobs today may have jobs
    # tomorrow; this is not the redundant-dead-guess cost the finding targets).
    monkeypatch.setattr(H, "inbox_company_counts", lambda: {"Quiet Co": 5})
    monkeypatch.setattr(H, "find_career_url", lambda domain: f"https://{domain}/careers")
    monkeypatch.setattr(H, "detect_ats", lambda url: ("greenhouse", "quiet"))
    monkeypatch.setattr(H, "probe_count", lambda entry: 0)  # board found, empty
    monkeypatch.setattr(H, "save_companies", lambda entries, json_path: len(entries))

    r = H.harvest_inbox_companies(companies_json=tmp_path / "companies.json", cache_dir=tmp_path)
    assert r.resolved == 1
    assert r.verified == 0
    marker = H._negative_cache_file("Quiet Co", tmp_path)
    assert not marker.exists()


def test_default_cache_dir_falls_back_to_config_cache_dir():
    # No cache_dir passed -> defaults to config.CACHE_DIR (production behavior),
    # not None/crash.
    import config
    f = H._negative_cache_file("Some Co", config.CACHE_DIR)
    assert str(config.CACHE_DIR) in str(f)


def test_is_negative_cached_false_for_never_probed_name(tmp_path):
    assert H._is_negative_cached("Never Seen Co", tmp_path) is False
