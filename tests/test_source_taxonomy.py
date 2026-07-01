"""The Muse / Jobicy were hardcoded to the engineering category server-side, so a
non-eng seeker got 0 results. source_taxonomy derives the category from the active
project's industry while staying byte-identical for engineering / unset."""
from config import THEMUSE_CATEGORIES
from search import source_taxonomy as st


def test_themuse_eng_default_is_byte_identical():
    assert st.themuse_categories("") == list(THEMUSE_CATEGORIES)
    assert st.themuse_categories("controls_engineering") == list(THEMUSE_CATEGORIES)
    assert st.themuse_categories("software") == list(THEMUSE_CATEGORIES)


def test_themuse_health_requests_healthcare():
    cats = st.themuse_categories("health_informatics")
    assert "Healthcare" in cats
    assert "Engineering" not in cats


def test_themuse_unmapped_noneng_sends_no_filter():
    # Unknown non-eng field → [] so the client fetches ALL categories (then
    # keyword-filters) instead of a guessed-wrong category returning 0.
    assert st.themuse_categories("underwater basket weaving") == []


def test_jobicy_eng_default_is_engineering():
    assert st.jobicy_industry("") == "engineering"
    assert st.jobicy_industry("robotics") == "engineering"


def test_jobicy_health_omits_param():
    # Jobicy's 'medical' slug returns 0; omitting the param (None) fetches all
    # remote jobs, which is strictly better than a 0-yield slug.
    assert st.jobicy_industry("health_informatics") is None


def test_jobicy_finance_maps():
    assert st.jobicy_industry("finance") == "finance"


def test_active_industry_explicit_wins():
    assert st.active_industry("finance") == "finance"
    assert st.active_industry("") == ""
