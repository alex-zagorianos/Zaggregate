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
from scrape.workable_scraper import fetch as scrape_workable
from scrape.recruitee_scraper import fetch as scrape_recruitee
from scrape.rippling_scraper import fetch as scrape_rippling
from scrape.personio_scraper import fetch as scrape_personio
from scrape.jsonld_scraper import scrape_jsonld


class CareersClient(JobAPIClient):
    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        cache_enabled: bool = True,
        top_n: int = 20,
        industry_filter: Optional[str] = None,
        discovery_enabled: bool = True,
        companies_file: Optional[Path] = None,
        tiered: bool = False,
        state_path: Optional[Path] = None,
    ):
        self.cache_dir = (cache_dir or CACHE_DIR) / "careers"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_enabled = cache_enabled
        self.top_n = top_n
        self.discovery_enabled = discovery_enabled
        self._base_companies = get_registry(industry_filter, user_json=companies_file)
        # Opt-in tiered scheduling: scrape only the registry companies that are
        # "due" this run (active boards every run, quiet/dead ones less often), so
        # a large registry doesn't make the daily run O(N). Off by default -> the
        # full registry is scraped exactly as before.
        self._tiered = tiered
        from config import CACHE_DIR as _CACHE
        self._state_path = state_path or (_CACHE / "registry_state.json")
        self._state = {}
        self._due_keys = None          # computed once per run on first search
        self._run_hits: dict[str, int] = {}
        if self._tiered:
            from scrape import tiering
            self._state = tiering.load_state(self._state_path)
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
        # Tiered mode: narrow the base registry to the boards due this run. The
        # due set is computed once per client (= once per run) and reused across
        # keywords so a company is decided once, not per-keyword.
        if self._tiered:
            from datetime import date
            from scrape import tiering
            if self._due_keys is None:
                due = tiering.due_companies(companies, self._state, date.today())
                self._due_keys = {tiering.company_key(c) for c in due}
            companies = [c for c in companies
                         if tiering.company_key(c) in self._due_keys]
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
                    if self._tiered:
                        from scrape import tiering
                        k = tiering.company_key(company)
                        self._run_hits[k] = self._run_hits.get(k, 0) + len(jobs)
                    results.extend(jobs)
                except Exception as e:
                    print(f"  [careers] {company.name}: error — {e}")
        return results

    def finalize_tiering(self) -> None:
        """Persist this run's per-board activity so the next run can schedule by
        tier. No-op unless tiered. Only boards actually scraped this run (the due
        set) are updated, so a deferred board keeps counting toward its interval."""
        if not self._tiered or self._due_keys is None:
            return
        from datetime import date
        from scrape import tiering
        today = date.today()
        for company in self._base_companies:
            key = tiering.company_key(company)
            if key in self._due_keys:
                tiering.update_after_scrape(self._state, company,
                                            self._run_hits.get(key, 0), today)
        tiering.save_state(self._state_path, self._state)

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
        elif company.ats_type == "workable":
            return scrape_workable(company.slug)
        elif company.ats_type == "recruitee":
            return scrape_recruitee(company.slug)
        elif company.ats_type == "rippling":
            return scrape_rippling(company.slug)
        elif company.ats_type == "personio":
            return scrape_personio(company.slug)
        elif company.ats_type in ("jsonld", "icims", "taleo", "successfactors"):
            # Enterprise/custom boards with no JSON API — extract schema.org/
            # JobPosting structured data from the career page.
            return scrape_jsonld(company, keyword, self.cache_dir, self.cache_enabled)
        else:
            return scrape_direct(company, keyword, self.cache_dir, self.cache_enabled)


