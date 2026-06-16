"""HN client must use a filename-safe hashed cache key (2026-06 review)."""
from search.hn_client import HNClient


class _Resp:
    def raise_for_status(self): pass
    def json(self): return {"hits": []}


def test_hn_search_writes_hashed_cache_file(tmp_path, monkeypatch):
    client = HNClient(cache_dir=tmp_path)
    monkeypatch.setattr(client, "_latest_thread_id", lambda: "1")
    monkeypatch.setattr(client.session, "get", lambda *a, **k: _Resp())
    client.search("controls/automation")
    cached = list((tmp_path / "hn").glob("*.json"))
    assert len(cached) == 1
    assert cached[0].stem.isalnum()
