from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from config import CACHE_DIR, CAREERS_MAX_WORKERS
from models import JobResult
from search.base_client import JobAPIClient
from scrape.company_registry import CompanyEntry, get_registry, save_companies
from scrape.discoverer import discover_companies
from scrape.ashby_scraper import scrape_ashby
from scrape.greenhouse_scraper import scrape_greenhouse
from scrape.smartrecruiters_scraper import scrape_smartrecruiters
from scrape.lever_scraper import scrape_lever
from scrape.direct_scraper import scrape_direct
from scrape.workday_scraper import scrape_workday


class CareersClient(JobAPIClient):
    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        cache_enabled: bool = True,
        top_n: int = 20,
        industry_filter: Optional[str] = None,
        discovery_enabled: bool = True,
        companies_file: Optional[Path] = None,
    ):
        self.cache_dir = (cache_dir or CACHE_DIR) / "careers"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_enabled = cache_enabled
        self.top_n = top_n
        self.discovery_enabled = discovery_enabled
        self._base_companies = get_registry(industry_filter, user_json=companies_file)
        # Industry tag applied to any discovered company we persist; falls back
        # to "discovered" so saved entries stay filterable by --industry.
        self.industry_tag = (industry_filter or "discovered").lower().replace(" ", "_")
        # Discovered companies that produced >=1 matching job this run (the
        # "winners" eligible for saving to companies.json).
        self._discovered_winners: dict[str, CompanyEntry] = {}

    def search(self, keyword: str, location: str = "",
               salary_min: Optional[int] = None, page: int = 1) -> dict:
        # Satisfies the abstract interface; real work is in search_and_parse.
        return {}

    def parse_results(self, raw: dict, source_keyword: str) -> list[JobResult]:
        return []

    def search_and_parse(self, keyword: str, location: str = "",
                         salary_min: Optional[int] = None, page: int = 1) -> list[JobResult]:
        if page > 1:
            return []

        # The curated registry is always scraped in full; top_n caps only the
        # auto-discovered additions. (Previously companies[:top_n] silently
        # dropped whole registries — health_informatics is listed first, so the
        # controls_engineering companies were never reached with industry=None.)
        companies = list(self._base_companies)
        discovered_slugs: set[str] = set()
        if self.discovery_enabled:
            known_slugs = {c.slug for c in companies}
            discovered = discover_companies(keyword, self.cache_dir, self.cache_enabled, known_slugs)
            discovered = discovered[: self.top_n]
            discovered_slugs = {c.slug for c in discovered}
            companies = companies + discovered

        return self._scrape_all_parallel(companies, keyword, discovered_slugs)

    def _scrape_all_parallel(self, companies: list[CompanyEntry], keyword: str,
                             discovered_slugs: set[str] = frozenset()) -> list[JobResult]:
        results: list[JobResult] = []
        with ThreadPoolExecutor(max_workers=CAREERS_MAX_WORKERS) as executor:
            futures = {
                executor.submit(self._scrape_one, company, keyword): company
                for company in companies
            }
            # The as_completed loop runs in the caller's thread, so recording
            # winners here needs no lock.
            for future in as_completed(futures):
                company = futures[future]
                try:
                    jobs = future.result()
                    if jobs:
                        print(f"  [careers] {company.name}: {len(jobs)} match(es)")
                        if company.slug in discovered_slugs:
                            self._record_winner(company)
                    results.extend(jobs)
                except Exception as e:
                    print(f"  [careers] {company.name}: error — {e}")
        return results

    def _record_winner(self, company: CompanyEntry) -> None:
        if company.slug not in self._discovered_winners:
            self._discovered_winners[company.slug] = CompanyEntry(
                name=company.name,
                ats_type=company.ats_type,
                slug=company.slug,
                industries=[self.industry_tag],
            )

    def persist_discovered(self, companies_file=None) -> int:
        """Save winner companies discovered this run to companies.json so they
        become a permanent part of the watchlist. Returns count added."""
        return save_companies(list(self._discovered_winners.values()), companies_file)

    def _scrape_one(self, company: CompanyEntry, keyword: str) -> list[JobResult]:
        if company.ats_type == "greenhouse":
            return scrape_greenhouse(company, keyword, self.cache_dir, self.cache_enabled)
        elif company.ats_type == "lever":
            return scrape_lever(company, keyword, self.cache_dir, self.cache_enabled)
        elif company.ats_type == "ashby":
            return scrape_ashby(company, keyword, self.cache_dir, self.cache_enabled)
        elif company.ats_type == "smartrecruiters":
            return scrape_smartrecruiters(company, keyword, self.cache_dir, self.cache_enabled)
        elif company.ats_type == "workday":
            return scrape_workday(company, keyword, self.cache_dir, self.cache_enabled)
        else:
            return scrape_direct(company, keyword, self.cache_dir, self.cache_enabled)


