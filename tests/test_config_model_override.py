import importlib


def test_anthropic_model_env_override(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-test-model")
    import config
    importlib.reload(config)
    try:
        assert config.ANTHROPIC_MODEL == "claude-test-model"
    finally:
        monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
        importlib.reload(config)
    assert config.ANTHROPIC_MODEL == "claude-sonnet-4-6"
