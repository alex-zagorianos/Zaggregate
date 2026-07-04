"""discover.inbox_harvest — inbox employer names -> verified registry entries.

All five external seams (inbox_company_counts, find_career_url, detect_ats,
probe_count, save_companies) are monkeypatched on the module itself, so no
test here touches the network or a real database. Every harvest_inbox_companies()
call also passes cache_dir=tmp_path (S35 #26 negative-cache) so a test run
never writes into the real cache/inbox_harvest/.
"""
import json

import discover.inbox_harvest as H


def _no_save(entries, json_path):
    return len(entries)


def test_skips_names_already_in_registry(monkeypatch, tmp_path):
    companies_json = tmp_path / "companies.json"
    companies_json.write_text(json.dumps({"companies": [
        {"name": "Acme Robotics", "ats_type": "greenhouse", "slug": "acmerobotics", "industries": ["x"]},
    ]}), encoding="utf-8")

    monkeypatch.setattr(H, "inbox_company_counts", lambda: {"Acme Robotics": 3, "Beta Corp": 2})
    monkeypatch.setattr(H, "find_career_url", lambda domain: f"https://{domain}/careers")
    monkeypatch.setattr(H, "detect_ats", lambda url: ("greenhouse", "beta"))
    monkeypatch.setattr(H, "probe_count", lambda entry: 5)

    saved = {}
    def fake_save(entries, json_path):
        saved["entries"] = list(entries)
        return len(entries)
    monkeypatch.setattr(H, "save_companies", fake_save)

    result = H.harvest_inbox_companies(companies_json=companies_json, cache_dir=tmp_path)

    assert result.candidates == 2
    assert result.already_in_registry == 1        # "Acme Robotics" canonicalizes to the seeded entry
    assert result.verified == 1
    assert [e.name for e in result.entries] == ["Beta Corp"]
    assert [e.name for e in saved["entries"]] == ["Beta Corp"]


def test_min_count_and_limit(monkeypatch, tmp_path):
    monkeypatch.setattr(H, "inbox_company_counts", lambda: {
        "Alpha Inc": 5, "Beta Inc": 3, "Gamma Inc": 1,
    })
    monkeypatch.setattr(H, "find_career_url", lambda domain: f"https://{domain}/careers")
    monkeypatch.setattr(H, "detect_ats",
                        lambda url: ("greenhouse", url.split("//", 1)[1].split(".")[0]))
    monkeypatch.setattr(H, "probe_count", lambda entry: 5)
    monkeypatch.setattr(H, "save_companies", _no_save)

    result = H.harvest_inbox_companies(min_count=2, limit=1,
                                       companies_json=tmp_path / "companies.json",
                                       cache_dir=tmp_path)

    # min_count=2 drops Gamma Inc (count 1) before candidates is even computed.
    assert result.candidates == 2
    # limit=1 keeps only the highest inbox-count name (Alpha Inc, count 5).
    assert result.verified == 1
    assert [e.name for e in result.entries] == ["Alpha Inc"]


def test_junk_names_dropped(monkeypatch, tmp_path):
    probed_domains = []
    monkeypatch.setattr(H, "inbox_company_counts", lambda: {
        "Unknown": 10, "": 5, "A": 5, "N/A": 5, "Real Company": 4,
    })
    def fake_find(domain):
        probed_domains.append(domain)
        return f"https://{domain}/careers"
    monkeypatch.setattr(H, "find_career_url", fake_find)
    monkeypatch.setattr(H, "detect_ats", lambda url: ("greenhouse", "real"))
    monkeypatch.setattr(H, "probe_count", lambda entry: 5)
    monkeypatch.setattr(H, "save_companies", _no_save)

    result = H.harvest_inbox_companies(companies_json=tmp_path / "companies.json",
                                       cache_dir=tmp_path)

    assert result.candidates == 1     # only "Real Company" survives the junk filter
    assert [e.name for e in result.entries] == ["Real Company"]
    # "Company" is stripped as a legal suffix by canonicalize_company, so the
    # only name ever probed is the "real" token -- confirms junk names never
    # reach find_career_url at all.
    assert probed_domains and all("real" in d for d in probed_domains)


