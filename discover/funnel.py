"""Unified discovery funnel (spec §5.1).

Brings the WS-2 discovery pieces — Common Crawl CDX slug harvest (cc_harvest),
per-domain careers-link finding (career_link) and ATS detection (detect) —
together into ONE additive pass that merges newly found ATS boards into
companies.json via registry.merge_discovered.

This is the orchestration that was missing: the modules existed but only the
Brave-search discoverer was wired into the live scrape path. run_funnel() is a
maintenance pass (occasional, not per-search; see cc_harvest's "runs
occasionally" note) reachable from the CLI's `--discover` flag.

Additive by construction: merge_discovered is user-wins and dedups, so the
funnel can only ADD boards to the registry — it can never remove or rescore an
existing one, so a search's coverage can't regress because of it.
"""
from __future__ import annotations

from discover import career_link, cc_harvest
from discover.detect import detect_ats
from discover.registry import merge_discovered

# ATS apex hosts CDX-harvested by default — the same boards the live scrapers
# understand (Brave discovery already covers these per-keyword; CDX is the
# generic, keyword-blind denominator pass).
_DEFAULT_ATS_HOSTS = [
    "boards.greenhouse.io",
    "jobs.lever.co",
    "jobs.ashbyhq.com",
    "jobs.smartrecruiters.com",
    "apply.workable.com",
]

# Enterprise ATS registered-domains — one host-level (matchType=domain) query
# reaches every tenant under them. This is where the big health systems /
# industrials live (Workday/iCIMS/Taleo/SuccessFactors); detect_ats already tags
# them (slug = the URL) and probe_count counts their JSON-LD. Only used on the
# host-level path (plan P6) — a per-URL CDX prefix can't span subdomains.
_ENTERPRISE_ATS_HOSTS = [
    "myworkdayjobs.com",
    "icims.com",
    "taleo.net",
    "successfactors.com",
]


def harvest_from_domains(domains) -> dict:
    """{ats_type: {slug,...}} from resolving each company domain to its careers
    URL and detecting the ATS board behind it. Fail-soft per domain."""
    boards: dict[str, set] = {}
    for domain in domains or []:
        url = career_link.find_career_url(domain)
        if not url:
            continue
        det = detect_ats(url)
        if det is None:
            continue
        ats_type, slug = det
        boards.setdefault(ats_type, set()).add(slug)
    return boards


def _merge_boards(into: dict, more: dict) -> None:
    for ats_type, slugs in (more or {}).items():
        into.setdefault(ats_type, set()).update(slugs)


def _apply_classify(boards: dict, classify) -> dict:
    """Filter a {ats:{slug}} board dict through a relevance classifier (plan P3).
    `classify(list[CompanyEntry]) -> kept (ats,slug) set`. No-op-safe (a keep-all
    classifier returns everything). Only used when an industry is being seeded."""
    if classify is None or not any(boards.values()):
        return boards
    from discover.registry import _name_from_slug
    from scrape.company_registry import CompanyEntry
    stubs = [CompanyEntry(_name_from_slug(a, s), a, s, [])
             for a, slugs in boards.items() for s in slugs]
    kept = classify(stubs) or set()
    out = {a: {s for s in slugs if (a, s) in kept} for a, slugs in boards.items()}
    return {a: s for a, s in out.items() if s}


def run_funnel(*, ats_hosts=None, domains=None, companies_json_path=None,
               crawl_id=None, limit=None, classify=None, host_level=False,
               enterprise=False, max_pages=None) -> dict:
    """Run the funnel and merge what it finds into companies.json.

    ats_hosts: ATS apex hosts to CDX-harvest (None = the common ATS hosts; pass
               [] to skip the CDX leg entirely).
    domains:   company domains to resolve careers-URL -> ATS board (optional).
    classify:  optional P3 relevance gate (callable(entries) -> kept set); only
               filters when an industry is being seeded, keep-all otherwise.
    host_level: use the registered-domain host-level harvest (plan P6 — spans all
               subdomains/tenants, paginated to max_pages) instead of per-host CDX.
    enterprise: also harvest the enterprise ATS domains (Workday/iCIMS/Taleo/SF).
               Implies the host-level path (a per-URL prefix can't span tenants).
    Returns {"harvested": {ats_type: count}, "added": n_added}.
    """
    boards: dict[str, set] = {}
    hosts = list(_DEFAULT_ATS_HOSTS if ats_hosts is None else ats_hosts)
    if enterprise:
        host_level = True
        hosts += [h for h in _ENTERPRISE_ATS_HOSTS if h not in hosts]
    if hosts:
        if host_level:
            _merge_boards(boards, cc_harvest.harvest_host_index(
                hosts, crawl_id=crawl_id, limit=limit, max_pages=max_pages))
        else:
            _merge_boards(boards, cc_harvest.harvest_slugs(
                hosts, crawl_id=crawl_id, limit=limit))
    if domains:
        _merge_boards(boards, harvest_from_domains(domains))
    boards = _apply_classify(boards, classify)
    added = merge_discovered(boards, companies_json_path)
    return {"harvested": {k: len(v) for k, v in boards.items()}, "added": added}
