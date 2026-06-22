import html
import re

import requests

from config import CAREERS_REQUEST_TIMEOUT
from models import JobResult

_BASE_URL = "https://{slug}.recruitee.com/api/offers/"
_TAG_RE = re.compile(r"<[^>]+>")
_HEADERS = {"Accept": "application/json", "User-Agent": "JobSearchTool/1.0 (personal use)"}


def _clean(raw: str) -> str:
    if not raw:
        return ""
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", html.unescape(raw))).strip()[:3000]


def fetch(slug: str, *, keyword: str = "") -> list[JobResult]:
    try:
        resp = requests.get(_BASE_URL.format(slug=slug), headers=_HEADERS,
                            timeout=CAREERS_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [recruitee] {slug}: error — {e}")
        return []
    offers = data.get("offers", []) or []
    out: list[JobResult] = []
    for o in offers:
        title = o.get("title", "") or ""
        body = _clean(o.get("description", ""))
        if keyword:
            from scrape.text_match import keyword_matches_deep
            if not keyword_matches_deep(keyword, title, body):
                continue
        loc = ", ".join(p for p in (o.get("city"), o.get("country")) if p)
        out.append(JobResult(
            title=title,
            company=o.get("company_name") or slug.replace("-", " ").title(),
            location=loc,
            salary_min=None,
            salary_max=None,
            description=body,
            url=o.get("careers_url") or "",
            source_keyword="",
            created=o.get("published_at") or "",
            job_id=f"recruitee_{o.get('id', '')}",
            source_api="careers",
            board_count=len(offers),
        ))
    return out
