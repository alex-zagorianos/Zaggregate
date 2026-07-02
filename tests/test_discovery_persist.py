import json

from models import JobResult
from scrape.company_registry import CompanyEntry, save_companies
import scrape.careers_client as cc
from scrape.careers_client import CareersClient


# ── save_companies ────────────────────────────────────────────────────────────

def _seed(path):
    path.write_text(json.dumps({
        "_comment": "keep me",
        "companies": [
            {"_example": "skip", "name": "Example", "ats_type": "greenhouse", "slug": "ex"},
            {"name": "Existing Co", "ats_type": "greenhouse", "slug": "existingco",
             "industries": ["controls_engineering"]},
        ],
    }), encoding="utf-8")


def test_save_companies_adds_new(tmp_path):
    p = tmp_path / "companies.json"
    _seed(p)
    added = save_companies(
        [CompanyEntry("Acme Robotics", "greenhouse", "acmerobotics", ["controls_engineering"])], p)
    assert added == 1
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert raw["_comment"] == "keep me"                      # comments preserved
    assert any(c.get("_example") for c in raw["companies"])  # example preserved
    assert any(c.get("slug") == "acmerobotics" for c in raw["companies"])


def test_save_companies_dedups_by_slug_and_name(tmp_path):
    p = tmp_path / "companies.json"
    _seed(p)
    added = save_companies([
        CompanyEntry("Existing Co", "greenhouse", "existingco", []),   # dup slug+name
        CompanyEntry("Different Name", "greenhouse", "existingco", []),  # dup slug
        CompanyEntry("Existing Co", "lever", "other", []),               # dup name
    ], p)
    assert added == 0


def test_save_companies_creates_missing_file(tmp_path):
    p = tmp_path / "companies.json"  # does not exist
    added = save_companies([CompanyEntry("New", "lever", "newco", ["x"])], p)
    assert added == 1
    assert json.loads(p.read_text(encoding="utf-8"))["companies"][0]["slug"] == "newco"


# ── P0-6: unverified boards persist but are excluded from scraping ─────────────
from scrape.company_registry import (UNVERIFIED_FLAG, get_registry,  # noqa: E402
                                     is_unverified, _load_user_companies)


def test_unverified_flag_round_trips_through_save_and_load(tmp_path):
    p = tmp_path / "companies.json"
    e = CompanyEntry("Dead Board", "greenhouse", "deadslug", ["controls_engineering"],
                     {UNVERIFIED_FLAG: True})
    assert save_companies([e], p) == 1
    raw = json.loads(p.read_text(encoding="utf-8"))
    rec = [c for c in raw["companies"] if c["name"] == "Dead Board"][0]
    assert rec["extra"] == {UNVERIFIED_FLAG: True}          # persisted in extra
    loaded = _load_user_companies(p)
    assert is_unverified(loaded[0]) is True                 # and reads back


def test_get_registry_excludes_unverified_by_default(tmp_path):
    p = tmp_path / "companies.json"
    save_companies([
        CompanyEntry("Live Co", "greenhouse", "liveco", ["controls_engineering"]),
        CompanyEntry("Dead Co", "greenhouse", "deadco", ["controls_engineering"],
                     {UNVERIFIED_FLAG: True}),
    ], p)
    names = {c.name for c in get_registry("controls_engineering", user_json=p)}
    assert "Live Co" in names
    assert "Dead Co" not in names                           # excluded from scraping
    # ...but visible when explicitly requested (e.g. a prune/manage view).
    all_names = {c.name for c in get_registry("controls_engineering", user_json=p,
                                              include_unverified=True)}
    assert {"Live Co", "Dead Co"} <= all_names


def test_reverifying_clears_unverified_via_real_save(tmp_path):
    # A board first saved unverified, then re-added after it verifies, is scraped
    # again — via the REAL save path (no hand-edit): the second (verified)
    # save_companies matches by (ats_type, slug)/name, upgrades the stored record
    # in place, and clears the UNVERIFIED_FLAG so get_registry re-includes it.
    p = tmp_path / "companies.json"
    save_companies([CompanyEntry("Flip Co", "greenhouse", "flipco",
                                 ["controls_engineering"], {UNVERIFIED_FLAG: True})], p)
    assert "Flip Co" not in {c.name for c in get_registry("controls_engineering", user_json=p)}

    # Second save: same board, now VERIFIED (no flag). Counts as an upgrade.
    upgraded = save_companies(
        [CompanyEntry("Flip Co", "greenhouse", "flipco", ["controls_engineering"])], p)
    assert upgraded == 1
    assert "Flip Co" in {c.name for c in get_registry("controls_engineering", user_json=p)}
    # The persisted record no longer carries the flag (extra dropped when empty).
    raw = json.loads(p.read_text(encoding="utf-8"))
    rec = [c for c in raw["companies"] if c["name"] == "Flip Co"][0]
    assert not (rec.get("extra") or {}).get(UNVERIFIED_FLAG)
    # And the board is exactly ONE record — the upgrade was in place, not a dup.
    assert sum(1 for c in raw["companies"] if c.get("slug") == "flipco") == 1


