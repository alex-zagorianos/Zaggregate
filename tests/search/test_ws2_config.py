import config

def test_new_source_consts_present():
    assert config.ARBEITNOW_URL.startswith("https://")
    assert config.JOOBLE_URL.startswith("https://")
    assert config.CAREERJET_URL.startswith("https://")
    assert config.LINKEDIN_GUEST_URL.startswith("https://")
    assert config.SERPAPI_URL.startswith("https://")
    assert isinstance(config.SERPAPI_MONTHLY_LIMIT, int)
    assert isinstance(config.ARBEITNOW_RATE_LIMIT, int)
