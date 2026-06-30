"""Wave 5a - Add-Companies comma form."""
from scrape.ats_detect import parse_line


def test_comma_name_url_form():
    e = parse_line("Vertical Aerospace, https://boards.greenhouse.io/verticalaerospace")
    assert e is not None
    assert e.ats_type == "greenhouse"
    assert e.slug == "verticalaerospace"
    assert e.name == "Vertical Aerospace"


def test_bare_url_still_works():
    e = parse_line("https://jobs.lever.co/anduril")
    assert e is not None and e.ats_type == "lever" and e.slug == "anduril"


def test_pipe_form_still_works():
    e = parse_line("Acme | https://boards.greenhouse.io/acme")
    assert e is not None and e.ats_type == "greenhouse" and e.slug == "acme"


def test_blank_and_comment_ignored():
    assert parse_line("") is None
    assert parse_line("# a comment") is None
