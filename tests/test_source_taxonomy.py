"""The Muse / Jobicy were hardcoded to the engineering slice server-side, so a
non-eng seeker got 0 results. source_taxonomy now delegates to industry_profile,
deriving the category from the active project's field."""
import industry_profile
from search import source_taxonomy as st


def setup_function(_):
    industry_profile.clear_cache()


def test_themuse_eng_default_uses_corrected_categories():
    # eng/empty -> the CORRECTED Muse eng categories. (The old code sent the
    # invalid string "Engineering" which returns 0; the real names are these.)
    for q in ("", "controls_engineering", "software"):
        assert st.themuse_categories(q) == ["Software Engineering", "Science and Engineering"]


def test_themuse_health_requests_healthcare():
    cats = st.themuse_categories("health_informatics")
    assert "Healthcare" in cats
    assert "Software Engineering" not in cats


def test_themuse_unmapped_noneng_sends_no_filter():
    assert st.themuse_categories("underwater basket weaving") == []


def test_jobicy_eng_default_is_engineering():
    assert st.jobicy_industry("") == "engineering"
    assert st.jobicy_industry("robotics") == "engineering"


def test_jobicy_health_skips():
    # Jobicy's medical slug returns 0; None => the client skips it.
    assert st.jobicy_industry("health_informatics") is None


def test_jobicy_finance_maps():
    assert st.jobicy_industry("finance") == "finance"


def test_active_industry_explicit_wins():
    assert st.active_industry("finance") == "finance"
    assert st.active_industry("") == ""
