"""WeWorkRemotely public RSS feed — free, no key, remote-only postings. Single
feed (no pagination, no server-side keyword search): fetched once per cache
cycle and filtered client-side per keyword (like remoteok/remotive).

The feed's ``<title>`` is conventionally "Company Name: Role Title"; the first
": " splits company from title. Some postings (rare) omit the colon entirely —
in that case the whole string is the title and the company falls back to
whatever ``<region>``/``<type>`` the item carries (or "Unknown").
"""
from typing import Optional

from models import JobResult
from scrape.xml_safe import _safe_fromstring
from search.single_feed_client import SingleFeedClient

WEWORKREMOTELY_URL = "https://weworkremotely.com/remote-jobs.rss"
WEWORKREMOTELY_RATE_LIMIT = 5


def _remote_location(loc: str) -> str:
    """This is a remote-only board, so make every posting recognizable as remote
    to geo/filter (which keys off the literal word 'remote'). Region values like
    'Anywhere in the World'/'USA Only' would otherwise be classed 'elsewhere' and
    hidden from the default 'Local + remote' Inbox view. Preserves the region."""
    loc = (loc or "").strip()
    if not loc:
        return "Remote"
    return loc if "remote" in loc.lower() else f"{loc} (Remote)"


def _text(el, tag: str) -> str:
    """Defensive child-text lookup: missing tag or empty text -> ''."""
    child = el.find(tag)
    return (child.text or "").strip() if child is not None and child.text else ""


def _parse_feed(raw) -> list[dict]:
    """Parse the RSS 2.0 XML into plain dicts (JSON-cacheable). Defensive: a
    malformed/unparseable document yields an empty list rather than raising."""
    try:
        root = _safe_fromstring(raw)  # XXE/billion-laughs-safe
    except Exception:
        return []
    items = []
    try:
        for item in root.iter("item"):
            items.append({
                "title": _text(item, "title"),
                "link": _text(item, "link"),
                "description": _text(item, "description"),
                # <region> and <type> are both used by the feed for the
                # remote-eligibility label depending on posting age/format.
                "region": _text(item, "region") or _text(item, "type"),
                "pubDate": _text(item, "pubDate"),
            })
    except Exception:
        return []
    return items


class WeWorkRemotelyClient(SingleFeedClient):
    cache_subdir = "weworkremotely"
    rate_limit = WEWORKREMOTELY_RATE_LIMIT

    def search(
        self,
        keyword: str,
        location: str = "",
        salary_min: Optional[int] = None,
        page: int = 1,
    ) -> dict:
        if page > 1:
            return {"items": []}  # single-document feed; no further pages

        def fetch():
            self.limiter.acquire()
            response = self.session.get(WEWORKREMOTELY_URL, timeout=30)
            response.raise_for_status()
            return {"items": _parse_feed(response.content)}

        return self._cached("feed", fetch)

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        from scrape.text_match import keyword_matches
        results = []
        for item in raw.get("items", []) or []:
            raw_title = item.get("title", "") or ""
            desc = self.strip_html(item.get("description", "") or "")
            region = item.get("region", "") or ""
            if ": " in raw_title:
                company, title = raw_title.split(": ", 1)
                company = company.strip() or "Unknown"
                title = title.strip()
            else:
                title = raw_title.strip()
                company = region or "Unknown"
            if not title:
                continue
            # Title+description filter (this feed carries no tags/category to
            # match on instead, unlike remoteok/remotive/arbeitnow/jobicy).
            if not keyword_matches(source_keyword, f"{title} {desc}"):
                continue
            results.append(JobResult(
                title=title,
                company=company,
                location=_remote_location(region),
                salary_min=None,
                salary_max=None,
                description=desc[:3000],
                url=item.get("link", "") or "",
                source_keyword=source_keyword,
                created=item.get("pubDate", "") or "",
                job_id=f"weworkremotely_{item.get('link', '')}",
                source_api="weworkremotely",
            ))
        return results
