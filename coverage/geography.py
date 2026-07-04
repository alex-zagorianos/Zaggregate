import csv, functools
from coverage._paths import static_path

@functools.lru_cache(maxsize=1)
def _rows() -> list[dict]:
    # Degrade gracefully: a missing/unreadable data file (e.g. data_static not
    # bundled in a frozen build) must NOT crash the inbox - fall back to an empty
    # CBSA table so metro_variants/classify still work on substring matching.
    try:
        with static_path("cbsa_delineation.csv").open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


# US state abbreviation -> full name, for satellite-city variant strings. Local
# copy (search.search_engine has one too) so coverage/ keeps zero search deps.
_STATE_NAMES = {
    "al": "alabama", "ak": "alaska", "az": "arizona", "ar": "arkansas",
    "ca": "california", "co": "colorado", "ct": "connecticut", "de": "delaware",
    "fl": "florida", "ga": "georgia", "hi": "hawaii", "id": "idaho",
    "il": "illinois", "in": "indiana", "ia": "iowa", "ks": "kansas",
    "ky": "kentucky", "la": "louisiana", "me": "maine", "md": "maryland",
    "ma": "massachusetts", "mi": "michigan", "mn": "minnesota",
    "ms": "mississippi", "mo": "missouri", "mt": "montana", "ne": "nebraska",
    "nv": "nevada", "nh": "new hampshire", "nj": "new jersey",
    "nm": "new mexico", "ny": "new york", "nc": "north carolina",
    "nd": "north dakota", "oh": "ohio", "ok": "oklahoma", "or": "oregon",
    "pa": "pennsylvania", "ri": "rhode island", "sc": "south carolina",
    "sd": "south dakota", "tn": "tennessee", "tx": "texas", "ut": "utah",
    "vt": "vermont", "va": "virginia", "wa": "washington",
    "wv": "west virginia", "wi": "wisconsin", "dc": "district of columbia",
}


@functools.lru_cache(maxsize=1)
def _satellites() -> dict[str, list[tuple[str, str]]]:
    """cbsa_code -> [(city, state_abbrev), ...] from metro_satellites.csv — the
    suburb/satellite municipalities of a metro that job postings name instead of
    the principal city ("Mason, OH", "Florence, KY" are Cincinnati-metro jobs).
    Same graceful degradation as _rows(): missing file -> no satellites."""
    try:
        with static_path("metro_satellites.csv").open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    except OSError:
        return {}
    out: dict[str, list[tuple[str, str]]] = {}
    for r in rows:
        city = (r.get("city") or "").strip().casefold()
        st = (r.get("state") or "").strip().casefold()
        if city and st:
            out.setdefault((r.get("cbsa_code") or "").strip(), []).append((city, st))
    return out

def resolve_cbsa(city: str | None, state: str | None) -> str | None:
    if not city or not state:
        return None
    c, s = city.strip().casefold(), state.strip().casefold()
    for r in _rows():
        if r["principal_city"].casefold() == c and r["state"].casefold() == s:
            return r["cbsa_code"]
    return None

def metro_variants(area: str) -> set[str]:
    out = {area.strip().casefold()}
    a = area.strip().casefold()
    for r in _rows():
        title = r["cbsa_title"].casefold()
        if a in title or title in a:
            out.add(title)
            out.add(r["principal_city"].casefold())
            bare = title.split(",")[0].replace(" metro area", "").strip()
            out.add(bare)
            # Multi-principal-city titles ("minneapolis-st. paul-bloomington")
            # carry every principal city hyphen-joined — add each one so a
            # posting naming any of them counts as metro. Additive only
            # (inclusion over precision); single-city titles are unchanged.
            for piece in bare.split("-"):
                piece = piece.strip()
                if len(piece) >= 3:
                    out.add(piece)
            # Satellite municipalities (metro_satellites.csv): postings name
            # the suburb, not the principal city ("Mason, OH" is a Cincinnati
            # job). Emitted WITH the state suffix in both abbrev and full-name
            # form ("florence, ky" / "florence, kentucky") — never bare, so an
            # ambiguous name can't cross-match another state (Aurora CO vs
            # Aurora IN, Loveland CO, Alexandria VA...). "city, oh" is itself
            # a prefix-substring of "city, ohio", but both forms are emitted
            # anyway to keep the matching rule dumb and obvious.
            for city, st in _satellites().get(r["cbsa_code"], []):
                out.add(f"{city}, {st}")
                full = _STATE_NAMES.get(st)
                if full:
                    out.add(f"{city}, {full}")
    # Non-US / unrecognized-metro fallback (S35): when NO US CBSA row matched, a
    # "City, Country" area (e.g. "London, United Kingdom") kept only its exact
    # string, so a posting listed as bare "London" or "London, England" was
    # bucketed 'elsewhere' and hidden from an international user's default Inbox
    # view. Add the bare city token so local matching works abroad. Guarded on
    # the no-CBSA-match case, so every US metro stays byte-identical.
    if len(out) == 1 and "," in a:
        city = a.split(",")[0].strip()
        if len(city) >= 3:
            out.add(city)
    return {v for v in out if v}
