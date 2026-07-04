"""GET /api/inbox filter-semantics parity + the detail endpoint.

Seeds inbox rows with varying score/source/size/location/fit/pay/freshness in a
tmp DB, then asserts each query param filters exactly as the tk InboxTab does. The
web filters are the Tk-free port in ``webui.inbox_filters``; a direct parity test
against the tk module's freshness helpers pins the two implementations together.

Every filter here is a VIEW filter (inclusion over precision): omitting a param is
a no-op, and no request path deletes a row.
"""
import json

from models import JobResult
from tracker import db
from webui import inbox_filters


_LOOPBACK = "http://127.0.0.1:5002"


def _job(url, *, title="Software Developer", company="Acme",
         location="Cincinnati, OH", score=70, board_count=-1,
         salary_min=None, salary_max=None, description="controls",
         source_api="adzuna", created="2026-06-21"):
    return JobResult(title=title, company=company, location=location,
                     salary_min=salary_min, salary_max=salary_max,
                     description=description, url=url, source_keyword="",
                     created=created, source_api=source_api, score=score,
                     board_count=board_count)


def _rows():
    return db.inbox_all()


def _stamp_new_batch(inbox_id, batch):
    """Stamp a row's extras with a freshness batch directly (inbox_add_many only
    stamps jobs carrying is_new=True; the test just needs the stored marker)."""
    with db.get_conn() as conn:
        conn.execute("UPDATE inbox SET extras=? WHERE id=?",
                     (json.dumps({"new_batch": batch}), inbox_id))


# ── freshness-helper parity (webui copy == tk copy) ───────────────────────────

def test_freshness_helpers_match_tk():
    """The Tk-free freshness helpers must agree with ui.tab_inbox's copies so the
    'New only' semantics never drift. Importing ui.tab_inbox is fine HERE (a test,
    not the GUI-free webui package)."""
    from ui import tab_inbox as tk
    rows = [
        {"extras": json.dumps({"new_batch": "2026-07-01T00:00:00"})},
        {"extras": json.dumps({"new_batch": "2026-07-04T00:00:00"})},
        {"extras": ""},
        {"extras": None},
        {"extras": "not json"},
    ]
    for r in rows:
        assert inbox_filters._row_new_batch(r) == tk._row_new_batch(r)
    assert inbox_filters._latest_new_batch(rows) == tk._latest_new_batch(rows)
    latest = inbox_filters._latest_new_batch(rows)
    for r in rows:
        assert inbox_filters._is_new_row(r, latest) == tk._is_new_row(r, latest)


# ── min_score boundary ────────────────────────────────────────────────────────

def test_min_score_is_inclusive_boundary(client, tmp_db):
    db.inbox_add_many([_job("https://x/1", score=69),
                       _job("https://x/2", company="B", score=70),
                       _job("https://x/3", company="C", score=71)])
    resp = client.get("/api/inbox?min_score=70")
    body = resp.get_json()
    assert resp.status_code == 200 and body["ok"] is True
    scores = sorted(r["score"] for r in body["rows"])
    assert scores == [70, 71]          # 70 kept (>=), 69 dropped
    assert body["total"] == 3 and body["shown"] == 2


# ── sources (csv, widened to a set) ───────────────────────────────────────────

def test_sources_csv_multi_select(client, tmp_db):
    db.inbox_add_many([_job("https://x/1", source_api="adzuna"),
                       _job("https://x/2", company="B", source_api="usajobs"),
                       _job("https://x/3", company="C", source_api="jsearch")])
    resp = client.get("/api/inbox?sources=adzuna,usajobs")
    srcs = sorted(r["source"] for r in resp.get_json()["rows"])
    assert srcs == ["adzuna", "usajobs"]


def test_sources_empty_is_noop(client, tmp_db):
    db.inbox_add_many([_job("https://x/1", source_api="adzuna"),
                       _job("https://x/2", company="B", source_api="usajobs")])
    assert client.get("/api/inbox?sources=").get_json()["shown"] == 2


# ── size letter ───────────────────────────────────────────────────────────────

