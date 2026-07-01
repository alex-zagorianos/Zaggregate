"""BambooHR careers-list scraper (Tier-1 simple style, mirrors recruitee/
workable/rippling/personio).

Endpoint: https://{slug}.bamboohr.com/careers/list -> JSON
    {"result": [ {job}, ... ], "meta": {...}}

Each job's shape varies by tenant; every field is read defensively via
.get(). The list payload does NOT carry a job description, so v1 leaves
`description=""` (see the follow-up note in the module docstring below and
in the calling agent's summary — fetching the per-job detail page is future
work, not done here to keep this scraper a single cheap request per board).

A `fetcher` seam (fetcher(url) -> str|dict) is exposed for dependency
injection/testability; the default fetcher is a plain `requests.get(...)`
call (BambooHR intermittently 403s a browser-like UA, so the default stays
minimal rather than mimicking a browser). Network/parse errors are caught
and logged -> `[]`, never raised, matching every other careers scraper.
"""
import json

import requests

from config import CAREERS_REQUEST_TIMEOUT
from models import JobResult

_BASE_URL = "https://{slug}.bamboohr.com/careers/list"
_JOB_URL = "https://{slug}.bamboohr.com/careers/{id}"
_HEADERS = {"Accept": "application/json", "User-Agent": "JobSearchTool/1.0 (personal use)"}


def _default_fetch(url: str):
    resp = requests.get(url, headers=_HEADERS, timeout=CAREERS_REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _location(job: dict) -> str:
    loc = job.get("atsLocation")
    if not isinstance(loc, dict):
        loc = job.get("location")
    if isinstance(loc, dict):
        if loc.get("isRemote"):
            return "Remote"
        parts = [loc.get("city"), loc.get("state")]
        joined = ", ".join(p for p in parts if p)
        if joined:
            return joined
    city = job.get("locationCity")
    state = job.get("locationState")
    joined = ", ".join(p for p in (city, state) if p)
    if joined:
        return joined
    if job.get("isRemote"):
        return "Remote"
    return ""


def fetch(slug: str, *, keyword: str = "", fetcher=None) -> list[JobResult]:
    fetch_fn = fetcher or _default_fetch
    try:
        data = fetch_fn(_BASE_URL.format(slug=slug))
        if isinstance(data, (str, bytes)):
            data = json.loads(data)
        jobs = data.get("result", []) or []
    except Exception as e:
        print(f"  [bamboohr] {slug}: error — {e}")
        return []

    out: list[JobResult] = []
    for job in jobs:
        title = job.get("jobOpeningName", "") or ""
        dept = job.get("departmentLabel", "") or ""
        if keyword:
            from scrape.text_match import keyword_matches_deep
            if not keyword_matches_deep(keyword, title, dept):
                continue
        job_id = job.get("id", "")
        out.append(JobResult(
            title=title,
            company=slug.replace("-", " ").replace("_", " ").title(),
            location=_location(job),
            salary_min=None,
            salary_max=None,
            description="",
            url=_JOB_URL.format(slug=slug, id=job_id) if job_id else "",
            source_keyword="",
            created=job.get("datePosted") or job.get("postingDate") or "",
            job_id=f"bamboohr_{job_id}",
            source_api="careers",
            board_count=len(jobs),
        ))
    return out
