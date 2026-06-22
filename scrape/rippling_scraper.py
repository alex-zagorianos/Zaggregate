import requests

from config import CAREERS_REQUEST_TIMEOUT
from models import JobResult

_BASE_URL = "https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs"
_HEADERS = {"Accept": "application/json", "User-Agent": "JobSearchTool/1.0 (personal use)"}


def fetch(slug: str, *, keyword: str = "") -> list[JobResult]:
    try:
        resp = requests.get(_BASE_URL.format(slug=slug), headers=_HEADERS,
                            timeout=CAREERS_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [rippling] {slug}: error — {e}")
        return []
    jobs = data if isinstance(data, list) else data.get("items", []) or []
    out: list[JobResult] = []
    for j in jobs:
        loc = (j.get("workLocation") or {}).get("label") or ""
        dept = (j.get("department") or {}).get("label") or ""
        desc = (j.get("description") or "")[:3000]
        if dept:
            desc = (desc + " " + dept).strip()
        title = j.get("name", "") or ""
        if keyword:
            from scrape.text_match import keyword_matches_deep
            if not keyword_matches_deep(keyword, title, desc):
                continue
        out.append(JobResult(
            title=title,
            company=slug.replace("-", " ").title(),
            location=loc,
            salary_min=None,
            salary_max=None,
            description=desc,
            url=j.get("url") or "",
            source_keyword="",
            created=j.get("createdAt") or j.get("postedDate") or "",
            job_id=f"rippling_{j.get('id', '')}",
            source_api="careers",
            board_count=len(jobs),
        ))
    return out
