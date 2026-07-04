"""Tk-free core of the 'Connect job sources' feature.

Everything the web API and the Tk dialog BOTH need lives here so the browser
layer can reuse the exact source catalog, the Adzuna paste-splitter, and the live
probe without importing tkinter (importing tkinter server-side is both pointless
and can fail on a headless box). ``ui/source_keys.py`` re-exports every public
name from this module and adds only the Tk ``open_dialog`` on top, so existing
callers/tests that reach ``source_keys.SOURCES`` / ``source_keys.test_source`` /
``source_keys.split_adzuna_paste`` keep working byte-for-byte.

Design constraints (repo rules): ASCII-only, no display dependency, and the live
probe NEVER runs under pytest (PYTEST_CURRENT_TEST guard) and degrades cleanly
offline.
"""
import os
import re as _re

from ui import settings

# --- Source catalog: field metadata drives the whole dialog + the web form -----
# Each source: a title, the free-signup URL, and its credential fields. A field is
# (secret_name, label). secret_name indexes config.SOURCE_SECRET_FILES and
# settings.get/set_api_key. ``impact`` is a one-line reach note the web card
# surfaces (the Tk dialog folds this into the title); it is additive metadata and
# does not change the persisted shape.
SOURCES = [
    {
        "key": "adzuna",
        "title": "Adzuna (aggregator, ~19 countries)",
        "url": "https://developer.adzuna.com/",
        "impact": "Broadens the net across ~19 countries — the single highest-reach free key.",
        "fields": [
            ("adzuna_app_id", "App ID"),
            ("adzuna_app_key", "App Key"),
        ],
    },
    {
        "key": "usajobs",
        "title": "USAJobs (US federal jobs)",
        # The API-key REQUEST page (not the generic dev home) so the button lands
        # the user straight on the free-key form.
        "url": "https://developer.usajobs.gov/apirequest/",
        "impact": "Adds the full US federal job board (GS roles, agencies).",
        "fields": [
            ("usajobs_api_key", "API Key"),
            ("usajobs_email", "Registered Email"),
        ],
    },
    {
        "key": "jooble",
        "title": "Jooble (aggregator)",
        "url": "https://jooble.org/api/about",
        "impact": "A second broad aggregator — more coverage, less overlap.",
        "fields": [
            ("jooble_api_key", "API Key"),
        ],
    },
    {
        "key": "careerjet",
        "title": "Careerjet (aggregator)",
        # The Publisher signup issues the affiliate ID the API needs — link there
        # directly rather than the generic partners landing page.
        "url": "https://www.careerjet.com/partners/publishers/",
        "impact": "International aggregator, strong outside the US.",
        "fields": [
            ("careerjet_affid", "Affiliate ID"),
        ],
    },
    {
        "key": "careeronestop",
        "title": "CareerOneStop (US DOL / NLx, ~3.5M US jobs/day)",
        "url": "https://www.careeronestop.org/Developers/WebAPI/registration.aspx",
        "impact": "US DOL / NLx feed — ~3.5M US jobs/day, deep blue-collar coverage.",
        "fields": [
            ("careeronestop_user_id", "User ID"),
            ("careeronestop_token", "API Token"),
        ],
    },
]


# --- Reference-only sources ----------------------------------------------------
# Two more free sources power features outside the credential-entry flow above:
# SerpApi backs the Inbox "reach" badge (and can act as a Google-Jobs backend) and
# JSearch aggregates the big walled boards (Indeed/LinkedIn/Glassdoor) via RapidAPI.
# Both are configured elsewhere (SERPAPI_KEY / secrets/serpapi_key, and
# JSEARCH_RAPIDAPI_KEY in .env), so here we surface their FREE-key signup links for
# completeness — a one-click "Get a free key" for every source the app can use.
REFERENCE_SOURCES = [
    ("SerpApi (reach badge / Google Jobs, free 250/mo)",
     "https://serpapi.com/users/sign_up"),
    ("JSearch via RapidAPI (Indeed / LinkedIn / Glassdoor, free 200/mo)",
     "https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch"),
]


def _in_pytest() -> bool:
    return bool(os.getenv("PYTEST_CURRENT_TEST"))


# --- paste helpers (6.6) -------------------------------------------------------
# Adzuna's developer page hands the user an Application ID (an 8-hex-digit string)
# and an Application Key (a 32-hex-digit string) on ONE screen. A user copying
# "both" (or copying the page region) lands a blob with both values; splitting it
# client-side turns two error-prone copies into one paste. Pure + regex-only so
# it is unit-testable without a Tk root.

# App ID: exactly 8 hex chars; App Key: exactly 32 hex chars. Anchored on token
# boundaries so they don't match substrings of a longer run.
_ADZUNA_ID_RE = _re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{8}(?![0-9a-fA-F])")
_ADZUNA_KEY_RE = _re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{32}(?![0-9a-fA-F])")


