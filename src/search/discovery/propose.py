"""Offline suggestion tiers (Search Discovery, cold start — plan §4.1/§4.2).

Pure: no DB writes, no network. Composes `industry_profile.resolve()` (SOC/seed
routing) with two bundled O*NET tsvs to produce core/adjacent/exploratory
keyword candidates for a free-text field. The API layer (not this module) is
responsible for feeding the result into `search.discovery.pool.upsert_terms`.

Adjacent MUST come from the cross-occupation relatedness graph
(onet_related_occupations.tsv), not more alt-titles of the same SOC — that was
the #1 flagged weakness in the base cold-start design (see plan §4.2 point 3).
"""
from __future__ import annotations

import bisect

import industry_profile
from coverage._paths import static_path

_ALT_TITLES_FILE = "onet_soc_alt_titles.tsv"
_RELATED_OCC_FILE = "onet_related_occupations.tsv"

_TIER_HINT = {"Primary-Short": "primary_short", "Primary-Long": "primary_long",
              "Supplemental": "supplemental"}

# ── lazy, process-wide indices (51k/18k rows — fine to hold in memory once) ───
_alt_by_soc: dict[str, list[str]] | None = None          # soc -> [alt_title, ...]
_alt_sorted: list[tuple[str, str, str]] | None = None    # (lower_title, soc, title), sorted
_alt_to_soc: dict[str, str] | None = None                # lower_alt_title -> soc (reverse lookup)
_related_by_soc: dict[str, list[tuple[str, str, str]]] | None = None  # soc -> [(related_soc, tier, related_title)]


def _read_tsv_rows(name: str, min_cols: int):
    """Yield tab-split rows from a bundled data_static tsv, skipping the two
    `#`-prefixed header lines and any short/malformed row. Never raises — a
    missing/corrupt file just yields nothing (caller degrades to empty tiers)."""
    try:
        text = static_path(name).read_text(encoding="utf-8")
    except Exception:
        return
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) < min_cols:
            continue
        yield cols


def _alt_titles_index() -> dict[str, list[str]]:
    global _alt_by_soc, _alt_sorted, _alt_to_soc
    if _alt_by_soc is not None:
        return _alt_by_soc
    by_soc: dict[str, list[str]] = {}
    sortable: list[tuple[str, str, str]] = []
    to_soc: dict[str, str] = {}
    for alt, soc, _soc_title in _read_tsv_rows(_ALT_TITLES_FILE, 3):
        by_soc.setdefault(soc, []).append(alt)
        sortable.append((alt.casefold(), soc, alt))
        to_soc.setdefault(alt.casefold(), soc)   # first occurrence wins
    sortable.sort()
    _alt_by_soc = by_soc
    _alt_sorted = sortable
    _alt_to_soc = to_soc
    return _alt_by_soc


def _soc_for_title(title: str) -> str | None:
    """EXACT (case-insensitive) alt-title -> SOC reverse lookup. No fuzzy match —
    keeps the O*NET exact-match routing discipline. None when the string isn't a
    literal O*NET alternate title."""
    key = (title or "").strip().casefold()
    if not key:
        return None
    if _alt_to_soc is None:
        _alt_titles_index()
    return (_alt_to_soc or {}).get(key)


def _alt_titles_sorted() -> list[tuple[str, str, str]]:
    if _alt_sorted is None:
        _alt_titles_index()
    return _alt_sorted or []


def _related_occ_index() -> dict[str, list[tuple[str, str, str]]]:
    global _related_by_soc
    if _related_by_soc is not None:
        return _related_by_soc
    by_soc: dict[str, list[tuple[str, str, str]]] = {}
    for soc, related_soc, tier, related_title in _read_tsv_rows(_RELATED_OCC_FILE, 4):
        if related_soc == soc:      # guard: relatedness graph should have no self-loops
            continue
        by_soc.setdefault(soc, []).append((related_soc, tier, related_title))
    _related_by_soc = by_soc
    return _related_by_soc


