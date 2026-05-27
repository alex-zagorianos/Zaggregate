from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from config import CACHE_DIR, CAREERS_MAX_WORKERS
from models import JobResult
from search.base_client import JobAPIClient
from scrape.company_registry import CompanyEntry, get_registry
from scrape.discoverer import discover_companies
from scrape.greenhouse_scraper import scrape_greenhouse
from scrape.lever_scraper import scrape_lever
from scrape.direct_scraper import scrape_direct


class CareersClient(JobAPIClient):
    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        cache_enabled: bool = True,
        top_n: int = 20,
        industry_filter: Optional[str] = None,
        discovery_enabled: bool = True,
    ):
        self.cache_dir = (cache_dir or CACHE_DIR) / "careers"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_enabled = cache_enabled
        self.top_n = top_n
        self.industry_filter = industry_filter
        self.discovery_enabled = discovery_enabled

    def search(
        self,
        keyword: str,
        location: str = "",
        salary_min: Optional[int] = None,
        page: int = 1,
    ) -> dict:
        # location and salary_min are not used — career APIs don't support these filters
        if page > 1:
            return {}

        companies = get_registry(self.industry_filter)
        known_slugs = {c.slug for c in companies}

        if self.discovery_enabled:
            discovered = discover_companies(keyword, self.cache_dir, self.cache_enabled, known_slugs)
            companies = companies + discovered

        companies = companies[: self.top_n]

        jobs = self._scrape_all_parallel(companies, keyword)
        return {"jobs": [_job_to_dict(j) for j in jobs]}

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        return [JobResult(**d) for d in raw.get("jobs", [])]

    def _scrape_all_parallel(self, companies: list[CompanyEntry], keyword: str) -> list[JobResult]:
        results: list[JobResult] = []
        with ThreadPoolExecutor(max_workers=CAREERS_MAX_WORKERS) as executor:
            futures = {
                executor.submit(self._scrape_one, company, keyword): company
                for company in companies
            }
            for future in as_completed(futures):
                company = futures[future]
                try:
                    jobs = future.result()
                    if jobs:
                        print(f"  [careers] {company.name}: {len(jobs)} match(es)")
                    results.extend(jobs)
                except Exception as e:
                    print(f"  [careers] {company.name}: error — {e}")
        return results

    def _scrape_one(self, company: CompanyEntry, keyword: str) -> list[JobResult]:
        if company.ats_type == "greenhouse":
            return scrape_greenhouse(company, keyword, self.cache_dir, self.cache_enabled)
        elif company.ats_type == "lever":
            return scrape_lever(company, keyword, self.cache_dir, self.cache_enabled)
        else:
            return scrape_direct(company, keyword, self.cache_dir, self.cache_enabled)


def _job_to_dict(job: JobResult) -> dict:
    return {
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "description": job.description,
        "url": job.url,
        "source_keyword": job.source_keyword,
        "created": job.created,
        "job_id": job.job_id,
        "source_api": job.source_api,
    }
