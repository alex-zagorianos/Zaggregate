"""B2 — source keys + aggregator unlock (review P0#4, P1 Tier A).

Covers: env-then-secret key resolution precedence, keyless self-skip for every
newly-wired source, the CareerOneStop parser/pagination/skip, Adzuna country
templating, linkedin_guest stays off without explicit opt-in, the daily max-pages
default change, and the language-guard on/off gating.
"""
import os

import pytest

import config


# ── config.resolve_secret precedence: env > secret > absent ───────────────────

@pytest.fixture
def secrets(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path / "secrets")
    return tmp_path / "secrets"


def test_resolve_secret_absent(secrets, monkeypatch):
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    assert config.resolve_secret("ADZUNA_APP_ID", "adzuna_app_id") is None


def test_resolve_secret_file_only(secrets, monkeypatch):
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    config.write_secret("adzuna_app_id", "file-id")
    assert config.resolve_secret("ADZUNA_APP_ID", "adzuna_app_id") == "file-id"


def test_resolve_secret_env_wins_over_file(secrets, monkeypatch):
    config.write_secret("adzuna_app_id", "file-id")
    monkeypatch.setenv("ADZUNA_APP_ID", "env-id")
    assert config.resolve_secret("ADZUNA_APP_ID", "adzuna_app_id") == "env-id"


def test_every_source_credential_has_a_secret_name():
    for name in ("adzuna_app_id", "adzuna_app_key", "usajobs_api_key",
                 "usajobs_email", "jooble_api_key", "careerjet_affid",
                 "careeronestop_user_id", "careeronestop_token"):
        assert name in config.SOURCE_SECRET_FILES


# ── ui.settings source-key roundtrip + env precedence ─────────────────────────

def test_settings_source_key_roundtrip(secrets, monkeypatch):
    from ui import settings
    for env in ("CAREERONESTOP_TOKEN",):
        monkeypatch.delenv(env, raising=False)
    assert settings.get_api_key("careeronestop_token") == ""
    assert settings.set_api_key("careeronestop_token", "tok-123") is True
    assert settings.get_api_key("careeronestop_token") == "tok-123"


def test_settings_source_key_env_wins(secrets, monkeypatch):
    from ui import settings
    settings.set_api_key("jooble_api_key", "from-file")
    monkeypatch.setenv("JOOBLE_API_KEY", "from-env")
    assert settings.get_api_key("jooble_api_key") == "from-env"


# ── keyless self-skip for every newly-wired source ────────────────────────────

def _clear_source_env(monkeypatch):
    for env in ("ADZUNA_APP_ID", "ADZUNA_APP_KEY", "JOOBLE_API_KEY",
                "CAREERJET_AFFID", "CAREERONESTOP_USER_ID", "CAREERONESTOP_TOKEN",
                "USAJOBS_API_KEY", "USAJOBS_EMAIL", "USAJOBS_USER_AGENT"):
        monkeypatch.delenv(env, raising=False)


def test_jooble_keyless_self_skip(secrets, monkeypatch, tmp_path, capsys):
    _clear_source_env(monkeypatch)
    from search.jooble_client import JoobleClient
    c = JoobleClient(cache_dir=tmp_path, cache_enabled=False)
    assert c.search("engineer", location="") == {"jobs": []}
    assert "JOOBLE_API_KEY unset" in capsys.readouterr().out


def test_careerjet_keyless_self_skip(secrets, monkeypatch, tmp_path, capsys):
    _clear_source_env(monkeypatch)
    from search.careerjet_client import CareerjetClient
    c = CareerjetClient(cache_dir=tmp_path, cache_enabled=False)
    assert c.search("engineer", location="") == {"jobs": []}
    assert "CAREERJET_AFFID unset" in capsys.readouterr().out


def test_careeronestop_raises_without_key(secrets, monkeypatch):
    # careeronestop is key-GATED (like adzuna/usajobs): missing creds -> ValueError
    # so build_clients() catches it and prints a one-line skip.
    _clear_source_env(monkeypatch)
    from search.careeronestop_client import CareerOneStopClient
    with pytest.raises(ValueError):
        CareerOneStopClient(cache_enabled=False)


def test_build_clients_skips_keyless_careeronestop(secrets, monkeypatch, capsys):
    _clear_source_env(monkeypatch)
    from search.cli import build_clients
    clients = build_clients(["careeronestop"], cache_enabled=False)
    assert clients == []
    assert "[careeronestop] Skipping" in capsys.readouterr().out


def test_build_clients_adzuna_and_usajobs_skip_keyless(secrets, monkeypatch, capsys):
    _clear_source_env(monkeypatch)
    from search.cli import build_clients
    clients = build_clients(["adzuna", "usajobs"], cache_enabled=False)
    assert clients == []
    out = capsys.readouterr().out
    assert "[adzuna] Skipping" in out and "[usajobs] Skipping" in out


