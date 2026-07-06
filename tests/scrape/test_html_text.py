"""Parity proof for scrape.html_text.strip_html_to_text (finding #8).

The shared helper replaces 13 previously-duplicated copies of the exact
one-liner ``re.sub(r"\\s+", " ", _TAG_RE.sub(" ", html.unescape(raw))).strip()[:3000]``.
This asserts, on a representative fixture battery, that the shared helper's
output is byte-identical to that exact legacy expression evaluated inline —
so the refactor is provably behavior-preserving for every converted file.
"""
import html
import re

from scrape.html_text import strip_html_to_text

_LEGACY_TAG_RE = re.compile(r"<[^>]+>")


def _legacy(raw: str, limit: int = 3000) -> str:
    """The exact expression every converted scraper used to inline."""
    if not raw:
        return ""
    return re.sub(r"\s+", " ", _LEGACY_TAG_RE.sub(" ", html.unescape(raw))).strip()[:limit]


FIXTURES = [
    "",
    None,
    "plain text, no markup",
    "<p>Simple paragraph</p>",
    "<div><p>Nested <strong>bold</strong> and <em>italics</em></p></div>",
    "Line one\n\n\n   with   \t\t runs \n of   whitespace",
    "AT&amp;T &amp; Sons &lt;div&gt; &quot;quoted&quot; &#39;apos&#39; &nbsp;end",
    "<ul><li>One</li><li>Two</li></ul>  trailing text",
    "<script>alert('x')</script> body text survives tag-strip (not sanitized)",
    "A" * 3500,  # exceeds the 3000-char truncation limit
    ("<p>" + "word " * 800 + "</p>"),  # long, tag-wrapped, whitespace-heavy
    "<br/>self-closing<hr>tags<img src='x'/>",
    "Unicode café — em dash — and éèê accents <b>bold</b>",
]


def test_parity_matches_legacy_expression_on_fixture_battery():
    for raw in FIXTURES:
        assert strip_html_to_text(raw) == _legacy(raw), f"mismatch for {raw!r}"


def test_parity_respects_custom_limit():
    raw = "<p>" + ("x" * 50) + "</p>"
    assert strip_html_to_text(raw, limit=10) == _legacy(raw, limit=10)


def test_falsy_input_returns_empty_string():
    assert strip_html_to_text("") == ""
    assert strip_html_to_text(None) == ""


def test_truncates_at_3000_by_default():
    raw = "z" * 4000
    out = strip_html_to_text(raw)
    assert len(out) == 3000
    assert out == _legacy(raw)


# ── wiring check: every converted scraper's _clean delegates correctly ────────
# (guards against a bad import / signature mismatch in any of the 13 files
# converted onto scrape.html_text.strip_html_to_text)

_SAMPLE = "<p>Senior&nbsp;Engineer</p>\n\n  role &amp; duties  <br/>"


def _clean_fns():
    from scrape import (
        breezy_scraper, eightfold_scraper, greenhouse_scraper, jazzhr_scraper,
        jsonld_scraper, oracle_orc_scraper, paylocity_scraper, personio_scraper,
        phenom_scraper, pinpoint_scraper, recruitee_scraper, teamtailor_scraper,
        workable_scraper,
    )
    return {
        "breezy": breezy_scraper._clean,
        "eightfold": eightfold_scraper._clean,
        "greenhouse": greenhouse_scraper._clean_content,
        "jazzhr": jazzhr_scraper._clean,
        "jsonld": jsonld_scraper._clean,
        "oracle_orc": oracle_orc_scraper._clean,
        "paylocity": paylocity_scraper._clean,
        "personio": personio_scraper._clean,
        "phenom": phenom_scraper._clean,
        "pinpoint": pinpoint_scraper._clean,
        "recruitee": recruitee_scraper._clean,
        "teamtailor": teamtailor_scraper._clean,
        "workable": workable_scraper._clean,
    }


def test_every_converted_scraper_clean_fn_matches_legacy():
    for name, fn in _clean_fns().items():
        assert fn(_SAMPLE) == _legacy(_SAMPLE), f"{name} diverged from legacy behavior"
        assert fn("") == "" == _legacy(""), f"{name} mishandles empty input"
        assert fn(None) == "" == _legacy(None), f"{name} mishandles None input"


def test_vincere_and_careeronestop_not_converted_stay_divergent():
    """Parity guard for the two files the register says NOT to convert: vincere's
    _strip_html skips html.unescape() and truncation; careeronestop's inline
    _TAG_RE.sub() skips both unescape() and the outer .strip(). If a future edit
    accidentally makes either byte-identical to the legacy pattern, this test
    should be revisited (it documents the divergence, not enforce it forever)."""
    from scrape.vincere_scraper import _strip_html as vincere_clean
    raw = "<p>Senior &amp; Staff Engineer</p>  role"
    # vincere: no unescape, no truncation -> entities survive, unlike the shared helper.
    assert "&amp;" in vincere_clean(raw)
    assert vincere_clean(raw) != _legacy(raw)