def test_reverify_upgrade_matches_by_name_across_slug(tmp_path):
    # The user's AI mis-guessed the slug on the first (failed) probe, then the
    # user re-adds the corrected live board. Identity match falls back to NAME,
    # so the corrected verified entry upgrades the stored unverified one.
    p = tmp_path / "companies.json"
    save_companies([CompanyEntry("Slug Fixup Co", "greenhouse", "wrongslug",
                                 ["controls_engineering"], {UNVERIFIED_FLAG: True})], p)
    assert "Slug Fixup Co" not in {c.name for c in get_registry("controls_engineering", user_json=p)}
    upgraded = save_companies(
        [CompanyEntry("Slug Fixup Co", "greenhouse", "rightslug", ["controls_engineering"])], p)
    assert upgraded == 1
    surfaced = {c.name for c in get_registry("controls_engineering", user_json=p)}
    assert "Slug Fixup Co" in surfaced
    raw = json.loads(p.read_text(encoding="utf-8"))
    recs = [c for c in raw["companies"] if c["name"] == "Slug Fixup Co"]
    assert len(recs) == 1                         # upgraded in place, not duplicated
    assert recs[0]["slug"] == "rightslug"         # fields replaced with the fresh entry
    assert not (recs[0].get("extra") or {}).get(UNVERIFIED_FLAG)


def test_reverify_upgrade_unions_industries(tmp_path):
    # Re-verifying under a different active field must not drop the board's prior
    # field tags — industries are unioned on upgrade.
    p = tmp_path / "companies.json"
    save_companies([CompanyEntry("Multi Field Co", "lever", "multifield",
                                 ["controls_engineering"], {UNVERIFIED_FLAG: True})], p)
    save_companies([CompanyEntry("Multi Field Co", "lever", "multifield",
                                 ["robotics"])], p)
    raw = json.loads(p.read_text(encoding="utf-8"))
    rec = [c for c in raw["companies"] if c["name"] == "Multi Field Co"][0]
    assert set(rec["industries"]) == {"controls_engineering", "robotics"}


def test_still_unverified_reprobe_does_not_upgrade(tmp_path):
    # An incoming STILL-unverified re-add never clears a stored flag (and never
    # demotes) — only a verified re-add upgrades.
    p = tmp_path / "companies.json"
    save_companies([CompanyEntry("Dead Again Co", "greenhouse", "deadagain",
                                 ["controls_engineering"], {UNVERIFIED_FLAG: True})], p)
    added = save_companies([CompanyEntry("Dead Again Co", "greenhouse", "deadagain",
                                         ["controls_engineering"], {UNVERIFIED_FLAG: True})], p)
    assert added == 0
    assert "Dead Again Co" not in {c.name for c in get_registry("controls_engineering", user_json=p)}


def test_verified_re_add_of_verified_board_is_plain_duplicate(tmp_path):
    # A verified re-add of an ALREADY-verified board stays a no-op skip (no
    # spurious upgrade churn).
    p = tmp_path / "companies.json"
    save_companies([CompanyEntry("Already Live Co", "lever", "alreadylive",
                                 ["controls_engineering"])], p)
    added = save_companies([CompanyEntry("Already Live Co", "lever", "alreadylive",
                                         ["controls_engineering"])], p)
    assert added == 0


