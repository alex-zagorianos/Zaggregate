"""Discover (EXPERIMENTAL) — recommend.py core + /api/recommend routes.

Isolated per-test project dir (workspace.project_dir monkeypatched) so the
recommendations.json + config writes never touch real user data.
"""
import json

import pytest

import recommend as core
import workspace


_H = {"Origin": "http://127.0.0.1:5002"}

_GOOD_REPLY = """Here you go!

```json
{
  "recommendations": [
    {"role": "Robotics Systems Engineer",
     "why": "Controls + mechanical design background maps directly.",
     "fit": 88, "lane": "core",
     "keywords": ["robotics systems engineer", "robot integration"],
     "sample_titles": ["Robotics Engineer II"]},
    {"role": "Test Automation Architect",
     "why": "Fixture design + embedded work.",
     "fit": "74", "lane": "Adjacent",
     "keywords": ["test automation engineer", "hil test engineer",
                  "test automation engineer"],
     "sample_titles": []},
    {"role": "", "why": "no role -> dropped"},
    {"role": "Solutions Engineer", "lane": "weird-lane"}
  ]
}
```
Good luck!"""


@pytest.fixture
def proj(tmp_path, monkeypatch):
    p = tmp_path / "proj"
    p.mkdir()
    (p / "config.json").write_text(
        json.dumps({"keywords": ["controls engineer"]}), encoding="utf-8")
    (p / "experience.md").write_text(
        "## WORK EXPERIENCE\n\nMechanical design + controls.\n", encoding="utf-8")
    monkeypatch.setattr(workspace, "project_dir", lambda slug=None: p)
    monkeypatch.setattr(workspace, "experience_file",
                        lambda slug=None: p / "experience.md")
    monkeypatch.setattr(workspace, "load_config",
                        lambda slug=None: json.loads(
                            (p / "config.json").read_text(encoding="utf-8")))

    def _save(cfg, slug=None):
        (p / "config.json").write_text(json.dumps(cfg), encoding="utf-8")

    monkeypatch.setattr(workspace, "save_config", _save)
    return p


# ── core: prompt ──────────────────────────────────────────────────────────────

def test_prompt_carries_experience_targets_and_interests(proj):
    prompt = core.build_recommend_prompt("humanoid robotics, AI tooling")
    assert "MY EXPERIENCE" in prompt
    assert "Mechanical design + controls." in prompt
    assert "controls engineer" in prompt              # already-searching block
    assert "humanoid robotics, AI tooling" in prompt  # interests note
    assert "```json" in prompt                        # output contract
    # The interests note persists for the next page load.
    assert core.load_state()["interests"] == "humanoid robotics, AI tooling"


def test_prompt_survives_missing_everything(proj):
    (proj / "experience.md").unlink()
    (proj / "config.json").write_text("{}", encoding="utf-8")
    prompt = core.build_recommend_prompt("")
    assert "OUTPUT FORMAT" in prompt                  # never blocked


# ── core: reply parsing ───────────────────────────────────────────────────────

def test_parse_good_reply_normalizes(proj):
    recs = core.parse_recommendations_reply(_GOOD_REPLY)
    assert [r["role"] for r in recs] == [
        "Robotics Systems Engineer", "Test Automation Architect",
        "Solutions Engineer"]                          # blank role dropped
    assert recs[0]["fit"] == 88 and recs[0]["lane"] == "core"
    assert recs[1]["fit"] == 74 and recs[1]["lane"] == "adjacent"  # str + case
    assert recs[1]["keywords"] == ["test automation engineer",
                                   "hil test engineer"]            # deduped
    assert recs[2]["lane"] == "adjacent"               # unknown lane -> default
    assert all(r["id"] for r in recs)


def test_parse_unfenced_and_bare_array(proj):
    bare = json.dumps({"recommendations": [{"role": "FPGA Engineer"}]})
    assert core.parse_recommendations_reply(bare)[0]["role"] == "FPGA Engineer"
    arr = json.dumps([{"role": "Mechatronics Lead"}])
    assert core.parse_recommendations_reply(arr)[0]["role"] == "Mechatronics Lead"


@pytest.mark.parametrize("bad", ["", "   ", "no json here at all",
                                 '{"recommendations": []}',
                                 '{"recommendations": [{"why": "no role"}]}'])
def test_parse_bad_replies_raise_friendly(proj, bad):
    with pytest.raises(ValueError):
        core.parse_recommendations_reply(bad)


# ── core: actions ─────────────────────────────────────────────────────────────

def test_apply_keywords_is_additive_only(proj):
    state = core.save_reply(_GOOD_REPLY)
    rec = state["recommendations"][0]
    out = core.apply_keywords(rec["id"])
    cfg = json.loads((proj / "config.json").read_text(encoding="utf-8"))
    # Existing keyword untouched + still first; new ones appended, deduped.
    assert cfg["keywords"][0] == "controls engineer"
    assert "robotics systems engineer" in cfg["keywords"]
    assert out["added"] == ["robotics systems engineer", "robot integration"]
    # Re-apply: nothing added twice, never an error.
    assert core.apply_keywords(rec["id"])["added"] == []
    assert core.load_state()["recommendations"][0]["applied"] is True


def test_dismiss_marks_card(proj):
    state = core.save_reply(_GOOD_REPLY)
    rid = state["recommendations"][1]["id"]
    assert core.dismiss(rid) is True
    assert core.load_state()["recommendations"][1]["dismissed"] is True
    assert core.dismiss("nope") is False


# ── routes ────────────────────────────────────────────────────────────────────

def test_route_roundtrip(client, proj):
    r = client.post("/api/recommend/prompt", headers=_H,
                    json={"interests": "robots"})
    assert r.status_code == 200 and "MY EXPERIENCE" in r.get_json()["prompt"]

    r = client.post("/api/recommend/reply", headers=_H,
                    json={"text": _GOOD_REPLY})
    body = r.get_json()
    assert r.status_code == 200 and len(body["recommendations"]) == 3

    rid = body["recommendations"][0]["id"]
    r = client.post(f"/api/recommend/{rid}/apply-keywords", headers=_H)
    assert r.status_code == 200 and r.get_json()["added"]

    r = client.get("/api/recommend")
    got = r.get_json()
    assert got["ok"] is True and got["recommendations"][0]["applied"] is True

    r = client.post(f"/api/recommend/{rid}/dismiss", headers=_H)
    assert r.get_json() == {"ok": True, "dismissed": True}


def test_route_bad_reply_is_400_envelope(client, proj):
    r = client.post("/api/recommend/reply", headers=_H,
                    json={"text": "not json"})
    assert r.status_code == 400
    body = r.get_json()
    assert body["ok"] is False and "recommendations JSON" in body["error"]


def test_route_unknown_rec_is_404(client, proj):
    r = client.post("/api/recommend/zzz/apply-keywords", headers=_H)
    assert r.status_code == 404
    assert r.get_json()["error"] == "unknown recommendation"


def test_mutating_routes_are_origin_gated(client, proj):
    # No Origin header -> the strict gate denies (the route-audit meta-test
    # verifies the marker; this exercises the behavior end-to-end).
    assert client.post("/api/recommend/prompt", json={}).status_code == 403
    assert client.post("/api/recommend/reply", json={}).status_code == 403
