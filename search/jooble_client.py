"""Jooble aggregator — free API key (JOOBLE_API_KEY) unlocks POST search.
Key-optional: without a key the client logs loudly and degrades to empty,
never raising (spec §7)."""
from typing import Optional

import config
from config import JOOBLE_RATE_LIMIT, JOOBLE_URL
from models import JobResult
from search.http_util import cache_key
from search.single_feed_client import SingleFeedClient


class JoobleClient(SingleFeedClient):
    cache_subdir = "jooble"
    rate_limit = JOOBLE_RATE_LIMIT

    @staticmethod
    def _api_key():
        # Re-resolve env-then-secret at call time (config constant froze at
        # import) so a key pasted into the in-app box is honored without restart.
        return config.resolve_secret("JOOBLE_API_KEY", "jooble_api_key")

    @classmethod
    def keyless(cls) -> bool:
        """True when this client will self-skip for a missing API key — the SAME
        predicate search() uses. Lets build_clients count the keyless skip from
        the source's own logic (not a hardcoded list)."""
        return not cls._api_key()

    def search(self, keyword: str, location: str = "", salary_min: Optional[int] = None,
               page: int = 1) -> dict:
        if page > 1:
            return {"jobs": []}
        api_key = self._api_key()
        if not api_key:
            print("  [jooble] WARNING: JOOBLE_API_KEY unset — Jooble skipped "
                  "(free key at jooble.org/api/about).")
            return {"jobs": []}
        key = cache_key("jooble", keyword, location)

        def fetch():
            self.limiter.acquire()
            resp = self.session.post(
                f"{JOOBLE_URL}{api_key}",
                json={"keywords": keyword, "location": location},
                timeout=30)
            resp.raise_for_status()
            return {"jobs": resp.json().get("jobs", [])}

        return self._cached(key, fetch)

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        results = []
        for item in raw.get("jobs", []):
            snippet = self.strip_html(item.get("snippet", "") or "")
            salary = (item.get("salary") or "").strip()
            if salary:
                snippet = f"Salary: {salary}\n{snippet}"
            results.append(JobResult(
                title=item.get("title", "") or "",
                company=item.get("company", "Unknown") or "Unknown",
                location=item.get("location", "") or "",
                salary_min=None,
                salary_max=None,
                description=snippet[:3000],
                url=item.get("link", "") or "",
                source_keyword=source_keyword,
                created=item.get("updated", "") or "",
                job_id=f"jooble_{item.get('id', '')}",
                source_api="jooble",
            ))
        return results
