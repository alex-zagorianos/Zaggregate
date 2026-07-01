from search import cli

def test_all_sources_includes_new():
    for s in ("arbeitnow", "jooble", "careerjet", "linkedin_guest", "serpapi", "socrata"):
        assert s in cli.ALL_SOURCES

def test_socrata_not_in_daily_sources():
    # Must stay opt-in so existing users' automated daily run is byte-identical.
    import config
    assert "socrata" not in config.DAILY_SOURCES

def test_build_clients_socrata_inert_without_cities(tmp_path):
    # Registers but no-ops (zero HTTP) until a city is configured.
    clients = cli.build_clients(["socrata"], cache_enabled=False)
    assert [type(c).__name__ for c in clients] == ["SocrataClient"]
    assert clients[0].search_and_parse("nurse", "", None, 1) == []

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