def test_size_letter_filter(client, tmp_db):
    db.inbox_add_many([_job("https://x/1", board_count=10),    # S
                       _job("https://x/2", company="B", board_count=80),   # M
                       _job("https://x/3", company="C", board_count=200),  # L
                       _job("https://x/4", company="D", board_count=500),  # XL
                       _job("https://x/5", company="E", board_count=-1)])  # ?
    got = {ltr: client.get(f"/api/inbox?size={ltr}").get_json()["shown"]
           for ltr in ("S", "M", "L", "XL", "?")}
    assert got == {"S": 1, "M": 1, "L": 1, "XL": 1, "?": 1}


def test_size_letter_matches_filter_module():
    assert inbox_filters.size_letter(10) == "S"
    assert inbox_filters.size_letter(80) == "M"
    assert inbox_filters.size_letter(200) == "L"
    assert inbox_filters.size_letter(500) == "XL"
    assert inbox_filters.size_letter(-1) == "?"
    assert inbox_filters.size_letter(None) == "?"


# ── unscored_only (fit < 0) ───────────────────────────────────────────────────

def test_unscored_only(client, tmp_db):
    db.inbox_add_many([_job("https://x/1"), _job("https://x/2", company="B")])
    scored_id = _rows()[0]["id"]
    db.inbox_set_fit(scored_id, 88, "great")
    resp = client.get("/api/inbox?unscored_only=1")
    ids = [r["id"] for r in resp.get_json()["rows"]]
    assert scored_id not in ids
    assert resp.get_json()["shown"] == 1


# ── new_only (latest new_batch) ───────────────────────────────────────────────

def test_new_only_surfaces_latest_batch(client, tmp_db):
    db.inbox_add_many([_job("https://x/old"), _job("https://x/new", company="B")])
    by_url = {r["url"]: r["id"] for r in _rows()}
    _stamp_new_batch(by_url["https://x/old"], "2026-07-01T00:00:00")
    _stamp_new_batch(by_url["https://x/new"], "2026-07-04T00:00:00")
    resp = client.get("/api/inbox?new_only=1")
    urls = [r["url"] for r in resp.get_json()["rows"]]
    assert urls == ["https://x/new"]     # only the latest batch is "new"


# ── pay_floor (disclosed comp top >= floor; undisclosed hidden) ───────────────

def test_pay_floor_hides_undisclosed_and_below(client, tmp_db, monkeypatch):
    # Resolve a floor of 100k server-side (client sends only the boolean toggle).
    monkeypatch.setattr("webui.api.inbox._resolve_home", lambda: {
        "home_area": "", "has_home": False, "remote_ok": True, "pay_floor": 100000})
    db.inbox_add_many([
        _job("https://x/hi", company="A", salary_min=120000, salary_max=140000),
        _job("https://x/lo", company="B", salary_min=60000, salary_max=80000),
        _job("https://x/none", company="C"),  # undisclosed
    ])
    resp = client.get("/api/inbox?pay_floor=1")
    urls = sorted(r["url"] for r in resp.get_json()["rows"])
    assert urls == ["https://x/hi"]       # below-floor + undisclosed both hidden


def test_pay_floor_toggle_off_is_noop(client, tmp_db, monkeypatch):
    monkeypatch.setattr("webui.api.inbox._resolve_home", lambda: {
        "home_area": "", "has_home": False, "remote_ok": True, "pay_floor": 100000})
    db.inbox_add_many([_job("https://x/none", company="C")])
    assert client.get("/api/inbox").get_json()["shown"] == 1


# ── hide_stale ────────────────────────────────────────────────────────────────

def test_hide_stale(client, tmp_db, monkeypatch):
    db.inbox_add_many([_job("https://x/1"), _job("https://x/2", company="B")])
    stale_id = _rows()[0]["id"]

    def fake_ghost(row, *a, **k):
        lvl = "stale" if row.get("id") == stale_id else "fresh"
        return {"score": 0, "level": lvl, "reasons": []}
    monkeypatch.setattr("webui.inbox_filters._ghostmod.ghost_score", fake_ghost)
    resp = client.get("/api/inbox?hide_stale=1")
    ids = [r["id"] for r in resp.get_json()["rows"]]
    assert stale_id not in ids and resp.get_json()["shown"] == 1


# ── q (title OR company substring, case-insensitive) ──────────────────────────

