from typing import Optional

from models import JobResult
from search.base_client import JobAPIClient


class SearchEngine:
    def __init__(self, clients: list[JobAPIClient]):
        self.clients = clients

    def run_full_search(
        self,
        keywords: list[str],
        location: str = "Cincinnati",
        salary_min: Optional[int] = None,
        max_pages_per_keyword: int = 2,
    ) -> list[JobResult]:
        all_results: list[JobResult] = []

        for client in self.clients:
            source = type(client).__name__
            for keyword in keywords:
                print(f"[{source}] Searching: {keyword!r} in {location}...")
                for page in range(1, max_pages_per_keyword + 1):
                    try:
                        raw = client.search(
                            keyword=keyword,
                            location=location,
                            salary_min=salary_min,
                            page=page,
                        )
                    except Exception as e:
                        print(f"  Error on page {page}: {e}")
                        break

                    results = client.parse_results(raw, keyword)
                    if not results:
                        break
                    all_results.extend(results)
                    print(f"  Page {page}: {len(results)} results")

        deduped = self._deduplicate(all_results)
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
