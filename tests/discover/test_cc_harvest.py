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
