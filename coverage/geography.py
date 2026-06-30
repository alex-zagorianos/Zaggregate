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
    return {v for v in out if v}
