import pytest

pytest.importorskip("mcp")  # server needs the MCP SDK; skip where absent

import mcp_server


def test_server_and_tools_exist():
    assert mcp_server.mcp is not None
    for name in ("get_preferences", "search_jobs", "list_inbox",
                 "set_fit_scores", "track_job", "dismiss_job",
                 "list_applications", "get_application", "set_status",
                 "set_follow_up", "followups_due", "funnel",
                 "draft_followup_context", "get_resume_prompt", "save_resume",
                 "skill_gap", "export_inbox", "import_scores", "seed_companies"):
        assert callable(getattr(mcp_server, name))


# ── seed_companies (item 4: URL-only seeding via the MCP channel) ─────────────
def test_seed_companies_verifies_and_gates(monkeypatch, tmp_path):
    import config
    from scrape import ats_detect
    monkeypatch.setattr(config, "COMPANIES_JSON", tmp_path / "companies.json")
    # Live probe: Acme is reachable, DeadCo is not (None -> unverified/P0-6).
    monkeypatch.setattr(ats_detect, "probe_count",
                        lambda e: 7 if "acme" in e.slug.lower() else None)
    lines = ("Acme | https://boards.greenhouse.io/acme\n"
             "DeadCo | https://boards.greenhouse.io/deadco\n"
             "Direct | https://direct.example/careers/\n")
    out = mcp_server.seed_companies(lines, industry="engineering")
    assert out["parsed"] == 3
    assert out["verified"] == 2          # Acme (live) + Direct (direct page)
    assert out["unverified"] == 1        # DeadCo failed its probe
    kinds = {v["name"]: v["verdict"] for v in out["verdicts"]}
    assert kinds == {"Acme": "live", "DeadCo": "unreachable", "Direct": "direct"}


def test_seed_companies_rejects_tos_blocked_host(monkeypatch, tmp_path):
    # An AI agent driving this tool must not be able to seed a ToS-blocked /
    # aggregator host (NEOGOV/governmentjobs, Indeed, ...) as an unprobed 'direct'
    # fetch target: those are rejected and never saved.
    import json
    import config
    from scrape import ats_detect
    monkeypatch.setattr(config, "COMPANIES_JSON", tmp_path / "companies.json")
    monkeypatch.setattr(ats_detect, "probe_count", lambda e: 7)
    lines = ("City Jobs | https://www.governmentjobs.com/careers/cincinnati\n"
             "Real Co | https://boards.greenhouse.io/realco\n")
    out = mcp_server.seed_companies(lines, industry="engineering")
    assert out["rejected"] == 1
    kinds = {v["name"]: v["verdict"] for v in out["verdicts"]}
    assert kinds["City Jobs"] == "rejected"
    assert kinds["Real Co"] == "live"
    saved = json.loads((tmp_path / "companies.json").read_text(encoding="utf-8"))
    names = {c["name"] for c in saved["companies"] if "_example" not in c}
    assert "City Jobs" not in names and "Real Co" in names


def test_seed_companies_bare_url_and_empty(monkeypatch, tmp_path):
    import config
    from scrape import ats_detect
    monkeypatch.setattr(config, "COMPANIES_JSON", tmp_path / "companies.json")
    monkeypatch.setattr(ats_detect, "probe_count", lambda e: 3)
    # A bare careers URL (no "Name |") is accepted; name is derived.
    out = mcp_server.seed_companies("https://jobs.lever.co/acme\n")
    assert out["parsed"] == 1 and out["added"] == 1
    # Empty input is a clean no-op.
    out2 = mcp_server.seed_companies("")
    assert out2["parsed"] == 0 and out2["verdicts"] == []


def test_list_inbox_compact_returns_facts(monkeypatch):
    rows = [{"id": 1, "title": "Controls Engineer", "company": "Acme",
             "location": "Cincinnati, OH", "fit": -1, "score": 70,
             "description": "PLC SCADA motion control, C++ required. " * 20,
             "url": "https://x/1", "source": "adzuna"}]
    monkeypatch.setattr(mcp_server.db, "inbox_all", lambda: rows)
    out = mcp_server.list_inbox(compact=True, unscored_only=False)
    assert "facts" in out[0] and "description" not in out[0]
    # facts summary is materially shorter than the raw description.
    assert len(out[0]["facts"]) < len(rows[0]["description"])


def test_get_preferences_shape(monkeypatch):
    monkeypatch.setattr(mcp_server.prefs_mod, "load",
                        lambda: {"profile_md": "controls roles",
                                 "hard": {"salary_min": 90000}})
    out = mcp_server.get_preferences()
    assert out["profile_md"] == "controls roles"
    assert out["hard_filters"]["salary_min"] == 90000


def test_set_fit_scores_applies_and_clamps(monkeypatch):
    applied = []

    def fake_set_fit(i, f, r, source="manual", batch=""):
        applied.append((i, f, r, source, batch))
        return True   # row landed

    monkeypatch.setattr(mcp_server.db, "inbox_set_fit", fake_set_fit)
    out = mcp_server.set_fit_scores([
        {"id": 1, "fit": 88, "rationale": "great"},
        {"id": 2, "fit": 150, "rationale": "clamp"},   # clamps to 100
        {"fit": 50},                                    # no id -> skipped
    ])
    assert out["applied"] == 2
    assert out["missed"] == 0
    assert applied[0][:3] == (1, 88, "great")
    assert applied[0][3] == "mcp"                       # tagged source
    assert applied[0][4] and applied[0][4] == applied[1][4]  # ONE shared batch
    assert applied[1][1] == 100