def split_adzuna_paste(text: str) -> tuple[str, str]:
    """Best-effort extraction of (app_id, app_key) from a pasted blob that may
    contain both Adzuna values (labeled or not). Returns ('', '') for either part
    it can't find. Never raises.

    Recognizes the two by SHAPE (8-hex id, 32-hex key) so it works whether the
    user pasted 'Application ID: xxxx  Application Key: yyyy', two lines, or the
    two tokens space-separated. If only one shape is present, only that slot is
    filled."""
    s = text or ""
    key_m = _ADZUNA_KEY_RE.search(s)
    app_key = key_m.group(0) if key_m else ""
    # Find an 8-hex id that is NOT the first 8 chars of the 32-hex key we matched.
    app_id = ""
    for m in _ADZUNA_ID_RE.finditer(s):
        if key_m and key_m.start() <= m.start() < key_m.end():
            continue  # inside the key token
        app_id = m.group(0)
        break
    return app_id, app_key


def looks_like_adzuna_paste(text: str) -> bool:
    """True when a pasted blob plausibly contains Adzuna credentials (a 32-hex key,
    or an 8-hex id) — used to decide whether to offer the split. Cheap/pure."""
    app_id, app_key = split_adzuna_paste(text)
    return bool(app_id or app_key)


# --- live probe ----------------------------------------------------------------
# The probe dispatch table: source_key -> (required_secret_names, client_factory,
# sample_query, has_page_arg). Keeping it as data (a) lets the web route and the
# Tk button share ONE definition, and (b) makes the "which keys does a source
# need / what client backs it" mapping unit-testable without any network. The
# client imports are deferred inside the factory so importing this module never
# drags in the whole search stack.
def _adzuna_client():
    from search.adzuna_client import AdzunaClient
    return AdzunaClient(cache_enabled=False)


def _usajobs_client():
    from search.usajobs_client import USAJobsClient
    return USAJobsClient(cache_enabled=False)


def _jooble_client():
    from search.jooble_client import JoobleClient
    return JoobleClient(cache_enabled=False)


def _careerjet_client():
    from search.careerjet_client import CareerjetClient
    return CareerjetClient(cache_enabled=False)


def _careeronestop_client():
    from search.careeronestop_client import CareerOneStopClient
    return CareerOneStopClient(cache_enabled=False)


# source_key -> dict(required=[...], factory=callable, query=str, paged=bool, missing=str)
PROBE_TABLE = {
    "adzuna": {
        "required": ["adzuna_app_id", "adzuna_app_key"],
        "factory": _adzuna_client, "query": "engineer", "paged": True,
        "missing": "App ID and App Key required",
    },
    "usajobs": {
        "required": ["usajobs_api_key", "usajobs_email"],
        "factory": _usajobs_client, "query": "engineer", "paged": True,
        "missing": "API Key and Email required",
    },
    "jooble": {
        "required": ["jooble_api_key"],
        "factory": _jooble_client, "query": "engineer", "paged": False,
        "missing": "API Key required",
    },
    "careerjet": {
        "required": ["careerjet_affid"],
        "factory": _careerjet_client, "query": "engineer", "paged": False,
        "missing": "Affiliate ID required",
    },
    "careeronestop": {
        "required": ["careeronestop_user_id", "careeronestop_token"],
        "factory": _careeronestop_client, "query": "nurse", "paged": True,
        "missing": "User ID and API Token required",
    },
}


def test_source(source_key: str) -> tuple[bool, str]:
    """Do ONE tiny live probe for a source and report (ok, message). Guarded:
    returns a benign 'skipped' result under pytest or when the source's key is
    unset, and turns any network/offline error into a clean (False, message)
    rather than raising. This is the button's/route's worker; separated out so it
    is unit-testable without a Tk root.

    The dispatch is table-driven (PROBE_TABLE); the branch bodies used to be
    copy-pasted per source. Behavior is byte-identical to the pre-refactor form:
    missing-key message, one paged/unpaged search, N parsed results, exceptions
    become ``(False, 'TypeName: msg')``."""
    if _in_pytest():
        return (False, "skipped (test mode)")

    spec = PROBE_TABLE.get(source_key)
    if spec is None:
        return (False, "unknown source")

    if not all(settings.get_api_key(name) for name in spec["required"]):
        return (False, spec["missing"])

    try:
        client = spec["factory"]()
        query = spec["query"]
        if spec["paged"]:
            raw = client.search(query, location="", page=1)
        else:
            raw = client.search(query, location="")
        n = len(client.parse_results(raw, query))
        return (True, f"OK - {n} sample result(s)")
    except Exception as e:  # offline / bad key / API change -> clean failure
        return (False, f"{type(e).__name__}: {e}")
