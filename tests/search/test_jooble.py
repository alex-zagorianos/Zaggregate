import json
from pathlib import Path
import config
from search.jooble_client import JoobleClient

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"

def _payload():
    return json.loads((FX / "jooble.json").read_text(encoding="utf-8"))

def test_parse_maps(tmp_path):
    c = JoobleClient(cache_dir=tmp_path, cache_enabled=False)
    jobs = c.parse_results(_payload(), "automation engineer")
    assert len(jobs) == 1
    assert jobs[0].title == "Automation Engineer"
    assert jobs[0].source_api == "jooble"
    assert "lines" in jobs[0].description  # html stripped
    assert jobs[0].url.endswith("/123")

def test_no_key_warns_and_empty(tmp_path, monkeypatch, capsys):
    # Key now resolves env-then-secret at call time: clear both so it's unset.
    monkeypatch.delenv("JOOBLE_API_KEY", raising=False)
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path / "no_secrets")
    c = JoobleClient(cache_dir=tmp_path, cache_enabled=False)
    assert c.search("automation engineer", "Cincinnati") == {"jobs": []}
    assert "WARNING" in capsys.readouterr().out


# ── S35: country -> per-country host routing (finding #30) ───────────────────
class _FakeResponse:
    def __init__(self):
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {"jobs": []}


def _client_with_captured_post(tmp_path, monkeypatch, country):
    monkeypatch.setenv("JOOBLE_API_KEY", "key123")
    c = JoobleClient(cache_dir=tmp_path, cache_enabled=False, country=country)
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _FakeResponse()

    monkeypatch.setattr(c.session, "post", fake_post)
    return c, captured


def test_jooble_us_country_hits_bare_host_byte_identical(tmp_path, monkeypatch):
    # US (and None/unset) must hit the EXACT same bare-host URL as today.
    c, captured = _client_with_captured_post(tmp_path, monkeypatch, country="us")
    c.search("automation engineer", "Cincinnati, OH")
    assert captured["url"] == "https://jooble.org/api/key123"
    assert captured["json"] == {"keywords": "automation engineer",
                                "location": "Cincinnati, OH"}


def test_jooble_no_country_hits_bare_host_byte_identical(tmp_path, monkeypatch):
    c, captured = _client_with_captured_post(tmp_path, monkeypatch, country=None)
    c.search("automation engineer", "Cincinnati, OH")
    assert captured["url"] == "https://jooble.org/api/key123"


def test_jooble_gb_country_hits_uk_host(tmp_path, monkeypatch):
    c, captured = _client_with_captured_post(tmp_path, monkeypatch, country="gb")
    c.search("automation engineer", "London, United Kingdom")
    assert captured["url"] == "https://uk.jooble.org/api/key123"


def test_jooble_unmapped_country_hits_bare_host(tmp_path, monkeypatch):
    c, captured = _client_with_captured_post(tmp_path, monkeypatch, country="zz")
    c.search("automation engineer", "Nowhere")
    assert captured["url"] == "https://jooble.org/api/key123"


def test_jooble_host_for_helper():
    assert config.jooble_host_for("gb") == "uk.jooble.org"
    assert config.jooble_host_for("us") == "jooble.org"
    assert config.jooble_host_for(None) == "jooble.org"
    assert config.jooble_host_for("zz") == "jooble.org"
