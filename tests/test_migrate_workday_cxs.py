"""S32c: the Workday registry migration script (scripts/migrate_workday_cxs.py).

Relabels parked 'direct'-typed myworkdayjobs boards and legacy 'workday' rows in
companies.json to the public 'workday_cxs' reader, but ONLY when a live probe
returns >0 jobs. Dead / 422 / 0-job rows are left byte-identical. Probing is
stubbed here so the logic is exercised with no network."""
import json

import pytest

from scripts import migrate_workday_cxs as mig


def _companies_file(tmp_path, records):
    p = tmp_path / "companies.json"
    p.write_text(json.dumps({
        "_comment": "test fixture",
        "companies": records,
    }), encoding="utf-8")
    return p


def _stub_probe(monkeypatch, mapping):
    """Stub probe_count keyed by the slug the entry is probed with. The script
    binds `probe_count` at import (from scrape.ats_detect import probe_count), so
    patch the name in the SCRIPT module, not the origin module."""
    def fake(entry):
        return mapping.get(entry.slug)
    monkeypatch.setattr(mig, "probe_count", fake)


def test_candidates_are_direct_workday_urls_and_legacy_workday(tmp_path):
    records = [
        {"name": "Legacy WD", "ats_type": "workday", "slug": "acme:5:Careers",
         "industries": []},
        {"name": "Parked Direct WD", "ats_type": "direct",
         "slug": "https://foo.wd1.myworkdayjobs.com/en-US/External", "industries": []},
        {"name": "A Greenhouse Co", "ats_type": "greenhouse", "slug": "ghco",
         "industries": []},
        {"name": "A Real Direct", "ats_type": "direct",
         "slug": "https://company.com/careers/", "industries": []},
        {"name": "Already Migrated", "ats_type": "workday_cxs",
         "slug": "bar:2:Ext", "industries": []},
    ]
    p = _companies_file(tmp_path, records)
    raw = json.loads(p.read_text(encoding="utf-8"))
    cands = mig._candidates(raw["companies"])
    names = {c["name"] for c in cands}
    # Only the legacy 'workday' and the myworkdayjobs 'direct' rows are candidates.
    assert names == {"Legacy WD", "Parked Direct WD"}


def test_dry_run_migrates_nothing_but_reports(tmp_path, monkeypatch):
    records = [
        {"name": "Legacy WD", "ats_type": "workday", "slug": "acme:5:Careers",
         "industries": ["nursing"]},
    ]
    p = _companies_file(tmp_path, records)
    _stub_probe(monkeypatch, {"acme:5:Careers": 42})
    rep = mig.migrate(p, apply=False)
    assert rep["candidates"] == 1
    assert rep["migrated"] == 0                       # dry-run never mutates
    assert rep["wrote"] is False
    assert rep["rows"][0]["action"] == "migrate"      # but reports it WOULD migrate
    assert rep["rows"][0]["count"] == 42
    # File untouched on disk.
    on_disk = json.loads(p.read_text(encoding="utf-8"))
    assert on_disk["companies"][0]["ats_type"] == "workday"


def test_apply_relabels_live_row_and_derives_slug(tmp_path, monkeypatch):
    records = [
        {"name": "Legacy WD", "ats_type": "workday", "slug": "acme:5:Careers",
         "industries": ["nursing"]},
        {"name": "Parked Direct WD", "ats_type": "direct",
         "slug": "https://foo.wd1.myworkdayjobs.com/en-US/External",
         "industries": ["nursing"]},
    ]
    p = _companies_file(tmp_path, records)
    # Legacy row probes to its tenant slug; direct row probes to its DERIVED slug.
    _stub_probe(monkeypatch, {"acme:5:Careers": 10, "foo:1:External": 7})
    rep = mig.migrate(p, apply=True)
    assert rep["migrated"] == 2 and rep["wrote"] is True
    on_disk = {c["name"]: c for c in
               json.loads(p.read_text(encoding="utf-8"))["companies"]}
    assert on_disk["Legacy WD"]["ats_type"] == "workday_cxs"
    assert on_disk["Legacy WD"]["slug"] == "acme:5:Careers"     # already the id
    assert on_disk["Parked Direct WD"]["ats_type"] == "workday_cxs"
    # The full careers URL is swapped for the derived tenant:N:site identity.
    assert on_disk["Parked Direct WD"]["slug"] == "foo:1:External"
    # Industries are preserved.
    assert on_disk["Legacy WD"]["industries"] == ["nursing"]


def test_dead_or_walled_row_left_untouched(tmp_path, monkeypatch):
    records = [
        {"name": "Walled WD", "ats_type": "direct",
         "slug": "https://fedex.wd1.myworkdayjobs.com/en-US/careers",
         "industries": []},
        {"name": "Empty WD", "ats_type": "workday", "slug": "empty:5:Ext",
         "industries": []},
    ]
    p = _companies_file(tmp_path, records)
    # 422/dead -> probe returns None; empty board -> 0. Neither may be relabeled.
    _stub_probe(monkeypatch, {"fedex:1:careers": None, "empty:5:Ext": 0})
    rep = mig.migrate(p, apply=True)
    assert rep["migrated"] == 0 and rep["wrote"] is False
    on_disk = {c["name"]: c for c in
               json.loads(p.read_text(encoding="utf-8"))["companies"]}
    assert on_disk["Walled WD"]["ats_type"] == "direct"        # untouched
    assert on_disk["Empty WD"]["ats_type"] == "workday"        # untouched
    actions = {r["name"]: r["action"] for r in rep["rows"]}
    assert actions == {"Walled WD": "leave", "Empty WD": "leave"}


def test_no_probe_never_migrates(tmp_path):
    records = [{"name": "Legacy WD", "ats_type": "workday", "slug": "acme:5:Careers",
                "industries": []}]
    p = _companies_file(tmp_path, records)
    rep = mig.migrate(p, apply=True, probe=False)             # offline preview
    assert rep["migrated"] == 0 and rep["wrote"] is False
    assert rep["rows"][0]["action"] == "leave"
    assert json.loads(p.read_text(encoding="utf-8"))["companies"][0]["ats_type"] == "workday"


def test_missing_file_reports_error(tmp_path):
    rep = mig.migrate(tmp_path / "nope.json", apply=False)
    # A missing file loads as {}, yielding zero candidates (not an error).
    assert rep["candidates"] == 0 and rep["rows"] == []


def test_limit_bounds_probing(tmp_path, monkeypatch):
    records = [
        {"name": f"WD{i}", "ats_type": "workday", "slug": f"t{i}:5:S", "industries": []}
        for i in range(5)
    ]
    p = _companies_file(tmp_path, records)
    _stub_probe(monkeypatch, {f"t{i}:5:S": 3 for i in range(5)})
    rep = mig.migrate(p, apply=False, limit=2)
    assert rep["candidates"] == 2                             # only first 2 probed
