from rerank.import_ import import_scores, ImportResult


def _rows_by_key():
    # job_key -> inbox row dict (must carry id + fit)
    return {
        "k1": {"id": 1, "fit": -1, "title": "Software Developer", "company": "Acme"},
        "k2": {"id": 2, "fit": 50, "title": "Controls Eng", "company": "Beta"},
    }


def _capture():
    seen = {}
    def writer(updates, *, source="file_import"):
        seen["updates"] = updates
        seen["source"] = source
        return len(updates)
    return seen, writer


def _write_csv(tmp_path, body, bom=False):
    p = tmp_path / "ret.csv"
    text = body
    if bom:
        text = "﻿" + text
    p.write_text(text, encoding="utf-8")
    return p


def test_import_csv_overwrite(tmp_path):
    seen, writer = _capture()
    body = ("job_key,new_fit,new_rank,fit_rationale,tags\n"
            "k1,88,1,great fit,plc\n"
            "k2,30,2,weak,\n")
    res = import_scores(_write_csv(tmp_path, body), _rows_by_key(),
                        policy="overwrite", _apply=writer)
    assert isinstance(res, ImportResult)
    assert res.matched == 2 and res.updated == 2 and res.unmatched == []
    ids = {u["id"]: u["new_fit"] for u in seen["updates"]}
    assert ids == {1: 88, 2: 30}


def test_import_strips_bom_and_clamps(tmp_path):
    seen, writer = _capture()
    body = "job_key,new_fit,fit_rationale\nk1,150,too high\n"
    res = import_scores(_write_csv(tmp_path, body, bom=True), _rows_by_key(),
                        _apply=writer)
    assert res.updated == 1
    assert seen["updates"][0]["new_fit"] == 100   # clamped


def test_import_locale_comma_decimal(tmp_path):
    seen, writer = _capture()
    body = 'job_key,new_fit\nk1,"88,0"\n'
    res = import_scores(_write_csv(tmp_path, body), _rows_by_key(), _apply=writer)
    assert res.updated == 1 and seen["updates"][0]["new_fit"] == 88


def test_import_unmatched_job_key_reported_not_dropped(tmp_path):
    seen, writer = _capture()
    body = "job_key,new_fit\nNOPE,90\nk1,70\n"
    res = import_scores(_write_csv(tmp_path, body), _rows_by_key(), _apply=writer)
    assert res.updated == 1
    assert len(res.unmatched) == 1 and res.unmatched[0]["job_key"] == "NOPE"


def test_import_keep_existing_skips_already_scored(tmp_path):
    seen, writer = _capture()
    body = "job_key,new_fit\nk1,88\nk2,99\n"
    res = import_scores(_write_csv(tmp_path, body), _rows_by_key(),
                        policy="keep_existing", _apply=writer)
    # k2 already has fit=50 -> kept; only k1 (fit=-1) updated
    assert res.updated == 1 and res.skipped == 1
    assert seen["updates"][0]["id"] == 1


def test_import_add_only_skips_already_scored(tmp_path):
    seen, writer = _capture()
    body = "job_key,new_fit\nk1,88\nk2,99\n"
    res = import_scores(_write_csv(tmp_path, body), _rows_by_key(),
                        policy="add_only", _apply=writer)
    assert res.updated == 1 and seen["updates"][0]["id"] == 1


def test_import_json_input(tmp_path):
    seen, writer = _capture()
    p = tmp_path / "ret.json"
    p.write_text('[{"job_key":"k1","new_fit":77,"fit_rationale":"ok"},]',
                 encoding="utf-8")  # note the tolerated trailing comma
    res = import_scores(p, _rows_by_key(), _apply=writer)
    assert res.updated == 1 and seen["updates"][0]["new_fit"] == 77


def test_import_bad_fit_recorded_as_error(tmp_path):
    seen, writer = _capture()
    body = "job_key,new_fit\nk1,notanumber\n"
    res = import_scores(_write_csv(tmp_path, body), _rows_by_key(), _apply=writer)
    assert res.updated == 0 and res.errors
