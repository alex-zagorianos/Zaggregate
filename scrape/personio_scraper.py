import html
import re
import xml.etree.ElementTree as ET
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

_BASE_URL = "https://{slug}.jobs.personio.de/xml"
_TAG_RE = re.compile(r"<[^>]+>")
_HEADERS = {"Accept": "application/xml", "User-Agent": "JobSearchTool/1.0 (personal use)"}


def _parse_xml_text(resp) -> str:
    """Validate + return the raw XML body as text so it can be cached as a plain
    string. Parsing (billion-laughs/XXE-safe) happens here so a malformed body
    is treated as a permanent (broken-board) failure by conditional_get, not
    cached. The returned string is re-parsed by the caller with the same safe
    parser."""
    text = resp.text
    _safe_fromstring(text.encode("utf-8"))  # raises on malformed/unsafe XML
    return text


def _clean(raw: str) -> str:
    if not raw:
        return ""
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", html.unescape(raw))).strip()[:3000]


def _descr(pos: ET.Element) -> str:
    parts = []
    for jd in pos.iter():
        if jd.tag == "value" and jd.text:
            parts.append(jd.text)
    return _clean(" ".join(parts))


def fetch(slug: str, *, keyword: str = "", cache_dir: Optional[Path] = None,
          cache_enabled: bool = False) -> list[JobResult]:
    url = _BASE_URL.format(slug=slug)
    cache_file = ((cache_dir or CACHE_DIR) / f"personio_{slug_safe(slug)}.json"
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
            print(f"  [personio] {slug}: gone — skipping")
            mark_failed(cache_file)
            return []
        if result.body is None:
            print(f"  [personio] {slug}: throttled/unreachable — skipping (not marked dead)")
            return []
        return _map(result.body, slug, keyword)

    careers_host_limiter(host_of(url)).acquire()
    try:
        resp = careers_session().get(url, headers=_HEADERS,
                                     timeout=CAREERS_REQUEST_TIMEOUT)
        resp.raise_for_status()
        xml_text = resp.text
    except Exception as e:
        print(f"  [personio] {slug}: error — {e}")
        return []
    return _map(xml_text, slug, keyword)


def _map(xml_text: str, slug: str, keyword: str) -> list[JobResult]:
    try:
        root = _safe_fromstring(xml_text.encode("utf-8"))  # XXE/billion-laughs-safe
    except Exception as e:
        print(f"  [personio] {slug}: parse error — {e}")
        return []
    positions = [el for el in root.iter() if el.tag == "position"]
    out: list[JobResult] = []
    for pos in positions:
        def _text(tag):
            el = pos.find(tag)
            return (el.text or "").strip() if el is not None and el.text else ""
        title = _text("name")
        desc = _descr(pos)
        if keyword:
            from scrape.text_match import keyword_matches_deep
            if not keyword_matches_deep(keyword, title, desc):
                continue
        out.append(JobResult(
            title=title,
            company=slug.replace("-", " ").title(),
            location=_text("office"),
            salary_min=None,
            salary_max=None,
            description=desc,
            url=f"https://{slug}.jobs.personio.de/job/{_text('id')}" if _text("id") else "",
            source_keyword="",
            created=_text("createdAt"),
            job_id=f"personio_{_text('id')}",
            source_api="careers",
            board_count=len(positions),
        ))
    return out
