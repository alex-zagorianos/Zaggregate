from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional

from models import JobResult
from search.base_client import JobAPIClient

_STATE_ABBREVS = {
    "alabama": "al", "alaska": "ak", "arizona": "az", "arkansas": "ar",
    "california": "ca", "colorado": "co", "connecticut": "ct", "delaware": "de",
    "florida": "fl", "georgia": "ga", "hawaii": "hi", "idaho": "id",
    "illinois": "il", "indiana": "in", "iowa": "ia", "kansas": "ks",
    "kentucky": "ky", "louisiana": "la", "maine": "me", "maryland": "md",
    "massachusetts": "ma", "michigan": "mi", "minnesota": "mn",
    "mississippi": "ms", "missouri": "mo", "montana": "mt", "nebraska": "ne",
    "nevada": "nv", "new hampshire": "nh", "new jersey": "nj",
    "new mexico": "nm", "new york": "ny", "north carolina": "nc",
    "north dakota": "nd", "ohio": "oh", "oklahoma": "ok", "oregon": "or",
    "pennsylvania": "pa", "rhode island": "ri", "south carolina": "sc",
    "south dakota": "sd", "tennessee": "tn", "texas": "tx", "utah": "ut",
    "vermont": "vt", "virginia": "va", "washington": "wa",
    "west virginia": "wv", "wisconsin": "wi", "wyoming": "wy",
    "district of columbia": "dc",
}

_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


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


def _parse_created(value: str) -> datetime:
    """Parse heterogeneous source date strings (ISO with/without tz, ``Z`` suffix,
    or date-only) into an aware datetime so sorting is chronological, not
    lexicographic. Unparseable/empty sinks to the epoch."""
    if not value:
        return _EPOCH
    s = value.strip().replace("Z", "+00:00")
    for candidate in (s, s[:19], s[:10]):
        try:
            dt = datetime.fromisoformat(candidate)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return _EPOCH


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

        # One task per client; each client walks its own keywords/pages. Clients
        # run concurrently (the rate limiter and file cache are thread-safe), so
        # a slow source no longer blocks the others. CareersClient is internally
        # parallel and counts as a single task here.
        max_workers = min(len(self.clients), 4) or 1
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    self._run_client, client, keywords, location,
                    salary_min, max_pages_per_keyword,
                ): client
                for client in self.clients
            }
            for future in as_completed(futures):
                source = type(futures[future]).__name__
                try:
                    res = future.result()
                    print(f"[{source}] {len(res)} results")
                    all_results.extend(res)
                except Exception as e:
                    print(f"[{source}] failed: {e}")

        deduped = self._deduplicate(all_results)
        if sort_by == "location":
            deduped.sort(key=lambda j: _location_score(j.location, location), reverse=True)
        else:
            deduped.sort(key=lambda j: _parse_created(j.created), reverse=True)

        print(f"\nTotal: {len(all_results)} raw -> {len(deduped)} after dedup")
        return deduped

    def _run_client(
        self,
        client: JobAPIClient,
        keywords: list[str],
        location: str,
        salary_min: Optional[int],
        max_pages: int,
    ) -> list[JobResult]:
        source = type(client).__name__
        out: list[JobResult] = []
        for keyword in keywords:
            for page in range(1, max_pages + 1):
                try:
                    results = client.search_and_parse(
                        keyword=keyword, location=location,
                        salary_min=salary_min, page=page,
                    )
                except Exception as e:
                    # Transient errors are already retried in the session; a
                    # failure here stops paging this keyword but not the run.
                    print(f"  [{source}] {keyword!r} page {page} error: {e}")
                    break
                if not results:
                    break  # genuine end-of-results for this keyword
                out.extend(results)
        return out

    def _deduplicate(self, results: list[JobResult]) -> list[JobResult]:
        # identity_key is URL-primary: cross-source location/tracking variants of
        # the same posting collapse, while distinct same-title reqs at different
        # URLs stay separate (dedup_key would have wrongly merged them).
        seen: set[str] = set()
        unique: list[JobResult] = []
        for job in results:
            if job.identity_key not in seen:
                seen.add(job.identity_key)
                unique.append(job)
        return unique
