import ranker
import models


def _job(title="Controls Engineer", url="https://x.co/1"):
    return models.JobResult(title=title, company="Acme", location="Cincinnati, OH",
                            salary_min=100000, salary_max=None, description="C++",
                            url=url, source_keyword="", created="", source_api="t")


def test_bridge_ranker_delegates_to_module_fns():
    r = ranker.BridgeRanker()
    prefs = {"profile_md": "controls roles", "hard": {}}
    assert r.build_request([_job()], prefs=prefs, experience_summary="C++") == \
        ranker.build_request([_job()], prefs=prefs, experience_summary="C++")


def test_api_ranker_build_request_matches_bridge():
    prefs = {"profile_md": "controls roles", "hard": {}}
    a, b = ranker.ApiRanker(), ranker.BridgeRanker()
    assert a.build_request([_job()], prefs=prefs) == b.build_request([_job()], prefs=prefs)


def test_all_rankers_satisfy_protocol():
    for r in (ranker.BridgeRanker(), ranker.ApiRanker(), ranker.FileRanker()):
        assert isinstance(r, ranker.Ranker)        # runtime_checkable Protocol


def test_file_ranker_build_request_is_export_prompt(monkeypatch):
    import preferences
    monkeypatch.setattr(preferences, "load", lambda: {"profile_md": "controls roles", "hard": {}})
    from rerank import schema
    fr = ranker.FileRanker()
    # FileRanker.build_request renders the versioned export prompt (job_key/new_fit present)
    req = fr.build_request([_job()])
    assert "job_key" in req and "new_fit" in req


def test_file_ranker_export_and_import_roundtrip(tmp_path):
    fr = ranker.FileRanker()
    rows = [{"id": 1, "title": "Software Developer", "company": "Acme",
             "location": "Cincinnati, OH", "salary_text": "$120k", "url": "https://x/1",
             "score": 70, "fit": -1, "description": "controls"}]
    paths = fr.export(rows, tmp_path)
    assert paths["csv"].exists()
    # build a returned CSV that fills new_fit for the exported job_key
    import csv
    with paths["csv"].open(encoding="utf-8-sig", newline="") as f:
        key = next(csv.DictReader(f))["job_key"]
    ret = tmp_path / "ret.csv"
    ret.write_text(f"job_key,new_fit\n{key},91\n", encoding="utf-8")
    captured = {}
    res = fr.import_(ret, {key: {"id": 1, "fit": -1}},
                     _apply=lambda u, *, source="file_import": (captured.update({"u": u}), len(u))[1])
    assert res.updated == 1 and captured["u"][0]["new_fit"] == 91
