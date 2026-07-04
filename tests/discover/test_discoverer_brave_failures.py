"""S35 finding #22 (major): Brave Search discovery failures beyond the
"no key at all" case (401 invalid key, 429 rate limit, any other exception)
used to be bare print()s with no persisted signal and no run-scoped dedup.
Now routed through the same applog.warn_once() pattern as the no-key case,
logging ONCE per run (not once per ats_site/keyword pair)."""
import applog
import scrape.discoverer as D


class _Resp:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def _setup(monkeypatch):
    monkeypatch.setattr(D, "BRAVE_SEARCH_API_KEY", "a-real-key")
    applog.reset_run_warnings()


def _n_warning_lines(console: str) -> int:
    # applog's console formatter prefixes each WARNING+ record's line with
    # "WARNING: "; count LINES with that prefix rather than substring
    # occurrences (the message text itself also says "WARNING:" for a friend
    # reading app.log, so a bare substring count double-counts each line).
    return sum(1 for ln in console.splitlines() if ln.startswith("WARNING:"))


def test_brave_401_warns_once_per_run(monkeypatch, capsys):
    _setup(monkeypatch)
    monkeypatch.setattr(D.requests, "get", lambda *a, **k: _Resp(401))
    out1 = D._brave_fetch("query one")
    out2 = D._brave_fetch("query two")  # a second, different query same run
    assert out1 is None and out2 is None
    console = capsys.readouterr().out
    assert _n_warning_lines(console) == 1     # deduped across calls this run
    assert "401" in console or "invalid" in console.lower()


def test_brave_429_warns_once_per_run(monkeypatch, capsys):
    _setup(monkeypatch)
    monkeypatch.setattr(D.requests, "get", lambda *a, **k: _Resp(429))
    D._brave_fetch("query one")
    D._brave_fetch("query two")
    console = capsys.readouterr().out
    assert _n_warning_lines(console) == 1
    assert "rate limit" in console.lower()


def test_brave_exception_warns_once_per_run(monkeypatch, capsys):
    _setup(monkeypatch)
    def boom(*a, **k):
        raise ConnectionError("dns failure")
    monkeypatch.setattr(D.requests, "get", boom)
    D._brave_fetch("query one")
    D._brave_fetch("query two")
    console = capsys.readouterr().out
    assert _n_warning_lines(console) == 1
    assert "dns failure" in console


def test_brave_failure_kinds_are_independently_tracked(monkeypatch, capsys):
    # A 401 warning and a 429 warning are DIFFERENT failure kinds -- both must
    # surface (distinct keys), not just the first one seen this run.
    _setup(monkeypatch)
    monkeypatch.setattr(D.requests, "get", lambda *a, **k: _Resp(401))
    D._brave_fetch("q1")
    monkeypatch.setattr(D.requests, "get", lambda *a, **k: _Resp(429))
    D._brave_fetch("q2")
    console = capsys.readouterr().out
    assert _n_warning_lines(console) == 2


def test_brave_success_after_failure_still_returns_data(monkeypatch, capsys):
    # A transient 429 must not poison subsequent calls this run.
    _setup(monkeypatch)
    monkeypatch.setattr(D.requests, "get", lambda *a, **k: _Resp(429))
    assert D._brave_fetch("q1") is None
    monkeypatch.setattr(D.requests, "get",
                        lambda *a, **k: _Resp(200, {"web": {"results": []}}))
    assert D._brave_fetch("q2") == {"web": {"results": []}}
