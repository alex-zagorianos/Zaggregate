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
    if reachable == 0:
        print("  [cc_harvest] WARNING: no ATS hosts reachable — discovery degraded; "
              "falling back to existing registry (spec §7).")
        return {}
    return out
