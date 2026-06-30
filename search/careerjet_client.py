"""Careerjet public search API — free affiliate id (CAREERJET_AFFID) required.
Key-optional: without an affid the client logs loudly and degrades to empty."""
import hashlib
from typing import Optional

from config import CAREERJET_AFFID, CAREERJET_RATE_LIMIT, CAREERJET_URL
from models import JobResult
from search.http_util import cache_key, to_float
from search.single_feed_client import SingleFeedClient


class CareerjetClient(SingleFeedClient):
    cache_subdir = "careerjet"
    rate_limit = CAREERJET_RATE_LIMIT

    def search(self, keyword: str, location: str = "", salary_min: Optional[int] = None,
               page: int = 1) -> dict:
        if page > 1:
            return {"jobs": []}
        if not CAREERJET_AFFID:
            print("  [careerjet] WARNING: CAREERJET_AFFID unset — Careerjet skipped "
                  "(free affiliate id at careerjet.com/partners/).")
            return {"jobs": []}
        key = cache_key("careerjet", keyword, location)

        def fetch():
            self.limiter.acquire()
            resp = self.session.get(CAREERJET_URL, params={
                "keywords": keyword, "location": location, "affid": CAREERJET_AFFID,
                "pagesize": 50, "user_ip": "11.22.33.44", "user_agent": self.user_agent,
            }, timeout=30)
            resp.raise_for_status()
            return {"jobs": resp.json().get("jobs", [])}

        return self._cached(key, fetch)

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        results = []
        for item in raw.get("jobs", []):
            results.append(JobResult(
                title=item.get("title", "") or "",
                company=item.get("company", "Unknown") or "Unknown",
                location=item.get("locations", "") or "",
                salary_min=to_float(item.get("salary_min")),
                salary_max=to_float(item.get("salary_max")),
                description=self.strip_html(item.get("description", "") or "")[:3000],
                url=item.get("url", "") or "",
                source_keyword=source_keyword,
                created=item.get("date", "") or "",
                job_id=f"careerjet_{hashlib.md5((item.get('url', '') or '').encode('utf-8')).hexdigest()[:12]}",
                source_api="careerjet",
            ))
        return results
