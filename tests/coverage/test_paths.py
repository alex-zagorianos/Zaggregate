from coverage._paths import static_path

def test_static_path_points_into_bundle():
    p = static_path("onet_soc_alt_titles.tsv")
    assert p.name == "onet_soc_alt_titles.tsv"
    assert p.parent.name == "data_static"
