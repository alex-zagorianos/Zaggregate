import html
import re
from typing import Optional

import requests

from config import CAREERS_REQUEST_TIMEOUT
from models import JobResult

_BASE_URL = "https://apply.workable.com/api/v1/widget/accounts/{slug}"
_TAG_RE = re.compile(r"<[^>]+>")
_HEADERS = {"Accept": "application/json", "User-Agent": "JobSearchTool/1.0 (personal use)"}


def _clean(raw: str) -> str:
    if not raw:
        return ""
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", html.unescape(raw))).strip()[:3000]


def _location(loc: dict) -> str:
    parts = [loc.get("city"), loc.get("region"), loc.get("country")]
    return ", ".join(p for p in parts if p)


def fetch(slug: str, *, keyword: str = "") -> list[JobResult]:
    try:
        resp = requests.get(_BASE_URL.format(slug=slug), headers=_HEADERS,
                            timeout=CAREERS_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [workable] {slug}: error — {e}")
        return []
    company = data.get("name") or slug.replace("-", " ").title()
    jobs = data.get("jobs", []) or []
    out: list[JobResult] = []
    for job in jobs:
        title = job.get("title", "") or ""
        body = _clean(job.get("description", ""))
        if keyword:
            from scrape.text_match import keyword_matches_deep
            if not keyword_matches_deep(keyword, title, body):
                continue
        out.append(JobResult(
            title=title,
            company=company,
            location=_location(job.get("location") or {}),
            salary_min=None,
            salary_max=None,
            description=body,
            url=job.get("url") or "",
            source_keyword="",
            created=job.get("published_on") or "",
            job_id=f"workable_{job.get('shortcode', '')}",
            source_api="careers",
            board_count=len(jobs),
        ))
    return out
