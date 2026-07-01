"""SearchEngine work-unit fan-out: keyword-parameterized clients split into one
fetch unit per keyword (concurrent), keyword-blind feeds stay one sequential
unit, and results aggregate across units."""
from models import JobResult
from search.search_engine import SearchEngine


def _job(url, title="t"):
    return JobResult(title=title, company="c", location="", salary_min=None,
                     salary_max=None, description="", url=url, source_keyword="k",
                     created="", job_id="", source_api="adzuna")


def test_parallel_client_splits_one_unit_per_keyword(monkeypatch):
    class Par:
        parallel_keywords = True
        def search_and_parse(self, **k): return []

    class Blind:  # no parallel_keywords attr -> single sequential unit
        def search_and_parse(self, **k): return []

    eng = SearchEngine([Par(), Blind()])
    seen = []
    # _run_client returns (results, error_str); the fan-out unpacks that tuple.
    monkeypatch.setattr(eng, "_run_client",
                        lambda client, kws, *a, **k: (seen.append((type(client).__name__, tuple(kws))), ([], ""))[1])
    eng.run_full_search(["x", "y"], max_pages_per_keyword=1)

    par_units = sorted(k for n, k in seen if n == "Par")
    blind_units = [k for n, k in seen if n == "Blind"]
    assert par_units == [("x",), ("y",)]   # one unit per keyword (run concurrently)
    assert blind_units == [("x", "y")]      # single unit, keywords handled in-client


def test_single_keyword_is_not_split(monkeypatch):
    class Par:
        parallel_keywords = True
        def search_and_parse(self, **k): return []

    eng = SearchEngine([Par()])
    seen = []
    monkeypatch.setattr(eng, "_run_client",
                        lambda client, kws, *a, **k: (seen.append(tuple(kws)), ([], ""))[1])
    eng.run_full_search(["only"], max_pages_per_keyword=1)
    assert seen == [("only",)]


def test_results_aggregate_across_keyword_units():
    class Par:
        parallel_keywords = True
        def search_and_parse(self, keyword, location, salary_min, page):
            return [_job(f"u-{keyword}", title=keyword)] if page == 1 else []

    eng = SearchEngine([Par()])
    out = eng.run_full_search(["a", "b"], max_pages_per_keyword=1)
    assert {j.url for j in out} == {"u-a", "u-b"}
