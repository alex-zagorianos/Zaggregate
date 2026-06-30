"""Wave 7 - Ashby liveness via the board API."""
import scrape.inbox_health as ih


class _Resp:
    def __init__(self, payload, ok=True):
        self._payload = payload
        self.ok = ok
        self.status_code = 200 if ok else 500

    def json(self):
        return self._payload


def test_ashby_alive_when_id_listed(monkeypatch):
    monkeypatch.setattr(ih.requests, "get",
                        lambda *a, **k: _Resp({"jobs": [{"id": "JOBID"}]}))
    assert ih._probe("https://jobs.ashbyhq.com/acme/JOBID") is True


def test_ashby_dead_when_id_absent(monkeypatch):
    monkeypatch.setattr(ih.requests, "get",
                        lambda *a, **k: _Resp({"jobs": [{"id": "other"}]}))
    assert ih._probe("https://jobs.ashbyhq.com/acme/JOBID") is False


def test_ashby_unknown_on_fetch_error(monkeypatch):
    def _boom(*a, **k):
        raise ih.requests.RequestException("net down")
    monkeypatch.setattr(ih.requests, "get", _boom)
    assert ih._probe("https://jobs.ashbyhq.com/acme/JOBID") is None


def test_ashby_board_only_url_is_unknown(monkeypatch):
    # A board root (no posting id) can't be judged -> keep.
    assert ih._probe("https://jobs.ashbyhq.com/acme") is None
