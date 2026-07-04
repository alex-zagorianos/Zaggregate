"""S35 finding #24 (inefficiency): CareersClient re-walked/re-fetched the WHOLE
company registry once PER KEYWORD (10 DEFAULT_KEYWORDS -> 10 full passes),
even though every dispatched scraper (except "workday" and "smartrecruiters",
see scrape.careers_client's module docstring for why those two are excluded)
fetches the whole board and filters client-side -- the fetch itself is
keyword-independent.

Fix: CareersClient._scrape_one now dispatches a memoizable ats_type's scraper
ONCE per company per run (keyword="", i.e. "fetch everything"), caches the
unfiltered JobResult rows in self._board_memo keyed by (slug, ats_type), and
re-filters in Python for every keyword pass using the SAME matcher shape
(_SHALLOW_MATCH_ATS: title-only / _DEEP_MATCH_ATS: title+description) the
scraper itself would have used. Results must be byte-identical to the
unmemoized path; only the number of underlying scraper calls should drop."""
import requests

from models import JobResult
from scrape.careers_client import CareersClient, _DEEP_MATCH_ATS, _SHALLOW_MATCH_ATS
from scrape.company_registry import CompanyEntry


def _client(tmp_path, **kw):
    return CareersClient(cache_dir=tmp_path, cache_enabled=False,
                         discovery_enabled=False, **kw)


# ---------------------------------------------------------------------------
# The finding's own literal test spec: a stub fetcher counts calls.
# ---------------------------------------------------------------------------
def test_n_boards_get_n_fetches_not_3n_across_3_keywords(tmp_path, monkeypatch):
    import scrape.careers_client as cc
    calls = {"n": 0}

    def stub(company, keyword, cache_dir, cache_enabled):
        calls["n"] += 1
        # Whole-board rows independent of keyword, mirroring a real greenhouse
        # fetch: two jobs, one matching "engineer", one matching "nurse".
        return [
            JobResult(title="Controls Engineer", company=company.name, location="",
                     salary_min=None, salary_max=None, description="", url="u1",
                     source_keyword=keyword, created="", job_id="1", source_api="careers"),
            JobResult(title="Staff Nurse", company=company.name, location="",
                     salary_min=None, salary_max=None, description="", url="u2",
                     source_keyword=keyword, created="", job_id="2", source_api="careers"),
        ]
    monkeypatch.setattr(cc, "scrape_greenhouse", stub)

    companies = [CompanyEntry(f"Co{i}", "greenhouse", f"co{i}", []) for i in range(4)]
    client = _client(tmp_path)
    client._base_companies = companies

    for kw in ("engineer", "nurse", "controls"):
        client.search_and_parse(kw)

    # 4 boards, 3 keywords -> without memoization this would be 12 calls;
    # WITH memoization each board is fetched exactly once.
    assert calls["n"] == 4


def test_memoized_results_are_byte_identical_to_unmemoized_per_keyword(tmp_path, monkeypatch):
    # Prove the memoized path returns exactly the same JobResults (same title/
    # company/url/job_id/description, just source_keyword corrected) as calling
    # the "real" scraper fresh per keyword would have.
    import scrape.careers_client as cc

    def real_shaped_scraper(company, keyword, cache_dir, cache_enabled):
        from scrape.text_match import keyword_matches
        rows = [("Controls Engineer", "u1", "1"), ("Staff Nurse", "u2", "2"),
               ("Senior Controls Technician", "u3", "3")]
        out = []
        for title, url, jid in rows:
            if not keyword_matches(keyword, title):
                continue
            out.append(JobResult(title=title, company=company.name, location="",
                                 salary_min=None, salary_max=None, description="",
                                 url=url, source_keyword=keyword, created="",
                                 job_id=jid, source_api="careers"))
        return out

    monkeypatch.setattr(cc, "scrape_greenhouse", real_shaped_scraper)
    company = CompanyEntry("Acme", "greenhouse", "acme", [])

    # "Unmemoized" baseline: call the real-shaped scraper directly per keyword.
    baseline = {}
    for kw in ("controls", "nurse", "engineer"):
        baseline[kw] = real_shaped_scraper(company, kw, tmp_path, False)

    client = _client(tmp_path)
    client._base_companies = [company]
    memoized = {}
    for kw in ("controls", "nurse", "engineer"):
        rows = client.search_and_parse(kw)
        memoized[kw] = rows

    for kw in ("controls", "nurse", "engineer"):
        b_titles = sorted(j.title for j in baseline[kw])
        m_titles = sorted(j.title for j in memoized[kw])
        assert b_titles == m_titles, f"keyword {kw!r}: {b_titles} != {m_titles}"
        # Every returned row's source_keyword reflects the REAL keyword, not
        # the internal keyword="" memo-fetch sentinel.
        assert all(j.source_keyword == kw for j in memoized[kw])


