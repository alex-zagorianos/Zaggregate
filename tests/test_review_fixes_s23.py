"""Regression tests for the Session-23 adversarial-review findings (all confirmed)."""
import json

import pytest


# ── #6 normalize_url: generic redirect unwrap must NOT touch direct/ATS URLs ──

def test_normalize_url_leaves_direct_apply_url_with_target_param():
    from models import normalize_url
    # A ZipRecruiter apply link carrying a marketing target= must stay itself, NOT
    # collapse to the employer marketing site (which would dedup distinct postings).
    a = normalize_url("https://www.ziprecruiter.com/apply/abc123?target=https://acme.com&utm_source=google")
    b = normalize_url("https://www.ziprecruiter.com/apply/xyz789?target=https://acme.com&utm_source=google")
    assert "ziprecruiter.com/apply/abc123" in a
    assert a != b                                  # distinct postings stay distinct


def test_normalize_url_still_unwraps_real_redirect_hosts():
    from models import normalize_url
    direct = "https://boards.greenhouse.io/acme/jobs/1"
    assert normalize_url("https://track.example.com/click?url=" + direct) == normalize_url(direct)
    assert normalize_url("https://www.google.com/url?q=" + direct) == normalize_url(direct)


# ── #4/#5 ranker._facts_profile falls back to active config when cfg is None ───

def test_facts_profile_falls_back_to_active_config(monkeypatch):
    import ranker
    import workspace
    monkeypatch.setattr(workspace, "load_config",
                        lambda *a, **k: {"industry": "health_informatics"})
    industry, _skills = ranker._facts_profile(None)   # the live GUI path
    assert industry == "health_informatics"           # was silently "" before


def test_facts_profile_tech_industry_still_no_skill_terms(monkeypatch):
    import ranker
    import workspace
    monkeypatch.setattr(workspace, "load_config",
                        lambda *a, **k: {"industry": "controls_engineering"})
    industry, skills = ranker._facts_profile(None)
    assert industry == "controls_engineering" and skills is None  # byte-identical


# ── #3 harvest_host_index keeps earlier pages when a later page fails ─────────

def test_host_index_keeps_partial_pages_on_later_failure(capsys):
    import discover.cc_harvest as H

    def fetch(host, crawl_id, limit, *, page=None, page_size=None):
        if page == 0:
            return ['{"url": "https://boards.greenhouse.io/acme/jobs/1"}']
        raise RuntimeError("CDX 500")             # page 1 fails after page 0 ok

    out = H.harvest_host_index(["boards.greenhouse.io"], max_pages=3,
                               fetch=fetch, num_pages=lambda h, c, ps: 3)
    assert out.get("greenhouse") == {"acme"}      # page-0 data preserved, not lost
    assert "no ATS hosts reachable" not in capsys.readouterr().out


# ── #1 dataset seed uses the dataset's real name (no same-slug name collision) ─

def test_dataset_seed_uses_real_name_avoids_slug_collision(tmp_path):
    from discover import dataset_seed as ds
    from scrape.company_registry import get_registry
    csv_text = ("name,ats,slug\n"
                "Acme Greenhouse Inc,greenhouse,acme\n"
                "Acme Lever LLC,lever,acme\n")   # same slug, DIFFERENT companies
    dpath = tmp_path / "d.csv"; dpath.write_text(csv_text, encoding="utf-8")
    cj = tmp_path / "companies.json"; cj.write_text('{"companies": []}', encoding="utf-8")
    res = ds.seed_from_dataset(dpath, "controls_engineering", probe=lambda e: 4,
                               companies_json_path=cj, existing=set())
    saved = {(e.name, e.ats_type) for e in get_registry(user_json=cj)}
    assert ("Acme Greenhouse Inc", "greenhouse") in saved
    assert ("Acme Lever LLC", "lever") in saved   # BOTH saved (distinct real names)
    assert res["added"] == 2


# ── #8 classify matches symbol-suffixed keywords (C++/.NET) ───────────────────

def test_classify_matches_symbol_keywords():
    from discover import classify as C
    assert C.is_relevant_deterministic("x", ["Senior C++ Engineer"], {"c++"}) is True
    assert C.is_relevant_deterministic("x", ["Senior .NET Developer"], {".net"}) is True
