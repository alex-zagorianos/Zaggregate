import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional

from config import SEARCH_MAX_WORKERS
from models import JobResult, normalize_url
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


def _location_score(job_location: str, target: str, *, remote_ok: bool = True) -> int:
    """Score how closely a job's location matches the search target. Higher = closer.

    A pure-remote posting (one carrying 'remote' but not the target metro) used to
    score 0, which capped remote roles at 85/100 and buried them below local jobs.
    When remote is acceptable (``remote_ok``), credit it as a full match instead:
    the location component means 'somewhere I'd take the job' = local OR
    acceptable-remote. With ``remote_ok=False`` a remote-only role still scores 0,
    so local-only users are unaffected."""
    jl = (job_location or "").lower()
    tl = target.lower().strip()
    if "remote" in jl and tl not in jl:
        return 3 if remote_ok else 0   # acceptable-remote -> full marks (l=1.0)
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

        # Build the fetch work-list. Every client runs concurrently (the rate
        # limiter and file cache are thread-safe), and a keyword-parameterized
        # client (parallel_keywords=True: Adzuna/JSearch/SerpApi/USAJobs) is
        # ALSO split into one unit per keyword so its keywords fetch in parallel
        # instead of serially — the old engine capped at 4 client tasks and ran
        # each client's keywords one-by-one, so a multi-keyword search serialized
        # most of its work. Keyword-blind feeds (SingleFeedClient: The Muse,
        # RemoteOK, …) stay a single unit: they fetch once and filter every
        # keyword client-side, and some carry per-instance paging state
        # (_raw_exhausted) that concurrent keywords on one instance would race.
        units: list[tuple[JobAPIClient, list[str]]] = []
        for client in self.clients:
            if getattr(client, "parallel_keywords", False) and len(keywords) > 1:
                units.extend((client, [kw]) for kw in keywords)
            else:
                units.append((client, list(keywords)))

        agg_n: dict[str, int] = defaultdict(int)
        agg_t: dict[str, float] = defaultdict(float)
        max_workers = min(len(units), SEARCH_MAX_WORKERS) or 1
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    self._timed_run_client, client, kws, location,
                    salary_min, max_pages_per_keyword,
                ): type(client).__name__
                for client, kws in units
            }
            for future in as_completed(futures):
                source = futures[future]
                try:
                    res, elapsed = future.result()
                    agg_n[source] += len(res)
                    # Units of one source run concurrently → its wall-clock is the
                    # slowest unit, not their sum.
                    agg_t[source] = max(agg_t[source], elapsed)
                    all_results.extend(res)
                except Exception as e:
                    print(f"[{source}] failed: {e}")

        # Per-source summary with timing (no per-source instrumentation existed
        # before, so a slow source couldn't be identified without guessing).
        for source in sorted(agg_n):
            print(f"[{source}] {agg_n[source]} results in ~{agg_t[source]:.1f}s")

        deduped = self._deduplicate(all_results)
        if sort_by == "location":
            deduped.sort(key=lambda j: _location_score(j.location, location), reverse=True)
        else:
            deduped.sort(key=lambda j: _parse_created(j.created), reverse=True)

        print(f"\nTotal: {len(all_results)} raw -> {len(deduped)} after dedup")
        return deduped

    def _timed_run_client(self, client, keywords, location, salary_min, max_pages):
        """_run_client wrapped with a wall-clock measurement (for the per-source
        timing summary). Returns (results, elapsed_seconds)."""
        t0 = time.perf_counter()
        res = self._run_client(client, keywords, location, salary_min, max_pages)
        return res, time.perf_counter() - t0

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
                    # A keyword-blind feed (e.g. The Muse) can return a page with
                    # raw postings but zero client-side keyword matches; keep
                    # paging until its RAW feed is spent. Other clients have no
                    # _raw_exhausted flag -> default True -> stop on empty (as before).
                    if getattr(client, "_raw_exhausted", True):
                        break  # genuine end-of-results for this keyword
                    continue
                out.extend(results)
        return out

    def _deduplicate(self, results: list[JobResult]) -> list[JobResult]:
        # URL is the fast path: normalized-url variants of the same posting
        # collapse, and distinct reqs at distinct URLs stay separate. job_key adds
        # cross-source collapsing for postings with NO usable URL: we key those on
        # the canonicalized company + title_core (the location-free part of job_key)
        # so formatting variants ("Acme, Inc." vs "Acme Inc"; "Cincinnati, OH" vs
        # "Cincinnati"/"Remote") merge while distinct roles/companies stay apart.
        seen_urls: set[str] = set()
        seen_keyless: set = set()
        unique: list[JobResult] = []
        for job in results:
            u = normalize_url(job.url)
            if u:
                if u in seen_urls:
                    continue
                seen_urls.add(u)
            else:
                key = _keyless_key(job)
                if key in seen_keyless:
                    continue
                seen_keyless.add(key)
            unique.append(job)
        return unique


def _keyless_key(job: JobResult):
    """Canonical identity for a URL-less posting (company + title + location
    bucket). Location IS included so the same title at the same company in two
    different cities (e.g. 'Director of Clinical Informatics' open in Cincinnati
    AND Remote) does not silently collapse to one row — the earlier location-free
    key over-merged distinct postings. Falls back to a raw string if the coverage
    entity module isn't importable (e.g. a stripped frozen build)."""
    try:
        from coverage import entity
        return (entity.canonicalize_company(job.company or ""),
                entity.title_core(job.title or ""),
                entity.location_token(entity.normalize_location(job.location or "")))
    except ImportError:
        return (f"{(job.title or '').lower().strip()}|"
                f"{(job.company or '').lower().strip()}|"
                f"{(job.location or '').lower().strip()}")
