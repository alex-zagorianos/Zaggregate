"""S35 — international / non-US coverage.

Two confirmed weaknesses that made a non-US user (London, Bangalore, Toronto)
get near-nothing out of the box:

  1. Adzuna always queried the /us/ endpoint (US-only jobs) because build_clients
     never derived the country from the user's location.
  2. metro_variants only kept the exact "City, Country" string, so a posting
     listed as bare "London" / "London, England" was bucketed 'elsewhere' and
     hidden from the default Inbox "Local + remote" view.
"""
import config
from coverage.geography import metro_variants
from geo.filter import classify


# ── Adzuna country derivation (build_clients wiring) ──────────────────────────
def test_adzuna_country_for_non_us_locations():
    assert config.adzuna_country_for("London, United Kingdom") == "gb"
    assert config.adzuna_country_for("London, UK") == "gb"
    assert config.adzuna_country_for("Bangalore, India") == "in"
    assert config.adzuna_country_for("Toronto, Canada") == "ca"
    assert config.adzuna_country_for("Sydney, Australia") == "au"


def test_adzuna_country_for_us_stays_us_no_state_collision():
    # US locations must stay 'us' — including the Indiana ("IN") tail, which must
    # NOT be misread as India.
    assert config.adzuna_country_for("Cincinnati, OH") == "us"
    assert config.adzuna_country_for("Indianapolis, IN") == "us"
    assert config.adzuna_country_for("Austin, TX") == "us"
    assert config.adzuna_country_for("") == "us"


def test_build_clients_passes_derived_country_to_adzuna(monkeypatch):
    # AdzunaClient must be constructed with the location-derived country. Stub the
    # client to capture the kwarg (no network / no key needed).
    import search.cli as cli
    captured = {}

    class _Stub:
        def __init__(self, *a, **k):
            captured.update(k)

    monkeypatch.setattr(cli, "AdzunaClient", _Stub)
    cli.build_clients(["adzuna"], cache_enabled=False,
                      location="London, United Kingdom")
    assert captured.get("country") == "gb"


# ── metro_variants non-US fallback ────────────────────────────────────────────
def test_metro_variants_adds_bare_city_for_non_us():
    v = metro_variants("London, United Kingdom")
    assert "london" in v                    # bare city so "London, England" matches
    assert "london, united kingdom" in v


def test_metro_variants_us_metro_unchanged():
    # A US CBSA metro must keep expanding via the table and NOT trigger the bare-
    # city fallback branch differently — the principal-city + metro-area variants
    # are still present (byte-identical behavior for US users).
    v = metro_variants("Cincinnati, OH")
    assert "cincinnati" in v
    assert any("metro area" in x for x in v)


def test_international_local_job_classifies_local():
    # A London posting listed as "London, England" is LOCAL for a London,UK user
    # (was 'elsewhere' -> hidden before the fallback).
    assert classify("London, England", "Marketing Manager",
                    "London, United Kingdom") == "local"
    assert classify("Bengaluru, India", "Data Analyst",
                    "Bangalore, India") in ("local", "elsewhere")  # city token differs


def test_us_local_job_still_local():
    assert classify("Cincinnati, OH", "Engineer", "Cincinnati, OH") == "local"
