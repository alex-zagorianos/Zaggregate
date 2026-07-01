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


def _city_state(d) -> str:
    """City + state/province from a BambooHR location dict — NO country (that's a
    coarse fallback that must not shadow a real city), collapsing consecutive
    duplicate parts (live data returns city==state=="Argentina")."""
    if not isinstance(d, dict):
        return ""
    seen: list[str] = []
    for p in (d.get("city"), d.get("state") or d.get("province")):
        p = (p or "").strip()
        if p and (not seen or seen[-1].lower() != p.lower()):
            seen.append(p)
    return ", ".join(seen)


def _location(job: dict) -> str:
    # BambooHR populates EITHER `location` (seen live) OR `atsLocation` (the
    # fixture/older shape); the other is often present but all-null. Resolve to
    # the MOST SPECIFIC value: an explicit remote flag, then a city/state from
    # ANY source, then the flat fields, then a bare country, then a remote signal.
    for key in ("location", "atsLocation"):
        d = job.get(key)
        if isinstance(d, dict) and d.get("isRemote"):
            return "Remote"
    for key in ("location", "atsLocation"):        # city/state beats country
        s = _city_state(job.get(key))
        if s:
            return s
    flat = ", ".join(p for p in (job.get("locationCity"), job.get("locationState")) if p)
    if flat:
        return flat
    for key in ("location", "atsLocation"):        # coarse: country only
        d = job.get(key)
        if isinstance(d, dict) and (d.get("country") or "").strip():
            return d["country"].strip()
    if job.get("isRemote") or "remote" in (job.get("employmentStatusLabel") or "").lower():
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
        if not isinstance(job, dict):
            continue  # skip null/soft-deleted entries — one bad row must not
                      # drop the whole board (docstring: never raise -> [])
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
