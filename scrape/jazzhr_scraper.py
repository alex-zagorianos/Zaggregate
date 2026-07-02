"""JazzHR careers scraper (applytojob.com XML feed, list style).

**PROVISIONAL** — the parser shape is DOC-DERIVED, not live-captured. JazzHR's
public XML job feed is documented (JazzHR "Integrate with Your Career Page /
Advanced Methods") as a `<jobs>` root of `<job>` elements carrying <id>,
<title>, <department>, <city>, <state>, <country>, <description>, <url>. As of
2026-07-01 the feed endpoint on the tenants tried (`/apply/jobs/feed`) 302'd or
404'd without exposing a public feed, so this scraper could NOT be validated
against a real board. The endpoint + field mapping below follow the docs; treat
field names as best-effort until a live board confirms them. A wrong endpoint
simply fails-soft to [] (no false data).

Endpoint (documented):
    GET https://{slug}.applytojob.com/apply/jobs/feed  ->  <jobs><job>...</job></jobs>

`slug` is the tenant subdomain (the applytojob.com prefix).

XML parsed via scrape.xml_safe (XXE/billion-laughs-safe). Routed through
careers_session + per-host limiter + conditional_get; fail-soft -> [].
"""
import html
import re
from pathlib import Path
from typing import Optional

from config import CACHE_DIR, CAREERS_REQUEST_TIMEOUT
from models import JobResult
from scrape.cache_helpers import (
    STATUS_PERMANENT, conditional_get, http_cache_body, is_failed, mark_failed,
    read_cache, slug_safe,
)
from scrape.xml_safe import _safe_fromstring
from search.http_util import careers_host_limiter, careers_session, host_of

_BASE_URL = "https://{slug}.applytojob.com/apply/jobs/feed"
_HEADERS = {"Accept": "application/xml, text/xml",
            "User-Agent": "JobSearchTool/1.0 (personal use)"}
_TAG_RE = re.compile(r"<[^>]+>")


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _clean(raw: str) -> str:
    if not raw:
        return ""
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", html.unescape(raw))).strip()[:3000]


def _parse_xml_text(resp) -> str:
    text = resp.text
    _safe_fromstring(text.encode("utf-8"))
    return text


def fetch(slug: str, *, keyword: str = "", cache_dir: Optional[Path] = None,
          cache_enabled: bool = False) -> list[JobResult]:
    url = _BASE_URL.format(slug=slug)
    cache_file = ((cache_dir or CACHE_DIR) / f"jazzhr_{slug_safe(slug)}.json"
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
            print(f"  [jazzhr] {slug}: gone — skipping")
            mark_failed(cache_file)
            return []
        if result.body is None:
            print(f"  [jazzhr] {slug}: throttled/unreachable — skipping (not marked dead)")
            return []
        return _map(result.body, slug, keyword)

    careers_host_limiter(host_of(url)).acquire()
    try:
        resp = careers_session().get(url, headers=_HEADERS,
                                     timeout=CAREERS_REQUEST_TIMEOUT)
        resp.raise_for_status()
        xml_text = resp.text
    except Exception as e:
        print(f"  [jazzhr] {slug}: error — {e}")
        return []
    return _map(xml_text, slug, keyword)


def _map(xml_text: str, slug: str, keyword: str) -> list[JobResult]:
    if not isinstance(xml_text, str):
        return []
    try:
        root = _safe_fromstring(xml_text.encode("utf-8"))
    except Exception as e:
        print(f"  [jazzhr] {slug}: parse error — {e}")
        return []
    jobs = [el for el in root.iter() if _localname(el.tag) == "job"]
    out: list[JobResult] = []
    for job in jobs:
        fields: dict[str, str] = {}
        for child in job:
            name = _localname(child.tag)
            if name not in fields:
                fields[name] = (child.text or "").strip()
        title = fields.get("title", "")
        desc = _clean(fields.get("description", ""))
        dept = fields.get("department", "")
        if dept:
            desc = (desc + " " + dept).strip()
        if keyword:
            from scrape.text_match import keyword_matches_deep
            if not keyword_matches_deep(keyword, title, desc):
                continue
        loc = ", ".join(p for p in (fields.get("city", ""), fields.get("state", "")) if p)
        if not loc:
            loc = fields.get("country", "") or fields.get("location", "")
        jid = fields.get("id", "") or fields.get("internalcode", "")
        out.append(JobResult(
            title=title,
            company=slug.replace("-", " ").title(),
            location=loc,
            salary_min=None,
            salary_max=None,
            description=desc,
            url=fields.get("url", ""),
            source_keyword="",
            created=fields.get("createdon", "") or fields.get("posteddate", ""),
            job_id=f"jazzhr_{jid}",
            source_api="careers",
            board_count=len(jobs),
        ))
    return out