def test_q_matches_title_or_company(client, tmp_db):
    db.inbox_add_many([
        _job("https://x/1", title="Senior Rust Engineer", company="Acme"),
        _job("https://x/2", title="Data Analyst", company="RustCorp"),
        _job("https://x/3", title="Marketing Lead", company="Zeta"),
    ])
    urls = sorted(r["url"] for r in client.get("/api/inbox?q=rust").get_json()["rows"])
    assert urls == ["https://x/1", "https://x/2"]   # title match + company match


# ── location_mode ─────────────────────────────────────────────────────────────

def test_location_mode_all_locations_is_noop(client, tmp_db):
    db.inbox_add_many([_job("https://x/1", location="Remote"),
                       _job("https://x/2", company="B", location="Berlin, DE")])
    assert client.get("/api/inbox?location_mode=All locations").get_json()["shown"] == 2


def test_location_mode_no_home_never_hides(client, tmp_db, monkeypatch):
    # No configured home metro -> a local-focus mode must behave as All locations
    # (inclusion over precision: never silently empty the view).
    monkeypatch.setattr("webui.api.inbox._resolve_home", lambda: {
        "home_area": "", "has_home": False, "remote_ok": True, "pay_floor": None})
    db.inbox_add_many([_job("https://x/1", location="Berlin, DE")])
    assert client.get("/api/inbox?location_mode=Local only").get_json()["shown"] == 1


# ── order roundrobin | score ──────────────────────────────────────────────────

def test_order_roundrobin_vs_score(client, tmp_db):
    db.inbox_add_many([
        _job("https://x/a1", company="A", score=90),
        _job("https://x/a2", company="A", score=85),
        _job("https://x/b1", company="B", score=80),
    ])
    rr = [r["url"] for r in client.get("/api/inbox?order=roundrobin").get_json()["rows"]]
    sc = [r["url"] for r in client.get("/api/inbox?order=score").get_json()["rows"]]
    # score: raw ranking a1(90) a2(85) b1(80)
    assert sc == ["https://x/a1", "https://x/a2", "https://x/b1"]
    # roundrobin: each company's best first, so B's 80 comes before A's 2nd (85)
    assert rr[1] == "https://x/b1"


# ── paging (limit / offset over the filtered view) ────────────────────────────

def test_limit_and_offset(client, tmp_db):
    db.inbox_add_many([_job(f"https://x/{i}", company=f"C{i}", score=100 - i)
                       for i in range(5)])
    body = client.get("/api/inbox?order=score&limit=2&offset=1").get_json()
    assert body["total"] == 5 and body["shown"] == 5   # shown = pre-paging
    assert len(body["rows"]) == 2
    assert [r["score"] for r in body["rows"]] == [99, 98]   # skipped the top (100)


# ── computed fields ───────────────────────────────────────────────────────────

def test_computed_fields_present(client, tmp_db):
    db.inbox_add_many([_job("https://x/1", board_count=10, location="Remote")])
    _stamp_new_batch(_rows()[0]["id"], "2026-07-04T00:00:00")
    row = client.get("/api/inbox").get_json()["rows"][0]
    c = row["computed"]
    assert c["size"] == "S"
    assert c["is_new"] is True
    assert c["location_visible"] is True   # no local-focus mode requested


# ── badges ────────────────────────────────────────────────────────────────────

def test_badges_shape(client, tmp_db):
    db.inbox_add_many([_job("https://x/1")])
    badges = client.get("/api/inbox").get_json()["badges"]
    assert set(badges) == {"last_run", "reach", "demo"}
    assert isinstance(badges["demo"], bool)


# ── detail endpoint ───────────────────────────────────────────────────────────

def test_detail_shape(client, tmp_db):
    db.inbox_add_many([_job("https://x/1",
                            description="Python controls SCADA PLC ladder logic")])
    rid = _rows()[0]["id"]
    db.inbox_set_fit(rid, 82, "solid controls overlap")
    body = client.get(f"/api/inbox/{rid}/detail").get_json()
    assert body["ok"] is True
    assert set(body) >= {"ok", "row", "fit_why", "score_notes", "ghost",
                         "ats", "description_preview"}
    assert body["fit_why"] == "solid controls overlap"
    assert body["row"]["id"] == rid
    assert isinstance(body["ats"]["lines"], list)
    assert len(body["description_preview"]) <= 500


def test_detail_unknown_id_404(client, tmp_db):
    assert client.get("/api/inbox/999999/detail").status_code == 404