def test_set_fit_scores_phantom_id_not_counted(monkeypatch):
    """A nonexistent id must NOT count as applied (phantom-applied fix): the
    real inbox_set_fit returns False for a missing row."""
    def fake_set_fit(i, f, r, source="manual", batch=""):
        return i == 1   # only id 1 exists

    monkeypatch.setattr(mcp_server.db, "inbox_set_fit", fake_set_fit)
    merged = []
    monkeypatch.setattr(mcp_server.db, "inbox_merge_extras",
                        lambda i, p: merged.append(i))
    out = mcp_server.set_fit_scores([
        {"id": 1, "fit": 80, "rationale": "real", "rank": 1},
        {"id": 999, "fit": 70, "rationale": "phantom", "rank": 2},
    ])
    assert out["applied"] == 1 and out["missed"] == 1
    assert merged == [1]                                # no rank write for phantom


def test_list_inbox_filters_unscored(monkeypatch):
    rows = [
        {"id": 1, "title": "A", "company": "X", "fit": -1, "score": 70},
        {"id": 2, "title": "B", "company": "Y", "fit": 80, "score": 60},
    ]
    monkeypatch.setattr(mcp_server.db, "inbox_all", lambda: rows)
    assert [r["id"] for r in mcp_server.list_inbox(unscored_only=True)] == [1]
    assert {r["id"] for r in mcp_server.list_inbox(unscored_only=False)} == {1, 2}


def test_list_inbox_limit_zero_returns_all_with_rank(monkeypatch):
    rows = [{"id": i, "title": "T", "company": "C", "fit": -1, "score": 70,
             "extras": ('{"rank":1,"rec_batch":"B"}' if i == 1 else "")}
            for i in (1, 2, 3)]
    monkeypatch.setattr(mcp_server.db, "inbox_all", lambda: rows)
    out = mcp_server.list_inbox(limit=0, unscored_only=False)
    assert len(out) == 3
    by_id = {r["id"]: r for r in out}
    assert by_id[1]["rank"] == 1 and by_id[2]["rank"] == -1
    assert all(r["job_key"] for r in out)


def test_set_fit_scores_persists_rank(monkeypatch):
    fits, patches = [], []
    monkeypatch.setattr(mcp_server.db, "inbox_set_fit",
                        lambda i, f, r, source="manual", batch="": (
                            fits.append((i, f, r)) or True))
    monkeypatch.setattr(mcp_server.db, "inbox_merge_extras",
                        lambda i, p: patches.append((i, p)))
    out = mcp_server.set_fit_scores([
        {"id": 1, "fit": 90, "rationale": "x", "rank": 1},
        {"id": 2, "fit": 80, "rationale": "y"},   # no rank -> no merge
    ])
    assert out["applied"] == 2
    assert len(patches) == 1 and patches[0][0] == 1
    assert patches[0][1]["rank"] == 1 and patches[0][1]["rec_batch"]


# ── A3: startup project pin (S27 concurrency class) ───────────────────────────
def test_main_pins_active_project_at_startup(monkeypatch):
    """A long-lived MCP session must pin the active project ONCE at startup so a
    later GUI switch can't redirect its writes to another project."""
    pinned = {}
    monkeypatch.setattr(mcp_server.userdata, "bootstrap", lambda: None)
    monkeypatch.setattr(mcp_server.db, "init_db", lambda: None)
    monkeypatch.setattr(mcp_server.mcp, "run", lambda: None)
    monkeypatch.setattr(mcp_server.workspace, "active_slug", lambda: "controls")
    monkeypatch.setattr(mcp_server.workspace, "pin_active",
                        lambda s: pinned.setdefault("slug", s))
    mcp_server.main([])                    # no --project -> pin whatever's active
    assert pinned["slug"] == "controls"


def test_main_pins_explicit_project(monkeypatch):
    pinned = {}
    monkeypatch.setattr(mcp_server.userdata, "bootstrap", lambda: None)
    monkeypatch.setattr(mcp_server.db, "init_db", lambda: None)
    monkeypatch.setattr(mcp_server.mcp, "run", lambda: None)
    monkeypatch.setattr(mcp_server.workspace, "list_projects",
                        lambda: [{"slug": "dad"}, {"slug": "controls"}])
    monkeypatch.setattr(mcp_server.workspace, "pin_active",
                        lambda s: pinned.setdefault("slug", s))
    mcp_server.main(["--project", "dad"])
    assert pinned["slug"] == "dad"


def test_main_rejects_unknown_project(monkeypatch):
    monkeypatch.setattr(mcp_server.userdata, "bootstrap", lambda: None)
    monkeypatch.setattr(mcp_server.workspace, "list_projects",
                        lambda: [{"slug": "controls"}])
    monkeypatch.setattr(mcp_server.mcp, "run", lambda: pytest.fail("must not serve"))
    with pytest.raises(SystemExit):
        mcp_server.main(["--project", "nope"])
