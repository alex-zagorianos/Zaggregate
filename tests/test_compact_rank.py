import json

import claude_bridge as bridge
import ranker
from match import facts as F
from models import JobResult

PREFS = {"profile_md": "Controls + embedded build roles; real-time motion.", "hard": {}}
CFG = {"keywords": ["controls engineer", "embedded systems engineer"],
       "salary_min": 85000, "exclude_titles": ["ai", "machine learning"]}


def _job(title, desc="", location="Cincinnati, OH", salary_min=100000, url=None):
    return JobResult(title=title, company="Acme", location=location, salary_min=salary_min,
                     salary_max=None, description=desc, url=url or f"https://x.co/{abs(hash(title))%9999}",
                     source_keyword="", created="", source_api="test")


def test_compact_prompt_is_smaller_than_full(monkeypatch, tmp_path):
    monkeypatch.setattr(F, "_cache_dir", lambda: tmp_path)
    long_desc = "C++ firmware for real-time motion control on STM32. " * 60  # ~3000 chars
    jobs = [_job("Controls Engineer", long_desc)]
    full = ranker.build_request(jobs, prefs=PREFS, experience_summary="")
    compact = ranker.build_compact_request(jobs, prefs=PREFS, cfg=CFG)
    assert "Facts:" in compact and "Description:" not in compact
    assert "controls engineer" in compact          # rubric present
    assert len(compact) < len(full)                # the whole point: less context


def test_prepare_compact_gates_and_roundtrips(monkeypatch, tmp_path):
    monkeypatch.setattr(F, "_cache_dir", lambda: tmp_path)
    jobs = [
        _job("Controls Engineer", "design and develop embedded firmware, real-time motion control"),
        _job("Electrical Engineer Intern", "embedded systems internship"),
        _job("Senior Manager, Embedded Systems", "manage a team of firmware engineers"),
        _job("Machine Learning Engineer", "train deep learning models"),
    ]
    out = ranker.prepare_compact(jobs, prefs=PREFS, cfg=CFG)
    kept_titles = [j.title for j, _f, _g in out["kept"]]
    dropped_titles = [j.title for j, _f, _g in out["dropped"]]

    assert "Controls Engineer" in kept_titles
    assert "Electrical Engineer Intern" in dropped_titles   # internship
    assert "Senior Manager, Embedded Systems" in dropped_titles  # people-management
    assert "Machine Learning Engineer" in dropped_titles    # excluded title
    assert out["prompt"]                                     # a prompt for the kept set

    # The kept set round-trips through the unchanged parse_response contract.
    kept_jobs = [j for j, _f, _g in out["kept"]]
    reply = json.dumps([{"i": n + 1, "token": bridge.fit_token(j), "fit": 80, "why": "fits"}
                        for n, j in enumerate(kept_jobs)])
    scored = ranker.parse_response(reply, kept_jobs)
    assert len(scored) == len(kept_jobs)
    assert all(fit == 80 for _j, fit, _why in scored)
