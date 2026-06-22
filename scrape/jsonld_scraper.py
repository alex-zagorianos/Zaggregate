"""Generic schema.org/JobPosting extractor (spec §5.3).

One parser, thousands of sites: scan <script type="application/ld+json"> for
JobPosting objects (directly, in @graph, or inside an ItemList) and map to
JobResult. Best-effort; malformed/partial entries are skipped, not raised.
Uses the stdlib html.parser via BeautifulSoup (no lxml dependency).
"""
from __future__ import annotations
import html as _html
import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from models import JobResult
from search.http_util import to_float

_TAG_RE = re.compile(r"<[^>]+>")


def _clean(raw: str) -> str:
    if not raw:
        return ""
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", _html.unescape(str(raw)))).strip()[:3000]


def _org_name(org) -> str:
    if isinstance(org, dict):
        return org.get("name") or ""
    if isinstance(org, str):
        return org
    return ""


def _location(loc) -> str:
    if isinstance(loc, list):
        return "; ".join(_location(x) for x in loc if _location(x))
    if isinstance(loc, dict):
        addr = loc.get("address")
        if isinstance(addr, dict):
            parts = [addr.get("addressLocality"), addr.get("addressRegion"),
                     addr.get("addressCountry")]
            parts = [p if isinstance(p, str) else (p or {}).get("name", "") for p in parts]
            return ", ".join(p for p in parts if p)
        if isinstance(addr, str):
            return addr
    if isinstance(loc, str):
        return loc
    return ""


def _salary(base) -> tuple:
    if not isinstance(base, dict):
        return (None, None)
    val = base.get("value")
    if isinstance(val, dict):
        lo, hi = val.get("minValue"), val.get("maxValue")
        if lo is None and hi is None:
            single = to_float(val.get("value"))
            return (single, single)
        return (to_float(lo), to_float(hi))
    single = to_float(val)
    return (single, single)


def _iter_objects(obj):
    """Yield every dict in a JSON-LD blob (handles @graph + ItemList)."""
    if isinstance(obj, list):
        for x in obj:
            yield from _iter_objects(x)
    elif isinstance(obj, dict):
        yield obj
        for key in ("@graph", "itemListElement"):
            if key in obj:
                yield from _iter_objects(obj[key])
        if "item" in obj and isinstance(obj["item"], dict):
            yield from _iter_objects(obj["item"])


def _is_jobposting(obj: dict) -> bool:
    t = obj.get("@type")
    if isinstance(t, list):
        return "JobPosting" in t
    return t == "JobPosting"


def _to_jobresult(obj: dict, base_url: str) -> JobResult | None:
    title = obj.get("title") or obj.get("name") or ""
    if not title:
        return None
    lo, hi = _salary(obj.get("baseSalary"))
    url = obj.get("url") or ""
    if url and base_url and "://" not in url:
        url = urljoin(base_url, url)
    return JobResult(
        title=_clean(title) or title,
        company=_org_name(obj.get("hiringOrganization")),
        location=_location(obj.get("jobLocation")),
        salary_min=lo,
        salary_max=hi,
        description=_clean(obj.get("description", "")),
        url=url,
        source_keyword="",
        created=obj.get("datePosted") or "",
        job_id="",
        source_api="careers",
    )


def extract_jobs(html: str, base_url: str, *, keyword: str = "") -> list[JobResult]:
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    out: list[JobResult] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.get_text() or ""
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            continue
        for obj in _iter_objects(data):
            if _is_jobposting(obj):
                jr = _to_jobresult(obj, base_url)
                if jr is not None:
                    if keyword:
                        from scrape.text_match import keyword_matches_deep
                        if not keyword_matches_deep(keyword, jr.title, jr.description):
                            continue
                    out.append(jr)
    return out