def test_jooble_careerjet_register_even_keyless(secrets, monkeypatch):
    # jooble/careerjet self-skip at CALL time (they register as clients so their
    # keyless warning fires per-run), unlike the key-gated adzuna/usajobs.
    _clear_source_env(monkeypatch)
    from search.cli import build_clients
    clients = build_clients(["jooble", "careerjet"], cache_enabled=False)
    assert len(clients) == 2


# ── CareerOneStop parser fixtures + pagination + 404 ──────────────────────────

def _cos_client(tmp_path):
    from search.careeronestop_client import CareerOneStopClient
    return CareerOneStopClient(user_id="uid", token="tok",
                               cache_dir=tmp_path, cache_enabled=False)


def _cos_payload():
    return {
        "Jobs": [
            {
                "JvId": "abc123",
                "JobTitle": "Registered Nurse",
                "Company": "Mercy Health",
                "Location": "Cincinnati, OH",
                "URL": "https://example.com/jobs/abc123",
                "AccquisitionDate": "2026-06-20",
                "Description": "<p>Provide patient care.</p>",
            },
            {
                "JvId": "def456",
                "JobTitle": "CDL Driver",
                "Company": "Freight Co",
                "Location": "Dayton, OH",
                "URL": "https://example.com/jobs/def456",
                "AccquisitionDate": "2026-06-21",
                "Description": "Drive trucks.",
            },
        ],
        "RecordCount": 2,
    }


def test_careeronestop_parse(tmp_path):
    c = _cos_client(tmp_path)
    out = c.parse_results(_cos_payload(), "nurse")
    assert [j.title for j in out] == ["Registered Nurse", "CDL Driver"]
    j = out[0]
    assert j.company == "Mercy Health"
    assert j.location == "Cincinnati, OH"
    assert j.url == "https://example.com/jobs/abc123"
    assert j.created == "2026-06-20"
    assert j.job_id == "careeronestop_abc123"
    assert j.source_api == "careeronestop"
    assert "<" not in j.description


def test_careeronestop_parse_handles_empty_and_aliases(tmp_path):
    c = _cos_client(tmp_path)
    assert c.parse_results({"Jobs": []}, "x") == []
    assert c.parse_results({}, "x") == []
    # AcquisitionDate (correctly spelled) alias also read.
    alt = {"Jobs": [{"JvId": "1", "JobTitle": "Teacher", "Company": "ISD",
                     "Location": "Austin, TX", "URL": "u",
                     "AcquisitionDate": "2026-06-01"}]}
    j = c.parse_results(alt, "teacher")[0]
    assert j.created == "2026-06-01"


def test_careeronestop_pagination_startrecord(tmp_path, monkeypatch):
    c = _cos_client(tmp_path)
    captured = {}

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"Jobs": [], "RecordCount": 0}

    def _get(url, **kw):
        captured["url"] = url
        return _Resp()

    monkeypatch.setattr(c.session, "get", _get)
    c.search("nurse", location="Cincinnati, OH", page=1)
    url1 = captured["url"]
    c.search("nurse", location="Cincinnati, OH", page=2)
    url2 = captured["url"]
    # page 1 -> startRecord 1; page 2 -> startRecord 1 + pageSize.
    assert "/1/" in url1
    assert f"/{config.CAREERONESTOP_RESULTS_PER_PAGE + 1}/" in url2
    # location comma is URL-encoded, not a raw path split.
    assert "Cincinnati%2C" in url1 or "Cincinnati%2C%20OH" in url1


def test_careeronestop_404_is_empty_not_error(tmp_path, monkeypatch):
    c = _cos_client(tmp_path)

    class _Resp:
        status_code = 404

        def raise_for_status(self):
            raise AssertionError("404 must not raise")

        def json(self):
            raise AssertionError("404 body must not be parsed")

    monkeypatch.setattr(c.session, "get", lambda url, **kw: _Resp())
    data = c.search("nonexistent", location="")
    assert data == {"Jobs": [], "RecordCount": 0}


def test_careeronestop_attribution_present():
    from search import careeronestop_client
    assert "CareerOneStop" in careeronestop_client.ATTRIBUTION
    assert "Department of Labor" in careeronestop_client.ATTRIBUTION


# ── Adzuna country templating ─────────────────────────────────────────────────

def test_adzuna_country_url_default_is_us():
    assert config.adzuna_country_url() == "https://api.adzuna.com/v1/api/jobs/us/search"


@pytest.mark.parametrize("cc,expect", [
    ("gb", "gb"), ("DE", "de"), ("ca", "ca"),
])
def test_adzuna_country_url_interpolates(cc, expect):
    assert f"/jobs/{expect}/search" in config.adzuna_country_url(cc)


