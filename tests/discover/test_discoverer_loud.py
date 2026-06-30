import scrape.discoverer as D

def test_no_brave_key_logs_loudly(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(D, "BRAVE_SEARCH_API_KEY", "")
    out = D.discover_companies("controls engineer", tmp_path, False, set())
    assert out == []
    assert "WARNING" in capsys.readouterr().out  # was silent before
