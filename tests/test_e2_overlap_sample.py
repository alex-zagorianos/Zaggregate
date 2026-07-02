"""E2 overlap_sample: overlap (f2) math on synthetic sets, key gating, parser
field mapping, snapshot persistence. No network — samplers are injected or
key-gated to a no-op."""
import pytest

from coverage import overlap_sample as ov
from models import JobResult


def _job(title, company, location="Cincinnati, OH"):
    return JobResult(
        title=title, company=company, location=location, salary_min=None,
        salary_max=None, description="", url=f"http://x/{title}",
        source_keyword="k", created="", job_id=f"id_{title}", source_api="careers")


# ── overlap math ──────────────────────────────────────────────────────────────
def test_overlap_exact_job_key_known_f2():
    captured = [_job("Registered Nurse", "Acme Health"),
                _job("Data Analyst", "Beta Corp"),
                _job("Welder", "Gamma Fab")]
    # sample: 2 exact-overlap + 1 novel -> f2 == 2
    sample = [ov._Posting("Registered Nurse", "Acme Health", "Cincinnati, OH"),
              ov._Posting("Data Analyst", "Beta Corp", "Cincinnati, OH"),
              ov._Posting("Chef", "Delta Foods", "Cincinnati, OH")]
    overlap, method = ov.compute_overlap(sample, captured, fuzzy=False)
    assert overlap == 2
    assert method == "job_key"


def test_overlap_zero_when_disjoint():
    captured = [_job("Registered Nurse", "Acme Health")]
    sample = [ov._Posting("Software Engineer", "TechCo", "Remote")]
    overlap, _ = ov.compute_overlap(sample, captured, fuzzy=False)
    assert overlap == 0


def test_overlap_all_when_identical():
    captured = [_job("RN", "Acme"), _job("LPN", "Beta")]
    # Location is part of job_key identity, so the sample must carry the same loc.
    sample = [ov._Posting("RN", "Acme", "Cincinnati, OH"),
              ov._Posting("LPN", "Beta", "Cincinnati, OH")]
    overlap, _ = ov.compute_overlap(sample, captured, fuzzy=False)
    assert overlap == 2


def test_overlap_accepts_precomputed_keys():
    from coverage import entity
    captured = [_job("RN", "Acme")]
    keys = [entity.job_key_for(captured[0])]
    sample = [ov._Posting("RN", "Acme", "Cincinnati, OH")]
    overlap, method = ov.compute_overlap(sample, keys, fuzzy=False)
    assert overlap == 1
    assert method == "job_key"  # no objects -> fuzzy disabled


def test_overlap_fuzzy_recovers_formatting_diff():
    pytest.importorskip("rapidfuzz")
    captured = [_job("Senior Registered Nurse", "Acme Health System")]
    # Different formatting: same company+role, would MISS exact job_key.
    sample = [ov._Posting("Registered Nurse, Senior", "Acme Health Systems")]
    exact, _ = ov.compute_overlap(sample, captured, fuzzy=False)
    fuzzy, method = ov.compute_overlap(sample, captured, fuzzy=True)
    assert fuzzy >= exact
    assert method == "job_key+fuzzy"


# ── run_overlap_sample end-to-end (injected sampler) ──────────────────────────
def test_run_overlap_sample_with_fake_sampler(tmp_path, monkeypatch):
    monkeypatch.setattr(ov.config, "USER_DATA_DIR", tmp_path)
    captured = [_job("RN", "Acme"), _job("Analyst", "Beta")]

    def fake_sampler(keyword, location, sample=40):
        return [ov._Posting("RN", "Acme", "Cincinnati, OH"),
                ov._Posting("Chef", "Delta", "Cincinnati, OH")]

    est = ov.run_overlap_sample("theirstack", captured, "nurse",
                                location="Cincinnati, OH", industry="nursing",
                                sampler=fake_sampler, project="testproj")
    assert est.n_sample == 2
    assert est.overlap == 1
    assert est.overlap_pct == 50.0
    assert est.n_captured == 2
    # Snapshot persisted + loadable.
    snap = ov.load_latest("theirstack", project="testproj")
    assert snap is not None
    assert snap["overlap"] == 1
    assert snap["source"] == "theirstack"


def test_run_overlap_unknown_source():
    est = ov.run_overlap_sample("bogus", [], "nurse", persist=False)
    assert est.n_sample == 0
    assert "unknown source" in est.message


def test_run_overlap_sampler_error_never_raises():
    def boom(*a, **k):
        raise RuntimeError("api down")

    est = ov.run_overlap_sample("theirstack", [_job("RN", "Acme")], "nurse",
                                sampler=boom, persist=False)
    assert est.n_sample == 0
    assert "sampler error" in est.message


# ── key gating: samplers self-skip without a key (no network) ─────────────────
def test_samplers_noop_without_key(monkeypatch):
    # Point secrets at an empty dir + clear env so no key resolves.
    monkeypatch.delenv("THEIRSTACK_API_KEY", raising=False)
    monkeypatch.delenv("TECHMAP_RAPIDAPI_KEY", raising=False)
    monkeypatch.setattr(ov, "_theirstack_key", lambda: None)
    monkeypatch.setattr(ov, "_techmap_key", lambda: None)
    assert ov.sample_theirstack("nurse", "Cincinnati") == []
    assert ov.sample_techmap("nurse", "Cincinnati") == []
    assert ov.key_present("theirstack") is False
    assert ov.key_present("techmap") is False


# ── parser field mapping ──────────────────────────────────────────────────────
def test_parse_theirstack_fields():
    data = {"data": [
        {"job_title": "Registered Nurse", "company": "Acme Health",
         "location": "Cincinnati, OH", "url": "http://acme/rn"},
        {"job_title": "LPN", "company": "Beta", "short_location": "Dayton, OH",
         "final_url": "http://beta/lpn"},
    ]}
    out = ov._parse_theirstack(data)
    assert [p.title for p in out] == ["Registered Nurse", "LPN"]
    assert out[0].company == "Acme Health"
    assert out[0].location == "Cincinnati, OH"
    assert out[1].location == "Dayton, OH"       # short_location fallback
    assert out[1].url == "http://beta/lpn"       # final_url fallback


def test_parse_techmap_aliases():
    # PROVISIONAL: several plausible shapes must all parse.
    data = {"jobs": [
        {"name": "Registered Nurse", "company": "Acme", "locality": "Cincinnati",
         "url": "http://a"},
        {"title": "LPN", "orgName": "Beta", "region": "OH", "apply_url": "http://b"},
    ]}
    out = ov._parse_techmap(data)
    assert [p.title for p in out] == ["Registered Nurse", "LPN"]
    assert out[0].company == "Acme"
    assert out[1].company == "Beta"
    assert out[1].location == "OH"
    assert out[1].url == "http://b"


def test_parse_techmap_list_shape():
    data = [{"name": "RN", "company": "Acme", "city": "Cincinnati"}]
    out = ov._parse_techmap(data)
    assert len(out) == 1 and out[0].title == "RN"
