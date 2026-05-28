from pathlib import Path
from urllib.parse import urlparse

import requests

from config import BRAVE_SEARCH_API_KEY, BRAVE_SEARCH_URL, CAREERS_REQUEST_TIMEOUT
from scrape.cache_helpers import read_cache, slug_safe, write_cache
from scrape.company_registry import CompanyEntry

_ATS_SITES = {
    "greenhouse": "boards.greenhouse.io",
    "lever":      "jobs.lever.co",
}


def discover_companies(
    keyword: str,
    cache_dir: Path,
    cache_enabled: bool,
    known_slugs: set[str],
) -> list[CompanyEntry]:
    if not BRAVE_SEARCH_API_KEY:
        return []

    discovered: list[CompanyEntry] = []

    for ats_type, site in _ATS_SITES.items():
        query = f'site:{site} "{keyword}"'
        cache_file = cache_dir / f"brave_{ats_type}_{slug_safe(keyword)}.json"

        if cache_enabled:
            data = read_cache(cache_file)
        else:
            data = None

        if data is None:
            data = _brave_fetch(query)
            if data and cache_enabled:
                write_cache(cache_file, data)
            if not data:
                continue

        slugs = _extract_slugs(data, site)
        for slug in slugs:
            if slug not in known_slugs:
                discovered.append(CompanyEntry(
                    name=slug.replace("-", " ").title(),
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
    try:
        resp = requests.get(
            BRAVE_SEARCH_URL,
            params={"q": query, "count": 20},
            headers=headers,
            timeout=CAREERS_REQUEST_TIMEOUT,
        )
        if resp.status_code == 401:
            print("  [discover] Brave Search: invalid API key — check BRAVE_SEARCH_API_KEY in .env")
            return None
        if resp.status_code == 429:
            print("  [discover] Brave Search: rate limit hit — discovery skipped")
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  [discover] Brave Search request failed - {e}")
        return None


def _extract_slugs(data: dict, site: str) -> list[str]:
    slugs: list[str] = []
    seen: set[str] = set()
    for result in data.get("web", {}).get("results", []):
        url = result.get("url", "")
        slug = _slug_from_url(url, site)
        if slug and slug not in seen:
            seen.add(slug)
            slugs.append(slug)
    return slugs


def _slug_from_url(url: str, site: str) -> str:
    if site not in url:
        return ""
    try:
        path = urlparse(url).path.strip("/")
        parts = path.split("/")
        if parts and parts[0]:
            return parts[0]
    except Exception:
        pass
    return ""
