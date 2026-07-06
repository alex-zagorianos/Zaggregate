"""Companies API — detect / validate-job / add gating / build-list + seed-metro
job lifecycle / AI seed prompt+apply (Phase 5).

Engine seams are monkeypatched (probe_board / save_companies / build_company_list
/ seed_my_metro / BusinessFinderClient.has_key) so the routes + job lifecycle +
P0-6 gating are exercised with no network. The job fns import their seams lazily
INSIDE the thread, so patches target the SOURCE module (scrape.ats_detect, etc.),
not the route module.
"""
import pytest

import config
import workspace
from tests.webui.conftest import wait_until


_LOOPBACK = "http://127.0.0.1:5002"


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "USER_DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "COMPANIES_JSON", tmp_path / "companies.json")
    monkeypatch.setattr(workspace, "BASE_DIR", tmp_path)
    return tmp_path


def _wait_status(client, job_id, target, timeout=3.0):
    def _check():
        snap = client.get(f"/api/jobs/{job_id}").get_json()
        return snap if snap.get("status") == target else None
    return wait_until(
        _check, timeout=timeout,
        message=f"job {job_id} never {target}: "
                f"{client.get(f'/api/jobs/{job_id}').get_json()}")


# ── detect ────────────────────────────────────────────────────────────────────
def test_detect_parses_lines(client):
    resp = client.post("/api/companies/detect",
                       json={"lines": "Acme | https://boards.greenhouse.io/acme\n"
                                       "Here are some employers:\n"
                                       "https://jobs.lever.co/beta"},
                       headers={"Origin": _LOOPBACK})
    assert resp.status_code == 200
    cands = resp.get_json()["candidates"]
    by_status = {c["status"] for c in cands}
    # The greenhouse + lever lines detect; the prose line ("Here are…") drops.
    assert "detected" in by_status
    assert "dropped" in by_status
    acme = next(c for c in cands if "Acme" in c["line"])
    assert acme["ats"] == "greenhouse"
    assert acme["slug"] == "acme"


def test_detect_accepts_list_body(client):
    resp = client.post("/api/companies/detect",
                       json={"lines": ["https://boards.greenhouse.io/foo"]},
                       headers={"Origin": _LOOPBACK})
    cands = resp.get_json()["candidates"]
    assert len(cands) == 1 and cands[0]["status"] == "detected"


def test_detect_headerless_403(client):
    resp = client.post("/api/companies/detect", json={"lines": "x"})
    assert resp.status_code == 403


# ── validate (job) ────────────────────────────────────────────────────────────
def test_validate_job_probes_each(client, monkeypatch):
    from scrape.ats_detect import ProbeResult

    def fake_probe(entry):
        # 'acme' is live with 3 jobs; everything else is unreachable.
        if entry.slug == "acme":
            return ProbeResult(3, True)
        return ProbeResult(None, False)

    monkeypatch.setattr("scrape.ats_detect.probe_board", fake_probe)

    resp = client.post("/api/companies/validate",
                       json={"candidates": [
                           {"name": "Acme", "ats": "greenhouse", "slug": "acme"},
                           {"name": "Dead", "ats": "lever", "slug": "dead"},
                           {"name": "Page", "ats": "direct", "slug": "https://x/careers"},
                       ]},
                       headers={"Origin": _LOOPBACK})
    assert resp.status_code == 200
    jid = resp.get_json()["job_id"]
    snap = _wait_status(client, jid, "done")
    results = {r["name"]: r for r in snap["result"]["results"]}
    assert results["Acme"]["verdict"] == "live" and results["Acme"]["count"] == 3
    assert results["Dead"]["verdict"] == "unreachable"
    assert results["Page"]["verdict"] == "direct"   # direct pages aren't probed


def test_validate_empty_400(client):
    resp = client.post("/api/companies/validate", json={"candidates": []},
                       headers={"Origin": _LOOPBACK})
    assert resp.status_code == 400


def test_validate_headerless_403(client):
    resp = client.post("/api/companies/validate",
                       json={"candidates": [{"slug": "x"}]})
    assert resp.status_code == 403


# ── add (P0-6 gating) ─────────────────────────────────────────────────────────
def test_add_saves_verified_and_gates_unreachable(client, monkeypatch):
    saved = {}

    def fake_save(entries, *a, **k):
        saved["entries"] = list(entries)
        return len(entries)

    monkeypatch.setattr("scrape.company_registry.save_companies", fake_save)

    resp = client.post("/api/companies/add",
                       json={"keep_unreachable": True, "entries": [
                           {"name": "Live", "ats": "greenhouse", "slug": "live",
                            "verdict": "live"},
                           {"name": "Walled", "ats": "lever", "slug": "walled",
                            "verdict": "unreachable"},
                       ]},
                       headers={"Origin": _LOOPBACK})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["verified"] == 1
    assert body["unverified"] == 1
    assert body["added"] == 2
    # The unreachable one carries the UNVERIFIED flag; the live one does not.
    from scrape.company_registry import UNVERIFIED_FLAG
    walled = next(e for e in saved["entries"] if e.name == "Walled")
    live = next(e for e in saved["entries"] if e.name == "Live")
    assert (walled.extra or {}).get(UNVERIFIED_FLAG) is True
    assert not (live.extra or {}).get(UNVERIFIED_FLAG)


def test_add_drops_unreachable_when_not_kept(client, monkeypatch):
    saved = {}
    monkeypatch.setattr("scrape.company_registry.save_companies",
                        lambda entries, *a, **k: saved.setdefault("e", list(entries)) or len(entries))
    resp = client.post("/api/companies/add",
                       json={"keep_unreachable": False, "entries": [
                           {"name": "Walled", "ats": "lever", "slug": "walled",
                            "verdict": "unreachable"},
                       ]},
                       headers={"Origin": _LOOPBACK})
    body = resp.get_json()
    assert body["added"] == 0
    assert body["dropped"] == 1
    assert body["unverified"] == 0


