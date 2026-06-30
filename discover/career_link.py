"""Company domain -> careers URL (spec §5.1).

robots.txt (harvest Sitemap:) -> sitemap.xml (filter job-ish locs) ->
homepage careers-anchor regex (one-hop). All HTTP behind _get() so tests mock
one seam. Fail-soft: every step returns None/[] on error, never raises.
"""
from __future__ import annotations
import ipaddress
import re
import socket
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from search.http_util import make_session
from scrape.xml_safe import _safe_fromstring   # XXE/billion-laughs-safe sitemap parse

_JOB_RE = re.compile(r"job|career|position|opening|vacanc", re.I)
_HEADERS = {"User-Agent": "JobSearchTool/1.0 (personal use)"}


def _url_ok(url: str) -> bool:
    """SSRF guard for LLM/user-supplied domains: only http(s), and reject any URL
    whose host resolves to a loopback/private/link-local/reserved/multicast IP."""
    try:
        p = urlsplit(url)
    except Exception:
        return False
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    try:
        infos = socket.getaddrinfo(p.hostname, None)
    except Exception:
        return False
    for info in infos:
        try:
            addr = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
            return False
    return True


def _get(url: str) -> str | None:
    if not _url_ok(url):
        return None
    try:
        resp = make_session().get(url, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
        # Re-check after redirects so a public host can't bounce us to an internal IP.
        if not _url_ok(resp.url):
            return None
        return resp.text
    except Exception:
        return None


def _origin(domain: str) -> str:
    d = (domain or "").strip()
    if not d:
        return ""
    if "://" not in d:
        d = "https://" + d
    parts = urlsplit(d)
    return f"{parts.scheme}://{parts.netloc}"


def _sitemap_urls_from_robots(origin: str) -> list[str]:
    txt = _get(f"{origin}/robots.txt")
    if not txt:
        return []
    return [line.split(":", 1)[1].strip()
            for line in txt.splitlines()
            if line.lower().startswith("sitemap:")]


def sitemap_job_urls(domain: str) -> list:
    origin = _origin(domain)
    if not origin:
        return []
    candidates = _sitemap_urls_from_robots(origin) or [f"{origin}/sitemap.xml"]
    found: list[str] = []
    for sm in candidates:
        xml = _get(sm)
        if not xml:
            continue
        try:
            root = _safe_fromstring(xml)
        except Exception:
            continue
        for loc in root.iter():
            if loc.tag.endswith("loc") and loc.text and _JOB_RE.search(loc.text):
                found.append(loc.text.strip())
    # dedupe, preserve order
    seen: set[str] = set()
    return [u for u in found if not (u in seen or seen.add(u))]


def find_career_url(domain: str) -> str | None:
    origin = _origin(domain)
    if not origin:
        return None
    job_urls = sitemap_job_urls(domain)
    if job_urls:
        return job_urls[0]
    html = _get(origin) or _get(f"{origin}/")
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)
        if _JOB_RE.search(href) or _JOB_RE.search(text):
            return urljoin(origin + "/", href)
    return None
