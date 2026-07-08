"""Offline suggestion-tier engine (Search Discovery cold start, plan §4.1/§4.2)."""
from search.discovery import propose


def test_propose_cold_start_has_all_tiers():
    result = propose.propose("registered nurse")
    assert result["resolved_soc"] == "29-1141.00"
    assert result["core"], "core must be non-empty for a well-known field"
    assert result["adjacent"], "adjacent must be non-empty for a well-known field"
    assert result["skills"] == []
    for item in result["core"]:
        assert item["source"] in ("onet", "seed")
        assert item["status"] == "suggested"


def test_adjacent_uses_related_soc_not_same_soc_alttitles():
    """Regression guard: adjacent must come from the RELATED-OCCUPATIONS graph
    (different SOCs), never more alt-titles of the resolved SOC itself."""
    result = propose.propose("registered nurse")
    resolved_soc = result["resolved_soc"]
    assert resolved_soc == "29-1141.00"

    related_index = propose._related_occ_index()
    cross_soc_titles = {
        title for related_soc, tier, title in related_index.get(resolved_soc, [])
        if related_soc != resolved_soc
    }
    assert cross_soc_titles, "fixture sanity: the related-occ tsv must have rows for this SOC"

    assert all(item["source"] == "related_soc" for item in result["adjacent"])
    assert any(item["term"] in cross_soc_titles for item in result["adjacent"])

    # Same-SOC alt-titles (the old, flagged weakness) must NOT be how adjacent
    # is populated: the resolved SOC's own alt-titles are a disjoint source.
    same_soc_alt_titles = set(propose._alt_titles_index().get(resolved_soc, []))
    adjacent_terms = {item["term"] for item in result["adjacent"]}
    assert adjacent_terms & cross_soc_titles
    # every adjacent term traces back to some related SOC's alt-title or its
    # own related_title -- never purely from same_soc_alt_titles alone.
    assert not adjacent_terms.issubset(same_soc_alt_titles)


def test_propose_eng_field_reverse_resolves_soc():
    """Engineers (the app's primary audience) are deliberately left SOC-less by
    resolve_soc (eng-like). The reverse alt-title fallback must recover a SOC so
    they still get a real adjacency graph, not empty tiers."""
    for field, expected_soc in [("mechanical engineering", "17-2141.00"),
                                ("software engineer", "15-1252.00")]:
        result = propose.propose(field)
        assert result["resolved_soc"] == expected_soc, field
        assert result["adjacent"], f"{field} must get non-empty adjacent"

        related_index = propose._related_occ_index()
        cross_soc_titles = {
            title for related_soc, tier, title in related_index.get(expected_soc, [])
            if related_soc != expected_soc
        }
        adjacent_terms = {item["term"] for item in result["adjacent"]}
        assert adjacent_terms & cross_soc_titles, f"{field} adjacent must trace to related SOCs"
        assert all(item["source"] == "related_soc" for item in result["adjacent"])
        # source stays honest (still the eng seed profile) despite reverse resolution
        assert result["source"] == "seed", field


def test_propose_generic_field_falls_back():
    result = propose.propose("quantum astrology")
    assert result["source"] == "generic"
    assert result["resolved_soc"] is None
    assert result["core"], "core must never be silently empty"
    assert result["core"][0]["term"] == "quantum astrology"
    assert result["adjacent"] == []
    assert result["exploratory"] == []
    assert result["skills"] == []


def test_propose_offline_no_network():
    # Sanity: runs cleanly under the conftest autouse socket guard (file-only).
    result = propose.propose("mechanical engineering")
    assert isinstance(result, dict)
    assert "core" in result and "resolved_soc" in result


def test_propose_blank_field_uses_resume_text():
    result = propose.propose("", resume_text="worked as a registered nurse on a bedside unit")
    assert result["resolved_soc"] == "29-1141.00" or result["source"] in ("seed", "onet")


def test_propose_never_raises_on_bad_input():
    assert propose.propose(None) is not None
    assert propose.propose(123)["source"] == "generic"   # non-str field -> caught, never raises
    result = propose.propose("")
    assert isinstance(result["core"], list)


def test_keyword_suggest_prefix():
    # "nursing" is itself a curated field-vocab term (exact hit), while many
    # O*NET titles ("Nursing Assistants", "Nursing Instructors...") only share
    # it as a PREFIX -- exercises both match kinds and their ranking.
    results = propose.keyword_suggest("nursing", limit=20)
    assert results
    assert all(r["kind"] in ("field", "title") for r in results)
    lower_terms = [r["term"].casefold() for r in results]
    assert any(t.startswith("nursing") for t in lower_terms)

    exact_idx = [i for i, t in enumerate(lower_terms) if t == "nursing"]
    prefix_idx = [i for i, t in enumerate(lower_terms) if t != "nursing" and t.startswith("nursing")]
    assert exact_idx, "the curated 'nursing' field-vocab term must surface as an exact match"
    assert prefix_idx, "fixture sanity: at least one O*NET title has 'nursing' as a prefix only"
    assert max(exact_idx) < min(prefix_idx)


def test_keyword_suggest_blank_is_empty():
    assert propose.keyword_suggest("") == []
    assert propose.keyword_suggest("   ") == []


def test_keyword_suggest_capped_and_deduped():
    results = propose.keyword_suggest("e", limit=5)
    assert len(results) <= 5
    seen = {(r["term"].casefold(), r["kind"]) for r in results}
    assert len(seen) == len(results)
