"""S35 finding #15 (major): the default (always-on) discovery host list omitted
platforms the codebase actually resolves + scrapes. icims/taleo/successfactors
are JSON-LD-scrapeable (ats_detect.py fingerprints them; careers_client.py
routes them to scrape_jsonld) but were previously reachable ONLY via the
opt-in --discover-enterprise flag, which per a prior review finding isn't even
wired into daily_run -- so these three scrapeable platforms were never
discovered by default.

Fix: _DEFAULT_SUBDOMAIN_ATS_HOSTS = [icims.com, taleo.net, successfactors.com]
is host-level-harvested (matchType=domain, required since these are
SUBDOMAIN-tenant hosts, not path-based) by run_funnel()'s default (no
explicit ats_hosts) path, in ADDITION to the existing path-based
_DEFAULT_ATS_HOSTS leg. UKG/Paycom/Cornerstone/Ceridian-Dayforce are
deliberately NOT added anywhere -- no ats_detect.py fingerprint branch and no
scraper exists for them, so a "discovered" board there would be an unprobeable
'direct' junk entry."""
from discover import funnel


def test_icims_taleo_successfactors_are_scrapeable():
    """The premise of the fix: these three ARE actually resolvable + scrapeable
    (ats_detect fingerprints them, careers_client routes them to scrape_jsonld)."""
    from scrape.ats_detect import detect_ats
    assert detect_ats("https://careers-kroger.icims.com/jobs/123/job")[0] == "icims"
    assert detect_ats("https://x.taleo.net/careersection/2/jobdetail.ftl")[0] == "taleo"
    assert detect_ats("https://performancemanager.successfactors.com/careers")[0] == "successfactors"

    import scrape.careers_client as cc
    for ats in ("icims", "taleo", "successfactors"):
        assert ats in cc._SHALLOW_MATCH_ATS  # dispatched (and memoizable) via scrape_jsonld


def test_default_subdomain_hosts_constant_matches_scrapeable_types():
    assert set(funnel._DEFAULT_SUBDOMAIN_ATS_HOSTS) == {
        "icims.com", "taleo.net", "successfactors.com"}


def test_ukg_paycom_cornerstone_ceridian_not_added_anywhere():
    # No ats_detect.py branch + no scraper exists for these -- a "discovered"
    # board there would fall back to ats_type='direct' (unprobeable junk), so
    # they must not appear in ANY of the funnel's host lists.
    banned_substrings = ("ukg", "kronos", "paycom", "cornerstone",
                         "ceridian", "dayforce")
    all_hosts = (funnel._DEFAULT_ATS_HOSTS + funnel._DEFAULT_SUBDOMAIN_ATS_HOSTS
                + funnel._ENTERPRISE_ATS_HOSTS)
    for host in all_hosts:
        low = host.lower()
        assert not any(b in low for b in banned_substrings), \
            f"{host!r} should not be in any default/enterprise host list (no scraper exists)"

    from scrape.ats_detect import detect_ats
    for url in (
        "https://acme.ukg.com/careers",
        "https://acme.kronos.net/jobs",
        "https://acme.paycomonline.net/careers",
        "https://acme.cornerstoneondemand.com/careers",
    ):
        ats_type, _ = detect_ats(url)
        assert ats_type == "direct", f"{url} unexpectedly got a real ats_type {ats_type!r}"


# ---------------------------------------------------------------------------
# run_funnel() wiring: default path host-level-harvests the subdomain hosts,
# additively, without requiring --discover-enterprise. All network seams
# mocked (funnel.cc_harvest.harvest_slugs / harvest_host_index).
# ---------------------------------------------------------------------------
def test_default_run_funnel_harvests_subdomain_hosts_without_enterprise_flag(monkeypatch):
    calls = {"host_index_hosts": None, "slugs_hosts": None}

    def fake_host_index(hosts, **kw):
        calls["host_index_hosts"] = list(hosts)
        return {"icims": {"https://careers-kroger.icims.com/jobs"}}

    def fake_slugs(hosts, **kw):
        calls["slugs_hosts"] = list(hosts)
        return {"greenhouse": {"acme"}}

    monkeypatch.setattr(funnel.cc_harvest, "harvest_host_index", fake_host_index)
    monkeypatch.setattr(funnel.cc_harvest, "harvest_slugs", fake_slugs)
    monkeypatch.setattr(funnel, "merge_discovered", lambda boards, path: len(boards))

    summary = funnel.run_funnel()  # no host_level=True, no enterprise=True

    assert set(calls["slugs_hosts"]) == set(funnel._DEFAULT_ATS_HOSTS)
    assert set(calls["host_index_hosts"]) == set(funnel._DEFAULT_SUBDOMAIN_ATS_HOSTS)
    assert "icims" in summary["harvested"]
    assert "greenhouse" in summary["harvested"]


def test_explicit_empty_ats_hosts_still_skips_everything(monkeypatch):
    # ats_hosts=[] ("skip the CDX leg entirely") must ALSO skip the new
    # subdomain-host leg -- an explicit override wins over the new default.
    calls = {"slugs": 0, "host_index": 0}
    monkeypatch.setattr(funnel.cc_harvest, "harvest_slugs",
                        lambda *a, **k: (calls.__setitem__("slugs", calls["slugs"] + 1), {})[1])
    monkeypatch.setattr(funnel.cc_harvest, "harvest_host_index",
                        lambda *a, **k: (calls.__setitem__("host_index", calls["host_index"] + 1), {})[1])
    monkeypatch.setattr(funnel, "merge_discovered", lambda boards, path: 0)

    funnel.run_funnel(ats_hosts=[])
    assert calls["slugs"] == 0
    assert calls["host_index"] == 0


def test_explicit_custom_ats_hosts_does_not_get_subdomain_hosts_appended(monkeypatch):
    # A caller passing their OWN explicit host list must get exactly that list
    # via harvest_slugs -- the new default subdomain leg is additive ONLY for
    # the true default (ats_hosts=None), never silently injected into a
    # caller-supplied list.
    calls = {"host_index": 0, "slugs_hosts": None}
    monkeypatch.setattr(funnel.cc_harvest, "harvest_slugs",
                        lambda hosts, **kw: (calls.__setitem__("slugs_hosts", list(hosts)), {})[1])
    monkeypatch.setattr(funnel.cc_harvest, "harvest_host_index",
                        lambda *a, **k: (calls.__setitem__("host_index", calls["host_index"] + 1), {})[1])
    monkeypatch.setattr(funnel, "merge_discovered", lambda boards, path: 0)

    funnel.run_funnel(ats_hosts=["boards.greenhouse.io"])
    assert calls["slugs_hosts"] == ["boards.greenhouse.io"]
    assert calls["host_index"] == 0


def test_enterprise_flag_skips_the_redundant_default_subdomain_leg(monkeypatch):
    # When --discover-enterprise already host-level-harvests icims/taleo/
    # successfactors (with deeper max_pages pagination) as part of
    # _ENTERPRISE_ATS_HOSTS, the default-path subdomain leg must not ALSO
    # fire a second, shallower (single-page) harvest of the same hosts.
    calls = {"host_index_calls": 0}

    def fake_host_index(hosts, **kw):
        calls["host_index_calls"] += 1
        return {}
    monkeypatch.setattr(funnel.cc_harvest, "harvest_host_index", fake_host_index)
    monkeypatch.setattr(funnel, "merge_discovered", lambda boards, path: 0)

    funnel.run_funnel(enterprise=True)
    assert calls["host_index_calls"] == 1  # ONE host-level call, not two
