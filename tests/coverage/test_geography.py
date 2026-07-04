from coverage.geography import resolve_cbsa, metro_variants

def test_resolve_cbsa_known_pair():
    assert resolve_cbsa("Cincinnati", "OH") is not None

def test_resolve_cbsa_none_inputs():
    assert resolve_cbsa(None, None) is None
    assert resolve_cbsa("Cincinnati", None) is None

def test_metro_variants_includes_input():
    assert "cincinnati" in metro_variants("Cincinnati")

def test_metro_variants_known_metro():
    v = metro_variants("Cincinnati, OH")
    assert any("cincinnati" in x for x in v)


# ── S36b recall widening: satellites + multi-principal-city titles ────────────

def test_metro_variants_include_satellite_suburbs_with_state():
    v = metro_variants("Cincinnati, OH")
    # Suburbs match WITH the state suffix (both abbrev + full-name forms)…
    assert "mason, oh" in v
    assert "west chester, oh" in v
    assert "florence, ky" in v
    assert "florence, kentucky" in v
    assert "lawrenceburg, in" in v
    # …and NEVER bare, so ambiguous names can't cross-match other states
    # (Aurora CO/IL, Loveland CO, Alexandria VA, Newport Beach CA…).
    assert "aurora" not in v
    assert "loveland" not in v
    assert "newport" not in v


def test_satellites_make_suburb_postings_local():
    from geo.filter import classify
    assert classify("Mason, OH", "Engineer", "Cincinnati, OH") == "local"
    assert classify("Florence, KY", "Engineer", "Cincinnati, OH") == "local"
    # Same-named city in another state stays elsewhere.
    assert classify("Aurora, CO", "Engineer", "Cincinnati, OH") == "elsewhere"
    assert classify("Loveland, CO", "Engineer", "Cincinnati, OH") == "elsewhere"


def test_multi_principal_city_titles_split():
    # (Bare-city form: "Minneapolis, MN" itself never substring-matches the
    # hyphenated CBSA title — a pre-existing, separate matching gap.)
    v = metro_variants("Minneapolis")
    # The CBSA title hyphen-joins principal cities — each becomes a variant.
    assert "st. paul" in v
    assert "bloomington" in v
    assert "minneapolis" in v


def test_metros_without_satellite_rows_unchanged():
    # A metro with no satellite data keeps exactly the pre-S36b variant shape
    # (input + title + principal city + bare title pieces).
    v = metro_variants("Boise, ID")
    assert "boise" in v
    assert not any("," in x and x.split(",")[1].strip() in ("oh", "ky", "in")
                   for x in v)
