import config
from resume import service
from ui import settings


def test_write_read_secret_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path / "secrets")
    assert config.read_secret("anthropic_key") is None
    assert config.write_secret("anthropic_key", "  sk-ant-abc123  ") is True
    assert config.read_secret("anthropic_key") == "sk-ant-abc123"   # trimmed
    assert config.write_secret("anthropic_key", "") is True         # blank clears
    assert config.read_secret("anthropic_key") is None


def test_ui_settings_api_key_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path / "secrets")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert settings.has_api_key("anthropic") is False
    assert settings.set_api_key("anthropic", "sk-ant-xyz7890abcdef") is True
    assert settings.get_api_key("anthropic").startswith("sk-ant-")
    assert settings.has_api_key("anthropic") is True
    assert settings.set_api_key("bogus", "x") is False              # unknown provider


def test_env_var_wins_over_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path / "secrets")
    settings.set_api_key("anthropic", "sk-ant-fromfile-aaaaaa")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fromenv")
    assert settings.get_api_key("anthropic") == "sk-ant-fromenv"


def test_looks_like_key():
    assert settings.looks_like_key("anthropic", "sk-ant-" + "x" * 20)
    assert not settings.looks_like_key("anthropic", "nope")
    assert settings.looks_like_key("serpapi", "abcd1234")
    assert not settings.looks_like_key("serpapi", "")


def test_api_available_honors_pasted_key(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path / "secrets")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", None)
    assert service.api_available() is False
    config.write_secret("anthropic_key", "sk-ant-test")
    assert service.api_available() is True
