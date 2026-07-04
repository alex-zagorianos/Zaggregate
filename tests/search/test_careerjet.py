import json
from pathlib import Path
import config
from search.careerjet_client import CareerjetClient

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"

def _payload():
    return json.loads((FX / "careerjet.json").read_text(encoding="utf-8"))

def test_parse_maps(tmp_path):
    c = CareerjetClient(cache_dir=tmp_path, cache_enabled=False)
    jobs = c.parse_results(_payload(), "test engineer")
    assert len(jobs) == 1
    assert jobs[0].title == "Test Engineer"
    assert jobs[0].source_api == "careerjet"
    assert jobs[0].salary_min == 80000 and jobs[0].salary_max == 100000
    assert "tests" in jobs[0].description

def test_no_affid_warns_and_empty(tmp_path, monkeypatch, capsys):
    # Affid now resolves env-then-secret at call time: clear both so it's unset.
    monkeypatch.delenv("CAREERJET_AFFID", raising=False)
    monkeypatch.setattr(config, "SECRETS_DIR", tmp_path / "no_secrets")
    c = CareerjetClient(cache_dir=tmp_path, cache_enabled=False)
    assert c.search("test engineer", "Cincinnati") == {"jobs": []}
    assert "WARNING" in capsys.readouterr().out


# ── S35: country -> locale_code routing (finding #30) ────────────────────────
class _FakeResponse:
    def __init__(self):
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {"jobs": []}


def _client_with_captured_get(tmp_path, monkeypatch, country):
    monkeypatch.setenv("CAREERJET_AFFID", "affid123")
    c = CareerjetClient(cache_dir=tmp_path, cache_enabled=False, country=country)
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = dict(params or {})
        return _FakeResponse()

    monkeypatch.setattr(c.session, "get", fake_get)
    return c, captured


def test_careerjet_us_country_omits_locale_code_byte_identical(tmp_path, monkeypatch):
    # US (and None/unset) must send EXACTLY today's params -- no locale_code key
    # at all, not even locale_code=None -- so a US user's request is unchanged.
    c, captured = _client_with_captured_get(tmp_path, monkeypatch, country="us")
    c.search("test engineer", "Cincinnati, OH")
    assert "locale_code" not in captured["params"]
    assert captured["params"] == {
        "keywords": "test engineer", "location": "Cincinnati, OH",
        "affid": "affid123", "pagesize": 50, "user_ip": "11.22.33.44",
        "user_agent": c.user_agent,
    }


def test_careerjet_no_country_omits_locale_code_byte_identical(tmp_path, monkeypatch):
    # Default (country=None, e.g. an older caller that doesn't pass it) is the
    # SAME as 'us' -- no locale_code, no crash.
    c, captured = _client_with_captured_get(tmp_path, monkeypatch, country=None)
    c.search("test engineer", "Cincinnati, OH")
    assert "locale_code" not in captured["params"]


def test_careerjet_gb_country_sends_locale_code(tmp_path, monkeypatch):
    c, captured = _client_with_captured_get(tmp_path, monkeypatch, country="gb")
    c.search("test engineer", "London, United Kingdom")
    assert captured["params"]["locale_code"] == "en_GB"


def test_careerjet_unmapped_country_omits_locale_code(tmp_path, monkeypatch):
    # A country with no known Careerjet locale (e.g. an ADZUNA_COUNTRIES member
    # Careerjet doesn't document) degrades to the US/default behavior rather
    # than sending a bogus param.
    c, captured = _client_with_captured_get(tmp_path, monkeypatch, country="zz")
    c.search("test engineer", "Nowhere")
    assert "locale_code" not in captured["params"]


def test_careerjet_locale_for_helper():
    assert config.careerjet_locale_for("gb") == "en_GB"
    assert config.careerjet_locale_for("us") is None
    assert config.careerjet_locale_for(None) is None
    assert config.careerjet_locale_for("zz") is None
