"""Inbox liveness prune — remove postings that are definitively gone (404)."""
import sqlite3

from scrape.inbox_health import prune_inbox


def _seed(db_path, rows):
    """rows = list of (title, company, url, source)."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE inbox (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "norm_url TEXT UNIQUE NOT NULL, title TEXT, company TEXT, url TEXT, source TEXT)"
    )
    for i, (title, company, url, source) in enumerate(rows):
        conn.execute(
            "INSERT INTO inbox (norm_url, title, company, url, source) VALUES (?,?,?,?,?)",
            (f"k{i}", title, company, url, source),
        )
    conn.commit()
    conn.close()


def _companies(db_path):
    conn = sqlite3.connect(str(db_path))
    out = [r[0] for r in conn.execute("SELECT company FROM inbox ORDER BY id")]
    conn.close()
    return out


def test_removes_only_definitive_404(tmp_path):
    db = tmp_path / "t.db"
    _seed(db, [
        ("A", "Alive", "https://job-boards.greenhouse.io/embed/job_app?for=a&token=1", "careers"),
        ("D", "Dead",  "https://job-boards.greenhouse.io/embed/job_app?for=d&token=2", "careers"),
        ("U", "Unknown", "https://job-boards.greenhouse.io/embed/job_app?for=u&token=3", "careers"),
    ])
    verdict = {"1": True, "2": False, "3": None}
    # probe receives the row's url; map by token.
    def probe(url):
        from scrape.greenhouse_url import parse
        return verdict[parse(url)[1]]

    removed = prune_inbox(db_path=db, probe=probe)
    assert [r["company"] for r in removed] == ["Dead"]
    assert _companies(db) == ["Alive", "Unknown"]   # 404 gone, alive + unknown kept


def test_dry_run_reports_but_keeps(tmp_path):
    db = tmp_path / "t.db"
    _seed(db, [
        ("D", "Dead", "https://job-boards.greenhouse.io/embed/job_app?for=d&token=2", "careers"),
    ])
    removed = prune_inbox(db_path=db, probe=lambda url: False, dry_run=True)
    assert [r["company"] for r in removed] == ["Dead"]
    assert _companies(db) == ["Dead"]               # nothing actually deleted


def test_non_careers_rows_are_left_alone(tmp_path):
    db = tmp_path / "t.db"
    _seed(db, [
        ("X", "Aggregator", "https://www.adzuna.com/land/ad/999", "adzuna"),
    ])
    # probe would say dead, but adzuna rows are never probed/removed.
    removed = prune_inbox(db_path=db, probe=lambda url: False)
    assert removed == []
    assert _companies(db) == ["Aggregator"]


def test_default_probe_dispatches_by_ats(monkeypatch):
    """The built-in probe hits the right API per ATS and reads 404 as dead."""
    import scrape.inbox_health as ih

    class _Resp:
        def __init__(self, status, payload=None):
            self.status_code = status
            self._payload = payload or {}
        @property
        def ok(self):
            return self.status_code < 400
        def json(self):
            return self._payload

    calls = []
    def fake_get(url, **kw):
        calls.append(url)
        # greenhouse boards-api job endpoint -> 404; lever -> 200; ashby board API
        # returns a board WITHOUT our posting id -> the posting is gone (dead).
        if "boards-api.greenhouse.io" in url:
            return _Resp(404)
        if "api.lever.co" in url:
            return _Resp(200)
        if "api.ashbyhq.com" in url:
            return _Resp(200, {"jobs": [{"id": "other"}]})
        return _Resp(404)
    monkeypatch.setattr(ih.requests, "get", fake_get)

    assert ih._probe("https://job-boards.greenhouse.io/embed/job_app?for=a&token=9") is False
    assert "boards-api.greenhouse.io/v1/boards/a/jobs/9" in calls[-1]
    assert ih._probe("https://jobs.lever.co/acme/abc-123") is True
    # Ashby now checks board-API membership: posting "uuid" absent -> dead.
    assert ih._probe("https://jobs.ashbyhq.com/acme/uuid") is False
    assert "api.ashbyhq.com/posting-api/job-board/acme" in calls[-1]
    # workday / direct are not reliably probeable -> unknown (keep)
    assert ih._probe("https://cat.wd5.myworkdayjobs.com/x/job/1") is None


# ── A3: resolve+pin the project once for the (slow) probe loop ─────────────────
def test_prune_pins_active_project_for_the_run(tmp_path, monkeypatch):
    """With no explicit db_path, prune_inbox resolves via current_db_path UNDER a
    pin, so a concurrent project switch mid-probe can't move the target DB."""
    import scrape.inbox_health as ih
    import workspace

    db = tmp_path / "t.db"
    _seed(db, [("D", "Dead",
                "https://job-boards.greenhouse.io/embed/job_app?for=d&token=2", "careers")])

    pins = []
    monkeypatch.setattr(workspace, "pin_active", lambda s: pins.append(s))
    monkeypatch.setattr(workspace, "active_slug", lambda: "controls")
    monkeypatch.setattr(ih, "current_db_path", lambda: db)

    removed = ih.prune_inbox(probe=lambda url: False)     # db_path=None -> pins
    assert [r["company"] for r in removed] == ["Dead"]
    # Pinned the resolved active slug, then RESTORED the prior pin (None) on exit.
    assert pins[0] == "controls"
    assert pins[-1] is None


def test_prune_explicit_project_overrides_active(tmp_path, monkeypatch):
    import scrape.inbox_health as ih
    import workspace

    db = tmp_path / "t.db"
    _seed(db, [("D", "Dead",
                "https://job-boards.greenhouse.io/embed/job_app?for=d&token=2", "careers")])
    pins = []
    monkeypatch.setattr(workspace, "pin_active", lambda s: pins.append(s))
    monkeypatch.setattr(ih, "current_db_path", lambda: db)

    ih.prune_inbox(probe=lambda url: False, project="dad")
    assert pins[0] == "dad"


def test_prune_explicit_db_path_skips_pinning(tmp_path, monkeypatch):
    """An explicit db_path is authoritative and must NOT touch the process pin."""
    import scrape.inbox_health as ih
    import workspace

    db = tmp_path / "t.db"
    _seed(db, [("D", "Dead",
                "https://job-boards.greenhouse.io/embed/job_app?for=d&token=2", "careers")])
    monkeypatch.setattr(workspace, "pin_active",
                        lambda s: (_ for _ in ()).throw(AssertionError("must not pin")))
    removed = ih.prune_inbox(db_path=db, probe=lambda url: False)
    assert [r["company"] for r in removed] == ["Dead"]