def _reset_caches() -> None:
    """Test hook: drop the lazy indices so a monkeypatched static_path is picked
    up fresh. Not part of the public API."""
    global _alt_by_soc, _alt_sorted, _alt_to_soc, _related_by_soc
    _alt_by_soc = _alt_sorted = _alt_to_soc = _related_by_soc = None


def _dedupe_cap(items: list[dict], limit: int) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for it in items:
        term = it["term"]
        key = term.casefold()
        if not term or key in seen:
            continue
        seen.add(key)
        out.append(it)
        if len(out) >= limit:
            break
    return out


def _field_from_resume(resume_text: str) -> str:
    """Best-effort field guess from résumé text when `field` is blank: token-
    overlap against the same seed-rule vocabularies `industry_profile.resolve`
    uses internally. Offline, no NLP deps. No overlap (or blank text) -> ""."""
    text_tokens = set(industry_profile._tokens(resume_text or ""))
    if not text_tokens:
        return ""
    best_hits: set[str] = set()
    for rule_tokens, _knobs in industry_profile._RULES:
        hits = rule_tokens & text_tokens
        if len(hits) > len(best_hits):
            best_hits = hits
    return " ".join(sorted(best_hits))


def propose(field: str = "", *, resume_text: str = "", limit_per_tier: int = 25) -> dict:
    """Offline suggestion tiers for a free-text field (résumé text optional, used
    only to help resolve the field when `field` is blank). Returns:
      {
        "core":        [{"term": str, "source": "onet"|"seed", "status": "suggested"}...],
        "adjacent":    [{"term": str, "source": "related_soc", "tier_hint": "primary_short"|"primary_long"}...],
        "exploratory": [{"term": str, "source": "related_soc", "tier_hint": "supplemental"|"major_group"}...],
        "skills":      [],   # deferred — onet_technology_skills.tsv isn't bundled yet
        "resolved_soc": str | None,
        "source": "seed"|"onet"|"generic"|"user",
      }
    Fully offline, zero network. Never raises."""
    try:
        effective_field = (field or "").strip()
        if not effective_field:
            effective_field = _field_from_resume(resume_text)

        profile = industry_profile.resolve(effective_field)
        soc_info = industry_profile.resolve_soc(effective_field)
        resolved_soc = (soc_info or {}).get("code")

        # Reverse-SOC fallback: resolve_soc() deliberately returns None for
        # eng/tech fields (the app treats them as "eng-like/unresolved"), which
        # would strand engineers -- the primary audience -- with empty
        # adjacent/exploratory tiers. Recover a confident SOC by an EXACT
        # (case-insensitive) alt-title lookup, trying the raw field text first,
        # then each curated core synonym (first hit wins). Never fuzzy. Purely
        # additive: any field that already resolved a SOC skips this untouched.
        if not resolved_soc:
            for candidate in (effective_field, *profile.query_synonyms):
                soc = _soc_for_title(candidate)
                if soc:
                    resolved_soc = soc
                    break

        # ── core: curated query_synonyms + O*NET alt-titles for the resolved SOC ──
        core: list[dict] = [{"term": t, "source": "seed", "status": "suggested"}
                             for t in profile.query_synonyms]
        if resolved_soc:
            alt_index = _alt_titles_index()
            for alt in alt_index.get(resolved_soc, []):
                core.append({"term": alt, "source": "onet", "status": "suggested"})
        core = _dedupe_cap(core, limit_per_tier)
        if not core and effective_field:
            # Never silently empty: echo the field itself so the user always
            # sees at least their own typed term as a startable core keyword.
            core = [{"term": effective_field, "source": "seed", "status": "suggested"}]

        # ── adjacent: Primary-Short/Primary-Long related occupations (cross-SOC) ──
        adjacent: list[dict] = []
        if resolved_soc:
            related_index = _related_occ_index()
            alt_index = _alt_titles_index()
            for related_soc, tier, related_title in related_index.get(resolved_soc, []):
                if tier not in ("Primary-Short", "Primary-Long"):
                    continue
                hint = _TIER_HINT[tier]
                adjacent.append({"term": related_title, "source": "related_soc",
                                  "tier_hint": hint})
                # Enrich with a couple of the related SOC's own alt-titles too —
                # still cross-SOC (not the resolved SOC's alt-titles).
                for extra in alt_index.get(related_soc, [])[:2]:
                    if extra == related_title:
                        continue
                    adjacent.append({"term": extra, "source": "related_soc",
                                      "tier_hint": hint})
        adjacent = _dedupe_cap(adjacent, limit_per_tier)

        # ── exploratory: Supplemental related occs, else same-major-group titles ──
        exploratory: list[dict] = []
        if resolved_soc:
            related_index = _related_occ_index()
            for related_soc, tier, related_title in related_index.get(resolved_soc, []):
                if tier == "Supplemental":
                    exploratory.append({"term": related_title, "source": "related_soc",
                                         "tier_hint": "supplemental"})
            if not exploratory:
                major = resolved_soc.split("-")[0]
                if major in industry_profile.SOC_MAJOR_GROUPS:
                    alt_index = _alt_titles_index()
                    for soc, titles in alt_index.items():
                        if soc == resolved_soc or not soc.startswith(major + "-"):
                            continue
                        for t in titles[:1]:
                            exploratory.append({"term": t, "source": "related_soc",
                                                 "tier_hint": "major_group"})
                        if len(exploratory) >= limit_per_tier:
                            break
        exploratory = _dedupe_cap(exploratory, limit_per_tier)

        return {
            "core": core,
            "adjacent": adjacent,
            "exploratory": exploratory,
            "skills": [],  # TODO: onet_technology_skills.tsv not bundled yet (plan §4.1/§4.2 point 5)
            "resolved_soc": resolved_soc,
            "source": profile.source,
        }
    except Exception:
        return {"core": [], "adjacent": [], "exploratory": [], "skills": [],
                "resolved_soc": None, "source": "generic"}


