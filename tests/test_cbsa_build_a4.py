"""A4 slice: config DEFAULT_LOCATION empty-safe + the CBSA build script's pure
join/derivation + the full-table geography acceptance (a Cleveland OH user gets
metro variants). No network -- build_rows is tested against a small fixture that
mirrors the real Census List 1 column layout."""
import config
from scripts import build_cbsa as bc


# -- config.DEFAULT_LOCATION -----------------------------------------------------
def test_default_location_is_empty():
    # No more Cincinnati leak into skip-wizard users.
    assert config.DEFAULT_LOCATION == ""


def test_default_location_empty_safe_in_scoring():
    # Empty location must be neutral downstream, not a crash.
    from search.search_engine import _location_score
    assert _location_score("Cincinnati, OH", config.DEFAULT_LOCATION,
                           remote_ok=True) == 0


# -- CBSA build: pure derivation -------------------------------------------------
def test_principal_city_and_state_multi_state_title():
    assert bc._principal_city_and_state("Cincinnati, OH-KY-IN") == ("Cincinnati", "OH")


def test_principal_city_and_state_multi_city_title():
    assert bc._principal_city_and_state(
        "Los Angeles-Long Beach-Anaheim, CA") == ("Los Angeles", "CA")


def test_principal_city_and_state_single():
    assert bc._principal_city_and_state("Aberdeen, SD") == ("Aberdeen", "SD")


def test_principal_city_and_state_no_comma():
    assert bc._principal_city_and_state("Weird Title No State") == ("", "")


# A tiny fixture mirroring the real Census List 1 sheet: two preamble rows, a
# header row (row 3), then county-level rows (a CBSA repeats across counties).
_FIXTURE_ROWS = [
    ["Table with row headers in column A ..."],
    ["List 1. CORE BASED STATISTICAL AREAS ..."],
    ["CBSA Code", "Metropolitan Division Code", "CSA Code", "CBSA Title",
     "Metropolitan/Micropolitan Statistical Area", "Metropolitan Division Title",
     "CSA Title", "County/County Equivalent", "State Name", "FIPS State Code",
     "FIPS County Code", "Central/Outlying County"],
    ["17140", "", "", "Cincinnati, OH-KY-IN", "Metropolitan Statistical Area", "",
     "", "Hamilton County", "Ohio", "39", "061", "Central"],
    ["17140", "", "", "Cincinnati, OH-KY-IN", "Metropolitan Statistical Area", "",
     "", "Butler County", "Ohio", "39", "017", "Outlying"],   # dup CBSA row
    ["10100", "", "", "Aberdeen, SD", "Micropolitan Statistical Area", "",
     "", "Brown County", "South Dakota", "46", "013", "Central"],
]


def test_build_rows_collapses_and_derives():
    rows = bc.build_rows(_FIXTURE_ROWS)
    # Two unique CBSAs (Cincinnati de-duped from its two county rows).
    codes = [r[0] for r in rows]
    assert codes == ["17140", "10100"]
    cincy = rows[0]
    assert cincy == ["17140", "Cincinnati, OH-KY-IN Metro Area", "Cincinnati", "OH"]
    aberdeen = rows[1]
    assert aberdeen == ["10100", "Aberdeen, SD Micro Area", "Aberdeen", "SD"]


def test_render_csv_header_matches_loader_contract():
    csv_text = bc.render_csv(bc.build_rows(_FIXTURE_ROWS))
    first = csv_text.splitlines()[0]
    assert first == "cbsa_code,cbsa_title,principal_city,state"


# -- full-table geography acceptance ---------------------------------------------
def test_full_table_cleveland_user_gets_metro_variants():
    import coverage.geography as g
    g._rows.cache_clear()
    # The shipped csv is now the full ~935-CBSA table, so a non-Cincinnati user
    # (Cleveland OH) resolves + gets metro variants (previously substring-luck).
    assert g.resolve_cbsa("Cleveland", "OH") is not None
    variants = g.metro_variants("Cleveland, OH")
    assert any("cleveland" in v for v in variants)
    # And the coverage stays broad: several hundred CBSAs present.
    assert len(g._rows()) > 500


def test_full_table_still_has_cincinnati():
    import coverage.geography as g
    g._rows.cache_clear()
    assert g.resolve_cbsa("Cincinnati", "OH") == "17140"
