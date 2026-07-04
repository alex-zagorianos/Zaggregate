"""Careerjet public search API — free affiliate id (CAREERJET_AFFID) required.
Key-optional: without an affid the client logs loudly and degrades to empty."""
import hashlib
from typing import Optional

import config
from config import CAREERJET_RATE_LIMIT, CAREERJET_URL
from models import JobResult
from search.http_util import cache_key, to_float
from search.single_feed_client import SingleFeedClient


class CareerjetClient(SingleFeedClient):
    cache_subdir = "careerjet"
    rate_limit = CAREERJET_RATE_LIMIT

    def __init__(self, *args, country: Optional[str] = None, **kwargs):
        # `country` (a two-letter code, e.g. from config.adzuna_country_for) picks
        # Careerjet's locale_code param. None/'us' -> no locale_code sent, so a US
        # caller's request is byte-identical to before this was added.
        super().__init__(*args, **kwargs)
        self.country = country

    @staticmethod
    def _affid():
        # Re-resolve env-then-secret at call time (config constant froze at
        # import) so an affid pasted into the in-app box is honored.
        return config.resolve_secret("CAREERJET_AFFID", "careerjet_affid")

    @classmethod
    def keyless(cls) -> bool:
        """True when this client will self-skip for a missing affiliate id — the
        SAME predicate search() uses. Lets build_clients count the keyless skip
        from the source's own logic (not a hardcoded list)."""
        return not cls._affid()

    def search(self, keyword: str, location: str = "", salary_min: Optional[int] = None,
               page: int = 1) -> dict:
        if page > 1:
            return {"jobs": []}
        affid = self._affid()
        if not affid:
            # Emitted once per run, not per keyword/pass (S32/L7).
            import applog
            applog.warn_once(
                "  [careerjet] WARNING: CAREERJET_AFFID unset — Careerjet skipped "
                "(free affiliate id at careerjet.com/partners/).",
                key="careerjet:no-affid")
            return {"jobs": []}
        locale_code = config.careerjet_locale_for(self.country)
        key = cache_key("careerjet", keyword, location, locale_code)

        def fetch():
            self.limiter.acquire()
            params = {
                "keywords": keyword, "location": location, "affid": affid,
                "pagesize": 50, "user_ip": "11.22.33.44", "user_agent": self.user_agent,
            }
            # Only sent for a mapped non-US country -- a US/unmapped request
            # omits the param exactly as before (byte-identical for Alex).
            if locale_code:
                params["locale_code"] = locale_code
            resp = self.session.get(CAREERJET_URL, params=params, timeout=30)
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
