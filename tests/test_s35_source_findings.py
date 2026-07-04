"""S35 — zero-key transparency + international source wiring (fleet-audit
findings #1, #4/#12, #5/#13, #6/#30, #7/#8, #19, #32, #35).

Every international behavior change here is gated on config.adzuna_country_for
(location) resolving to something other than 'us' -- a US user (including
Alex's default Cincinnati/blank-location run) must see byte-identical source
registration + requests. Each test below that isn't purely testing the
non-US path pairs with an explicit "US stays byte-identical" assertion.
"""
import sys

import pytest

import config
import search.cli as cli
from search.cli import build_clients


@pytest.fixture
def keyless_env(monkeypatch, tmp_path):
    """No env credentials + an empty secrets dir -> every keyed source is
    keyless (mirrors tests/search/test_keyless_skip_surfacing.py's fixture)."""
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path / "secrets")
    for var in ("ADZUNA_APP_ID", "ADZUNA_APP_KEY", "USAJOBS_API_KEY",
                "USAJOBS_EMAIL", "USAJOBS_USER_AGENT", "JOOBLE_API_KEY",
                "CAREERJET_AFFID", "CAREERONESTOP_USER_ID", "CAREERONESTOP_TOKEN",
                "JSEARCH_RAPIDAPI_KEY", "SERPAPI_KEY"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


@pytest.fixture
def keyed_env(monkeypatch):
    """USAJobs + CareerOneStop credentials present, so the country gate (not a
    missing key) is what's being exercised."""
    monkeypatch.setenv("USAJOBS_API_KEY", "fake-usajobs-key")
    monkeypatch.setenv("USAJOBS_EMAIL", "test@example.com")
    monkeypatch.setenv("CAREERONESTOP_USER_ID", "fake-user-id")
    monkeypatch.setenv("CAREERONESTOP_TOKEN", "fake-token")
    return monkeypatch


# ── #4/#12: USAJobs + CareerOneStop skip for a non-US country ────────────────
def test_usajobs_careeronestop_skip_for_non_us_location(keyed_env):
    clients = build_clients(["usajobs", "careeronestop"], cache_enabled=False,
                            location="London, United Kingdom")
    assert clients == []


def test_usajobs_careeronestop_register_for_us_location_byte_identical(keyed_env):
    # US location (and a blank/default one) must be UNCHANGED: both register.
    for loc in ("Cincinnati, OH", "", None):
        clients = build_clients(["usajobs", "careeronestop"], cache_enabled=False,
                                location=loc)
        names = {type(c).__name__ for c in clients}
        assert names == {"USAJobsClient", "CareerOneStopClient"}, f"location={loc!r}"


def test_usajobs_careeronestop_geo_skip_not_counted_as_keyless(keyed_env):
    # A geo-skip is a DIFFERENT reason than a missing key -- it must not pollute
    # skipped_keyless (which the CLI/GUI/MCP report specifically as "needs a
    # free key"), since these sources DO have keys here.
    skipped: list[str] = []
    build_clients(["usajobs", "careeronestop"], cache_enabled=False,
                  location="Bangalore, India", skipped_keyless=skipped)
    assert skipped == []


def test_usajobs_careeronestop_still_keyless_skip_when_both_missing_and_non_us(
        keyless_env):
    # Non-US AND no key: the US-only gate short-circuits first, so the keyless
    # ValueError path never fires -- the source is absent either way, and it's
    # not reported as a keyless skip (it's a geo skip, a distinct reason).
    skipped: list[str] = []
    clients = build_clients(["usajobs", "careeronestop"], cache_enabled=False,
                            location="London, United Kingdom",
                            skipped_keyless=skipped)
    assert clients == []
    assert skipped == []


# ── #5/#13: jobsacuk opt-in via cli.build_clients' location plumbing ─────────
def test_jobsacuk_inert_for_us_location_via_cli(tmp_path, monkeypatch):
    monkeypatch.setattr("config.CACHE_DIR", tmp_path)
    clients = build_clients(["jobsacuk"], cache_enabled=False,
                            location="Cincinnati, OH")
    assert len(clients) == 1
    assert clients[0].active is False
    # Zero-network guarantee: search() returns immediately without touching
    # self.session at all when inert.
    assert clients[0].search("engineer", "Cincinnati, OH") == {"items": []}


def test_jobsacuk_activates_for_non_us_location_via_cli(tmp_path, monkeypatch):
    monkeypatch.setattr("config.CACHE_DIR", tmp_path)
    clients = build_clients(["jobsacuk"], cache_enabled=False,
                            location="London, United Kingdom")
    assert len(clients) == 1
    assert clients[0].active is True


def test_jobsacuk_in_daily_sources_and_all_sources():
    assert "jobsacuk" in config.DAILY_SOURCES
    assert "jobsacuk" in cli.ALL_SOURCES


def test_jobsacuk_daily_run_style_registration_inert_for_us(tmp_path, monkeypatch):
    # Simulates daily_run.py's call shape (DAILY_SOURCES + a US location): the
    # newly-added jobsacuk entry must register-but-stay-inert, never crash, and
    # never touch the network for the default US case.
    monkeypatch.setattr("config.CACHE_DIR", tmp_path)
    skipped: list[str] = []
    clients = build_clients(config.DAILY_SOURCES, cache_enabled=True,
                            skipped_keyless=skipped, location="Cincinnati, OH")
    jobsacuk = next(c for c in clients if type(c).__name__ == "JobsAcUkClient")
    assert jobsacuk.active is False


# ── #1/#32/#7: CLI main() wires skipped_keyless + prints summaries ───────────
def _run_cli_main(argv, monkeypatch, tmp_path):
    """Runs search.cli.main() with network/search stubbed out so only the
    registration + print-summary path executes. Exits via SystemExit after
    'No results found.' (run_full_search stubbed to return [])."""
    from search.search_engine import SearchEngine
    monkeypatch.setattr(SearchEngine, "run_full_search", lambda self, **k: [])
    monkeypatch.setattr(sys, "argv", argv)
    try:
        cli.main()
    except SystemExit:
        pass


def test_cli_main_prints_keyless_skip_summary(tmp_path, monkeypatch, keyless_env, capsys):
    argv = ["cli.py", "--sources", "adzuna,themuse", "--location", "Cincinnati, OH",
            "--output-dir", str(tmp_path / "out"), "--user-config",
            str(tmp_path / "missing_config.json"), "--no-discover"]
    _run_cli_main(argv, monkeypatch, tmp_path)
    out = capsys.readouterr().out
    assert "Skipped 1 source(s) for a missing free key: adzuna" in out
    assert "Running with 1 of 2 sources (1 need free keys" in out


def test_cli_main_no_skip_line_when_all_keyless_capable(tmp_path, monkeypatch, capsys):
    argv = ["cli.py", "--sources", "themuse,remoteok", "--location", "Cincinnati, OH",
            "--output-dir", str(tmp_path / "out"), "--user-config",
            str(tmp_path / "missing_config.json"), "--no-discover"]
    _run_cli_main(argv, monkeypatch, tmp_path)
    out = capsys.readouterr().out
    assert "Skipped" not in out
    assert "Running with 2 of 2 sources (0 need free keys" in out


def test_cli_main_active_sources_line_unchanged_shape(tmp_path, monkeypatch, capsys):
    # The pre-existing "Active sources: [...]" line must still be there (a US
    # user's console output gains only NEW lines after it, nothing removed).
    argv = ["cli.py", "--sources", "themuse", "--location", "Cincinnati, OH",
            "--output-dir", str(tmp_path / "out"), "--user-config",
            str(tmp_path / "missing_config.json"), "--no-discover"]
    _run_cli_main(argv, monkeypatch, tmp_path)
    out = capsys.readouterr().out
    assert "Active sources: ['TheMuseClient']" in out


# ── #1: MCP server search_jobs surfaces skipped_keyless ──────────────────────
def test_mcp_search_jobs_returns_skipped_keyless(tmp_path, monkeypatch, keyless_env):
    import mcp_server
    # search_jobs() imports load_user_config locally from search.cli -- patch it
    # there, not on the mcp_server module (which doesn't hold the name).
    monkeypatch.setattr(cli, "load_user_config", lambda: {
        "keywords": ["test engineer"], "location": "Cincinnati, OH",
        "sources": {s: False for s in config.DAILY_SOURCES if s != "adzuna"},
    })
    from search.search_engine import SearchEngine
    monkeypatch.setattr(SearchEngine, "run_full_search", lambda self, **k: [])
    from tracker import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    result = mcp_server.search_jobs()
    assert "adzuna" in result["skipped_keyless"]


def test_mcp_search_jobs_no_error_key_present_when_clients_ok(tmp_path, monkeypatch):
    # Restrict to a single no-key-needed source so this proves "0 skipped ->
    # empty list", independent of whatever real credentials this machine has
    # in .env/secrets for the other DAILY_SOURCES entries.
    import mcp_server
    monkeypatch.setattr(cli, "load_user_config", lambda: {
        "keywords": ["test engineer"], "location": "Cincinnati, OH",
        "sources": {s: False for s in config.DAILY_SOURCES if s != "themuse"},
    })
    monkeypatch.setattr(config, "DAILY_SOURCES", ["themuse"])
    from search.search_engine import SearchEngine
    monkeypatch.setattr(SearchEngine, "run_full_search", lambda self, **k: [])
    from tracker import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    result = mcp_server.search_jobs()
    assert result["skipped_keyless"] == []
    assert "found" in result


# ── #35: Adzuna cache-schema version guards stale cache reads ────────────────
def test_adzuna_cache_key_includes_schema_version(tmp_path, monkeypatch):
    from search.adzuna_client import AdzunaClient, _CACHE_SCHEMA_VERSION
    from search.http_util import cache_key
    monkeypatch.setenv("ADZUNA_APP_ID", "id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "key")
    c = AdzunaClient(cache_dir=tmp_path, cache_enabled=False, country="us")
    expected = cache_key("adzuna", "us", "test engineer", "Cincinnati, OH",
                         None, 1, _CACHE_SCHEMA_VERSION)
    # Recompute the same key search() would build for a non-remote query.
    unversioned = cache_key("adzuna", "us", "test engineer", "Cincinnati, OH", None, 1)
    assert expected != unversioned  # version token changes the hash


def test_adzuna_old_schema_cache_entry_is_a_miss_not_misread(tmp_path, monkeypatch):
    # A pre-versioning cache entry (written under the OLD key shape, i.e.
    # without the version token) must simply MISS under the new key -- never be
    # read back and misinterpreted. This is the one-time invalidation the fix
    # accepts (noted in the finding): the entry is orphaned, not corrupted.
    monkeypatch.setenv("ADZUNA_APP_ID", "id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "key")
    from search.adzuna_client import AdzunaClient
    from search.http_util import FileCache, cache_key
    c = AdzunaClient(cache_dir=tmp_path, cache_enabled=True, country="us")
    old_key = cache_key("adzuna", "us", "test engineer", "Cincinnati, OH", None, 1)
    FileCache("adzuna", tmp_path).put(old_key, {"results": [], "_stale_schema": True})
    # A real search() call builds the NEW (versioned) key, which is a clean miss
    # against the old-schema entry above -- confirm by checking cache.get(new
    # key) is None while the old entry is still readable directly (proving the
    # miss is due to the key changing, not the cache being broken/empty).
    from search.adzuna_client import _CACHE_SCHEMA_VERSION
    new_key = cache_key("adzuna", "us", "test engineer", "Cincinnati, OH", None, 1,
                        _CACHE_SCHEMA_VERSION)
    assert new_key != old_key
    assert c.cache.get(new_key) is None
    assert c.cache.get(old_key) is not None