# ── sample (demo) inbox — first-run onboarding parity with tk InboxTab ─────────

def _force_demo(monkeypatch, on=True):
    """Make should_show_demo deterministic regardless of the real user's retire
    marker so these tests don't depend on the dev machine's onboarding state."""
    import demo_data
    monkeypatch.setattr(demo_data, "should_show_demo", lambda *a, **k: on)


def test_empty_inbox_serves_demo_rows(client, tmp_db, monkeypatch):
    """A brand-new user with a genuinely empty real inbox sees the bundled sample
    rows via GET /api/inbox — parity with the tk InboxTab, which swaps the demo
    sample into ``self._all`` when the real inbox is empty (finding: the web route
    used to return 0 rows here, regressing onboarding)."""
    _force_demo(monkeypatch, on=True)
    body = client.get("/api/inbox").get_json()
    assert body["ok"] is True
    assert body["total"] == 20 and body["shown"] == 20
    assert len(body["rows"]) == 20
    assert all(r.get("is_demo") for r in body["rows"])
    assert all(r["source"] == "Demo" for r in body["rows"])
    assert all(r["id"] < 0 for r in body["rows"])          # negative demo ids
    assert body["badges"]["demo"] is True


def test_demo_rows_bypass_all_view_filters(client, tmp_db, monkeypatch):
    """The sample set is shown UNFILTERED (tk _filtered L661-669): its varied
    locations/scores ARE the demo, so a leftover Local-only mode or a min_score from
    a previous project must not whittle it down before the first real search."""
    _force_demo(monkeypatch, on=True)
    # Filters that would normally slash the set to near-zero:
    q = "min_score=100&location_mode=Local+only&size=XL&hide_stale=1&q=zzz-nomatch"
    body = client.get(f"/api/inbox?{q}").get_json()
    assert body["ok"] is True
    assert body["shown"] == 20 and len(body["rows"]) == 20   # nothing dropped


def test_demo_detail_pane_renders(client, tmp_db, monkeypatch):
    """The detail endpoint serves demo rows (negative ids, not in the DB) from their
    inline fit_why/score_notes/description so the pane works during onboarding."""
    _force_demo(monkeypatch, on=True)
    rows = client.get("/api/inbox").get_json()["rows"]
    rid = rows[0]["id"]
    assert rid < 0
    body = client.get(f"/api/inbox/{rid}/detail").get_json()
    assert body["ok"] is True
    assert body["row"]["id"] == rid
    assert set(body) >= {"ok", "row", "fit_why", "score_notes", "ghost",
                         "ats", "description_preview"}


def test_real_inbox_suppresses_demo(client, tmp_db, monkeypatch):
    """The moment a real inbox exists, the demo is gone even if should_show_demo
    were true — a non-empty real inbox short-circuits the fallback (tk parity: the
    real rows win, demo is retired)."""
    _force_demo(monkeypatch, on=True)
    db.inbox_add_many([_job("https://x/1", company="Real Co")])
    body = client.get("/api/inbox").get_json()
    assert body["total"] == 1
    assert all(not r.get("is_demo") for r in body["rows"])
    assert body["rows"][0]["company"] == "Real Co"


def test_filter_rows_bypasses_when_all_demo():
    """Unit: filter_rows returns an all-demo set unfiltered regardless of params
    (the bypass the finding asks for — latent until demo rows reach it, wired here)."""
    demo = [{"id": -1, "is_demo": True, "score": 10, "source": "Demo",
             "location": "Remote", "title": "A", "company": "X", "fit": -1},
            {"id": -2, "is_demo": True, "score": 20, "source": "Demo",
             "location": "London", "title": "B", "company": "Y", "fit": -1}]
    out = inbox_filters.filter_rows(demo, min_score=100, hide_stale=True,
                                    q="nomatch", size="XL")
    assert out == demo   # completely unfiltered

    # A set that MIXES a real row in must NOT bypass (guards against a real row
    # being smuggled through unfiltered).
    mixed = demo + [{"id": 5, "score": 5, "source": "adzuna", "title": "C",
                     "company": "Z", "fit": -1, "location": ""}]
    out2 = inbox_filters.filter_rows(mixed, min_score=100)
    assert out2 == []    # min_score=100 drops all (no bypass)
