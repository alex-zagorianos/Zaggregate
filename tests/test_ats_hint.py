"""SB-6 — free local ATS match hint (Jobscan-lite). Pure logic: no display, no
network, no AI. Verifies ATS detection labels, the keyword-overlap composition
(reusing match.skillgap), the honest guidance rendering, and full defensiveness.
"""
from match import ats_hint


# ── ats_label ─────────────────────────────────────────────────────────────────

def test_ats_label_known_systems():
    assert ats_hint.ats_label("https://boards.greenhouse.io/acme/jobs/1") == "Greenhouse"
    assert ats_hint.ats_label("https://jobs.lever.co/acme/abc") == "Lever"
    # Both Workday variants (legacy + wday/cxs) surface as one name.
    assert ats_hint.ats_label(
        "https://nvidia.wd5.myworkdayjobs.com/en-US/Careers") == "Workday"
    assert ats_hint.ats_label("https://careers-acme.icims.com/jobs/5") == "iCIMS"
    assert ats_hint.ats_label("https://acme.taleo.net/careersection/x") == "Oracle Taleo"


def test_ats_label_direct_and_empty_are_blank():
    # A company's own careers page / unrecognized host => no ATS claim.
    assert ats_hint.ats_label("https://acme.com/careers") == ""
    assert ats_hint.ats_label("") == ""
    assert ats_hint.ats_label(None) == ""


def test_ats_label_unknown_key_titlecases_gracefully(monkeypatch):
    # If ats_detect ever returns a type we don't have a friendly name for, we
    # still render something readable rather than a raw key or a crash.
    monkeypatch.setattr(ats_hint, "detect_ats", None, raising=False)
    import scrape.ats_detect as d
    monkeypatch.setattr(d, "detect_ats", lambda u: ("some_new_ats", "slug"))
    assert ats_hint.ats_label("https://x.example/y") == "Some New Ats"


# ── match_hint ────────────────────────────────────────────────────────────────

def test_match_hint_composes_ats_and_keyword_overlap():
    desc = ("We use Python and Kubernetes daily. Experience with SQL and "
            "Terraform is required.")
    hint = ats_hint.match_hint(
        desc, "https://boards.greenhouse.io/acme",
        skill_terms=frozenset({"python", "sql"}))
    assert hint["ats"] == "Greenhouse"
    # user skills the JD names
    assert set(hint["matched"]) == {"python", "sql"}
    assert hint["have"] == 2
    # JD terms the user lacks (freq-ranked); kubernetes + terraform are salient.
    assert "kubernetes" in hint["missing"]
    assert "terraform" in hint["missing"]
    # matched terms never leak into missing
    assert not (set(hint["matched"]) & set(hint["missing"]))


def test_match_hint_blank_description_is_valid_empty():
    hint = ats_hint.match_hint("", "https://boards.greenhouse.io/acme")
    # ATS still detected from the URL even with no description...
    assert hint["ats"] == "Greenhouse"
    # ...but no keyword read without JD text.
    assert hint["matched"] == [] and hint["missing"] == [] and hint["have"] == 0


def test_match_hint_all_empty_never_raises():
    hint = ats_hint.match_hint("", "")
    assert hint == {"ats": "", "matched": [], "missing": [], "have": 0}


def test_match_hint_respects_limit():
    desc = " ".join(f"Skill{i}" for i in range(30))  # 30 capitalized tokens
    hint = ats_hint.match_hint(desc, "", skill_terms=frozenset(), limit=5)
    assert len(hint["missing"]) <= 5


# ── hint_lines ────────────────────────────────────────────────────────────────

def test_hint_lines_render_all_three_pieces():
    hint = {"ats": "Greenhouse", "matched": ["python", "sql"],
            "missing": ["kubernetes"], "have": 2}
    lines = ats_hint.hint_lines(hint)
    assert len(lines) == 3
    assert any("Greenhouse" in l for l in lines)
    assert any("python" in l and "sql" in l for l in lines)
    assert any("kubernetes" in l for l in lines)


def test_hint_lines_omit_empty_pieces():
    # No ATS, no matched -> only the missing line.
    lines = ats_hint.hint_lines({"ats": "", "matched": [], "missing": ["rust"]})
    assert lines == [
        "Terms the job asks for that aren't in your profile yet: rust "
        "— add any you genuinely have."]
    # Nothing at all -> no lines.
    assert ats_hint.hint_lines({"ats": "", "matched": [], "missing": []}) == []
    assert ats_hint.hint_lines({}) == []


def test_hint_lines_never_claims_a_score():
    # The honest-guidance contract: we describe the ATS + overlap, we never
    # fabricate a percentage/score the way a paid "ATS score" tool does.
    hint = {"ats": "Workday", "matched": ["excel"], "missing": ["sap"]}
    blob = " ".join(ats_hint.hint_lines(hint)).lower()
    assert "score" not in blob
    assert "%" not in blob


def test_hint_lines_caps_and_counts_matched():
    matched = [f"skill{i}" for i in range(12)]
    hint = {"ats": "", "matched": matched, "missing": [], "have": 12}
    lines = ats_hint.hint_lines(hint, matched_cap=8)
    # Shows the true total (12) and a "+N more" tail for the capped remainder.
    assert "(12)" in lines[0]
    assert "+4 more" in lines[0]
