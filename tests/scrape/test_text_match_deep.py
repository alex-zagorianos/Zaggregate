from scrape.text_match import keyword_matches, keyword_matches_deep

def test_title_only_still_works():
    assert keyword_matches("controls engineer", "Senior Controls Engineer")
    assert not keyword_matches("controls engineer", "Software Developer")

def test_deep_matches_body_when_title_misses():
    # generic title, but the body mentions the role
    assert keyword_matches_deep("controls engineer",
                                "Engineer II",
                                "You will own PLC controls engineer duties on the line.")

def test_deep_matches_title():
    assert keyword_matches_deep("controls engineer", "Controls Engineer", "")

def test_deep_no_match_anywhere():
    assert not keyword_matches_deep("controls engineer", "Barista", "Make coffee.")