def test_concurrent_save_companies_loses_no_write(tmp_path):
    # The threaded Flask /clip receiver and the GUI add both write companies.json
    # in the SAME process. Without serialization each racing writer reads the same
    # base list, appends, and the second atomic write clobbers the first — one
    # board silently lost. The module lock in save_companies serializes the
    # read-modify-write; assert every one of N concurrent distinct writers lands.
    import threading

    p = tmp_path / "companies.json"
    N = 24
    barrier = threading.Barrier(N)     # maximize the overlap window

    def _writer(i):
        barrier.wait()                 # release all writers as simultaneously as possible
        save_companies([CompanyEntry(f"Co {i}", "greenhouse", f"slug{i}",
                                     ["controls_engineering"])], p)

    threads = [threading.Thread(target=_writer, args=(i,)) for i in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    raw = json.loads(p.read_text(encoding="utf-8"))
    slugs = {c["slug"] for c in raw["companies"] if "_example" not in c}
    assert slugs == {f"slug{i}" for i in range(N)}   # not one write lost


# ── S33: browser-only boards persist, count, but are excluded from scraping ────
from scrape.company_registry import (BROWSER_ONLY_FLAG, is_browser_only,  # noqa: E402
                                     browser_only_count)


def test_browser_only_flag_round_trips_through_save_and_load(tmp_path):
    p = tmp_path / "companies.json"
    e = CompanyEntry("Fedex", "workday_cxs", "fedex:5:careers",
                     ["warehouse logistics"], {BROWSER_ONLY_FLAG: True})
    assert save_companies([e], p) == 1
    raw = json.loads(p.read_text(encoding="utf-8"))
    rec = [c for c in raw["companies"] if c["name"] == "Fedex"][0]
    assert rec["extra"] == {BROWSER_ONLY_FLAG: True}        # persisted in extra
    loaded = _load_user_companies(p)
    assert is_browser_only(loaded[0]) is True               # and reads back


def test_get_registry_keeps_browser_only_but_scraper_excludes_it(tmp_path):
    p = tmp_path / "companies.json"
    save_companies([
        CompanyEntry("Live Co", "greenhouse", "liveco", ["controls_engineering"]),
        CompanyEntry("Walled Co", "workday_cxs", "walled:5:ext",
                     ["controls_engineering"], {BROWSER_ONLY_FLAG: True}),
    ], p)
    # Browser-only is a REAL company: visible in the default listing (GUI count,
    # dedup) — unlike an unverified board, which is hidden by default.
    listed = {c.name for c in get_registry("controls_engineering", user_json=p)}
    assert {"Live Co", "Walled Co"} <= listed
    # But the SCRAPER view (include_browser_only=False) drops it.
    scraped_view = {c.name for c in get_registry("controls_engineering",
                                                 user_json=p, include_browser_only=False)}
    assert "Live Co" in scraped_view
    assert "Walled Co" not in scraped_view
    assert browser_only_count(p) == 1


def test_browser_only_is_not_unverified(tmp_path):
    # The two flags are distinct: a browser-only board is NOT 'unverified'.
    p = tmp_path / "companies.json"
    save_companies([CompanyEntry("Walled Co", "workday_cxs", "walled:5:ext",
                                 ["controls_engineering"], {BROWSER_ONLY_FLAG: True})], p)
    e = _load_user_companies(p)[0]
    assert is_browser_only(e) and not is_unverified(e)
    # Included even with include_unverified=False (it's not unverified).
    assert "Walled Co" in {c.name for c in get_registry("controls_engineering", user_json=p)}


def test_server_reverify_clears_browser_only_flag(tmp_path):
    # The wall came down: a SERVER-verified re-add upgrades a browser-only board
    # in place, clearing BROWSER_ONLY_FLAG so it re-enters the scraped set.
    p = tmp_path / "companies.json"
    save_companies([CompanyEntry("Walled Co", "workday_cxs", "walled:5:ext",
                                 ["controls_engineering"], {BROWSER_ONLY_FLAG: True})], p)
    scraped_view = {c.name for c in get_registry("controls_engineering", user_json=p,
                                                 include_browser_only=False)}
    assert "Walled Co" not in scraped_view                  # excluded from scraping
    upgraded = save_companies(
        [CompanyEntry("Walled Co", "workday_cxs", "walled:5:ext",
                      ["controls_engineering"])], p)         # now server-verified
    assert upgraded == 1
    raw = json.loads(p.read_text(encoding="utf-8"))
    rec = [c for c in raw["companies"] if c["name"] == "Walled Co"][0]
    assert not (rec.get("extra") or {}).get(BROWSER_ONLY_FLAG)   # flag cleared
    assert sum(1 for c in raw["companies"] if c.get("slug") == "walled:5:ext") == 1
    # And it's back in the scraper view.
    assert "Walled Co" in {c.name for c in get_registry("controls_engineering", user_json=p,
                                                        include_browser_only=False)}


def test_incoming_browser_only_never_upgrades_stored_flag(tmp_path):
    # A browser-only re-save (not a server read) never clears a stored flag and
    # never demotes a server-verified record.
    p = tmp_path / "companies.json"
    save_companies([CompanyEntry("Walled Co", "workday_cxs", "walled:5:ext",
                                 ["controls_engineering"], {BROWSER_ONLY_FLAG: True})], p)
    added = save_companies([CompanyEntry("Walled Co", "workday_cxs", "walled:5:ext",
                                         ["controls_engineering"], {BROWSER_ONLY_FLAG: True})], p)
    assert added == 0                                       # still a no-op dup
    e = _load_user_companies(p)[0]
    assert is_browser_only(e)                               # flag intact


def test_careers_client_does_not_scrape_browser_only(tmp_path, monkeypatch):
    # End-to-end: the scraper reads get_registry(include_browser_only=False), so a
    # browser-only board never reaches _scrape_one (S33). Discovery off.
    p = tmp_path / "companies.json"
    save_companies([
        CompanyEntry("Live Co", "greenhouse", "liveco", ["controls_engineering"]),
        CompanyEntry("Walled Co", "workday_cxs", "walled:5:ext",
                     ["controls_engineering"], {BROWSER_ONLY_FLAG: True}),
    ], p)
    client = CareersClient(cache_dir=tmp_path, cache_enabled=False,
                           industry_filter="controls_engineering", top_n=0,
                           discovery_enabled=False, companies_file=p)
    scraped = []
    monkeypatch.setattr(client, "_scrape_one",
                        lambda company, keyword: scraped.append(company.name) or [])
    client.search_and_parse("controls engineer")
    assert "Live Co" in scraped
    assert "Walled Co" not in scraped


def test_careers_client_does_not_scrape_unverified(tmp_path, monkeypatch):
    # End-to-end: the scraper reads get_registry, so a flagged board never
    # reaches _scrape_one (P0-6). Discovery off so only the base registry is seen.
    p = tmp_path / "companies.json"
    save_companies([
        CompanyEntry("Live Co", "greenhouse", "liveco", ["controls_engineering"]),
        CompanyEntry("Dead Co", "greenhouse", "deadco", ["controls_engineering"],
                     {UNVERIFIED_FLAG: True}),
    ], p)
    client = CareersClient(cache_dir=tmp_path, cache_enabled=False,
                           industry_filter="controls_engineering", top_n=0,
                           discovery_enabled=False, companies_file=p)
    scraped = []
    monkeypatch.setattr(client, "_scrape_one",
                        lambda company, keyword: scraped.append(company.name) or [])
    client.search_and_parse("controls engineer")
    assert "Live Co" in scraped
    assert "Dead Co" not in scraped


# ── CareersClient winner tracking ─────────────────────────────────────────────

def test_only_winners_recorded_and_tagged(tmp_path, monkeypatch):
    discovered = CompanyEntry("Acme Robotics", "greenhouse", "acmerobotics", [])
    monkeypatch.setattr(cc, "discover_companies",
                        lambda kw, cache_dir, cache_enabled, known: [discovered])

    client = CareersClient(cache_dir=tmp_path, cache_enabled=False,
                           industry_filter="controls_engineering", top_n=100)

    job = JobResult(title="Controls Engineer", company="Acme Robotics", location="",
                    salary_min=None, salary_max=None, description="", url="u",
                    source_keyword="k", created="", job_id="", source_api="careers")

    # Only the discovered company returns a job; everything else is empty.
    monkeypatch.setattr(client, "_scrape_one",
                        lambda company, keyword: [job] if company.slug == "acmerobotics" else [])

    client.search_and_parse("controls engineer")

    assert "acmerobotics" in client._discovered_winners
    assert client._discovered_winners["acmerobotics"].industries == ["controls_engineering"]

    out = tmp_path / "companies.json"
    assert client.persist_discovered(out) == 1
    saved = json.loads(out.read_text(encoding="utf-8"))["companies"]
    assert saved[0]["slug"] == "acmerobotics"


def test_non_winner_discovered_not_saved(tmp_path, monkeypatch):
    discovered = CompanyEntry("Dud Co", "lever", "dudco", [])
    monkeypatch.setattr(cc, "discover_companies",
                        lambda kw, cache_dir, cache_enabled, known: [discovered])
    client = CareersClient(cache_dir=tmp_path, cache_enabled=False, top_n=100)
    monkeypatch.setattr(client, "_scrape_one", lambda company, keyword: [])  # nobody matches
    client.search_and_parse("controls engineer")
    assert client._discovered_winners == {}
    assert client.persist_discovered(tmp_path / "c.json") == 0
