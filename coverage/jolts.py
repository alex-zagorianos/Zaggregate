from __future__ import annotations
from dataclasses import dataclass

_PASS_LO, _PASS_HI = 0.05, 5.0

@dataclass
class JoltsResult:
    expected_openings: int | None
    ratio: float | None
    verdict: str  # "pass" | "fail" | "skip"

def jolts_gate(area: str, naics: str | None, our_count: int, *, api_key: str | None = None) -> JoltsResult:
    if not api_key:
        return JoltsResult(None, None, "skip")
    # BLS JOLTS publishes national and STATE openings, but NOT metro/MSA (those
    # exist only as unofficial research estimates). If the area doesn't resolve to
    # a whole US state, honestly skip rather than silently comparing a metro slice
    # against the national series (the old bug: _series_id ignored its arguments).
    series = _series_id(area, naics)
    if series is None:
        return JoltsResult(None, None, "skip")
    try:
        expected = _fetch_expected_openings(series, area, naics, api_key)
    except Exception:
        return JoltsResult(None, None, "skip")
    if not expected:
        return JoltsResult(None, None, "skip")
    ratio = our_count / expected
    verdict = "pass" if _PASS_LO <= ratio <= _PASS_HI else "fail"
    return JoltsResult(expected_openings=expected, ratio=ratio, verdict=verdict)

def _fetch_expected_openings(series: str, area: str, naics: str | None, api_key: str) -> int | None:
    import requests
    from search.http_util import FileCache, cache_key, RateLimiter
    cache = FileCache("jolts")
    key = cache_key("jolts", series)
    cached = cache.get(key)
    if cached is not None:
        return cached.get("openings")
    RateLimiter(50).acquire()
    resp = requests.post(
        "https://api.bls.gov/publicAPI/v2/timeseries/data/",
        json={"seriesid": [series], "registrationkey": api_key},
        timeout=30,
    )
    resp.raise_for_status()
    series_data = resp.json().get("Results", {}).get("series", [])
    if not series_data or not series_data[0].get("data"):
        return None
    openings = int(float(series_data[0]["data"][0]["value"])) * 1000
    cache.put(key, {"openings": openings})
    return openings


# US state -> FIPS (JOLTS state series encode the 2-digit state FIPS in the area
# field). Metros/other strings that don't resolve to a whole state get None.
_STATE_FIPS = {
    "al": "01", "ak": "02", "az": "04", "ar": "05", "ca": "06", "co": "08",
    "ct": "09", "de": "10", "dc": "11", "fl": "12", "ga": "13", "hi": "15",
    "id": "16", "il": "17", "in": "18", "ia": "19", "ks": "20", "ky": "21",
    "la": "22", "me": "23", "md": "24", "ma": "25", "mi": "26", "mn": "27",
    "ms": "28", "mo": "29", "mt": "30", "ne": "31", "nv": "32", "nh": "33",
    "nj": "34", "nm": "35", "ny": "36", "nc": "37", "nd": "38", "oh": "39",
    "ok": "40", "or": "41", "pa": "42", "ri": "44", "sc": "45", "sd": "46",
    "tn": "47", "tx": "48", "ut": "49", "vt": "50", "va": "51", "wa": "53",
    "wv": "54", "wi": "55", "wy": "56",
}
_STATE_NAMES = {
    "alabama": "al", "alaska": "ak", "arizona": "az", "arkansas": "ar",
    "california": "ca", "colorado": "co", "connecticut": "ct", "delaware": "de",
    "district of columbia": "dc", "florida": "fl", "georgia": "ga", "hawaii": "hi",
    "idaho": "id", "illinois": "il", "indiana": "in", "iowa": "ia", "kansas": "ks",
    "kentucky": "ky", "louisiana": "la", "maine": "me", "maryland": "md",
    "massachusetts": "ma", "michigan": "mi", "minnesota": "mn", "mississippi": "ms",
    "missouri": "mo", "montana": "mt", "nebraska": "ne", "nevada": "nv",
    "new hampshire": "nh", "new jersey": "nj", "new mexico": "nm", "new york": "ny",
    "north carolina": "nc", "north dakota": "nd", "ohio": "oh", "oklahoma": "ok",
    "oregon": "or", "pennsylvania": "pa", "rhode island": "ri", "south carolina": "sc",
    "south dakota": "sd", "tennessee": "tn", "texas": "tx", "utah": "ut",
    "vermont": "vt", "virginia": "va", "washington": "wa", "west virginia": "wv",
    "wisconsin": "wi", "wyoming": "wy",
}


def _state_fips(area: str) -> str | None:
    """Resolve an area string to a state FIPS, but ONLY when it names a whole
    state ("Ohio", "OH"). A metro ("Cincinnati", "Cincinnati, OH") is sub-state
    and returns None so the gate skips rather than mislabels."""
    a = (area or "").strip().lower().rstrip(".")
    if a in _STATE_NAMES:                      # full state name
        return _STATE_FIPS[_STATE_NAMES[a]]
    if a in _STATE_FIPS:                        # 2-letter abbrev alone
        return _STATE_FIPS[a]
    return None


def _series_id(area: str, naics: str | None) -> str | None:
    """Build a JOLTS job-openings-LEVEL series id (21 chars):

        JTS <industry:6> <state_fips:2> <area:5> <sizeclass:2> JO L

    - Seasonally adjusted (JTS), total-nonfarm industry (000000), all size classes.
    - Only STATE-level series are constructed (BLS doesn't publish MSA JOLTS);
      returns None for anything that isn't a whole state so jolts_gate() skips.
    - naics is accepted for a future supersector mapping; today we use total
      nonfarm (comparing an industry slice to a state supersector needs a JOLTS
      industry-code table — deferred; total-nonfarm keeps the gate honest, if coarse).
    """
    fips = _state_fips(area)
    if fips is None:
        return None
    industry = "000000"
    return f"JTS{industry}{fips}00000" + "00" + "JOL"
