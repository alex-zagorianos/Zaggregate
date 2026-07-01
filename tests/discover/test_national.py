"""P5 — remote = nationwide scope: enumerate_companies runs a metro pass plus a
nationwide/remote-first pass, cross-dedups domains, and tags national adds."""
import json

import enumerate_companies as ec
from discover import enumerate as enum
from scrape.company_registry import CompanyEntry


def _fake_enum(metro, industries, *, exclude_names=(), exclude_domains=(),
               angles=None, limit=40, model=None):
    if metro == ec.NATIONAL_METRO:
        # RemoteCo is genuinely new; MetroDup collides with the metro pass domain
        # and must be excluded by exclude_domains before verify.
        cands = [{"name": "RemoteCo", "domain": "remoteco.com"},
                 {"name": "MetroDup", "domain": "metroco.com"}]
        excl = {enum.normalize_domain(d) for d in exclude_domains}
        return [c for c in cands if enum.normalize_domain(c["domain"]) not in excl]
    return [{"name": "MetroCo", "domain": "metroco.com"}]


def _capture_rv(calls):
    def fake_rv(candidates, industries, *, metro_tag="cincinnati", resolve=None,
                probe=None, existing_names=None, max_workers=12):
        calls.append({"names": [c["name"] for c in candidates],
                      "industries": list(industries), "metro_tag": metro_tag,
                      "existing": list(existing_names or [])})
        verified = [(CompanyEntry(c["name"], "greenhouse", c["name"].lower(),
                                  list(industries) + [metro_tag]), 3) for c in candidates]
        return verified, []
    return fake_rv


def _run(monkeypatch, tmp_path, extra_args, remote_ok=True):
    calls = []
    monkeypatch.setattr(enum, "enumerate_via_api", _fake_enum)
    monkeypatch.setattr(ec, "resolve_and_verify", _capture_rv(calls))
    monkeypatch.setattr(ec, "_remote_ok", lambda: remote_ok)
    monkeypatch.setattr(ec, "_existing_names", lambda p: [])
    cj = tmp_path / "companies.json"
    cj.write_text(json.dumps({"companies": []}), encoding="utf-8")
    rc = ec.main(["--metro", "Cincinnati", "--industry", "controls",
                  "--json", str(cj), "--dry-run"] + extra_args)
    return rc, calls


def test_national_flag_runs_second_pass(monkeypatch, tmp_path):
    rc, calls = _run(monkeypatch, tmp_path, ["--national"], remote_ok=True)
    assert rc == 0
    assert len(calls) == 2                                  # metro + national
    metro, natl = calls
    assert metro["names"] == ["MetroCo"]
    assert metro["metro_tag"] == "cincinnati"
    # national pass: MetroDup excluded by cross-pass domain dedup
    assert natl["names"] == ["RemoteCo"]
    assert natl["metro_tag"] == "remote"
    assert "national" in natl["industries"] and "remote" in natl["industries"]
    # pass 2 excludes pass-1 verified names
    assert "MetroCo" in natl["existing"]


def test_default_is_metro_only_even_when_remote_ok(monkeypatch, tmp_path):
    # National is opt-in: a bare run must NOT silently fire a 2nd LLM pass just
    # because remote is allowed (the review finding).
    rc, calls = _run(monkeypatch, tmp_path, [], remote_ok=True)
    assert rc == 0
    assert len(calls) == 1                                  # metro only
    assert calls[0]["names"] == ["MetroCo"]


def test_national_flag_forces_pass_even_if_not_remote(monkeypatch, tmp_path):
    rc, calls = _run(monkeypatch, tmp_path, ["--national"], remote_ok=False)
    assert len(calls) == 2


def test_remote_ok_reads_hard_prefs(monkeypatch):
    import preferences
    monkeypatch.setattr(preferences, "load", lambda *a, **k: {"hard": {"remote_ok": True}})
    assert ec._remote_ok() is True
    monkeypatch.setattr(preferences, "load", lambda *a, **k: {"hard": {"remote_ok": False}})
    assert ec._remote_ok() is False
