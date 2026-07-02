"""Remote-only search intent + national-feed localization helpers.

A user whose search location is a bare "Remote" (no concrete metro) used to get
almost nothing from the keyed aggregators: Adzuna geocoded the literal string
"Remote" as a place (-> 0) and USAJobs sent it as ``LocationName`` (-> 0). This
module centralizes the one decision — "is this a remote-only search?" — so every
client applies the SAME rule, and provides the shared metro-localization used by
the national sector RSS feeds (RNJobSite / HigherEdJobs) whose rows are otherwise
national noise that dies at the location gate.

Design intent (plan P0-5 + coverage §4/§5):
  * ``is_remote_only(location)`` is deliberately CONSERVATIVE — it fires only when
    the string carries a remote signal and NO concrete place token. "Cincinnati,
    OH", "Boise, ID", "" (Alex's empty default) all return False, so every
    non-remote search path is byte-identical to before.
  * The national feeds don't fake locality: for a metro-bound user their rows are
    filtered to the user's metro (real localization); for a remote-only user the
    feed is genuinely nationwide, so its rows survive per the user's ``remote_ok``.
"""
from __future__ import annotations

import re

# Remote-signal tokens. A location that is ONLY these (optionally with a US /
# region qualifier or punctuation) is a remote-only intent, not a place.
_REMOTE_TOKENS = frozenset({
    "remote", "anywhere", "wfh", "work from home", "telework", "telecommute",
    "virtual", "distributed",
})

# Qualifiers that commonly ride along with a remote token but are NOT a concrete
# metro ("Remote - US", "US Remote", "Remote (Nationwide)", "Remote, USA").
_REMOTE_QUALIFIERS = frozenset({
    "us", "usa", "u.s.", "u.s.a.", "united states", "nationwide", "national",
    "only", "us-remote", "usremote", "based", "eligible", "friendly", "first",
    "worldwide", "global",
})


def is_remote_only(location: str | None) -> bool:
    """True when ``location`` expresses a remote-only search with no concrete
    metro (so aggregators should query remote-wide instead of geocoding the
    literal token). Conservative: any recognizable place word that isn't a remote
    token/qualifier makes it False, so "Cincinnati, OH", "Boise, ID" and "" are
    all False (non-remote behavior unchanged)."""
    if not location:
        return False
    raw = location.strip().lower()
    if not raw:
        return False
    # Protect known multi-word phrases so they tokenize as one unit, then split
    # on any separator (space/comma/paren/dash/slash/pipe).
    for phrase in ("work from home", "united states"):
        raw = raw.replace(phrase, phrase.replace(" ", "_"))
    words = [w.replace("_", " ") for w in re.split(r"[\s,()\-/|]+", raw) if w]
    if not words:
        return False
    has_remote = False
    for w in words:
        if w in _REMOTE_TOKENS:
            has_remote = True
        elif w in _REMOTE_QUALIFIERS:
            continue
        else:
            # A concrete place/word that is neither a remote token nor a known
            # qualifier -> this is a located search, not remote-only.
            return False
    return has_remote


def remote_region_of(location: str | None) -> str | None:
    """The remote region a remote-only search is scoped to, for tagging national
    rows and gating. Returns 'us' when the string carries a US qualifier (the
    common case), else None (unqualified / worldwide remote)."""
    if not location:
        return None
    raw = location.strip().lower()
    if re.search(r"\b(u\.?s\.?a?|united states|nationwide|national)\b", raw):
        return "us"
    return None


def metro_variant_set(location: str | None) -> set[str]:
    """Lowercased metro-variant tokens for ``location`` (CBSA-based, agnostic),
    used to localize a national feed to the user's metro. Always includes the
    bare entry + bare city so "Boise, ID" also matches a row that says just
    "Boise". Degrades to the bare lowercased forms if the geo bundle is missing —
    never raises."""
    loc = (location or "").strip()
    if not loc:
        return set()
    out = {loc.lower(), loc.split(",")[0].strip().lower()}
    try:
        from coverage.geography import metro_variants
        out |= {v.lower() for v in metro_variants(loc) if v}
    except Exception:
        pass
    return {v for v in out if v}


# "City, ST" (2-letter US state) at the END of a row location, e.g. "Hamilton, OH".
_ROW_STATE_RE = re.compile(r",\s*([A-Za-z]{2})\b\s*$")


