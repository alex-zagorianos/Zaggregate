"""Metro company enumeration: the LLM proposes candidates, the probe-verify gate
keeps only live boards (so hallucinated/dead companies are dropped)."""
import json

import enumerate_companies as ec
from discover import enumerate as enum


# ── pure helpers ──────────────────────────────────────────────────────────────

def test_normalize_domain_strips_scheme_www_path_case():
    assert enum.normalize_domain("https://www.Acme.com/careers") == "acme.com"
    assert enum.normalize_domain("Foo.IO") == "foo.io"
    assert enum.normalize_domain("http://jobs.globex.com:443/x") == "jobs.globex.com"
    assert enum.normalize_domain("") == ""


def test_parse_response_handles_fences_prose_and_dupes():
    txt = (
        "Sure! Here you go:\n```json\n"
        '[{"name":"Acme","domain":"acme.com"},'
        '{"name":"Dup","domain":"https://acme.com"},'
        '{"name":"Globex","domain":"globex.io"}]\n```'
    )
    got = enum.parse_enumeration_response(txt)
    assert [c["name"] for c in got] == ["Acme", "Globex"]  # dup domain collapsed
    assert got[0]["domain"] == "acme.com"


def test_parse_response_accepts_object_wrapper_and_bad_input():
    wrapped = json.dumps({"companies": [{"name": "A", "domain": "a.com"}]})
    assert enum.parse_enumeration_response(wrapped) == [{"name": "A", "domain": "a.com"}]
    assert enum.parse_enumeration_response("not json at all") == []
    assert enum.parse_enumeration_response("") == []


def test_build_prompt_contains_metro_industries_exclusions():
    p = enum.build_enumeration_prompt("Cincinnati", ["controls", "software"],
                                      exclude_names=["Acme Corp"], angle="Focus on industrials.")
    assert "Cincinnati" in p and "controls, software" in p
    assert "Acme Corp" in p and "Focus on industrials." in p
    assert "JSON array" in p and "domain" in p


def test_dedupe_candidates_drops_known_domains():
    cands = [{"name": "A", "domain": "a.com"}, {"name": "A2", "domain": "www.a.com"},
             {"name": "B", "domain": "b.com"}]
    out = enum.dedupe_candidates(cands, exclude_domains=["b.com"])
    assert [c["name"] for c in out] == ["A"]  # a.com deduped, b.com excluded


# ── the verify gate (injected resolve/probe) ──────────────────────────────────

def _resolve(domain):
    return {"live.com": ("greenhouse", "livegh"),
            "dead.com": ("lever", "deadlv"),
            "noats.com": None}.get(domain)


def _probe(entry):
    # livegh has jobs; deadlv resolves but is empty; direct boards are uncountable
    return {"livegh": 5, "deadlv": 0, "directslug": None}.get(entry.slug, 0)


def test_verify_keeps_live_drops_dead_unresolved_and_known():
    cands = [
        {"name": "Live GH", "domain": "live.com"},
        {"name": "Dead Board", "domain": "dead.com"},
        {"name": "No ATS", "domain": "noats.com"},
        {"name": "Known Co", "domain": "known.com"},
    ]
    verified, dropped = ec.resolve_and_verify(
        cands, ["controls"], resolve=_resolve, probe=_probe, existing_names=["Known Co"])

    assert [e.name for e, _ in verified] == ["Live GH"]
    assert verified[0][1] == 5
    # metro tag appended to industries, order preserved, deduped
    assert verified[0][0].industries == ["controls", "cincinnati"]

    reasons = {c["name"]: r for c, r in dropped}
    assert reasons["Dead Board"] == "no live jobs"
    assert reasons["No ATS"] == "no ATS board detected"
    assert reasons["Known Co"] == "already known"


def test_verify_unverifiable_board_dropped():
    cands = [{"name": "Direct Co", "domain": "direct.com"}]
    verified, dropped = ec.resolve_and_verify(
        cands, ["controls"], resolve=lambda d: ("direct", "directslug"), probe=_probe)
    assert verified == []
    assert dropped[0][1].startswith("unverifiable board")
