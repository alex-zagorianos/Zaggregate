"""S35 finding #23 (major): build_clients() had no top-level guard, so ANY
non-ValueError exception during a single source's construction (a malformed
user_config.json hitting a KeyError/TypeError, a registry-loading bug) would
propagate out of build_clients and abort the ENTIRE run -- the user gets zero
jobs from every source, not just the broken one.

Each source's construction now runs inside a per-source try/except Exception
that logs "[source] failed to initialize — skipped: {e}" and continues. The
existing per-source `except ValueError` keyless-skip paths are UNCHANGED --
they still catch ValueError themselves and never reach the new outer handler."""
import pytest

from search import cli


def test_non_valueerror_in_one_source_does_not_abort_others(monkeypatch, tmp_path):
    # themuse's constructor is patched to raise a KeyError (a stand-in for "a
    # config-reading bug hits a malformed user_config.json"), which is NOT a
    # ValueError and previously had no handler anywhere in build_clients.
    from search import themuse_client

    def _boom(*a, **k):
        raise KeyError("malformed config")
    monkeypatch.setattr(themuse_client, "TheMuseClient", _boom)

    clients = cli.build_clients(
        ["themuse", "remoteok", "remotive"], cache_enabled=False)
    names = {type(c).__name__ for c in clients}
    # themuse is skipped (its construction raised)...
    assert "TheMuseClient" not in names
    # ...but the OTHER sources still built successfully -- the run is not
    # aborted just because themuse's constructor blew up.
    assert names == {"RemoteOKClient", "RemotiveClient"}


def test_non_valueerror_logs_failed_to_initialize(monkeypatch, capsys):
    from search import themuse_client

    def _boom(*a, **k):
        raise KeyError("malformed config")
    monkeypatch.setattr(themuse_client, "TheMuseClient", _boom)

    cli.build_clients(["themuse"], cache_enabled=False)
    console = capsys.readouterr().out
    assert "[themuse]" in console
    assert "failed to initialize" in console
    assert "skipped" in console


def test_keyed_source_valueerror_path_unchanged(monkeypatch, tmp_path):
    # Regression guard: a keyed source's documented ValueError (missing key)
    # must still be caught by its OWN except ValueError block (and reported via
    # skipped_keyless), not routed through the new generic "failed to
    # initialize" message -- those are semantically different (missing key vs.
    # a genuine bug).
    import config
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path / "secrets")
    for var in ("ADZUNA_APP_ID", "ADZUNA_APP_KEY"):
        monkeypatch.delenv(var, raising=False)

    skipped: list[str] = []
    clients = cli.build_clients(["adzuna"], cache_enabled=False,
                                skipped_keyless=skipped)
    assert clients == []
    assert skipped == ["adzuna"]


def test_construction_bug_in_careers_does_not_abort_run(monkeypatch, tmp_path):
    # A concrete instance of the finding's own example: CareersClient's
    # constructor (registry loading) throwing a non-ValueError must not sink
    # every other source in the same build_clients() call.
    from scrape import careers_client

    def _boom(*a, **k):
        raise TypeError("registry json malformed")
    monkeypatch.setattr(careers_client, "CareersClient", _boom)

    clients = cli.build_clients(["careers", "remoteok"], cache_enabled=False)
    names = {type(c).__name__ for c in clients}
    assert "RemoteOKClient" in names
    assert not any("Careers" in n for n in names)


def test_all_sources_can_still_blow_up_together_gracefully(monkeypatch):
    # Every requested source failing must still return [] cleanly (the
    # existing "ABORT: no sources could be initialized" path in daily_run.py
    # is driven by an EMPTY clients list, not an uncaught exception).
    from search import themuse_client, remoteok_client

    def _boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(themuse_client, "TheMuseClient", _boom)
    monkeypatch.setattr(remoteok_client, "RemoteOKClient", _boom)

    clients = cli.build_clients(["themuse", "remoteok"], cache_enabled=False)
    assert clients == []
