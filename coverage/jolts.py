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
    try:
        expected = _fetch_expected_openings(area, naics, api_key)
    except Exception:
        return JoltsResult(None, None, "skip")
    if not expected:
        return JoltsResult(None, None, "skip")
    ratio = our_count / expected
    verdict = "pass" if _PASS_LO <= ratio <= _PASS_HI else "fail"
    return JoltsResult(expected_openings=expected, ratio=ratio, verdict=verdict)

def _fetch_expected_openings(area: str, naics: str | None, api_key: str) -> int | None:
    import requests
    from search.http_util import FileCache, cache_key, RateLimiter
    cache = FileCache("jolts")
    key = cache_key("jolts", area, naics or "")
    cached = cache.get(key)
    if cached is not None:
        return cached.get("openings")
    RateLimiter(50).acquire()
    resp = requests.post(
        "https://api.bls.gov/publicAPI/v2/timeseries/data/",
        json={"seriesid": [_series_id(area, naics)], "registrationkey": api_key},
        timeout=30,
    )
    resp.raise_for_status()
    series = resp.json().get("Results", {}).get("series", [])
    if not series or not series[0].get("data"):
        return None
    openings = int(float(series[0]["data"][0]["value"])) * 1000
    cache.put(key, {"openings": openings})
    return openings

def _series_id(area: str, naics: str | None) -> str:
    # JTU national total-nonfarm job openings, level (NSA) -- safe default series.
    return "JTU000000000000000JOL"
