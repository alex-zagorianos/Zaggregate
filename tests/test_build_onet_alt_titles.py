"""Tests for scripts.build_onet_alt_titles — the pure parse/join logic only
(no network calls; _fetch_text/_fetch_first_available are I/O and untested
here by design). Fixture data mirrors the REAL O*NET 30.3 text column layout
(verified live against onetcenter.org 2026-07-01):
  Occupation Data.txt:            O*NET-SOC Code, Title, Description
  Job Titles.txt:                 O*NET-SOC Code, Job Title, Short Title, Source(s)
  Sample of Reported Titles.txt:  O*NET-SOC Code, Reported Job Title, Shown in My Next Move
"""
from scripts import build_onet_alt_titles as b


def _rows(text: str) -> list[list[str]]:
    return b._parse_tsv_rows(text)


OCC_TEXT = (
    "O*NET-SOC Code\tTitle\tDescription\n"
    "29-1141.00\tRegistered Nurses\tAssess patient health.\n"
    "17-2141.00\tMechanical Engineers\tDesign mechanical devices.\n"
)

ALT_TEXT = (
    "O*NET-SOC Code\tJob Title\tShort Title\tSource(s)\n"
    "29-1141.00\tStaff Nurse\tn/a\t08\n"
    "29-1141.00\tRN\tRN\t10\n"
    "17-2141.00\tMechanical Design Engineer\tn/a\t08\n"
)

REPORTED_TEXT = (
    "O*NET-SOC Code\tReported Job Title\tShown in My Next Move\n"
    "29-1141.00\tCharge Nurse\tY\n"
    "99-9999.99\tNo Such Occupation\tN\n"          # SOC not in occupation data -> dropped
)


def _fake_data():
    return {
        "occupation_rows": _rows(OCC_TEXT),
        "alt_title_rows": _rows(ALT_TEXT),
        "alt_title_file": "Job Titles.txt",
        "reported_title_rows": _rows(REPORTED_TEXT),
    }


def test_parse_tsv_rows_skips_header_and_blank_lines():
    rows = _rows("H1\tH2\nfoo\tbar\n\nbaz\tqux\n")
    assert rows == [["foo", "bar"], ["baz", "qux"]]


def test_parse_tsv_rows_empty_text():
    assert _rows("") == []


def test_build_rows_includes_canonical_title_mapped_to_itself():
    rows = b.build_rows(_fake_data())
    d = {(alt.casefold(), soc): title for alt, soc, title in rows}
    assert d[("registered nurses", "29-1141.00")] == "Registered Nurses"
    assert d[("mechanical engineers", "17-2141.00")] == "Mechanical Engineers"


def test_build_rows_includes_alt_and_short_titles():
    rows = b.build_rows(_fake_data())
    alts = {alt.casefold() for alt, _soc, _title in rows}
    assert "staff nurse" in alts
    assert "rn" in alts                         # short title
    assert "mechanical design engineer" in alts


def test_build_rows_includes_reported_titles():
    rows = b.build_rows(_fake_data())
    alts = {alt.casefold() for alt, _soc, _title in rows}
    assert "charge nurse" in alts


def test_build_rows_drops_titles_for_unknown_soc():
    rows = b.build_rows(_fake_data())
    alts = {alt.casefold() for alt, _soc, _title in rows}
    assert "no such occupation" not in alts      # 99-9999.99 has no Occupation Data row


def test_build_rows_higher_priority_source_wins_ambiguous_text():
    # The SAME literal alt-title text can be attached to unrelated SOC codes
    # across sources (found running this against the real O*NET data). Priority
    # (canonical > alt/job titles > reported titles) must decide, not file order.
    data = _fake_data()
    # A generic reported title collides with the canonical "Registered Nurses"
    # text, attached to an UNRELATED occupation.
    data["reported_title_rows"].append(["17-2141.00", "Registered Nurses", "N"])
    rows = b.build_rows(data)
    d = {alt.casefold(): soc for alt, soc, _t in rows}
    assert d["registered nurses"] == "29-1141.00"      # canonical wins, not the reported dupe


def test_build_rows_alt_title_beats_reported_title_for_same_text():
    data = _fake_data()
    # "Charge Nurse" appears (hypothetically) as BOTH a curated alt title for
    # the correct SOC and a reported title for an unrelated one -- alt wins.
    data["alt_title_rows"].append(["29-1141.00", "Charge Nurse", "n/a", "08"])
    data["reported_title_rows"][0] = ["17-2141.00", "Charge Nurse", "N"]
    rows = b.build_rows(data)
    d = {alt.casefold(): soc for alt, soc, _t in rows}
    assert d["charge nurse"] == "29-1141.00"


def test_build_rows_dedupes_exact_alt_soc_pairs():
    data = _fake_data()
    data["alt_title_rows"].append(["29-1141.00", "Staff Nurse", "n/a", "08"])  # exact dup
    rows = b.build_rows(data)
    keys = [(alt.casefold(), soc) for alt, soc, _t in rows]
    assert keys.count(("staff nurse", "29-1141.00")) == 1


def test_build_rows_drops_na_short_titles():
    rows = b.build_rows(_fake_data())
    alts = [alt.casefold() for alt, _soc, _title in rows]
    assert "n/a" not in alts


def test_render_tsv_format_matches_bundled_convention():
    rows = [("registered nurse", "29-1141.00", "Registered Nurses")]
    text = b.render_tsv(rows, version="30.3")
    lines = text.splitlines()
    assert lines[0].startswith("# onet_version=30.3")
    assert lines[1] == "# format: alt_title<TAB>soc_code<TAB>soc_title"
    assert lines[2] == "registered nurse\t29-1141.00\tRegistered Nurses"


def test_render_tsv_is_loadable_by_coverage_entity(tmp_path, monkeypatch):
    """Round-trip: a file this script writes must parse with the SAME loader
    the app uses (coverage.entity._onet), proving format compatibility."""
    rows = [("registered nurse", "29-1141.00", "Registered Nurses"),
           ("staff nurse", "29-1141.00", "Registered Nurses")]
    text = b.render_tsv(rows)
    p = tmp_path / "onet_soc_alt_titles.tsv"
    p.write_text(text, encoding="utf-8")

    import coverage.entity as centity
    monkeypatch.setattr(centity, "static_path", lambda name: p)
    centity._onet.cache_clear()
    table = centity._onet()
    assert table["staff nurse"] == ("29-1141.00", "Registered Nurses")
    centity._onet.cache_clear()