def test_memoization_respects_cache_enabled_false(tmp_path, monkeypatch):
    # cache_enabled=False must still memoize IN-MEMORY for the run (no disk
    # persistence either way) -- the whole point is avoiding repeat in-process
    # dispatch cost, independent of on-disk caching.
    import scrape.careers_client as cc
    calls = {"n": 0}

    def stub(company, keyword, cache_dir, cache_enabled):
        calls["n"] += 1
        assert cache_enabled is False  # threaded through unchanged
        return []
    monkeypatch.setattr(cc, "scrape_greenhouse", stub)

    company = CompanyEntry("Acme", "greenhouse", "acme", [])
    client = _client(tmp_path)
    client._base_companies = [company]
    client.search_and_parse("a")
    client.search_and_parse("b")
    assert calls["n"] == 1


def test_tiered_mode_unaffected_by_memoization(tmp_path, monkeypatch):
    # Tiered mode narrows the registry to "due" companies once per run
    # (self._due_keys); the memo must not interfere with that gate -- a
    # not-due company is never dispatched at all, memoized or not.
    import scrape.careers_client as cc
    from scrape import tiering

    calls = {"n": 0}

    def stub(company, keyword, cache_dir, cache_enabled):
        calls["n"] += 1
        return []
    monkeypatch.setattr(cc, "scrape_greenhouse", stub)

    due_co = CompanyEntry("Due Co", "greenhouse", "due", [])
    cold_co = CompanyEntry("Cold Co", "greenhouse", "cold", [])
    client = _client(tmp_path, tiered=True,
                     state_path=tmp_path / "registry_state.json")
    client._base_companies = [due_co, cold_co]

    def fake_due(companies, state, today):
        return [due_co]  # only Due Co is due this run
    monkeypatch.setattr(tiering, "due_companies", fake_due)

    client.search_and_parse("engineer")
    client.search_and_parse("technician")
    assert calls["n"] == 1  # Due Co fetched once across both keywords; Cold Co never


# ---------------------------------------------------------------------------
# Excluded ats_types (workday, smartrecruiters) dispatch every keyword, unmemoized.
# ---------------------------------------------------------------------------
def test_workday_dispatches_every_keyword_not_memoized(tmp_path, monkeypatch):
    import scrape.careers_client as cc
    calls = []

    def stub(company, keyword, cache_dir, cache_enabled):
        calls.append(keyword)
        return []
    monkeypatch.setattr(cc, "scrape_workday", stub)

    company = CompanyEntry("Cat", "workday", "cat:1:CaterpillarCareers", [])
    client = _client(tmp_path)
    client._base_companies = [company]
    client.search_and_parse("engineer")
    client.search_and_parse("technician")
    # Both real keywords reach the scraper -- workday does its own server-side
    # keyword search and must never be called with a "" sentinel.
    assert calls == ["engineer", "technician"]


def test_smartrecruiters_dispatches_every_keyword_not_memoized(tmp_path, monkeypatch):
    import scrape.careers_client as cc
    calls = []

    def stub(company, keyword, cache_dir, cache_enabled):
        calls.append(keyword)
        return []
    monkeypatch.setattr(cc, "scrape_smartrecruiters", stub)

    company = CompanyEntry("Visa", "smartrecruiters", "visa", [])
    client = _client(tmp_path)
    client._base_companies = [company]
    client.search_and_parse("consultant")
    client.search_and_parse("analyst")
    assert calls == ["consultant", "analyst"]


# ---------------------------------------------------------------------------
# Memo key collision guard: two DIFFERENT ats_types sharing the same slug
# string (a jsonld/icims/taleo/successfactors "slug" is the raw URL) must not
# collide in the memo.
# ---------------------------------------------------------------------------
def test_memo_key_includes_ats_type_not_just_slug(tmp_path, monkeypatch):
    import scrape.careers_client as cc
    calls = []
    monkeypatch.setattr(cc, "scrape_jsonld",
                        lambda company, kw, cd, ce: (calls.append(company.ats_type), [])[1])

    client = _client(tmp_path)
    same_url = "https://co.example/careers"
    for ats in ("icims", "taleo", "successfactors", "jsonld"):
        client._scrape_one(CompanyEntry("Co", ats, same_url), "controls")
    assert calls == ["icims", "taleo", "successfactors", "jsonld"]  # all 4 dispatched


# ---------------------------------------------------------------------------
# Classification sanity: every ats_type CareersClient dispatches is accounted
# for in exactly one of the two matcher-shape sets, or is deliberately excluded.
# ---------------------------------------------------------------------------
def test_shallow_and_deep_sets_are_disjoint():
    assert _SHALLOW_MATCH_ATS.isdisjoint(_DEEP_MATCH_ATS)


def test_workday_and_smartrecruiters_are_not_memoizable():
    from scrape.careers_client import _MEMOIZABLE_ATS_TYPES
    assert "workday" not in _MEMOIZABLE_ATS_TYPES
    assert "smartrecruiters" not in _MEMOIZABLE_ATS_TYPES
