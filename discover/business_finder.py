"""CareerOneStop Business Finder client — the "supply side" the Seed-My-Area
plan (brain/plan-2026-07-01-ai-assisted-setup-seeding.md Leg B) identified as its
missing half, re-scoped per SB-2 of brain/improvement-plan-2026-07-02-general-user.md.

Business Finder is a VERIFIED-DIRECTORY employer lookup: "contact information for
more than 13 million employers", searchable by keyword/industry + location +
radius. It lives in CareerOneStop's open LMI/toolkit family — the SAME free
`userId` + API-token credential as the (governance-gated) Jobs feed, but the
directory endpoints are expected to stay self-serve (research-sources.md §2/§E:
"the occupation/LMI/skills/Business-Finder family stays self-serve free — verify
at registration"). So a user who registers one CareerOneStop key unlocks employer
discovery here even before the Jobs API access request clears.

Key-gated exactly like search/careeronestop_client.py: a missing credential makes
the client self-skip with ONE warn_once (never a raised exception up into a GUI or
a daily run — this is a discovery/opt-in path, not a scored source), so a keyless
user's app stays byte-identical.

Endpoint (documented shape — see CITATION below). All segments are URL-encoded
PATH parameters, mirroring the List-Jobs endpoint the sibling client already uses:

    GET {BASE}/{userId}/{keyword}/{location}/{radius}/{limit}
    Authorization: Bearer {token}

    where keyword = an industry/business keyword (mapped from the user's field via
    _industry_to_keyword below), location = "City, ST" | ZIP | "ST", radius in
    miles, limit = max businesses.

Response shape (BusinessList of business records):

    {"BusinessList": [
        {"CompanyName", "Address1", "City", "StateAbbr" (or "State"), "Zip",
         "Phone", "Industry" (or "NaicsTitle"), "Naics", "WebSite" (or "Url"),
         "Distance", ...},
        ...], "RecordCount": N, ...}

CITATION / VERIFY-ONCE (this machine has NO CareerOneStop key, and every
CareerOneStop developer/api-explorer docs page — technical-information.aspx,
find-businesses-help.aspx, the api-explorer JSON — returns 403/500 to an automated
fetch, 2026-07-02, exactly as search/careeronestop_client.py already recorded).
So the per-field names below are DERIVED from:
  - the Business Finder tool docs (fields it displays per business):
    https://www.careeronestop.org/Toolkit/Jobs/find-businesses.aspx
    https://www.careeronestop.org/Toolkit/Jobs/find-businesses-help.aspx
  - the sibling List-Jobs endpoint's proven path-segment + Bearer-auth convention:
    https://www.careeronestop.org/Developers/WebAPI/Jobs/list-jobs.aspx
  - the API-Overview endpoint index:
    https://github.com/CareerOneStop/API-Overview
The parser reads several plausible aliases per field so a minor casing/spelling
difference does not silently drop a business. Both the path template
(BUSINESS_FINDER_URL / _build_url) and the field mapping (_parse_business) are
marked PROVISIONAL — a recorded-fixture toggle (COS_BF_FIXTURE env var, read by
`search`) makes them trivially verifiable the moment Alex gets a key: drop one
real JSON response into the fixture path and the tests replay it byte-for-byte.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import applog
import config
from search.http_util import FileCache, RateLimiter, cache_key, make_session

# Required by the US DOL terms of use; re-exported so a caller can display it.
ATTRIBUTION = config.CAREERONESTOP_ATTRIBUTION

# Business Finder path base. Sibling jobs base is
# https://api.careeronestop.org/v1/jobsearch; the directory endpoint sits under
# the same /v1 host. PROVISIONAL (see module CITATION) — overridable via env so a
# corrected path needs no code edit once verified against a live key.
BUSINESS_FINDER_URL = os.getenv(
    "CAREERONESTOP_BUSINESSFINDER_URL",
    "https://api.careeronestop.org/v1/businessfinder",
)
# Fixture toggle: point COS_BF_FIXTURE at a saved real JSON response and the
# client replays it instead of calling the network — the "trivially verifiable
# once Alex gets a key" path the plan asks for.
_FIXTURE_ENV = "COS_BF_FIXTURE"

DEFAULT_RADIUS = config.CAREERONESTOP_RADIUS   # miles (reuse the jobs default: 25)
DEFAULT_LIMIT = 50

# ── industry token -> Business Finder keyword mapping (documented choice) ──────
# Business Finder searches by a free-text business/industry KEYWORD, not by a NAICS
# code in the request (NAICS comes back on each record). The user's field token is
# an arbitrary phrase ("mechanical engineering", "warehouse logistics"), so we map
# it to the plain-English INDUSTRY term the directory indexes on. We deliberately
# reuse industry_profile.resolve()'s query_synonyms/title_terms — the app's single
# genre-knowledge surface — as the keyword source, so a field already tuned there
# needs no second mapping. The mapping choice, in order of preference:
#   1. the field's first query_synonym (a broad, canonical industry phrase), else
#   2. the raw industry text itself (spaces preserved — this is a search keyword,
#      NOT a registry tag, so it must NOT be underscore-normalized), else
#   3. a couple of curated fallbacks for the bare-token verticals that carry no
#      synonyms, so e.g. "nursing" searches "hospital" (where nurses are employed)
#      rather than the literal word "nursing".
# Documented + intentional: a directory keyword should name the EMPLOYER TYPE, not
# the job title — "hospital" finds nurse employers, "school district" finds teacher
# employers. These curated hints encode that where the field token alone wouldn't.
_KEYWORD_HINTS: dict[str, str] = {
    "nursing": "hospital",
    "nurse": "hospital",
    "teaching": "school",
    "teacher": "education",
    "warehouse": "warehouse",
    "logistics": "logistics",
    "trades": "construction",
    "hospitality": "restaurant",
    "consulting": "consulting",
}


def _industry_to_keyword(industry: str) -> str:
    """Map the user's field token to a Business Finder search keyword (the
    documented mapping — see module comment). Returns "" for an empty field, in
    which case the caller should require an explicit keyword."""
    ind = (industry or "").strip()
    if not ind:
        return ""
    # 1) curated employer-type hint keyed on any token of the field.
    toks = [t for t in ind.lower().replace("-", " ").replace("_", " ").split() if t]
    for t in toks:
        if t in _KEYWORD_HINTS:
            return _KEYWORD_HINTS[t]
    # 2) the field's own first broad synonym from the genre surface.
    try:
        import industry_profile
        syns = industry_profile.resolve(ind).query_synonyms
        if syns:
            return syns[0]
    except Exception:
        pass
    # 3) the raw field text (spaces preserved — it's a keyword, not a tag).
    return ind


def _seg(value) -> str:
    """URL-encode one path segment; a blank required segment -> '0' sentinel and
    '/' fully escaped (mirrors careeronestop_client._seg so 'Cincinnati, OH'
    can't split the path)."""
    s = str(value).strip()
    if not s:
        return "0"
    return quote(s, safe="")


class BusinessFinderClient:
    """CareerOneStop Business Finder employer lookup. Fail-soft + key-gated: a
    missing credential does NOT raise (unlike the scored jobs client) — it
    self-skips with one warn_once and returns [] so a keyless GUI/CLI path is
    a clean no-op, never a crash."""

    def __init__(
        self,
        user_id: Optional[str] = None,
        token: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        cache_enabled: bool = True,
        radius: Optional[int] = None,
    ):
        # Re-resolve env-then-secret at construction (a key pasted into the in-app
        # box after import is honored). Explicit args still win for tests.
        self.user_id = user_id or config.resolve_secret(
            "CAREERONESTOP_USER_ID", "careeronestop_user_id")
        self.token = token or config.resolve_secret(
            "CAREERONESTOP_TOKEN", "careeronestop_token")
        self.radius = radius if radius is not None else DEFAULT_RADIUS
        self.cache = FileCache("businessfinder", cache_dir)
        self.cache_enabled = cache_enabled
        self.session = make_session()
        # Reuse the jobs client's per-minute budget so one key can't burst both.
        self.limiter = RateLimiter(config.CAREERONESTOP_RATE_LIMIT, quiet=True)

    def has_key(self) -> bool:
        return bool(self.user_id and self.token)

    def _build_url(self, keyword: str, location: str, limit: int) -> str:
        return "/".join([
            BUSINESS_FINDER_URL.rstrip("/"),
            _seg(self.user_id),
            _seg(keyword),
            _seg(location),
            _seg(self.radius),
            str(int(limit)),
        ])

    def search(self, keyword: str, location: str = "", limit: int = DEFAULT_LIMIT) -> dict:
        """One Business Finder lookup. Fail-soft: an unset key, a network error,
        or an unexpected status returns an empty {"BusinessList": []} rather than
        raising, and warns once so a keyless run degrades honestly."""
        # Fixture replay (verify-once path): a saved real response short-circuits
        # the network so the mapping is testable the moment a key exists.
        fixture = os.getenv(_FIXTURE_ENV)
        if fixture:
            try:
                return json.loads(Path(fixture).read_text(encoding="utf-8"))
            except Exception as e:
                applog.warn_once(
                    f"Business Finder fixture unreadable ({e}); ignoring.",
                    key="cos_bf_fixture_bad")
                return {"BusinessList": []}

        if not self.has_key():
            applog.warn_once(
                "CareerOneStop key not set — 'Seed my area' employer discovery is "
                "off. Add a free CAREERONESTOP_USER_ID + CAREERONESTOP_TOKEN "
                "(Tools > Connect job sources) to turn it on.",
                key="cos_businessfinder_nokey")
            return {"BusinessList": []}

        key = cache_key("businessfinder", keyword, location, self.radius, limit)
        if self.cache_enabled:
            cached = self.cache.get(key)
            if cached is not None:
                return cached

        self.limiter.acquire()
        url = self._build_url(keyword, location, limit)
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        try:
            response = self.session.get(url, headers=headers, timeout=30)
        except Exception as e:
            applog.warn_once(
                f"Business Finder request failed ({type(e).__name__}); skipping.",
                key="cos_businessfinder_neterr")
            return {"BusinessList": []}
        # 404 = no matches (not an error), same as the jobs endpoint.
        if response.status_code == 404:
            data = {"BusinessList": [], "RecordCount": 0}
        elif not response.ok:
            applog.warn_once(
                f"Business Finder returned HTTP {response.status_code}; skipping.",
                key="cos_businessfinder_http")
            return {"BusinessList": []}
        else:
            try:
                data = response.json()
            except ValueError:
                data = {"BusinessList": [], "RecordCount": 0}

        if self.cache_enabled:
            self.cache.put(key, data)
        return data

    @staticmethod
    def _first(item: dict, *names: str) -> str:
        for n in names:
            v = item.get(n)
            if v not in (None, ""):
                return str(v).strip()
        return ""

    def parse_businesses(self, raw: dict) -> list[dict]:
        """Normalize the raw response into a list of employer dicts:
            {name, domain, city, state, zip, phone, naics, industry, distance}
        `domain` is the registrable host derived from any website field ("" when
        the directory carries none — the seed pipeline then guesses one). A few
        harmless key aliases per field guard against upstream casing/spelling."""
        items = (raw.get("BusinessList") or raw.get("Businesses")
                 or raw.get("businessList") or raw.get("Business") or [])
        out: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = self._first(item, "CompanyName", "BusinessName", "Name", "company")
            if not name:
                continue
            website = self._first(item, "WebSite", "Website", "Url", "URL", "WebUrl")
            out.append({
                "name": name,
                "domain": _domain_from(website),
                "website": website,
                "city": self._first(item, "City", "city"),
                "state": self._first(item, "StateAbbr", "State", "StateAbbreviation", "state"),
                "zip": self._first(item, "Zip", "ZipCode", "PostalCode", "zip"),
                "phone": self._first(item, "Phone", "PhoneNumber", "phone"),
                "naics": self._first(item, "Naics", "NAICS", "NaicsCode"),
                "industry": self._first(item, "Industry", "NaicsTitle", "IndustryTitle"),
                "distance": self._first(item, "Distance", "distance"),
            })
        return out

    def find_employers(self, *, industry: str = "", keyword: str = "",
                       location: str = "", limit: int = DEFAULT_LIMIT) -> list[dict]:
        """High-level: field/keyword + location -> normalized employer dicts.
        `keyword` wins if given; else it is mapped from `industry` (documented
        mapping, _industry_to_keyword). Fail-soft all the way down."""
        kw = (keyword or "").strip() or _industry_to_keyword(industry)
        if not kw:
            applog.warn_once(
                "Business Finder needs a field or keyword to search — skipping.",
                key="cos_businessfinder_nokw")
            return []
        raw = self.search(kw, location=location, limit=limit)
        return self.parse_businesses(raw)


def _domain_from(website: str) -> str:
    """Registrable host from a website field, or "" — reuses the enumerate
    normalizer so dedup keys match the rest of the discovery pipeline."""
    if not website:
        return ""
    try:
        from discover.enumerate import normalize_domain
        return normalize_domain(website)
    except Exception:
        return ""
