import html
import re
import xml.etree.ElementTree as ET

import requests

from config import CAREERS_REQUEST_TIMEOUT
from models import JobResult
from scrape.xml_safe import _safe_fromstring

_BASE_URL = "https://{slug}.jobs.personio.de/xml"
_TAG_RE = re.compile(r"<[^>]+>")
_HEADERS = {"Accept": "application/xml", "User-Agent": "JobSearchTool/1.0 (personal use)"}


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


def fetch(slug: str, *, keyword: str = "") -> list[JobResult]:
    try:
        resp = requests.get(_BASE_URL.format(slug=slug), headers=_HEADERS,
                            timeout=CAREERS_REQUEST_TIMEOUT)
        resp.raise_for_status()
        root = _safe_fromstring(resp.content)   # XXE/billion-laughs-safe (Task 2a.0)
    except Exception as e:
        print(f"  [personio] {slug}: error — {e}")
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
