"""Socrata / SODA municipal job-board client — free US city/county job-posting
datasets published via the open-data Socrata platform (https://dev.socrata.com/).

Each city publishes its own dataset at its own domain with its own column
names (NYC's "Job Postings" dataset != Chicago's, etc). A ``DatasetSpec``
captures one city's schema (endpoint identity + column-name mapping), and
``SOCRATA_DATASETS`` maps a short city key to its spec. Adding a new city is a
pure data change — one new ``DatasetSpec`` entry — no code changes here.

Free; no API key required. An optional Socrata app token (env
``SOCRATA_APP_TOKEN`` or the ``app_token`` constructor arg) raises the per-IP
throttling ceiling but changes nothing about correctness.

No-op by default: ``SocrataClient()`` (no cities passed) returns ``[]`` from
every search without making an HTTP call, so it's safe to register in
cli.py's ALL_SOURCES before any user opts a city in via config.
"""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from models import JobResult
from search.base_client import JobAPIClient
from search.http_util import FileCache, RateLimiter, cache_key, make_session, to_float

# Socrata's published unauthenticated throttling limit is generous (roughly
# 1000 req/hour per IP); this default keeps every request well under that
# without requiring an app token. A token (X-App-Token) raises the ceiling
# further but isn't needed for correctness.
_DEFAULT_RATE_LIMIT = 60
_DEFAULT_LIMIT = 50


@dataclass(frozen=True)
class DatasetSpec:
    """One city's Socrata (SODA) job-postings dataset: its endpoint identity
    (domain + dataset_id) plus the column names that vary dataset-to-dataset.

    ``url_template`` should contain a single ``{id}`` placeholder for the
    posting's own permalink (e.g. NYC Jobs' cityjobs.nyc.gov). Leave it "" to
    fall back to a constructed, still-stable domain+dataset(+id) URL.
    """
    domain: str
    dataset_id: str
    col_title: str
    col_company: str
    col_location: str
    col_salary_min: str
    col_salary_max: str
    col_desc: str
    col_posted: str
    col_id: str
    url_template: str = ""

    @property
    def endpoint(self) -> str:
        return f"https://{self.domain}/resource/{self.dataset_id}.json"


# City key -> DatasetSpec. Add a city by adding an entry here; SocrataClient
# needs no code change to pick it up (see the DatasetSpec docstring).
SOCRATA_DATASETS: dict[str, DatasetSpec] = {
    "nyc": DatasetSpec(
        domain="data.cityofnewyork.us",
        dataset_id="kpav-sd4t",
        col_title="business_title",
        col_company="agency",
        col_location="work_location",
        col_salary_min="salary_range_from",
        col_salary_max="salary_range_to",
        col_desc="job_description",
        col_posted="posting_date",
        col_id="job_id",
        url_template="https://cityjobs.nyc.gov/jobs/{id}",
    ),
}


def _dataset_url(spec: DatasetSpec, row_id: str) -> str:
    """A stable per-posting URL: the dataset's own ``url_template`` when a row
    id is available, else a constructed domain+dataset(+id) fallback — every
    posting still gets a usable, collision-resistant identity URL."""
    if row_id and spec.url_template:
        try:
            return spec.url_template.format(id=row_id)
        except (KeyError, IndexError):
            pass
    if row_id:
        return f"https://{spec.domain}/resource/{spec.dataset_id}/{row_id}"
    return f"https://{spec.domain}/d/{spec.dataset_id}"


def _row_to_job(row: dict, spec: DatasetSpec, source_keyword: str) -> JobResult:
    """Map one SODA row to a JobResult using ``spec``'s column names. Every
    field read defensively (``.get``) — a dataset row missing an optional
    column (salary, description) degrades to None/"" rather than raising."""
    row_id = str(row.get(spec.col_id, "") or "")
    return JobResult(
        title=row.get(spec.col_title, "") or "Unknown",
        company=row.get(spec.col_company, "") or "Unknown",
        location=row.get(spec.col_location, "") or "",
        salary_min=to_float(row.get(spec.col_salary_min)),
        salary_max=to_float(row.get(spec.col_salary_max)),
        description=row.get(spec.col_desc, "") or "",
        url=_dataset_url(spec, row_id),
        source_keyword=source_keyword,
        created=row.get(spec.col_posted, "") or "",
        job_id=f"socrata_{row_id}" if row_id else "",
        source_api="socrata",
    )


class SocrataClient(JobAPIClient):
    """Free municipal job-board client over the Socrata Open Data (SODA) API.

    Keyword-parameterized + stateless across keywords -> SearchEngine may fetch
    each keyword concurrently (mirrors usajobs_client). Queries every enabled
    city's dataset per keyword/page and merges rows across cities, keyed by
    city, so ``parse_results`` can apply each row's OWN city's DatasetSpec.

    With no cities configured (the default) this client is a documented
    no-op: ``search()`` returns ``{}`` without any HTTP call.
    """
    # Keyword-parameterized + stateless across keywords → SearchEngine may fetch
    # each keyword concurrently (see search_engine.run_full_search).
    parallel_keywords = True

    def __init__(
        self,
        cities: Optional[list[str]] = None,
        app_token: Optional[str] = None,
        limit: int = _DEFAULT_LIMIT,
        cache_dir: Optional[Path] = None,
        cache_enabled: bool = True,
    ):
        requested = list(cities or [])
        self.cities = [c for c in requested if c in SOCRATA_DATASETS]
        unknown = [c for c in requested if c not in SOCRATA_DATASETS]
        if unknown:
            print(f"  [socrata] Unknown city key(s) {unknown} — not in "
                  f"SOCRATA_DATASETS, ignoring.")
        self.app_token = app_token or os.getenv("SOCRATA_APP_TOKEN")
        self.limit = limit
        self.cache = FileCache("socrata", cache_dir)
        self.cache_enabled = cache_enabled
        self.session = make_session()
        self.limiter = RateLimiter(_DEFAULT_RATE_LIMIT, quiet=True)

    def search(
        self,
        keyword: str,
        location: str = "",
        salary_min: Optional[int] = None,
        page: int = 1,
    ) -> dict:
        """Returns ``{city_key: [row, ...]}`` for every enabled city. Empty
        dict (no HTTP calls at all) when no cities are configured — the
        documented no-op path."""
        raw: dict[str, list] = {}
        for city in self.cities:
            spec = SOCRATA_DATASETS[city]
            key = cache_key("socrata", city, keyword, page, self.limit)
            if self.cache_enabled:
                cached = self.cache.get(key)
                if cached is not None:
                    raw[city] = cached
                    continue

            self.limiter.acquire()
            headers = {"X-App-Token": self.app_token} if self.app_token else {}
            params = {
                "$q": keyword,
                "$limit": self.limit,
                # SODA $offset is 0-based; SearchEngine pages from 1, so
                # page 1 -> offset 0, page 2 -> offset `limit`, etc.
                "$offset": (page - 1) * self.limit,
            }
            response = self.session.get(
                spec.endpoint, headers=headers, params=params, timeout=30
            )
            response.raise_for_status()
            rows = response.json()
            if not isinstance(rows, list):
                rows = []

            if self.cache_enabled:
                self.cache.put(key, rows)
            raw[city] = rows

        return raw

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        results = []
        for city, rows in (raw or {}).items():
            spec = SOCRATA_DATASETS.get(city)
            if spec is None or not isinstance(rows, list):
                continue
            for row in rows:
                if isinstance(row, dict):
                    results.append(_row_to_job(row, spec, source_keyword))
        return results