def test_add_rejects_tos_blocked_host(client, monkeypatch):
    monkeypatch.setattr("scrape.company_registry.save_companies",
                        lambda entries, *a, **k: len(list(entries)))
    # An Indeed URL is a ToS-blocked host — rejected regardless of verdict.
    resp = client.post("/api/companies/add",
                       json={"keep_unreachable": True, "entries": [
                           {"name": "Bad", "ats": "direct",
                            "slug": "https://www.indeed.com/jobs?q=x",
                            "verdict": "direct"},
                       ]},
                       headers={"Origin": _LOOPBACK})
    body = resp.get_json()
    assert body["rejected"] == 1
    assert body["added"] == 0


def test_add_empty_400(client):
    resp = client.post("/api/companies/add", json={"entries": []},
                       headers={"Origin": _LOOPBACK})
    assert resp.status_code == 400


def test_add_headerless_403(client):
    resp = client.post("/api/companies/add",
                       json={"entries": [{"slug": "x", "verdict": "live"}]})
    assert resp.status_code == 403


# ── build-list (exclusive job) ────────────────────────────────────────────────
def test_build_list_job(client, monkeypatch):
    calls = {}

    def fake_build(*, project=None, log=print, **kw):
        log("== building ==")
        calls["kw"] = kw
        calls["project"] = project
        return {"industry": "nursing", "metro": "Boston, MA", "stages": {}}

    monkeypatch.setattr("build_company_list.build_company_list", fake_build)

    resp = client.post("/api/companies/build-list",
                       json={"opts": {"industry": "nursing", "metro": "Boston, MA",
                                      "jobhive": True, "use_inbox": False}},
                       headers={"Origin": _LOOPBACK})
    assert resp.status_code == 200
    jid = resp.get_json()["job_id"]
    snap = _wait_status(client, jid, "done")
    assert snap["result"]["industry"] == "nursing"
    assert calls["kw"]["industry"] == "nursing"
    assert calls["kw"]["jobhive"] is True
    assert calls["kw"]["use_inbox"] is False


def test_build_list_headerless_403(client):
    resp = client.post("/api/companies/build-list", json={"opts": {}})
    assert resp.status_code == 403


# ── seed-metro (key-gated exclusive job) ──────────────────────────────────────
def test_seed_metro_keyless_409(client, monkeypatch):
    # No key -> up-front 409 (never spins an exclusive job).
    monkeypatch.setattr(
        "discover.business_finder.BusinessFinderClient.has_key",
        lambda self: False)
    resp = client.post("/api/companies/seed-metro",
                       json={"industry": "nursing", "metro": "Boston, MA"},
                       headers={"Origin": _LOOPBACK})
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["ok"] is False
    assert body["need_key"] is True
    assert "CareerOneStop" in body["error"]


def test_seed_metro_job_runs_with_key(client, monkeypatch):
    monkeypatch.setattr(
        "discover.business_finder.BusinessFinderClient.has_key",
        lambda self: True)

    class _FakeResult:
        def as_dict(self):
            return {"industry": "nursing", "metro": "Boston, MA", "added": 4,
                    "verified": 4, "discovered": 10}

    def fake_seed(*, industry="", metro="", keyword="", limit=40, log=print, **k):
        log(f"[seed-metro] seeding {industry} near {metro}")
        return _FakeResult()

    monkeypatch.setattr("discover.seed_metro.seed_my_metro", fake_seed)

    resp = client.post("/api/companies/seed-metro",
                       json={"industry": "nursing", "metro": "Boston, MA"},
                       headers={"Origin": _LOOPBACK})
    assert resp.status_code == 200
    jid = resp.get_json()["job_id"]
    snap = _wait_status(client, jid, "done")
    assert snap["result"]["added"] == 4
    assert snap["result"]["industry"] == "nursing"


def test_seed_metro_headerless_403(client, monkeypatch):
    monkeypatch.setattr(
        "discover.business_finder.BusinessFinderClient.has_key",
        lambda self: True)
    resp = client.post("/api/companies/seed-metro",
                       json={"industry": "x", "metro": "y"})
    assert resp.status_code == 403


# ── AI seed prompt / apply ────────────────────────────────────────────────────
def test_seed_prompt_static(client):
    body = client.get("/api/companies/seed-prompt?field=nursing&metro=Boston").get_json()
    assert body["ok"] is True
    assert "careers" in body["prompt"].lower()
    assert "nursing" in body["prompt"]


def test_seed_apply_saves(client, isolated, monkeypatch):
    from scrape.ats_detect import ProbeResult
    monkeypatch.setattr("scrape.ats_detect.probe_board",
                        lambda e: ProbeResult(2, True))
    saved = {}
    monkeypatch.setattr("scrape.company_registry.save_companies",
                        lambda entries, *a, **k: saved.setdefault("n", len(list(entries))))

    resp = client.post("/api/companies/seed-apply",
                       json={"text": "Acme | https://boards.greenhouse.io/acme",
                             "industry": "nursing"},
                       headers={"Origin": _LOOPBACK})
    assert resp.status_code == 200
    result = resp.get_json()["result"]
    assert result["parsed"] == 1
    assert result["verified"] == 1


def test_seed_apply_empty_400(client):
    resp = client.post("/api/companies/seed-apply", json={"text": "  "},
                       headers={"Origin": _LOOPBACK})
    assert resp.status_code == 400


def test_seed_apply_headerless_403(client):
    resp = client.post("/api/companies/seed-apply",
                       json={"text": "Acme | https://x"})
    assert resp.status_code == 403
