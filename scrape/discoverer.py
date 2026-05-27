import time
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import requests
from bs4 import BeautifulSoup

from config import CAREERS_DDG_SLEEP_SECONDS, CAREERS_REQUEST_TIMEOUT
from scrape.cache_helpers import read_cache, slug_safe, write_cache
from scrape.company_registry import CompanyEntry

_DDG_URL = "https://html.duckduckgo.com/html/"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
_ATS_SITES = {
    "greenhouse": "boards.greenhouse.io",
    "lever": "jobs.lever.co",
}


def discover_companies(
    keyword: str,
    cache_dir: Path,
    cache_enabled: bool,
    known_slugs: set[str],
) -> list[CompanyEntry]:
    discovered: list[CompanyEntry] = []

    for ats_type, site in _ATS_SITES.items():
        query = f'site:{site} "{keyword}"'
        cache_file = cache_dir / f"ddg_{ats_type}_{slug_safe(keyword)}.html"

        if cache_enabled:
            html = read_cache(cache_file)
        else:
            html = None

        if html is None:
            html = _ddg_fetch(query)
            if html and cache_enabled:
                write_cache(cache_file, html)
            if not html:
                continue
            time.sleep(CAREERS_DDG_SLEEP_SECONDS)

        slugs = _extract_slugs(html, site)
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


def _ddg_fetch(query: str) -> str:
    try:
        resp = requests.post(
            _DDG_URL,
            data={"q": query},
            headers=_HEADERS,
            timeout=CAREERS_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        html = resp.text
        # DDG returns a bot-challenge page when rate-limiting; detect and bail cleanly
        if "anomaly.js" in html or "cc=botnet" in html:
            print("  [discover] DuckDuckGo bot challenge — discovery skipped (try again later)")
            return ""
        return html
    except Exception as e:
        print(f"  [discover] DuckDuckGo request failed — {e}")
        return ""


def _extract_slugs(html: str, site: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    slugs: list[str] = []
    seen: set[str] = set()

    for a in soup.select("a.result__a, a.result__url"):
        href = a.get("href", "") or a.get_text(strip=True)
        slug = _slug_from_href(href, site)
        if slug and slug not in seen:
            seen.add(slug)
            slugs.append(slug)

    return slugs


def _slug_from_href(href: str, site: str) -> str:
    if site not in href:
        return ""
    try:
        path = urlparse(href).path.strip("/")
        parts = path.split("/")
        if parts:
            return parts[0]
    except Exception:
        pass
    return ""
