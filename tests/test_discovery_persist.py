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


def test_reverifying_clears_unverified_via_user_wins(tmp_path):
    # A board first saved unverified, then re-added after it verifies, is
    # scraped again: save_companies dedups by (ats_type, slug) so the second
    # write is a no-op ADD, but the earlier flagged record still excludes it.
    # The real re-verify path in the GUI overwrites the same name with a fresh
    # (unflagged) entry, so simulate that by writing the cleared record directly.
    p = tmp_path / "companies.json"
    save_companies([CompanyEntry("Flip Co", "greenhouse", "flipco",
                                 ["controls_engineering"], {UNVERIFIED_FLAG: True})], p)
    assert "Flip Co" not in {c.name for c in get_registry("controls_engineering", user_json=p)}
    # Manually clear the flag (what a successful re-probe would persist).
    raw = json.loads(p.read_text(encoding="utf-8"))
    for c in raw["companies"]:
        if c["name"] == "Flip Co":
            c.pop("extra", None)
    p.write_text(json.dumps(raw), encoding="utf-8")
    assert "Flip Co" in {c.name for c in get_registry("controls_engineering", user_json=p)}


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
