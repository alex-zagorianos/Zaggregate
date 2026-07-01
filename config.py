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

# Adzuna
ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY")
ADZUNA_BASE_URL = "https://api.adzuna.com/v1/api/jobs/us/search"
ADZUNA_RATE_LIMIT = 25
ADZUNA_RESULTS_PER_PAGE = 50

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

# USAJobs — federal job board (requires registration at usajobs.gov)
USAJOBS_API_KEY = os.getenv("USAJOBS_API_KEY")
USAJOBS_USER_AGENT = os.getenv("USAJOBS_USER_AGENT")  # must be your email
USAJOBS_BASE_URL = "https://data.usajobs.gov/api/search"
USAJOBS_RATE_LIMIT = 50
USAJOBS_RESULTS_PER_PAGE = 25

# Search defaults
DEFAULT_LOCATION = "Cincinnati"
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
DAILY_SOURCES = ["adzuna", "usajobs", "careers", "themuse", "remoteok",
                 "remotive", "jobicy", "himalayas", "hn"]
# jsearch is excluded from DAILY_SOURCES: 10 keywords/day would blow the
# 200/month free tier in ~3 weeks. Use it for manual searches only.

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

# Jooble — aggregator; free API key (env JOOBLE_API_KEY) unlocks POST search.
JOOBLE_URL = "https://jooble.org/api/"
JOOBLE_API_KEY = os.getenv("JOOBLE_API_KEY")
JOOBLE_RATE_LIMIT = 10

# Careerjet — aggregator; free affiliate key (env CAREERJET_AFFID) for the public search API.
CAREERJET_URL = "https://public.api.careerjet.net/search"
CAREERJET_AFFID = os.getenv("CAREERJET_AFFID")
CAREERJET_RATE_LIMIT = 10

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
