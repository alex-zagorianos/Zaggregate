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
