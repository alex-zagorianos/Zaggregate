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
