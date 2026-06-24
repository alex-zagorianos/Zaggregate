"""The discovery funnel unifies CDX harvest + careers-link finding and merges
new ATS boards into companies.json. Additive by construction (merge_discovered
is user-wins + dedup), so it can only add boards — never remove or rescore one.
Network seams (cc_harvest, career_link) are mocked; detect + merge run for real."""
import json

from discover import funnel


def _read_slugs(cf):
    data = json.loads(cf.read_text(encoding="utf-8"))
    return {c["slug"] for c in data.get("companies", [])}


def test_run_funnel_merges_cdx_and_domain_legs(tmp_path, monkeypatch):
    cf = tmp_path / "companies.json"
    cf.write_text('{"companies": []}', encoding="utf-8")
    monkeypatch.setattr(funnel.cc_harvest, "harvest_slugs",
                        lambda hosts, **kw: {"greenhouse": {"acme"}})
    monkeypatch.setattr(funnel.career_link, "find_career_url",
                        lambda d: "https://jobs.lever.co/globex")
    summary = funnel.run_funnel(domains=["globex.io"], companies_json_path=cf, limit=50)
    assert summary["added"] >= 2                  # acme (greenhouse) + globex (lever)
    assert {"acme", "globex"} <= _read_slugs(cf)


def test_run_funnel_is_additive_never_removes(tmp_path, monkeypatch):
    cf = tmp_path / "companies.json"
    cf.write_text(json.dumps({"companies": [
        {"name": "Existing", "ats_type": "greenhouse", "slug": "existing", "industries": []}
    ]}), encoding="utf-8")
    monkeypatch.setattr(funnel.cc_harvest, "harvest_slugs",
                        lambda hosts, **kw: {"greenhouse": {"newco"}})
    funnel.run_funnel(domains=None, companies_json_path=cf)
    slugs = _read_slugs(cf)
    assert "existing" in slugs and "newco" in slugs   # additive: nothing removed


def test_harvest_from_domains_skips_unresolvable(monkeypatch):
    monkeypatch.setattr(
        funnel.career_link, "find_career_url",
        lambda d: None if d == "bad.com" else "https://boards.greenhouse.io/ok")
    boards = funnel.harvest_from_domains(["bad.com", "good.com"])
    assert boards == {"greenhouse": {"ok"}}


def test_run_funnel_skips_cdx_when_hosts_empty(tmp_path, monkeypatch):
    cf = tmp_path / "companies.json"
    cf.write_text('{"companies": []}', encoding="utf-8")
    called = []
    monkeypatch.setattr(funnel.cc_harvest, "harvest_slugs",
                        lambda *a, **k: (called.append(1), {})[1])
    funnel.run_funnel(ats_hosts=[], domains=None, companies_json_path=cf)
    assert called == []                           # [] hosts -> CDX leg skipped