def _field_vocab() -> list[tuple[str, str | None]]:
    """(term, soc) pairs for the typeahead's 'field' vocabulary: every seed-rule
    trigger token plus the curated exact-alias phrases (soc set only for the
    latter — a bare rule token has no single fixed SOC)."""
    seen: dict[str, str | None] = {}
    for rule_tokens, _knobs in industry_profile._RULES:
        for tok in rule_tokens:
            seen.setdefault(tok, None)
    for phrase, (soc, _title) in industry_profile._SOC_ALIASES.items():
        seen[phrase] = soc
    return sorted(seen.items())


def keyword_suggest(q: str, limit: int = 20) -> list[dict]:
    """Typeahead over the field/title vocabulary: EXACT + PREFIX matches only
    (never fuzzy — keeps the O*NET exact-match discipline). Returns
    [{"term": str, "soc": str|None, "kind": "field"|"title"}...] ranked exact-first
    then prefix, deduped, capped at `limit`. Blank q -> []."""
    try:
        needle = (q or "").strip().casefold()
        if not needle:
            return []

        exact: list[dict] = []
        prefix: list[dict] = []

        for term, soc in _field_vocab():
            if term == needle:
                exact.append({"term": term, "soc": soc, "kind": "field"})
            elif term.startswith(needle):
                prefix.append({"term": term, "soc": soc, "kind": "field"})

        sorted_titles = _alt_titles_sorted()
        lo = bisect.bisect_left(sorted_titles, (needle,))
        hi = bisect.bisect_left(sorted_titles, (needle + "￿",))
        for lower_title, soc, original in sorted_titles[lo:hi]:
            entry = {"term": original, "soc": soc, "kind": "title"}
            if lower_title == needle:
                exact.append(entry)
            else:
                prefix.append(entry)

        combined = exact + prefix
        return _dedupe_cap_typeahead(combined, limit)
    except Exception:
        return []


def _dedupe_cap_typeahead(items: list[dict], limit: int) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for it in items:
        key = (it["term"].casefold(), it["kind"])
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
        if len(out) >= limit:
            break
    return out
