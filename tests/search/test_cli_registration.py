from search import cli

def test_all_sources_includes_new():
    for s in ("arbeitnow", "jooble", "careerjet", "linkedin_guest", "serpapi"):
        assert s in cli.ALL_SOURCES

def test_build_clients_arbeitnow(tmp_path):
    clients = cli.build_clients(["arbeitnow"], cache_enabled=False)
    assert [type(c).__name__ for c in clients] == ["ArbeitnowClient"]

def test_build_clients_serpapi_skipped_without_key(monkeypatch, capsys):
    import search.serpapi_client as SC
    monkeypatch.setattr(SC, "SERPAPI_KEY", "")
    import config
    monkeypatch.setattr(SC.config, "SECRETS_DIR", config.USER_DATA_DIR / "nonexistent")
    clients = cli.build_clients(["serpapi"], cache_enabled=False)
    assert clients == []
    assert "Skipping" in capsys.readouterr().out