def test_all_guesses_fail_probe_not_added(monkeypatch, tmp_path):
    monkeypatch.setattr(H, "inbox_company_counts", lambda: {"NoBoard Corp": 5})
    monkeypatch.setattr(H, "find_career_url", lambda domain: f"https://{domain}/careers")
    monkeypatch.setattr(H, "detect_ats", lambda url: ("greenhouse", "noboard"))
    monkeypatch.setattr(H, "probe_count", lambda entry: 0)   # board found, zero live jobs
    monkeypatch.setattr(H, "save_companies", _no_save)

    result = H.harvest_inbox_companies(companies_json=tmp_path / "companies.json",
                                       cache_dir=tmp_path)

    assert result.candidates == 1
    assert result.resolved == 1       # detect_ats succeeded on a guess
    assert result.verified == 0       # but no guess ever cleared probe_count > 0
    assert result.entries == []
    assert result.added == 0


def test_dry_run_does_not_save(monkeypatch, tmp_path):
    monkeypatch.setattr(H, "inbox_company_counts", lambda: {"Live Co": 5})
    monkeypatch.setattr(H, "find_career_url", lambda domain: f"https://{domain}/careers")
    monkeypatch.setattr(H, "detect_ats", lambda url: ("greenhouse", "live"))
    monkeypatch.setattr(H, "probe_count", lambda entry: 12)

    calls = {"n": 0}
    def fake_save(entries, json_path):
        calls["n"] += 1
        return len(entries)
    monkeypatch.setattr(H, "save_companies", fake_save)

    result = H.harvest_inbox_companies(dry_run=True, companies_json=tmp_path / "companies.json",
                                       cache_dir=tmp_path)

    assert calls["n"] == 0
    assert result.verified == 1
    assert len(result.entries) == 1
    assert result.entries[0].name == "Live Co"
    assert result.added == 1          # preview count == len(entries) though nothing was written


def test_industries_tag_correct(monkeypatch, tmp_path):
    monkeypatch.setattr(H, "find_career_url", lambda domain: f"https://{domain}/careers")
    monkeypatch.setattr(H, "detect_ats", lambda url: ("greenhouse", "tagged"))
    monkeypatch.setattr(H, "probe_count", lambda entry: 5)
    monkeypatch.setattr(H, "save_companies", _no_save)

    monkeypatch.setattr(H, "inbox_company_counts", lambda: {"Tagged Co": 5})
    tagged = H.harvest_inbox_companies("robotics", companies_json=tmp_path / "companies.json",
                                       cache_dir=tmp_path)
    assert tagged.entries[0].industries == ["robotics"]

    monkeypatch.setattr(H, "inbox_company_counts", lambda: {"Default Co": 5})
    default = H.harvest_inbox_companies(None, companies_json=tmp_path / "companies.json",
                                        cache_dir=tmp_path)
    assert default.entries[0].industries == ["harvested"]


# ── review s26 F4: inbox_company_counts() keys are LOWERCASED; the saved entry
#    name must recover the original display casing, not persist it lowercased. ──
def test_display_casing_preserved(monkeypatch, tmp_path):
    # Real contract: counts is keyed by a lowercased/stripped name...
    monkeypatch.setattr(H, "inbox_company_counts", lambda: {"acme robotics, inc.": 3})
    # ...and inbox_company_display_names() recovers the cased spelling.
    monkeypatch.setattr(H, "inbox_company_display_names",
                        lambda: {"acme robotics, inc.": "Acme Robotics, Inc."})
    monkeypatch.setattr(H, "find_career_url", lambda domain: f"https://{domain}/careers")
    monkeypatch.setattr(H, "detect_ats", lambda url: ("greenhouse", "acmerobotics"))
    monkeypatch.setattr(H, "probe_count", lambda entry: 5)
    monkeypatch.setattr(H, "save_companies", _no_save)

    result = H.harvest_inbox_companies(companies_json=tmp_path / "companies.json",
                                       cache_dir=tmp_path)

    assert [e.name for e in result.entries] == ["Acme Robotics, Inc."]  # NOT lowercased


# ── review s26 F5: a multi-word name must NOT be shortened to its bare first
#    word (that domain can belong to an unrelated live company). ──
def test_domain_guesses_no_bare_first_word():
    guesses = H._domain_guesses("Apex Controls")
    assert "apexcontrols.com" in guesses          # specific full-token guess kept
    assert "apex.com" not in guesses              # collision-prone shortcut dropped
    # a genuinely single-word name still guesses its own domain
    assert "apex.com" in H._domain_guesses("Apex")
