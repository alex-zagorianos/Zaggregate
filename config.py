import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def _dir_writable(path: Path) -> bool:
    """True if we can create + write files under `path` (creating it if needed)."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_test"
        probe.write_text("", encoding="ascii")
        probe.unlink()
        return True
    except OSError:
        return False


def _get_data_dir() -> Path:
    """Read-only bundle root: _MEIPASS when frozen, else the repo root."""
    if _is_frozen():
        return Path(sys._MEIPASS)
    return Path(__file__).parent


def _get_user_data_dir() -> Path:
    """External, user-editable data root: experience/preferences/companies/db/
    cache/output/secrets live here. JOBPROGRAM_DATA overrides anywhere. Frozen
    default: <exe>/data if writable, else %LOCALAPPDATA%/JobProgram. Dev (not
    frozen): the repo root, so the current files-at-root layout is unchanged."""
    override = os.getenv("JOBPROGRAM_DATA")
    if override:
        return Path(override)
    if _is_frozen():
        exe_data = Path(sys.executable).parent / "data"
        if _dir_writable(exe_data):
            return exe_data
        return Path(os.getenv("LOCALAPPDATA", ".")) / "JobProgram"
    return Path(__file__).parent


DATA_DIR = _get_data_dir()
USER_DATA_DIR = _get_user_data_dir()
# Back-compat aliases: BASE_DIR = read-only bundle (code/templates in the .exe);
# WRITABLE_DIR is now the user data folder (alias of USER_DATA_DIR).
BASE_DIR = DATA_DIR
WRITABLE_DIR = USER_DATA_DIR

# User-editable data (lives in the data folder; bundle templates scaffold these).
EXPERIENCE_FILE  = USER_DATA_DIR / "experience.md"
COMPANIES_JSON   = USER_DATA_DIR / "companies.json"
PREFERENCES_MD   = USER_DATA_DIR / "preferences.md"
PREFERENCES_JSON = USER_DATA_DIR / "preferences.json"
USER_CONFIG_JSON = USER_DATA_DIR / "user_config.json"
SECRETS_DIR      = USER_DATA_DIR / "secrets"


def read_secret(name):
    """Read a secret (e.g. 'anthropic_key') from SECRETS_DIR; None if absent/empty.
    The canonical accessor so every key resolver reads the same place."""
    try:
        v = (SECRETS_DIR / name).read_text(encoding="utf-8").strip()
        return v or None
    except OSError:
        return None


def write_secret(name, value):
    """Write/replace a plaintext secret file under SECRETS_DIR (created on demand);
    an empty/None value deletes it. Single-user local app — SECRETS_DIR is
    gitignored and never bundled into the distributable. Returns True on success."""
    try:
        SECRETS_DIR.mkdir(parents=True, exist_ok=True)
        path = SECRETS_DIR / name
        if not value or not str(value).strip():
            path.unlink(missing_ok=True)
            return True
        path.write_text(str(value).strip(), encoding="utf-8")
        return True
    except OSError:
        return False


def resolve_secret(env_name, secret_name):
    """Resolve a job-source credential the same way serpapi already does: the
    matching env var wins (a power user's .env still overrides), else the
    plaintext file under SECRETS_DIR (the in-app 'Connect job sources' box writes
    there), else None. This is the single accessor every source-key resolver uses
    so env-over-secret-over-absent precedence is defined in exactly one place.

    Resolved lazily (not frozen at import) so the source clients see a secret
    written after startup and tests that monkeypatch SECRETS_DIR work without a
    reimport."""
    v = os.getenv(env_name)
    if v:
        return v
    return read_secret(secret_name)


# Canonical secrets/ filenames for every job-source credential. The in-app
# 'Connect job sources' dialog (ui/source_keys.py) and ui/settings._KEY_FILES
# both read this so the on-disk names stay defined in exactly one place. Mirrors
# the anthropic_key / serpapi_key convention already in secrets/.
SOURCE_SECRET_FILES = {
    "adzuna_app_id":        "adzuna_app_id",
    "adzuna_app_key":       "adzuna_app_key",
    "usajobs_api_key":      "usajobs_api_key",
    "usajobs_email":        "usajobs_email",
    "jooble_api_key":       "jooble_api_key",
    "careerjet_affid":      "careerjet_affid",
    "careeronestop_user_id": "careeronestop_user_id",
    "careeronestop_token":  "careeronestop_token",
}


# Writable runtime state (under the data folder).
CACHE_DIR = USER_DATA_DIR / "cache"
OUTPUT_DIR = USER_DATA_DIR / "output"


def ensure_writable_dirs() -> None:
    """Create cache/ and output/ under WRITABLE_DIR. Safe to call repeatedly."""
    for d in (CACHE_DIR, OUTPUT_DIR):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass


# Best-effort at import (don't crash on a read-only bundle dir).
ensure_writable_dirs()

# Adzuna. Credentials resolve env-then-secret (see resolve_secret); frozen at
# import for back-compat, but the clients re-resolve at construction so a key
# pasted into the in-app 'Connect job sources' box takes effect without restart.
ADZUNA_APP_ID = resolve_secret("ADZUNA_APP_ID", "adzuna_app_id")
ADZUNA_APP_KEY = resolve_secret("ADZUNA_APP_KEY", "adzuna_app_key")
# Adzuna serves ~19 countries off ONE free key; the two-letter country code is
# interpolated into the endpoint (adzuna_country_url). Default 'us' = today's
# behavior byte-for-byte. Env ADZUNA_COUNTRY or a project's location/country
# field (adzuna_country_for) can widen it. Non-'us' also arms the language guard
# (see LANGUAGE_GUARD) so foreign-language postings aren't confidently mis-scored.
ADZUNA_COUNTRY = (os.getenv("ADZUNA_COUNTRY") or "us").strip().lower() or "us"
ADZUNA_BASE_URL = "https://api.adzuna.com/v1/api/jobs/us/search"
ADZUNA_RATE_LIMIT = 25
ADZUNA_RESULTS_PER_PAGE = 50


def adzuna_country_url(country=None):
    """The Adzuna search endpoint for a two-letter country code (default
    ADZUNA_COUNTRY). One free key covers ~19 countries; only the /{cc}/ path
    segment changes."""
    cc = (country or ADZUNA_COUNTRY or "us").strip().lower() or "us"
    return f"https://api.adzuna.com/v1/api/jobs/{cc}/search"


# Adzuna's ~19 supported country codes (adzuna.com/products). Anything outside
# this set falls back to 'us' so a typo can't 404 the whole source.
ADZUNA_COUNTRIES = frozenset({
    "us", "gb", "at", "au", "be", "br", "ca", "ch", "de", "es", "fr", "in",
    "it", "mx", "nl", "nz", "pl", "sg", "za",
})


def adzuna_country_for(location=None, country=None):
    """Derive the Adzuna country code for a project. An explicit `country`
    (config's 'adzuna_country'/'country' field) wins; else a light location-tail
    heuristic ('Toronto, Canada' -> 'ca'); else ADZUNA_COUNTRY. Always returns a
    supported code (unsupported -> the module default)."""
    if country:
        cc = str(country).strip().lower()
        if cc in ADZUNA_COUNTRIES:
            return cc
    loc = (location or "").strip().lower()
    if loc:
        tail = loc.rsplit(",", 1)[-1].strip()
        _NAME_TO_CC = {
            "usa": "us", "united states": "us", "us": "us",
            "uk": "gb", "united kingdom": "gb", "england": "gb", "gb": "gb",
            "canada": "ca", "australia": "au", "germany": "de", "france": "fr",
            "spain": "es", "italy": "it", "netherlands": "nl", "poland": "pl",
            "brazil": "br", "mexico": "mx", "india": "in", "singapore": "sg",
            "new zealand": "nz", "austria": "at", "belgium": "be",
            "switzerland": "ch", "south africa": "za",
        }
        cc = _NAME_TO_CC.get(tail)
        if cc in ADZUNA_COUNTRIES:
            return cc
    return ADZUNA_COUNTRY

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# JSearch (RapidAPI) — aggregates Indeed, LinkedIn, Glassdoor
JSEARCH_RAPIDAPI_KEY = os.getenv("JSEARCH_RAPIDAPI_KEY")
JSEARCH_RAPIDAPI_HOST = "jsearch.p.rapidapi.com"
JSEARCH_BASE_URL = "https://jsearch.p.rapidapi.com/search"
JSEARCH_RATE_LIMIT = 5       # per minute (free tier: 200 req/month total)
JSEARCH_MONTHLY_LIMIT = 200  # free-tier hard cap; tracked in cache/jsearch_usage.json
JSEARCH_RESULTS_PER_PAGE = 10

# USAJobs — federal job board (requires registration at usajobs.gov). The
# User-Agent MUST be your registered email; the in-app box stores it under the
# secret name 'usajobs_email' (env USAJOBS_EMAIL, or the legacy USAJOBS_USER_AGENT).
USAJOBS_API_KEY = resolve_secret("USAJOBS_API_KEY", "usajobs_api_key")
USAJOBS_USER_AGENT = (os.getenv("USAJOBS_EMAIL") or os.getenv("USAJOBS_USER_AGENT")
                      or read_secret("usajobs_email"))
USAJOBS_BASE_URL = "https://data.usajobs.gov/api/search"
USAJOBS_RATE_LIMIT = 50
USAJOBS_RESULTS_PER_PAGE = 25

# Search defaults
# Empty by default: a hardcoded "Cincinnati" leaked Alex's home metro into every
# skip-wizard user's Search prefill, Inbox home area, and keyless fallbacks (P3).
# Empty means "no location filter" -- non-GUI consumers treat "" as unset (search
# without a location bias rather than everyone's default being Cincinnati). GUI
# consumers that need a display placeholder are handled in a later wave.
DEFAULT_LOCATION = ""
# Field/industry the app is tuned for. Empty = today's behavior (eng-flavored
# enumeration angles, no industry scoping). A user onboarding into another field
# sets this (via the wizard / project config) so company enumeration, registry
# scoping, and coverage measurement name THEIR field instead of engineering.
DEFAULT_INDUSTRY = ""
DEFAULT_KEYWORDS = [
    "controls engineer",
    "embedded systems engineer",
    "mechatronics engineer",
    "mechanical design engineer",
    "machine design engineer",
    "manufacturing engineer",
    "automation engineer",
    "R&D engineer",
    "test engineer",
    "software engineer manufacturing",
]

CACHE_TTL_HOURS = 24
# Negative-cache (dead-URL "_FAILED" markers) live far longer than content: a
# 404/timeout URL doesn't recover overnight, but the 24h content TTL used to
# expire the failure marker too, so every daily run re-paid the full timeout on
# every known-dead board (~"150 doomed requests a day" per direct_scraper). A
# 7-day marker TTL means a dead URL is retried ~weekly, not daily.
FAILED_TTL_HOURS = 168
# A TRANSIENT failure (HTTP 429 throttle, 5xx outage, or a network blip) is NOT
# a dead board -- poisoning it for a week (FAILED_TTL_HOURS) is exactly the
# self-inflicted-429 under-coverage bug. When a scraper opts to negative-cache a
# transient at all, it uses this short window so the board is re-probed within
# the hour instead of skipped for days.
FAILED_TTL_TRANSIENT_HOURS = 1
# cache/ (ATS payload blobs, per-source FileCaches) is write-mostly and was
# never evicted -> grew to hundreds of MB. A GC pass at the end of a daily run
# deletes entries older than this; anything still needed is re-fetched cheaply.
CACHE_GC_MAX_AGE_HOURS = 168

# Flask server ports
PORT_RESUME   = 5000
PORT_TRACKER  = 5001
PORT_RECEIVER = 5002

# The Muse — free public API, no key. Keyword filtering is client-side.
THEMUSE_BASE_URL = "https://www.themuse.com/api/public/jobs"
THEMUSE_RATE_LIMIT = 20          # polite ceiling; unauthenticated tier
THEMUSE_CATEGORIES = ["Engineering", "Science and Engineering"]

# RemoteOK — free public JSON feed, no key. Remote-only postings.
REMOTEOK_URL = "https://remoteok.com/api"
REMOTEOK_RATE_LIMIT = 5

# Remotive — free public API, no key. Remote-only. Their legal notice asks
# for <=4 fetches/day; the 24h FileCache keeps us at ~1.
REMOTIVE_URL = "https://remotive.com/api/remote-jobs"
REMOTIVE_RATE_LIMIT = 2

# Jobicy — free public API, no key. Remote-only, ~50 jobs/call max.
JOBICY_URL = "https://jobicy.com/api/v2/remote-jobs"
JOBICY_RATE_LIMIT = 2
JOBICY_COUNT = 50                 # API max per request
JOBICY_INDUSTRY = "engineering"   # server-side category filter

# Himalayas — free public API, no key. Remote-only, paginated. The API
# hard-caps each response at 20 jobs regardless of the `limit` param, so we
# page by offset; 200 deep = 10 requests on a cold cache (once/day).
HIMALAYAS_URL = "https://himalayas.app/jobs/api"
HIMALAYAS_RATE_LIMIT = 5
HIMALAYAS_PAGE_SIZE = 20          # server's hard per-response cap
# 200-deep = 10 sequential requests, but the 5/min limiter forces a ~59s sleep
# after page 5 — a measured 61s cold fetch that matched only ~4 postings. Capping
# at 100 (5 pages) fits inside the rate window (no sleep, ~2-3s) and stays within
# the self-imposed politeness limit (no risk of the free feed IP-blocking us).
# The dropped tail (jobs 101-200 of one keyword-filtered remote feed) contributes
# ~0 matches in practice. To restore full depth without the wall instead, raise
# HIMALAYAS_RATE_LIMIT to 10 (a once-per-cache-cycle burst) and set this to 200.
HIMALAYAS_MAX_JOBS = 100          # total feed depth fetched per cache cycle

# Hacker News "Who is hiring?" via Algolia — free, no key. Monthly thread,
# searched per-keyword against its comments.
HN_ALGOLIA_URL = "https://hn.algolia.com/api/v1"
HN_RATE_LIMIT = 10

# Match scoring (match/scorer.py)
MIN_SCORE_DEFAULT = 0            # CLI --min-score default (0 = show all)
DAILY_MIN_SCORE = 40             # daily_run.py inbox threshold

# Local semantic ranking (match/semantic.py, Model2Vec). OFF by default: enabling
# it is Alex's explicit call. When ON *and* the model is present, a semantic
# similarity component joins the score AND vetoes generic-token full title matches
# (sem below SEMANTIC_TITLE_VETO_SIM caps the title component). Env SEMANTIC_RANKING
# overrides this constant (semantic._enabled reads env first). No model -> abstains,
# score byte-identical.
SEMANTIC_RANKING = os.getenv("SEMANTIC_RANKING", "0") not in ("", "0", "false", "False", "no")
# Below this profile<->job cosine similarity, a full keyword title match is treated
# as generic-token noise and its title component is capped (see SEMANTIC_TITLE_CAP).
SEMANTIC_TITLE_VETO_SIM = 0.35
SEMANTIC_TITLE_CAP = 0.6
DAILY_SOURCES = ["adzuna", "usajobs", "careeronestop", "careers", "themuse",
                 "remoteok", "remotive", "jobicy", "himalayas", "hn",
                 "weworkremotely", "workingnomads", "jooble", "careerjet"]
# weworkremotely + workingnomads (2026-07-01): free/keyless remote boards, same
# risk profile as remoteok/remotive — added to widen the daily net. They auto-gate
# OFF for non-knowledge-work fields (TECH_SKEWED_SOURCES). jsearch stays excluded:
# 10 keywords/day would blow the 200/month free tier in ~3 weeks (manual only).
# jooble + careerjet (aggregators) and careeronestop (US DOL, ~3.5M jobs/day) are
# now in the daily net but ALL THREE self-skip cleanly when their free key is
# unset (build_clients logs a one-line skip), so a keyless user's daily run is
# unchanged — they light up the moment a key is pasted into 'Connect job sources'.

# Brave Search API — free tier: 2,000 req/month at api.search.brave.com
# Sign up at https://api.search.brave.com/ and add to .env to enable company discovery.
BRAVE_SEARCH_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY")
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"

# Careers scraper
CAREERS_MAX_WORKERS = 8
# Tiered timeouts: fast JSON ATS APIs (greenhouse/lever/ashby/workable/recruitee/
# rippling/personio/smartrecruiters) answer in <1-2s, so a 12s cap fails dead
# boards ~40% sooner without cutting healthy ones. Workday is the exception —
# big enterprise boards + CSRF priming + offset pagination legitimately need
# longer — so it uses CAREERS_SLOW_TIMEOUT.
CAREERS_REQUEST_TIMEOUT = 12
CAREERS_SLOW_TIMEOUT = 20

# Per-ATS-host request ceiling (requests/min) for the parallel careers scrape.
# CAREERS_MAX_WORKERS=8 threads can otherwise burst every request at one shared
# ATS host (all greenhouse boards -> boards-api.greenhouse.io) simultaneously and
# earn a 429 that then poisons live boards. A per-host sliding-window limiter (the
# same class stealth_fetch uses) smooths the burst. Conservative default; a well-
# behaved public ATS easily serves this. Tunable per host below.
CAREERS_HOST_RATE_LIMIT = 30
# Optional per-host overrides (host -> requests/min). Empty by default; add an
# entry only if a specific ATS proves more/less tolerant.
CAREERS_HOST_RATE_LIMITS: dict = {}

# Search engine concurrency: how many (client[, keyword]) fetch units run at
# once. The old engine capped at 4 clients, so 5+ sources queued behind the
# first wave; lifting it lets every source (and, for keyword-parameterized
# clients, every keyword) fetch concurrently. Per-source RateLimiters still
# bound real request rates, so this speeds wall-clock without abusing any API.
SEARCH_MAX_WORKERS = 12

# Scrapling stealth/JS fetch fallback for direct/JS-SPA career pages. On by
# default; a graceful no-op if the `scrapling` package isn't installed. Set
# SCRAPLING_FALLBACK=0 to disable.
SCRAPLING_FALLBACK = os.getenv("SCRAPLING_FALLBACK", "1") != "0"

# Per-domain cooldown for the stealth-fetch escalation (scrape/stealth_fetch.py).
# A real browser render is the most detectable, most server-costly request this
# app makes, and it previously had NO rate limiting at all. Conservative and
# per-HOST (not global), matching the "low volume, non-abusive" fact pattern
# the legal analysis relies on (research-2026-07-01-reach-stealth-legal.md).
STEALTH_FETCH_RATE_LIMIT = 3

# Arbeitnow — free public job-board API, no key. Remote + EU/US listings.
ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"
ARBEITNOW_RATE_LIMIT = 5

# Jooble — aggregator; free API key (env JOOBLE_API_KEY / secrets/jooble_api_key)
# unlocks POST search.
JOOBLE_URL = "https://jooble.org/api/"
JOOBLE_API_KEY = resolve_secret("JOOBLE_API_KEY", "jooble_api_key")
JOOBLE_RATE_LIMIT = 10

# Careerjet — aggregator; free affiliate key (env CAREERJET_AFFID /
# secrets/careerjet_affid) for the public search API.
CAREERJET_URL = "https://public.api.careerjet.net/search"
CAREERJET_AFFID = resolve_secret("CAREERJET_AFFID", "careerjet_affid")
CAREERJET_RATE_LIMIT = 10

# CareerOneStop (US DOL / NLx) — free-key REST API; ~3.5M active US jobs/day from
# all 50 state job banks + ~300k employers (nurses, teachers, trades, retail,
# state/local gov). The single biggest free reach win for non-tech users. Register
# at careeronestop.org/Developers/WebAPI/registration.aspx for a userId + API
# token; both resolve env-then-secret. Key-gated skip like adzuna.
CAREERONESTOP_USER_ID = resolve_secret("CAREERONESTOP_USER_ID", "careeronestop_user_id")
CAREERONESTOP_TOKEN = resolve_secret("CAREERONESTOP_TOKEN", "careeronestop_token")
CAREERONESTOP_BASE_URL = "https://api.careeronestop.org/v1/jobsearch"
CAREERONESTOP_RATE_LIMIT = 20
CAREERONESTOP_RESULTS_PER_PAGE = 50
CAREERONESTOP_RADIUS = 25    # miles around the location
CAREERONESTOP_DAYS = 30      # postings from the last N days
# Required attribution string (US DOL terms of use); surfaced later in the UI.
CAREERONESTOP_ATTRIBUTION = (
    "This data is provided by CareerOneStop, sponsored by the "
    "U.S. Department of Labor, Employment and Training Administration."
)

# Language guard (match/language.py): when armed, a posting whose title+description
# does not read as English is marked score=None ('not scored (language)') instead
# of letting keyword scoring confidently mis-rank a foreign-language listing. OFF
# by default -> byte-identical for Alex; auto-arms when ADZUNA_COUNTRY != 'us', or
# force it with LANGUAGE_GUARD=1.
LANGUAGE_GUARD = os.getenv("LANGUAGE_GUARD", "0") not in ("", "0", "false", "False", "no")


def language_guard_active():
    """True when the English-language guard should run this session: an explicit
    LANGUAGE_GUARD flag, or a non-US Adzuna country where foreign-language
    postings are expected. Read as a function so a test/CLI that flips either
    input mid-process sees the change."""
    if LANGUAGE_GUARD:
        return True
    return (ADZUNA_COUNTRY or "us").strip().lower() != "us"

# LinkedIn — logged-out GUEST endpoint only (public; no auth/cookies/accounts).
# Off by default; the user opts in by adding 'linkedin_guest' to --sources.
LINKEDIN_GUEST_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
LINKEDIN_GUEST_RATE_LIMIT = 3      # conservative; public guest surface
LINKEDIN_GUEST_PAGE_SIZE = 25      # guest endpoint pages by 25

# SerpApi — BYO-paid Google-Jobs backend (env SERPAPI_KEY or secrets/serpapi_key).
SERPAPI_URL = "https://serpapi.com/search"
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
SERPAPI_RATE_LIMIT = 5
SERPAPI_MONTHLY_LIMIT = 250        # verified real free-tier cap (serpapi.com/pricing,
                                    # 2026-07-01: 250 searches/mo, 50/hr); tracked in
                                    # cache/serpapi_usage.json
# SerpApi engine: "google_jobs" (default, surfaces Indeed via Google-for-Jobs) or
# "indeed" (a direct Indeed pull — paid; different JSON shape, parsed defensively).
# ToS-clean routes to Indeed; there is deliberately NO standalone Indeed scraper.
# NOTE (2026-07-01 research): SerpApi's current public engine catalog no longer
# clearly documents a standalone "indeed" engine (only google_jobs/google_jobs_
# listing) — it may be legacy/deprecated. serpapi_client.py warns once (stderr)
# if this engine yields no jobs_results rather than silently returning zero.
SERPAPI_ENGINE = os.getenv("SERPAPI_ENGINE", "google_jobs")

# Socrata / SODA municipal job boards — free, no key required. Optional
# X-App-Token (env SOCRATA_APP_TOKEN) raises the per-IP rate ceiling. City keys
# in SOCRATA_CITIES index into search.socrata_client.SOCRATA_DATASETS (currently
# "nyc"). Empty by default -> the client registers but is inert (no HTTP calls)
# until a user opts a city in; deliberately NOT in DAILY_SOURCES, so the
# automated daily run stays byte-identical for existing users.
SOCRATA_APP_TOKEN = os.getenv("SOCRATA_APP_TOKEN")
SOCRATA_CITIES: list[str] = []
