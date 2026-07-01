"""Common Crawl CDX -> ATS slugs per host (the generic denominator winner,
spec §5.1). Bounded + cached: a full harvest runs occasionally, not per search.
Loud on unreachability — never returns empty silently when a host blew up.
"""
from __future__ import annotations
import json

from discover.detect import detect_ats
from search.http_util import make_session

_CDX_INDEX = "https://index.commoncrawl.org/CC-MAIN-2025-05-index"


def _cdx_fetch(host: str, crawl_id: str | None, limit: int | None) -> list:
    """Return CDX NDJSON lines for `host`. Isolated so tests mock it."""
    index = f"https://index.commoncrawl.org/CC-MAIN-{crawl_id}-index" if crawl_id else _CDX_INDEX
    session = make_session()
    params = {"url": f"{host}/*", "output": "json"}
    if limit:
        params["limit"] = str(limit)
    resp = session.get(index, params=params, timeout=30)
    resp.raise_for_status()
    return [ln for ln in resp.text.splitlines() if ln.strip()]


def _boards_from_lines(lines, out: dict[str, set]) -> None:
    """Fold CDX NDJSON lines into {ats_type: {slug}} via detect_ats."""
    for line in lines:
        try:
            url = json.loads(line).get("url", "")
        except (ValueError, TypeError):
            continue
        det = detect_ats(url)
        if det is None:
            continue
        ats_type, slug = det
        out.setdefault(ats_type, set()).add(slug)


def harvest_slugs(ats_hosts: list, *, crawl_id: str | None = None,
                  limit: int | None = None) -> dict[str, set]:
    """{ats_type: {slug,...}} harvested from Common Crawl for each host."""
    if not ats_hosts:
        return {}
    out: dict[str, set] = {}
    reachable = 0
    for host in ats_hosts:
        try:
            lines = _cdx_fetch(host, crawl_id, limit)
            reachable += 1
        except Exception as e:
            print(f"  [cc_harvest] WARNING: {host} unreachable — {e}")
            continue
        _boards_from_lines(lines, out)
    if reachable == 0:
        print("  [cc_harvest] WARNING: no ATS hosts reachable — discovery degraded; "
              "falling back to existing registry (spec §7).")
        return {}
    return out


# ── Host-level harvest (plan P6) ─────────────────────────────────────────────
# The per-host `host/*` CDX prefix above only sees ONE host. A registered-domain
# query (matchType=domain) captures the host AND every subdomain/tenant under it
# — e.g. one query on `myworkdayjobs.com` reaches every `<tenant>.wdN.myworkday
# jobs.com` board. Paginating past the default cap is the real completeness lever.
# It is also more robust to the occasional per-host CDX 400 (the ashby quirk).

def _cdx_fetch_host(host: str, crawl_id: str | None, limit: int | None, *,
                    page: int | None = None, page_size: int | None = None) -> list:
    """CDX NDJSON for a whole registered DOMAIN (matchType=domain). Isolated so
    tests mock it; one page per call (paginate via `page`)."""
    index = f"https://index.commoncrawl.org/CC-MAIN-{crawl_id}-index" if crawl_id else _CDX_INDEX
    session = make_session()
    params = {"url": host, "matchType": "domain", "output": "json"}
    if limit:
        params["limit"] = str(limit)
    if page is not None:
        params["page"] = str(page)
    if page_size is not None:
        params["pageSize"] = str(page_size)
    resp = session.get(index, params=params, timeout=30)
    resp.raise_for_status()
    return [ln for ln in resp.text.splitlines() if ln.strip()]


def _cdx_num_pages(host: str, crawl_id: str | None, page_size: int | None) -> int:
    """How many CDX pages the domain query spans (showNumPages=true)."""
    index = f"https://index.commoncrawl.org/CC-MAIN-{crawl_id}-index" if crawl_id else _CDX_INDEX
    session = make_session()
    params = {"url": host, "matchType": "domain", "output": "json", "showNumPages": "true"}
    if page_size is not None:
        params["pageSize"] = str(page_size)
    resp = session.get(index, params=params, timeout=30)
    resp.raise_for_status()
    text = resp.text.strip()
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return int(payload.get("pages", 1))
        return int(payload)
    except (ValueError, TypeError):
        return 1


def harvest_host_index(hosts: list, *, crawl_id: str | None = None,
                       limit: int | None = None, max_pages: int | None = None,
                       page_size: int | None = None,
                       fetch=None, num_pages=None) -> dict[str, set]:
    """Host-LEVEL harvest: registered-domain CDX query (all subdomains/tenants),
    paginated to `max_pages`. Same {ats_type:{slug}} shape + loud-on-unreachable
    contract as harvest_slugs; `fetch`/`num_pages` injectable for tests."""
    if not hosts:
        return {}
    fetch = fetch or _cdx_fetch_host
    count_pages = num_pages or _cdx_num_pages
    out: dict[str, set] = {}
    reachable = 0
    for host in hosts:
        pages = 1
        if max_pages is not None and max_pages > 1:
            try:
                pages = min(max_pages, max(1, count_pages(host, crawl_id, page_size)))
            except Exception:
                pages = 1
        # First page decides reachability; a LATER page failing must NOT discard
        # the pages already harvested (or mislabel a reachable host as unreachable).
        try:
            lines = fetch(host, crawl_id, limit,
                          page=(0 if pages > 1 else None), page_size=page_size)
            _boards_from_lines(lines, out)
            reachable += 1
        except Exception as e:
            print(f"  [cc_harvest] WARNING: {host} unreachable — {e}")
            continue
        for pg in range(1, pages):
            try:
                lines = fetch(host, crawl_id, limit, page=pg, page_size=page_size)
                _boards_from_lines(lines, out)
            except Exception as e:
                print(f"  [cc_harvest] WARNING: {host} page {pg} failed — {e}; "
                      "keeping earlier pages")
                break
    if reachable == 0:
        print("  [cc_harvest] WARNING: no ATS hosts reachable (host-level) — "
              "discovery degraded; falling back to existing registry (spec §7).")
        return {}
    return out
