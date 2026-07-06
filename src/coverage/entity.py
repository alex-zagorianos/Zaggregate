from __future__ import annotations
import functools, hashlib, json, re, unicodedata
from dataclasses import dataclass
from coverage._paths import static_path
from coverage.geography import resolve_cbsa

try:
    from cleanco import basename as _cc_basename
except ImportError:
    _SUFFIX = re.compile(r"\b(inc|llc|ltd|gmbh|corp|co)\b\.?", re.I)
    def _cc_basename(n: str) -> str:
        return _SUFFIX.sub("", n)

try:
    from rapidfuzz import process as _rf_process, fuzz as _rf_fuzz
    _HAVE_RAPIDFUZZ = True
except ImportError:
    _HAVE_RAPIDFUZZ = False

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]")
_SENIORITY = re.compile(r"\b(sr|senior|jr|junior|i{1,3}|iv|lead|principal|staff)\b\.?", re.I)
_REMOTE = re.compile(r"\bremote\b|\banywhere\b", re.I)
_CONF_FLOOR = 0.6

@functools.lru_cache(maxsize=1)
def _aliases() -> dict[str, str]:
    return json.loads(static_path("company_aliases.json").read_text(encoding="utf-8"))

@functools.lru_cache(maxsize=1)
def _onet() -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for line in static_path("onet_soc_alt_titles.tsv").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        alt, soc, soc_title = line.split("\t")
        out[alt.casefold()] = (soc, soc_title)
    return out


@functools.lru_cache(maxsize=1)
def _onet_keys() -> list[str]:
    """The alt-title key list, materialized ONCE. normalize_title's fuzzy path
    rebuilt this ~51k-element list on every call (the dominant CPU cost of a daily
    run, since job_key -> normalize_title fires for every result); hoisting it here
    makes each fuzzy call O(scan) instead of O(build + scan)."""
    return list(_onet().keys())

def canonicalize_company(name: str) -> str:
    if not name:
        return ""
    s = _cc_basename(name)
    s = unicodedata.normalize("NFKD", s).casefold()
    s = _PUNCT.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    return _aliases().get(s, s)

@dataclass
class NormalizedTitle:
    soc_code: str
    soc_title: str
    seniority: str | None
    confidence: float

def title_core(title: str) -> str:
    s = _SENIORITY.sub("", title or "")
    return _WS.sub(" ", s).strip().casefold()

def _seniority_of(title: str) -> str | None:
    m = _SENIORITY.search(title or "")
    return m.group(0).strip().casefold() if m else None

@functools.lru_cache(maxsize=8192)
def normalize_title(title: str) -> NormalizedTitle:
    core = title_core(title)
    seniority = _seniority_of(title)
    table = _onet()
    if core in table:
        soc, soc_title = table[core]
        return NormalizedTitle(soc, soc_title, seniority, 1.0)
    if _HAVE_RAPIDFUZZ and table:
        # Hoisted key list + score_cutoff: rapidfuzz can early-exit anything below
        # the confidence floor (identical result -- the code already rejected
        # conf < _CONF_FLOOR), and the ~51k-element key list is built once.
        match = _rf_process.extractOne(
            core, _onet_keys(), scorer=_rf_fuzz.token_set_ratio,
            score_cutoff=_CONF_FLOOR * 100)
        if match:
            cand, score, _ = match
            conf = score / 100.0
            if conf >= _CONF_FLOOR:
                soc, soc_title = table[cand]
                return NormalizedTitle(soc, soc_title, seniority, conf)
    return NormalizedTitle("00-0000", core, seniority, 0.0)

@dataclass
class NormalizedLocation:
    city: str | None
    state: str | None
    cbsa: str | None
    is_remote: bool

def normalize_location(loc: str) -> NormalizedLocation:
    if not loc:
        return NormalizedLocation(None, None, None, False)
    if _REMOTE.search(loc):
        return NormalizedLocation(None, None, None, True)
    parts = [p.strip() for p in loc.split(",")]
    city = parts[0] or None
    state = parts[1].split()[0] if len(parts) > 1 and parts[1] else None
    return NormalizedLocation(city, state, resolve_cbsa(city, state), False)

def location_token(nl: NormalizedLocation) -> str:
    # City-based (not city|state): a posting's location formatting varies across
    # sources ("Cincinnati, OH" vs "Cincinnati"), and the same city name rarely
    # repeats across states for one company+role, so the bare city is the robust
    # cross-source token. CBSA/grouping still uses state via NormalizedLocation.
    if nl.is_remote:
        return "remote"
    return (nl.city or "").strip().casefold()

def compute_job_key(company_canon: str, soc_code: str, loc_token: str, title_core_str: str) -> str:
    payload = "\x1f".join([company_canon, soc_code, loc_token, title_core_str])
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]

def job_key_for(job) -> str:
    company = canonicalize_company(getattr(job, "company", "") or "")
    nt = normalize_title(getattr(job, "title", "") or "")
    nl = normalize_location(getattr(job, "location", "") or "")
    return compute_job_key(company, nt.soc_code, location_token(nl), title_core(getattr(job, "title", "") or ""))
