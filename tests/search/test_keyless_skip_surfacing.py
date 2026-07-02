"""Silent-zero surfacing: build_clients reports which sources self-skipped for a
missing FREE key via the skipped_keyless out-param, driven by each source's OWN
skip condition (not a hardcoded list). The GUI turns the count into an actionable
line. See review-onboarding 'silent self-skip' finding."""
import pytest

from search import cli


@pytest.fixture
def keyless_env(monkeypatch, tmp_path):
    """No env credentials + an empty secrets dir -> every keyed source is keyless."""
    import config
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path / "secrets")
    for var in ("ADZUNA_APP_ID", "ADZUNA_APP_KEY", "USAJOBS_API_KEY",
                "USAJOBS_EMAIL", "USAJOBS_USER_AGENT", "JOOBLE_API_KEY",
                "CAREERJET_AFFID", "CAREERONESTOP_USER_ID", "CAREERONESTOP_TOKEN",
                "JSEARCH_RAPIDAPI_KEY", "SERPAPI_KEY"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def test_skipped_keyless_collects_raising_and_selfskip_sources(keyless_env):
    skipped: list[str] = []
    clients = cli.build_clients(
        ["adzuna", "usajobs", "careeronestop", "jooble", "careerjet", "themuse"],
        cache_enabled=False, skipped_keyless=skipped)
    # adzuna/usajobs/careeronestop raise -> not registered; jooble/careerjet
    # register but self-skip (their keyless() predicate) -> counted too.
    assert set(skipped) == {"adzuna", "usajobs", "careeronestop",
                            "jooble", "careerjet"}
    # themuse needs no key -> never counted.
    assert "themuse" not in skipped
    # The key-gated raisers are absent from the built clients; the self-skippers
    # are still present (they just fetch nothing without a key).
    names = {type(c).__name__ for c in clients}
    assert "AdzunaClient" not in names
    assert {"JoobleClient", "CareerjetClient", "TheMuseClient"} <= names


def test_skipped_keyless_is_optional_and_backward_compatible(keyless_env):
    # Callers that don't pass the list get identical behavior (no crash).
    clients = cli.build_clients(["themuse"], cache_enabled=False)
    assert [type(c).__name__ for c in clients] == ["TheMuseClient"]


def test_skipped_keyless_empty_when_no_keyed_sources(keyless_env):
    skipped: list[str] = []
    cli.build_clients(["themuse", "remoteok"], cache_enabled=False,
                      skipped_keyless=skipped)
    assert skipped == []


def test_jooble_careerjet_keyless_predicate(keyless_env):
    from search.jooble_client import JoobleClient
    from search.careerjet_client import CareerjetClient
    assert JoobleClient.keyless() is True
    assert CareerjetClient.keyless() is True


def test_jooble_not_keyless_with_key(keyless_env, monkeypatch):
    monkeypatch.setenv("JOOBLE_API_KEY", "abc123")
    from search.jooble_client import JoobleClient
    assert JoobleClient.keyless() is False
    skipped: list[str] = []
    cli.build_clients(["jooble"], cache_enabled=False, skipped_keyless=skipped)
    assert "jooble" not in skipped
