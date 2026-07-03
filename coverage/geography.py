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
