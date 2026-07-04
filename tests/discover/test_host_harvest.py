"""P6 — host-level (registered-domain) CC harvest + enterprise ATS hosts."""
from pathlib import Path

import discover.cc_harvest as H
from discover import funnel

FX = Path(__file__).resolve().parents[1] / "fixtures" / "ws2"


def _cdx_lines():
    return (FX / "cdx_greenhouse.jsonl").read_text(encoding="utf-8").splitlines()


def test_host_index_single_page(monkeypatch):
    seen = {}

    def fake_fetch(host, crawl_id, limit, *, page=None, page_size=None):
        seen["page"] = page
        return _cdx_lines()

    out = H.harvest_host_index(["boards.greenhouse.io"], fetch=fake_fetch)
    assert out.get("greenhouse") == {"acme", "beta"}
    assert seen["page"] is None                      # single page -> no page param


def test_host_index_paginates_across_pages(monkeypatch):
    pages_fetched = []

    def fake_fetch(host, crawl_id, limit, *, page=None, page_size=None):
        pages_fetched.append(page)
        # Different slug per page to prove all pages are folded together.
        slug = {0: "acme", 1: "beta", 2: "gamma"}[page]
        return ['{"url": "https://boards.greenhouse.io/%s/jobs/1"}' % slug]

    out = H.harvest_host_index(["boards.greenhouse.io"], max_pages=5,
                               fetch=fake_fetch, num_pages=lambda h, c, ps: 3)
    assert out["greenhouse"] == {"acme", "beta", "gamma"}
    assert pages_fetched == [0, 1, 2]                # bounded by the 3 real pages


def test_host_index_unreachable_is_loud_and_empty(monkeypatch, capsys):
    def boom(host, crawl_id, limit, *, page=None, page_size=None):
        raise RuntimeError("net")

    out = H.harvest_host_index(["boards.greenhouse.io"], fetch=boom)
    assert out == {}
    assert "WARNING" in capsys.readouterr().out


def test_enterprise_host_captures_workday_tenant(monkeypatch):
    # A host-level query on myworkdayjobs.com must fold in tenant boards.
    def fake_fetch(host, crawl_id, limit, *, page=None, page_size=None):
        return ['{"url": "https://acme.wd5.myworkdayjobs.com/en-US/External/job/x"}']

    out = H.harvest_host_index(["myworkdayjobs.com"], fetch=fake_fetch)
    # Public Workday URLs fold under the cxs reader type now.
    assert out.get("workday_cxs") == {"acme:5:External"}


def test_funnel_host_level_and_enterprise_wiring(monkeypatch):
    calls = {"slugs": 0, "host": 0, "hosts": None}

    def fake_host_index(hosts, *, crawl_id=None, limit=None, max_pages=None,
                        page_size=None, fetch=None, num_pages=None):
        calls["host"] += 1
        calls["hosts"] = list(hosts)
        return {"greenhouse": {"acme"}}

    def fake_slugs(hosts, *, crawl_id=None, limit=None):
        calls["slugs"] += 1
        return {"greenhouse": {"legacy"}}

    monkeypatch.setattr(funnel.cc_harvest, "harvest_host_index", fake_host_index)
    monkeypatch.setattr(funnel.cc_harvest, "harvest_slugs", fake_slugs)
    monkeypatch.setattr(funnel, "merge_discovered", lambda boards, path: 0)

    # enterprise implies host-level AND adds the enterprise domains
    funnel.run_funnel(enterprise=True)
    assert calls["host"] == 1 and calls["slugs"] == 0
    assert "myworkdayjobs.com" in calls["hosts"] and "icims.com" in calls["hosts"]

    # default (no flags) still uses the per-host slug path for the path-based
    # hosts (greenhouse/lever/ashby/smartrecruiters/workable), AND (S35 #15)
    # now ALSO host-level-harvests the subdomain-tenant ATSes
    # (icims/taleo/successfactors) that are JSON-LD-scrapeable but were
    # previously reachable only via the opt-in --discover-enterprise flag.
    calls["host"] = calls["slugs"] = 0
    funnel.run_funnel()
    assert calls["slugs"] == 1
    assert calls["host"] == 1
    assert set(calls["hosts"]) == {"icims.com", "taleo.net", "successfactors.com"}
    # The enterprise-only hosts (myworkdayjobs.com, eightfold.ai, etc.) are
    # still NOT part of the default surface -- only the 3 JSON-LD-scrapeable
    # subdomain hosts graduated out of the enterprise-only gate.
    assert "myworkdayjobs.com" not in calls["hosts"]
