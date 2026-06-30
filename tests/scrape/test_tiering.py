"""Tiered scrape scheduling: active boards every run, quiet/dead ones less often
— and crucially, tiering can never starve an active board (no coverage loss)."""
from datetime import date

from scrape import tiering
from scrape.company_registry import CompanyEntry


def _co(slug, ats="greenhouse"):
    return CompanyEntry(slug.title(), ats, slug, [])


def test_classify_tier():
    assert tiering.classify_tier(5) == "hot"
    assert tiering.classify_tier(0) == "warm"
    assert tiering.classify_tier(0, reachable=False) == "cold"
    assert tiering.classify_tier(None) == "warm"


def test_is_due_never_seen_is_always_due():
    assert tiering.is_due(None, date(2026, 6, 25)) is True
    assert tiering.is_due({}, date(2026, 6, 25)) is True
    assert tiering.is_due({"tier": "cold"}, date(2026, 6, 25)) is True  # no last_scraped


def test_is_due_respects_tier_interval():
    today = date(2026, 6, 25)
    hot = {"last_scraped": "2026-06-24", "tier": "hot"}      # 1 day ago, interval 1
    warm = {"last_scraped": "2026-06-20", "tier": "warm"}    # 5 days ago, interval 7
    cold = {"last_scraped": "2026-06-01", "tier": "cold"}    # 24 days ago, interval 30
    assert tiering.is_due(hot, today) is True
    assert tiering.is_due(warm, today) is False
    assert tiering.is_due(cold, today) is False
    # warm becomes due after a week; cold after a month
    assert tiering.is_due(warm, date(2026, 6, 27)) is True
    assert tiering.is_due(cold, date(2026, 7, 2)) is True


def test_due_companies_filters_by_state():
    today = date(2026, 6, 25)
    a, b, c = _co("aa"), _co("bb"), _co("cc")
    state = {
        tiering.company_key(a): {"last_scraped": "2026-06-24", "tier": "hot"},   # due
        tiering.company_key(b): {"last_scraped": "2026-06-24", "tier": "warm"},  # not due
        # c absent -> never seen -> due
    }
    due = {x.slug for x in tiering.due_companies([a, b, c], state, today)}
    assert due == {"aa", "cc"}


def test_hot_company_never_starved_coverage_preserved():
    # The safety guarantee: a board that returned jobs is HOT (interval 1) and is
    # therefore due EVERY run — tiering can only defer quiet/dead boards.
    today = date(2026, 6, 25)
    active = _co("active")
    state = tiering.update_after_scrape({}, active, hit_count=7, today=date(2026, 6, 24))
    assert state[tiering.company_key(active)]["tier"] == "hot"
    assert tiering.due_companies([active], state, today) == [active]


def test_update_after_scrape_records_fields():
    state = tiering.update_after_scrape({}, _co("x"), 3, date(2026, 6, 25))
    e = state["greenhouse:x"]
    assert e == {"last_scraped": "2026-06-25", "last_hit_count": 3, "tier": "hot"}
    state = tiering.update_after_scrape(state, _co("x"), 0, date(2026, 6, 26))
    assert state["greenhouse:x"]["tier"] == "warm"


def test_state_round_trips(tmp_path):
    p = tmp_path / "registry_state.json"
    assert tiering.load_state(p) == {}            # missing file -> {}
    state = tiering.update_after_scrape({}, _co("y"), 2, date(2026, 6, 25))
    tiering.save_state(p, state)
    assert tiering.load_state(p) == state


# ── CareersClient opt-in integration ─────────────────────────────────────────

def test_careers_client_tiered_scrapes_only_due_and_updates_state(tmp_path, monkeypatch):
    from scrape.careers_client import CareersClient
    state_path = tmp_path / "registry_state.json"
    client = CareersClient(cache_dir=tmp_path, cache_enabled=False,
                           discovery_enabled=False, tiered=True, state_path=state_path)
    active, quiet = _co("active"), _co("quiet")
    # Seed state: 'quiet' was scraped today as warm (not due); 'active' is unseen.
    tiering.save_state(state_path, {
        tiering.company_key(quiet): {"last_scraped": date.today().isoformat(), "tier": "warm"},
    })
    client._state = tiering.load_state(state_path)
    client._base_companies = [active, quiet]
    client._due_keys = None

    from models import JobResult
    def fake_scrape_one(company, keyword):
        if company.slug == "active":
            return [JobResult(title="Controls Engineer", company="Active", location="",
                              salary_min=None, salary_max=None, description="", url="http://a",
                              source_keyword="", created="", source_api="careers")]
        return []
    monkeypatch.setattr(client, "_scrape_one", fake_scrape_one)

    jobs = client.search_and_parse("controls")
    assert len(jobs) == 1                       # only 'active' was due + scraped
    client.finalize_tiering()

    saved = tiering.load_state(state_path)
    assert saved[tiering.company_key(active)]["tier"] == "hot"      # got a hit
    assert saved[tiering.company_key(active)]["last_hit_count"] == 1
    # 'quiet' was deferred (not due) -> its state is untouched (no re-stamp).
    assert saved[tiering.company_key(quiet)]["tier"] == "warm"


def test_careers_client_tiered_marks_unreachable_board_cold(tmp_path, monkeypatch):
    from scrape.careers_client import CareersClient
    state_path = tmp_path / "registry_state.json"
    client = CareersClient(cache_dir=tmp_path, cache_enabled=False,
                           discovery_enabled=False, tiered=True, state_path=state_path)
    dead = _co("dead")
    client._base_companies = [dead]
    client._due_keys = None

    def boom(company, keyword):
        raise RuntimeError("board unreachable")
    monkeypatch.setattr(client, "_scrape_one", boom)

    client.search_and_parse("controls")   # error is caught inside the scrape loop
    client.finalize_tiering()

    saved = tiering.load_state(state_path)
    # Never responded -> cold (monthly), not warm (weekly).
    assert saved[tiering.company_key(dead)]["tier"] == "cold"