def metro_state_set(location: str | None) -> set[str]:
    """Lowercased 2-letter US state codes a metro-bound search spans, for the
    state-aware national-feed filter. A CBSA can span several states (Cincinnati =
    OH-KY-IN), so this returns EVERY member state, not just the principal city's.

    Sources, unioned: (a) the target's own explicit state token (via
    search_engine's abbrev table — "Columbus, OH" -> {"oh"}); (b) every state in
    the CBSA title's multi-state suffix for the matched metro ("Cincinnati, OH-KY-IN
    Metro Area" -> {"oh","ky","in"}). Empty/remote/unresolvable -> empty set (the
    caller then falls open, never state-filtering)."""
    loc = (location or "").strip()
    if not loc:
        return set()
    low = loc.lower()
    states: set[str] = set()
    target_st: str | None = None
    # (a) the target's own state token — this ANCHORS which same-name CBSA we pick.
    try:
        from search.search_engine import _STATE_ABBREVS
        toks = {t.strip().rstrip(",.") for t in low.replace(",", " ").split()}
        abbrevs = set(_STATE_ABBREVS.values())
        for t in toks:
            if t in abbrevs:
                target_st = t
        for full, ab in _STATE_ABBREVS.items():
            if full in low:
                target_st = ab
    except Exception:
        target_st = None
    if target_st:
        states.add(target_st)
    # (b) the matched CBSA's member states. A bare city name repeats across states
    # (Columbus OH/GA/IN/MS/NE), so anchor on the target's own state: pick the CBSA
    # whose principal city matches AND whose title suffix INCLUDES the target state.
    # Without a target state (bare "Cincinnati") fall back to the single best
    # principal-city title match.
    try:
        from coverage.geography import _rows
        city = low.split(",")[0].strip()

        def _suffix_states(title: str) -> set[str]:
            # "cincinnati, oh-ky-in metro area" -> {"oh","ky","in"}.
            suffix = title.split(",")[-1].strip()
            suffix = re.sub(r"\b(metro|micro)\s+area\b", "", suffix).strip()
            return {p.strip() for p in suffix.split("-")
                    if len(p.strip()) == 2 and p.strip().isalpha()}

        for r in _rows():
            title = (r.get("cbsa_title") or "").lower()
            pc = (r.get("principal_city") or "").lower()
            if not (city and city == pc):
                continue
            sfx = _suffix_states(title)
            if target_st:
                # Only the CBSA whose title actually spans the target's state.
                if target_st in sfx:
                    states |= sfx
            else:
                # Bare-city target (no state): any principal-city match contributes
                # (best-effort — we can't disambiguate same-name metros).
                states |= sfx
    except Exception:
        pass
    return states


def row_state_of(row_location: str | None) -> str | None:
    """The lowercased 2-letter US state a national-feed row's location ends with
    ("Hamilton, OH" -> "oh", "Edgewood, KY" -> "ky"), or None when the row carries
    no trailing "City, ST" (bare city / remote / malformed). Pure, no network."""
    m = _ROW_STATE_RE.search((row_location or "").strip())
    return m.group(1).lower() if m else None


def national_row_locality(
    row_location: str,
    metro_variants: set[str] | None,
    metro_states: set[str] | None,
) -> str:
    """Classify a national-feed row for a metro-bound search, STATE-AWARE:

      'metro'  — the row is in the user's metro (a variant substring hit whose
                 row state, when present, is one of the metro's member states);
      'state'  — the row is out-of-metro but in a metro member state (a real,
                 commutable/in-state locality worth keeping on fail-open);
      'other'  — the row is elsewhere (different state, or a same-name city in a
                 non-member state — the "Columbus, GA" for a "Columbus, OH" seeker
                 false-keep this fixes);
      'remote' — the row is itself remote (always kept).

    metro_variants None (unresolvable target) => everything is 'metro' (fail open,
    unchanged from the old no-filter behavior). metro_states empty (no resolvable
    state) => the variant substring test alone decides metro vs other (degrades to
    the old bare-substring behavior rather than dropping everything)."""
    low = (row_location or "").lower().strip()
    if not low:
        return "metro"                       # no location -> don't drop (fail open)
    if "remote" in low:
        return "remote"
    if metro_variants is None:
        return "metro"                       # unresolvable target -> keep all
    rs = row_state_of(row_location)
    variant_hit = any(v in low for v in metro_variants)
    if variant_hit:
        # A bare-city variant substring hit is only trusted when the row's state
        # (if it names one) is a member state — this rejects "Columbus, GA" for a
        # "Columbus, OH" seeker while keeping "Columbus, OH". No row state / no
        # resolved metro states -> trust the substring (old behavior).
        if not rs or not metro_states or rs in metro_states:
            return "metro"
        # variant matched but the row's state is NOT a member state -> a same-name
        # out-of-area city (e.g. "Columbus, GA" for a "Columbus, OH" seeker).
        return "other"
    # Not a metro variant: keep it only if it's in a metro member state.
    if rs and metro_states and rs in metro_states:
        return "state"
    return "other"


def tag_nationwide_remote(loc: str | None, region: str | None = "us") -> str:
    """Tag a national-feed row so the location gate treats it per ``remote_ok``.

    Used ONLY for the remote-only path of the national sector feeds, whose rows
    are genuinely nationwide (not a specific metro the user could match). Adds a
    'Remote' marker (and a US qualifier when region='us') WITHOUT discarding any
    real location the row carried — 'Houston TX' becomes 'Houston TX (Remote, US)'
    so the gate's remote branch keeps it while the origin city is still visible.
    An empty/None location becomes a plain 'Remote'/'Remote, US'."""
    base = (loc or "").strip()
    marker = "Remote, US" if region == "us" else "Remote"
    if not base:
        return marker
    if "remote" in base.lower():
        return base
    return f"{base} ({marker})"
