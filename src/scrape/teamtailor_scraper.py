"""Teamtailor careers scraper (public jobs.rss, XML/RSS list style).

Endpoint (public RSS feed, no auth):
    GET https://{slug}.teamtailor.com/jobs.rss  ->  RSS 2.0 <channel><item>...

`slug` is the tenant subdomain. Feed shape (validated live 2026-07-01 against a
real Teamtailor board): standard RSS <item> elements with <title>, <link>,
<description> (HTML-escaped body), <pubDate>, <guid>; Teamtailor also emits
namespaced <tt:location>/<tt:department>-style tags whose plain-tag localname is
read defensively.

XML is parsed via scrape.xml_safe (XXE/billion-laughs-safe, like personio).
Routed through careers_session + per-host limiter + conditional_get; fail-soft -> [].
"""
from pathlib import Path
from typing import Optional

from config import CACHE_DIR, CAREERS_REQUEST_TIMEOUT
from models import JobResult
from scrape.cache_helpers import (
    STATUS_PERMANENT, conditional_get, http_cache_body, is_failed, mark_failed,
    read_cache, slug_safe,
)
from scrape.html_text import strip_html_to_text
from scrape.xml_safe import _safe_fromstring
from scrape._log import diag
from search.http_util import careers_host_limiter, careers_session, host_of

_BASE_URL = "https://{slug}.teamtailor.com/jobs.rss"
_HEADERS = {"Accept": "application/rss+xml, application/xml",
            "User-Agent": "JobSearchTool/1.0 (personal use)"}


def _localname(tag: str) -> str:
    """Strip any XML namespace so '{ns}location' -> 'location'."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _clean(raw: str) -> str:
    return strip_html_to_text(raw)


def _nested_location(item) -> str:
    """First location from Teamtailor's nested <tt:locations><tt:location>
    structure: prefer a <name>, else assemble city/country-ish name/address
    fragments. Returns '' if no nested location is present."""
    for el in item.iter():
        if _localname(el.tag) != "location":
            continue
        name = ""
        parts: list[str] = []
        for sub in el.iter():
            ln = _localname(sub.tag)
            txt = (sub.text or "").strip()
            if not txt:
                continue
            if ln == "name" and not name:
                name = txt
            elif ln in ("city", "country", "address", "region"):
                parts.append(txt)
        if name:
            return name
        if parts:
            return ", ".join(parts)
    return ""


def _parse_xml_text(resp) -> str:
    """Validate + return the raw RSS body as text (safe-parse to reject
    malformed/unsafe XML so conditional_get treats a broken feed as permanent)."""
    text = resp.text
    _safe_fromstring(text.encode("utf-8"))
    return text


def fetch(slug: str, *, keyword: str = "", cache_dir: Optional[Path] = None,
          cache_enabled: bool = False) -> list[JobResult]:
    url = _BASE_URL.format(slug=slug)
    cache_file = ((cache_dir or CACHE_DIR) / f"teamtailor_{slug_safe(slug)}.json"
                  if cache_enabled else None)

    if cache_enabled and cache_file is not None:
        cached = read_cache(cache_file)
        if is_failed(cached):
            return []
        if cached is not None:
            return _map(http_cache_body(cached), slug, keyword)

        careers_host_limiter(host_of(url)).acquire()
        result = conditional_get(url, cache_file, headers=_HEADERS,
                                 timeout=CAREERS_REQUEST_TIMEOUT,
                                 session=careers_session(), parse=_parse_xml_text)
        if result.status == STATUS_PERMANENT:
            diag(f"  [teamtailor] {slug}: gone — skipping")
            mark_failed(cache_file)
            return []
        if result.body is None:
            diag(f"  [teamtailor] {slug}: throttled/unreachable — skipping (not marked dead)")
            return []
        return _map(result.body, slug, keyword)

    careers_host_limiter(host_of(url)).acquire()
    try:
        resp = careers_session().get(url, headers=_HEADERS,
                                     timeout=CAREERS_REQUEST_TIMEOUT)
        resp.raise_for_status()
        xml_text = resp.text
    except Exception as e:
        diag(f"  [teamtailor] {slug}: error — {e}")
        return []
    return _map(xml_text, slug, keyword)


def _map(xml_text: str, slug: str, keyword: str) -> list[JobResult]:
    if not isinstance(xml_text, str):
        return []
    try:
        root = _safe_fromstring(xml_text.encode("utf-8"))
    except Exception as e:
        diag(f"  [teamtailor] {slug}: parse error — {e}")
        return []
    items = [el for el in root.iter() if _localname(el.tag) == "item"]
    out: list[JobResult] = []
    for item in items:
        fields: dict[str, str] = {}
        for child in item:
            name = _localname(child.tag)
            # First-wins for duplicate localnames (namespaced + plain).
            if name not in fields:
                fields[name] = (child.text or "").strip()
        title = fields.get("title", "")
        desc = _clean(fields.get("description", ""))
        dept = fields.get("department", "")
        if dept:
            desc = (desc + " " + dept).strip()
        # Teamtailor nests location under <tt:locations><tt:location><tt:name>.
        # Read a flat <location> if present, else the first nested location name.
        location = fields.get("location", "") or _nested_location(item)
        if keyword:
            from scrape.text_match import keyword_matches_deep
            if not keyword_matches_deep(keyword, title, desc):
                continue
        job_url = fields.get("link", "") or fields.get("guid", "")
        jid = fields.get("guid", "") or job_url
        out.append(JobResult(
            title=title,
            company=slug.replace("-", " ").title(),
            location=location,
            salary_min=None,
            salary_max=None,
            description=desc,
            url=job_url,
            source_keyword="",
            created=fields.get("pubDate", ""),
            job_id=f"teamtailor_{slug_safe(jid)}" if jid else "teamtailor_",
            source_api="careers",
            board_count=len(items),
        ))
    return out
