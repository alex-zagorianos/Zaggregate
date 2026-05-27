from typing import Optional

from models import JobResult
from search.base_client import JobAPIClient

_STATE_ABBREVS = {
    "ohio": "oh", "kentucky": "ky", "indiana": "in",
    "pennsylvania": "pa", "texas": "tx", "california": "ca",
    "new york": "ny", "virginia": "va", "michigan": "mi", "illinois": "il",
    "georgia": "ga", "florida": "fl", "north carolina": "nc", "tennessee": "tn",
}


def _location_score(job_location: str, target: str) -> int:
    """Score how closely a job's location matches the search target. Higher = closer."""
    jl = (job_location or "").lower()
    tl = target.lower().strip()
    if "remote" in jl and tl not in jl:
        return 0
    target_tokens = [t.strip().rstrip(",") for t in tl.replace(",", " ").split()]
    score = 0
    for token in target_tokens:
        if token in jl:
            score += 2 if len(token) > 3 else 1
        for full, abbrev in _STATE_ABBREVS.items():
            if (token == abbrev and full in jl) or (token == full and abbrev in jl):
                score += 1
    return score


class SearchEngine:
    def __init__(self, clients: list[JobAPIClient]):
        self.clients = clients

    def run_full_search(
        self,
        keywords: list[str],
        location: str = "Cincinnati",
        salary_min: Optional[int] = None,
        max_pages_per_keyword: int = 2,
        sort_by: str = "date",
    ) -> list[JobResult]:
        all_results: list[JobResult] = []

        for client in self.clients:
            source = type(client).__name__
            for keyword in keywords:
                print(f"[{source}] Searching: {keyword!r} in {location}...")
                for page in range(1, max_pages_per_keyword + 1):
                    try:
                        results = client.search_and_parse(
                            keyword=keyword,
                            location=location,
                            salary_min=salary_min,
                            page=page,
                        )
                    except Exception as e:
                        print(f"  Error on page {page}: {e}")
                        break

                    if not results:
                        break
                    all_results.extend(results)
                    print(f"  Page {page}: {len(results)} results")

        deduped = self._deduplicate(all_results)
        if sort_by == "location":
            deduped.sort(key=lambda j: _location_score(j.location, location), reverse=True)
        else:
            deduped.sort(key=lambda j: j.created or "", reverse=True)

        print(f"\nTotal: {len(all_results)} raw -> {len(deduped)} after dedup")
        return deduped

    def _deduplicate(self, results: list[JobResult]) -> list[JobResult]:
        seen: set[str] = set()
        unique: list[JobResult] = []
        for job in results:
            if job.dedup_key not in seen:
                seen.add(job.dedup_key)
                unique.append(job)
        return unique
