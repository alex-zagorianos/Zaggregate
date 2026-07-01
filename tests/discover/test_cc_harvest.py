from pathlib import Path
import discover.cc_harvest as H

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"

class _Resp:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status
    def raise_for_status(self):
        pass

def _cdx_text():
    return (FX / "cdx_greenhouse.jsonl").read_text(encoding="utf-8")

def test_harvest_dedupes_slugs(monkeypatch):
    monkeypatch.setattr(H, "_cdx_fetch", lambda host, crawl_id, limit: _cdx_text().splitlines())
    out = H.harvest_slugs(["boards.greenhouse.io"])
    assert out.get("greenhouse") == {"acme", "beta"}  # robots.txt -> no slug, deduped

def test_harvest_unreachable_logs_and_empties(monkeypatch, capsys):
    monkeypatch.setattr(H, "_cdx_fetch", lambda host, crawl_id, limit: (_ for _ in ()).throw(RuntimeError("net")))
    out = H.harvest_slugs(["boards.greenhouse.io"])
    assert out == {}
    assert "WARNING" in capsys.readouterr().out  # loud, not silent

def test_empty_hosts_returns_empty():
    assert H.harvest_slugs([]) == {}


class _JsonResp:
    def __init__(self, payload):
        self._payload = payload
    def raise_for_status(self):
        pass
    def json(self):
        return self._payload


def test_latest_crawl_index_resolves_newest(monkeypatch):
    H._latest_index_cache = None  # reset process cache
    newest = "https://index.commoncrawl.org/CC-MAIN-2026-26-index"
    payload = [{"id": "CC-MAIN-2026-26", "cdx-api": newest},
               {"id": "CC-MAIN-2026-20", "cdx-api": "https://x/old-index"}]

    class _S:
        def get(self, url, timeout=30):
            return _JsonResp(payload)
    monkeypatch.setattr(H, "make_session", lambda: _S())
    assert H._latest_crawl_index() == newest
    assert H._index_url(None) == newest            # None -> newest crawl
    assert "2025-05" in H._index_url("2025-05")    # explicit id honored
    H._latest_index_cache = None


def test_latest_crawl_index_falls_back_on_error(monkeypatch):
    H._latest_index_cache = None
    class _S:
        def get(self, url, timeout=30):
            raise RuntimeError("offline")
    monkeypatch.setattr(H, "make_session", lambda: _S())
    assert H._latest_crawl_index() == H._FALLBACK_INDEX
    H._latest_index_cache = None
