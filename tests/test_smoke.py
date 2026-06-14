"""Import smoke test — every module must import cleanly."""
import importlib

import pytest

MODULES = [
    "config", "models",
    "search.base_client", "search.adzuna_client", "search.jsearch_client",
    "search.usajobs_client", "search.search_engine", "search.cli",
    "search.report_html", "search.report_csv", "search.http_util",
    "scrape.cache_helpers", "scrape.careers_client", "scrape.company_registry",
    "scrape.greenhouse_scraper", "scrape.lever_scraper", "scrape.workday_scraper",
    "scrape.direct_scraper", "scrape.discoverer", "scrape.browser_receiver",
    "scrape.company_health",
    "tracker.db", "tracker.app",
    "resume.experience_parser", "resume.generator", "resume.docx_builder",
    "resume.app", "resume.service",
    "gui",
]


@pytest.mark.parametrize("mod", MODULES)
def test_import(mod):
    importlib.import_module(mod)