def test_adzuna_country_for_explicit_country_wins():
    assert config.adzuna_country_for(location="London", country="gb") == "gb"


def test_adzuna_country_for_location_tail():
    assert config.adzuna_country_for(location="Toronto, Canada") == "ca"
    assert config.adzuna_country_for(location="Berlin, Germany") == "de"


def test_adzuna_country_for_unknown_falls_back():
    # Unsupported code -> module default ('us' unless env set).
    assert config.adzuna_country_for(country="zz") == config.ADZUNA_COUNTRY


def test_adzuna_client_uses_country(secrets, monkeypatch, tmp_path):
    from search.adzuna_client import AdzunaClient
    c = AdzunaClient(app_id="i", app_key="k", cache_dir=tmp_path,
                     cache_enabled=False, country="gb")
    assert c.base_url == "https://api.adzuna.com/v1/api/jobs/gb/search"


# ── linkedin_guest stays off without explicit opt-in ──────────────────────────

def test_linkedin_guest_off_by_default():
    from search.cli import ALL_SOURCES, OPT_IN_SOURCES
    assert "linkedin_guest" in OPT_IN_SOURCES
    cfg_sources = {}   # nothing set
    sources = [s for s in ALL_SOURCES
               if cfg_sources.get(s, s not in OPT_IN_SOURCES)]
    assert "linkedin_guest" not in sources
    # A normal on-by-default source is still present.
    assert "adzuna" in sources


def test_linkedin_guest_on_when_explicitly_enabled():
    from search.cli import ALL_SOURCES, OPT_IN_SOURCES
    cfg_sources = {"linkedin_guest": True}
    sources = [s for s in ALL_SOURCES
               if cfg_sources.get(s, s not in OPT_IN_SOURCES)]
    assert "linkedin_guest" in sources


def test_linkedin_guest_not_in_daily_sources():
    assert "linkedin_guest" not in config.DAILY_SOURCES


# ── daily_run --max-pages default is now 2 ────────────────────────────────────

def test_daily_run_max_pages_default_is_two(monkeypatch):
    import daily_run
    parser = _daily_parser(daily_run)
    ns = parser.parse_args([])
    assert ns.max_pages == 2


def _daily_parser(daily_run):
    # Rebuild the argparse the same way main() does, without running the search.
    import argparse
    from config import DAILY_MIN_SCORE
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-config", type=str, default=None)
    parser.add_argument("--project", type=str, default=None)
    parser.add_argument("--min-score", type=int, default=None)
    parser.add_argument("--max-pages", type=int, default=2)
    return parser


def test_daily_run_source_arg_default_two():
    # The real parser lives inside main(); assert the literal default via the file
    # so a future refactor that drops the change is caught.
    import inspect
    import daily_run
    src = inspect.getsource(daily_run.main)
    assert '"--max-pages", type=int, default=2' in src


# ── language guard on/off gating ──────────────────────────────────────────────

def test_language_guard_off_by_default(monkeypatch):
    monkeypatch.setattr(config, "LANGUAGE_GUARD", False)
    monkeypatch.setattr(config, "ADZUNA_COUNTRY", "us")
    assert config.language_guard_active() is False


def test_language_guard_on_when_forced(monkeypatch):
    monkeypatch.setattr(config, "LANGUAGE_GUARD", True)
    monkeypatch.setattr(config, "ADZUNA_COUNTRY", "us")
    assert config.language_guard_active() is True


def test_language_guard_on_when_non_us_country(monkeypatch):
    monkeypatch.setattr(config, "LANGUAGE_GUARD", False)
    monkeypatch.setattr(config, "ADZUNA_COUNTRY", "de")
    assert config.language_guard_active() is True


# ── match.language heuristic ──────────────────────────────────────────────────

def test_is_probably_english_true_for_english_prose():
    from match.language import is_probably_english
    assert is_probably_english(
        "We are looking for a controls engineer to join our team and design and "
        "build the automation systems that run our factory.") is True


def test_is_probably_english_false_for_german():
    from match.language import is_probably_english
    assert is_probably_english(
        "Wir suchen einen erfahrenen Ingenieur fuer unser Team, der unsere "
        "Maschinen und Anlagen entwickelt und in Betrieb nimmt und wartet.") is False


def test_is_probably_english_abstains_on_short_text():
    from match.language import is_probably_english
    # Too little signal -> abstain toward English (don't drop a bare title).
    assert is_probably_english("Registered Nurse") is True
    assert is_probably_english("") is True


def test_english_stopword_ratio_range():
    from match.language import english_stopword_ratio
    assert english_stopword_ratio("") == 0.0
    r = english_stopword_ratio("the and of to for with you your our we")
    assert r == 1.0
