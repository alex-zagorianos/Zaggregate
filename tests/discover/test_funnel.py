"""The discovery funnel unifies CDX harvest + careers-link finding and merges
new ATS boards into companies.json. Additive by construction (merge_discovered
is user-wins + dedup), so it can only add boards — never remove or rescore one.
Network seams (cc_harvest, career_link) are mocked; detect + merge run for real.

S35 #15: run_funnel()'s DEFAULT (no explicit ats_hosts) path now ALSO
host-level-harvests _DEFAULT_SUBDOMAIN_ATS_HOSTS (icims/taleo/successfactors)
via cc_harvest.harvest_host_index, so every test that exercises the default
path must mock that seam too or it will attempt a real network call."""
import json

from discover import funnel


def _read_slugs(cf):
    data = json.loads(cf.read_text(encoding="utf-8"))
    return {c["slug"] for c in data.get("companies", [])}


def _no_subdomain_boards(monkeypatch):
    """Mock the S35 #15 default subdomain-host leg to a no-op so pre-existing
    tests that only care about the path-based CDX leg stay offline/unaffected."""
    monkeypatch.setattr(funnel.cc_harvest, "harvest_host_index", lambda hosts, **kw: {})


def test_run_funnel_merges_cdx_and_domain_legs(tmp_path, monkeypatch):
    cf = tmp_path / "companies.json"
    cf.write_text('{"companies": []}', encoding="utf-8")
    monkeypatch.setattr(funnel.cc_harvest, "harvest_slugs",
                        lambda hosts, **kw: {"greenhouse": {"acme"}})
    _no_subdomain_boards(monkeypatch)
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
    _no_subdomain_boards(monkeypatch)
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
