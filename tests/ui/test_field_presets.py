"""QW-1 / §6.2 — the wizard field picker's validated presets.

Each preset must emit a CANONICAL industry token that (a) resolves to a
non-generic industry_profile (so Muse/Jobicy source routing + query synonyms
actually turn on — the whole point of the picker) and (b) round-trips through
the token-aware registry matcher (so a user's seeded employers for that field
are actually searched, the P0-1 bug the picker exists to prevent).

This is the regression contract behind the picker: change a preset token and
this test proves it still routes correctly before it can ship.
"""
import industry_profile as ip
import scrape.company_registry as cr
from ui import setup_wizard as sw


def test_every_preset_resolves_to_non_generic_profile():
    """A preset token must NOT fall through to the generic (no-routing) tier —
    that would leave the user with the exact broad-but-unrouted behavior the
    free-text box gave. 'seed'/'onet'/'user' are all fine; 'generic' fails."""
    for tok in sw.preset_tokens():
        prof = ip.resolve(tok)
        assert prof.source != "generic", (
            f"preset token {tok!r} routes to generic (no source routing) — "
            f"pick a token that hits a seed rule or O*NET occupation")


def test_every_preset_token_self_matches_registry_tag():
    """The canonical token, once normalized to a company tag, must match itself
    under the registry's token-aware matcher. This is the P0-1 regression: a
    multi-word field ('mechanical engineering', 'data analytics') must match a
    company tagged with its normalized form, not silently drop every seed."""
    for tok in sw.preset_tokens():
        norm = cr._normalize_industry(tok)
        assert cr._industry_tag_match(tok, norm), (
            f"preset token {tok!r} does not match its own normalized tag "
            f"{norm!r} — seeded employers for this field would never be searched")


def test_preset_tokens_are_lowercase_and_nonblank():
    toks = sw.preset_tokens()
    assert toks, "there must be at least one validated preset"
    for tok in toks:
        assert tok and tok == tok.strip().lower()
    # No accidental duplicate tokens.
    assert len(toks) == len(set(toks))


def test_other_preset_is_the_free_text_escape_hatch():
    """'Other' maps to an empty token (free-text takes over) and is excluded from
    preset_tokens() so it's never asserted as a routed field."""
    assert sw._OTHER_PRESET in sw._PRESET_LABELS
    assert sw._PRESET_TO_TOKEN[sw._OTHER_PRESET] == ""
    assert "" not in sw.preset_tokens()


def test_token_to_preset_label_roundtrips():
    """A configured field token pre-selects the matching dropdown row; an
    unlisted field falls to 'Other'; blank selects nothing."""
    for label, tok in sw._FIELD_PRESETS:
        if tok:
            assert sw._token_to_preset_label(tok) == label
            # case/space-insensitive
            assert sw._token_to_preset_label(tok.upper()) == label
    assert sw._token_to_preset_label("underwater basket weaving") == sw._OTHER_PRESET
    assert sw._token_to_preset_label("") == ""


def test_personas_are_all_represented():
    """The eight tested general-user personas each have a preset (QW-1: every
    non-tech persona flagged their field was unrepresented in the old examples)."""
    labels = " | ".join(sw._PRESET_LABELS).lower()
    for needle in ("software", "mechanical", "consulting", "marketing",
                   "warehouse", "data", "teaching", "nursing", "controls"):
        assert needle in labels, f"no preset covers {needle!r}"
