from pathlib import Path

import requests

from config import (
    BRAVE_SEARCH_API_KEY, BRAVE_SEARCH_URL, CAREERS_REQUEST_TIMEOUT,
    DISCOVERY_CACHE_TTL_HOURS,
)
from scrape.cache_helpers import read_cache, slug_safe, write_cache
from scrape.company_registry import CompanyEntry

# Process-local, run-scoped memo of (ats_label, keyword) -> the Brave payload
# already fetched/read this run. discover_companies() is called once per
# keyword by CareersClient.search_and_parse, so this only pays off when a
# keyword repeats within the same process (an identical --add-keyword, a
# re-run search, or a future caller that queries the same keyword twice) --
# but it's a free, correctness-safe win either way: same cache-hit data,
# just without the repeat disk read (S35 #25). NOT persisted across runs;
# the on-disk cache (DISCOVERY_CACHE_TTL_HOURS) is what saves the network call.
_RUN_QUERY_MEMO: dict[tuple[str, str], dict | None] = {}


def reset_run_memo() -> None:
    """Clear the in-run query memo. Call at the start of a run so a stale
    result from a previous in-process run/test isn't reused."""
    _RUN_QUERY_MEMO.clear()

# Public-board host for each ATS we can discover via Brave site: search. The
# key is the brave-cache label; the value is the host passed to `site:`. Ashby,
# SmartRecruiters and Workday were added so discovery is no longer blind to the
# three newer scrapers (was Greenhouse/Lever only). Workday boards live on
# per-tenant subdomains, so we target the shared apex and let detect_ats pull
# the tenant:N:site slug out of each result URL.
_ATS_SITES = {
    "greenhouse":      "boards.greenhouse.io",
    "lever":           "jobs.lever.co",
    "ashby":           "jobs.ashbyhq.com",
    "smartrecruiters": "jobs.smartrecruiters.com",
    "workday":         "myworkdayjobs.com",
}
# NOTE: bamboohr/rippling are intentionally NOT auto-discovered here. Adding them
# would make an existing BRAVE_SEARCH_API_KEY user's daily 'careers' run start
# finding+scraping+persisting new boards with no companies.json entry — i.e. a
# behavior change against the "inert until a registry entry exists" / byte-identical
# invariant. They ARE still detected for pasted URLs + inbox-harvest (ats_detect.py,
# discover/detect.py), which is the intended reach path.


def discover_companies(
    keyword: str,
    cache_dir: Path,
    cache_enabled: bool,
    known_slugs: set[str],
) -> list[CompanyEntry]:
    if not BRAVE_SEARCH_API_KEY:
        # Once per run, not per keyword (S32/L7).
        import applog
        applog.warn_once(
            "  [discover] WARNING: BRAVE_SEARCH_API_KEY unset — Brave company "
            "discovery skipped; relying on the existing registry only (spec §7).",
            key="discover:no-brave-key")
        return []

    discovered: list[CompanyEntry] = []

    for ats_label, site in _ATS_SITES.items():
        query = f'site:{site} "{keyword}"'
        memo_key = (ats_label, keyword)
        cache_file = cache_dir / f"brave_{ats_label}_{slug_safe(keyword)}.json"

        # In-run memo first: the SAME (ats_site, keyword) pair queried twice in
        # one process (e.g. an --add-keyword duplicate, a re-run search) reuses
        # whatever this run already fetched/read, with zero extra disk I/O and
        # no possibility of a different answer mid-run (S35 #25).
        if memo_key in _RUN_QUERY_MEMO:
            data = _RUN_QUERY_MEMO[memo_key]
        else:
            if cache_enabled:
                # Discovery gets its own, much longer TTL than the generic
                # CACHE_TTL_HOURS (24h): new boards appearing on a fixed ATS
                # site for a fixed keyword don't change hour-to-hour, so a
                # 24h TTL just re-fired a live Brave call on essentially every
                # scheduled daily run (S35 #25).
                data = read_cache(cache_file, ttl_hours=DISCOVERY_CACHE_TTL_HOURS)
            else:
                data = None

            if data is None:
                data = _brave_fetch(query)
                if data and cache_enabled:
                    write_cache(cache_file, data)
            _RUN_QUERY_MEMO[memo_key] = data

        if not data:
            continue

        for ats_type, slug, name in _extract_entries(data, site):
            if slug not in known_slugs:
                discovered.append(CompanyEntry(
                    name=name,
                    ats_type=ats_type,
                    slug=slug,
                    industries=[],
                ))
                known_slugs.add(slug)

    return discovered


def _brave_fetch(query: str) -> dict | None:
    headers = {
        "Accept":               "application/json",
        "Accept-Encoding":      "gzip",
        "X-Subscription-Token": BRAVE_SEARCH_API_KEY,
    }
    # Every failure branch below used to be a bare print() to a console the
    # frozen exe discards, with no persisted signal and no run-scoped dedup --
    # unlike the "no key at all" case in discover_companies() (S32/L7). This is
    # a DISTINCT, plausible failure mode (a previously-working key that expires
    # or gets rate-limited) that silently and permanently stops the registry
    # from growing with no visible signal (S35 #22). Routed through the same
    # applog.warn_once() run-scoped dedup so it logs ONCE per run (not once per
    # ats_site/keyword pair -- _brave_fetch is called up to 5x per keyword).
    import applog
    try:
        resp = requests.get(
            BRAVE_SEARCH_URL,
            params={"q": query, "count": 20},
            headers=headers,
            timeout=CAREERS_REQUEST_TIMEOUT,
        )
        if resp.status_code == 401:
            applog.warn_once(
                "  [discover] WARNING: Brave Search key rejected (401 invalid "
                "API key) — check BRAVE_SEARCH_API_KEY in .env; company "
                "discovery is contributing nothing this run.",
                key="discover:brave-401")
            return None
        if resp.status_code == 429:
            applog.warn_once(
                "  [discover] WARNING: Brave Search rate limit hit (429) — "
                "company discovery skipped for the rest of this run.",
                key="discover:brave-429")
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        applog.warn_once(
            f"  [discover] WARNING: Brave Search request failed — {e}; "
            "company discovery is contributing nothing this run.",
            key="discover:brave-exception")
        return None


def _extract_entries(data: dict, site: str) -> list[tuple[str, str, str]]:
    """Yield (ats_type, slug, name) for each result URL on `site`. Uses the
    shared detect_ats parser so every ATS (incl. Workday's tenant:N:site slug
    and Ashby subdomain boards) is recognized, not just path-first slugs."""
    from scrape.ats_detect import detect_ats

    entries: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for result in data.get("web", {}).get("results", []):
        url = result.get("url", "")
        if not url or site not in url:
            continue
        ats_type, slug = detect_ats(url)
        # detect_ats falls back to 'direct' for anything it can't classify; a
        # discovered company we can't actually scrape via an API is noise here.
        if ats_type == "direct" or not slug or slug in seen:
            continue
        seen.add(slug)
        entries.append((ats_type, slug, _name_from_slug(ats_type, slug)))
    return entries


def _name_from_slug(ats_type: str, slug: str) -> str:
    # Workday slug is 'tenant:N:site' — derive the display name from the tenant.
    core = slug.split(":")[0] if ats_type in ("workday", "workday_cxs") else slug
    return core.replace("-", " ").replace("_", " ").title()
