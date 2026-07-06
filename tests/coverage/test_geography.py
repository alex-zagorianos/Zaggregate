import pytest

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


def test_multi_principal_city_titles_split_state_qualified():
    # (Bare-city form: fixed below — "Minneapolis, MN" now also matches the
    # hyphenated CBSA title via _city_state_input_matches_title.)
    v = metro_variants("Minneapolis")
    # Each hyphen-joined principal city becomes a variant — WITH its state
    # suffix only (review-confirmed: bare pieces cross-match other metros).
    assert "st. paul, mn" in v
    assert "bloomington, mn" in v
    assert "st. paul" not in v
    assert "bloomington" not in v
    assert "minneapolis" in v          # whole bare title: pre-existing


def test_split_pieces_never_cross_match_other_states():
    # "Denver-Aurora-Centennial, CO" must NOT make an Aurora IL/IN job local.
    from geo.filter import classify
    v = metro_variants("Denver")
    assert "aurora" not in v
    assert "aurora, co" in v
    assert classify("Aurora, IL", "Engineer", "Denver") == "elsewhere"
    assert classify("Aurora, CO", "Engineer", "Denver") == "local"


def test_metros_without_satellite_rows_unchanged():
    # A metro with no satellite data keeps exactly the pre-S36b variant shape
    # (input + title + principal city + bare title pieces).
    v = metro_variants("Boise, ID")
    assert "boise" in v
    assert not any("," in x and x.split(",")[1].strip() in ("oh", "ky", "in")
                   for x in v)


# ── "City, ST" vs hyphenated multi-city CBSA titles (KNOWN_ISSUES gap fix) ────
#
# Root cause: metro_variants()'s match test was `a in title or title in a`,
# comparing the FULL "city, st" input against the CBSA title string. For a
# single-principal-city metro ("Cincinnati, OH-KY-IN Metro Area") the literal
# "cincinnati, oh" IS a substring of the title, so it already worked. But for
# a hyphenated multi-city title ("Minneapolis-St. Paul-Bloomington, MN-WI
# Metro Area") the input "minneapolis, mn" is followed by a comma, while the
# title has "minneapolis-st. paul..." (a hyphen) — neither substring test can
# ever pass, so the whole CBSA row (and all its satellite/piece variants) was
# skipped. Only the BARE city ("Minneapolis", no state) happened to work,
# because it substring-matches inside the title's hyphenated prefix.
#
# Fix (_city_state_input_matches_title, additive OR arm in metro_variants):
# a "City, ST" input now also matches when City is one of the title's
# hyphen-separated principal cities AND ST (abbrev or full name) is one of
# the title's hyphen-separated suffix states. Purely additive — every input
# that already matched via the old substring test still matches (never
# fewer rows visible), and same-named cities in a DIFFERENT CBSA's state
# suffix are excluded because both city AND state must agree.

@pytest.mark.parametrize("query", [
    "Minneapolis, MN",
    "St. Paul, MN",
    "Bloomington, MN",
])
def test_city_state_matches_own_hyphenated_multi_city_cbsa(query):
    v = metro_variants(query)
    assert "minneapolis" in v
    assert "minneapolis-st. paul-bloomington, mn-wi metro area" in v


def test_city_state_matches_wi_side_suburb_of_the_same_cbsa():
    # The Minneapolis-St. Paul-Bloomington CBSA's own state suffix is
    # "MN-WI" (it spans both states), so a WI-side variant of a principal
    # city ("Bloomington, WI") is a legitimate member-state token for a
    # "Minneapolis, MN" search — a real posting naming the WI side of the
    # metro must still resolve as local, not get dropped.
    v = metro_variants("Minneapolis, MN")
    assert "bloomington, wi" in v
    assert "bloomington, wisconsin" in v


@pytest.mark.parametrize("query,forbidden_substrings", [
    # Bloomington, IN is its OWN separate CBSA (14020) — must NOT match the
    # Minneapolis-St. Paul-Bloomington, MN-WI metro (14020's title).
    ("Bloomington, IN", ["minneapolis", "st. paul"]),
    # Portland, ME (Portland-South Portland, ME metro, 38860) must NOT match
    # the different Portland-Vancouver-Hillsboro, OR-WA metro (38900).
    ("Portland, ME", ["vancouver", "hillsboro", "or-wa"]),
])
def test_city_state_does_not_cross_match_other_states_cbsa(query, forbidden_substrings):
    v = metro_variants(query)
    for bad in forbidden_substrings:
        assert not any(bad in x for x in v), f"{query!r} unexpectedly matched {bad!r}: {v}"


def test_city_state_negative_does_not_shrink_existing_bare_city_match():
    # The pre-existing bare-city fallback for the multi-city CBSA must be
    # unaffected by the new city+state arm (inclusion-only: never fewer rows).
    v = metro_variants("Minneapolis")
    assert "minneapolis-st. paul-bloomington, mn-wi metro area" in v
    assert "st. paul, mn" in v
    assert "bloomington, mn" in v
