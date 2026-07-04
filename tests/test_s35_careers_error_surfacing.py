"""S35 finding #6 (critical): per-company ATS scraper failures inside
CareersClient never reached the run's health/summary -- a broken board
degraded silently to 0 jobs forever. Per-board fail-soft behavior is
UNCHANGED (a broken board still doesn't raise, doesn't abort the run); this
only adds visibility: CareersClient.company_errors() accumulates a per-run
count + failed-board names, and search_engine.run_full_search emits ONE
aggregate warning line at the end of the run when any client exposes that
method (a generic hasattr hook, mirroring finalize_tiering)."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from scrape.careers_client import CareersClient
from scrape.company_registry import CompanyEntry
from search.search_engine import SearchEngine
from models import JobResult


def _job(company="Acme", title="Engineer"):
    return JobResult(title=title, company=company, location="", salary_min=None,
                     salary_max=None, description="", url=f"https://x/{company}",
                     source_keyword="k", created="", job_id="", source_api="careers")


def _client(tmp_path, companies, scrape_one):
    client = CareersClient(cache_dir=tmp_path, cache_enabled=False,
                           discovery_enabled=False)
    client._base_companies = companies
    client._scrape_one = scrape_one
    return client


# ---------------------------------------------------------------------------
# CareersClient.company_errors()
# ---------------------------------------------------------------------------
def test_company_errors_empty_when_nothing_failed(tmp_path):
    good = CompanyEntry("Good Co", "greenhouse", "good", [])
    client = _client(tmp_path, [good], lambda company, keyword: [])
    client.search_and_parse("engineer")
    errs = client.company_errors()
    assert errs == {"count": 0, "failed": []}


def test_company_errors_records_failing_board(tmp_path):
    good = CompanyEntry("Good Co", "greenhouse", "good", [])
    bad = CompanyEntry("Bad Co", "workday", "bad:1:Careers", [])

    def scrape_one(company, keyword):
        if company.name == "Bad Co":
            raise RuntimeError("board broke")
        return [_job(company.name)]

    client = _client(tmp_path, [good, bad], scrape_one)
    results = client.search_and_parse("engineer")
    # Per-board fail-soft is unchanged: the good board's job still comes back,
    # the run doesn't abort, and search_and_parse raises nothing.
    assert [j.company for j in results] == ["Good Co"]
    errs = client.company_errors()
    assert errs["count"] == 1
    assert errs["failed"] == ["Bad Co"]


def test_company_errors_accumulates_across_keywords_without_duplicate_names(tmp_path):
    bad = CompanyEntry("Bad Co", "workday", "bad:1:Careers", [])

    def scrape_one(company, keyword):
        raise RuntimeError("board broke")

    client = _client(tmp_path, [bad], scrape_one)
    client.search_and_parse("engineer")
    client.search_and_parse("technician")
    errs = client.company_errors()
    # Two keyword passes both hit the same broken board -> count reflects both
    # failures, but the board name is listed once (not duplicated).
    assert errs["count"] == 2
    assert errs["failed"] == ["Bad Co"]


def test_company_errors_multiple_distinct_boards(tmp_path):
    boards = [CompanyEntry(f"Co{i}", "greenhouse", f"co{i}", []) for i in range(3)]

    def scrape_one(company, keyword):
        if company.name in ("Co0", "Co2"):
            raise RuntimeError("boom")
        return []

    client = _client(tmp_path, boards, scrape_one)
    client.search_and_parse("engineer")
    errs = client.company_errors()
    assert errs["count"] == 2
    assert set(errs["failed"]) == {"Co0", "Co2"}


# ---------------------------------------------------------------------------
# search_engine.run_full_search folds the summary in (generic hasattr hook)
# ---------------------------------------------------------------------------
def test_run_full_search_logs_careers_failure_summary(tmp_path, capsys):
    bad = CompanyEntry("Bad Co", "workday", "bad:1:Careers", [])
    client = _client(tmp_path, [bad], lambda company, keyword: (_ for _ in ()).throw(
        RuntimeError("board broke")))
    # search_and_parse must not raise out to the engine (fail-soft preserved).
    engine = SearchEngine([client])
    out = engine.run_full_search(["engineer"], max_pages_per_keyword=1)
    assert out == []
    console = capsys.readouterr().out
    assert "WARNING" in console
    assert "[careers]" in console
    assert "1/1 board(s) failed this run" in console
    assert "Bad Co" in console


def test_run_full_search_silent_when_no_careers_failures(tmp_path, capsys):
    good = CompanyEntry("Good Co", "greenhouse", "good", [])
    client = _client(tmp_path, [good], lambda company, keyword: [])
    engine = SearchEngine([client])
    engine.run_full_search(["engineer"], max_pages_per_keyword=1)
    console = capsys.readouterr().out
    assert "board(s) failed this run" not in console


def test_run_full_search_ignores_clients_without_company_errors(tmp_path, capsys):
    # A plain stub client (no company_errors method) must not blow up the
    # generic hasattr-style hook.
    class Stub:
        def search_and_parse(self, keyword, location="", salary_min=None, page=1):
            return []
    engine = SearchEngine([Stub()])
    engine.run_full_search(["engineer"], max_pages_per_keyword=1)
    console = capsys.readouterr().out
    assert "board(s) failed this run" not in console


def test_run_full_search_truncates_long_failed_list(tmp_path, capsys):
    boards = [CompanyEntry(f"Co{i}", "greenhouse", f"co{i}", []) for i in range(10)]

    def scrape_one(company, keyword):
        raise RuntimeError("boom")

    client = _client(tmp_path, boards, scrape_one)
    engine = SearchEngine([client])
    engine.run_full_search(["engineer"], max_pages_per_keyword=1)
    console = capsys.readouterr().out
    assert "10/10 board(s) failed this run" in console
    assert "+2 more" in console
