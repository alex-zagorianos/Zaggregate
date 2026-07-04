import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Product version (single source of truth) ──────────────────────────────────
# Every user-facing version string (packaged zip name, CHANGES.txt, the About
# dialog, last_run.json, the "Report a problem" bundle, app.spec metadata) reads
# THIS constant so a release bumps one line. Semantic versioning; see
# brain/review-2026-07-01-deep-product-review.md (P7 product lifecycle).
APP_VERSION = "1.0.0"

# ── Logging framework (applog.py) ─────────────────────────────────────────────
# A rotating file log lives under the user data folder so source failures,
# 429-erosion, and daily-run errors finally persist somewhere a friend can zip
# up and send ("Report a problem"). Console output is unchanged; the file is an
# additive mirror. See applog.get_logger().
LOG_DIR_NAME = "logs"            # <USER_DATA_DIR>/logs/
LOG_FILE_NAME = "app.log"        # rotating primary log
LOG_MAX_BYTES = 1_048_576        # 1 MB per file
LOG_BACKUP_COUNT = 5             # app.log + app.log.1 .. app.log.5


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
LOG_DIR = USER_DATA_DIR / LOG_DIR_NAME


def log_dir() -> Path:
    """The rotating-log directory (<USER_DATA_DIR>/logs), created on demand.
    A function (not just the LOG_DIR constant) so a test that repoints
    USER_DATA_DIR still lands its logs under the temp folder via applog, which
    resolves this lazily."""
    d = USER_DATA_DIR / LOG_DIR_NAME
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


def ensure_writable_dirs() -> None:
    """Create cache/, output/ and logs/ under WRITABLE_DIR. Safe to call
    repeatedly."""
    for d in (CACHE_DIR, OUTPUT_DIR, LOG_DIR):
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


# Careerjet's public search API is locale-scoped (its ~90 country sites each
# have a `locale_code` like "en_GB", "de_DE"); a bare US-English default is
# implicit when the param is omitted, so 'us' stays byte-identical (no
# locale_code sent — see careerjet_client.py). Only countries Careerjet
# documents a locale for are mapped; anything else (including an unmapped
# ADZUNA_COUNTRIES member) falls back to omitting locale_code entirely, same
# as today.
CAREERJET_LOCALES: dict = {
    "gb": "en_GB", "ca": "en_CA", "au": "en_AU", "in": "en_IN", "sg": "en_SG",
    "nz": "en_NZ", "za": "en_ZA", "de": "de_DE", "fr": "fr_FR", "es": "es_ES",
    "it": "it_IT", "nl": "nl_NL", "pl": "pl_PL", "br": "pt_BR", "mx": "es_MX",
    "at": "de_AT", "be": "fr_BE", "ch": "de_CH",
}

# Jooble is a per-country-hostname aggregator (`{cc}.jooble.org/api/{key}`); the
# bare `jooble.org` host (no subdomain) is its US/international default, so
# 'us' stays byte-identical (no host change — see jooble_client.py). Only
# countries with a known Jooble country site are mapped.
JOOBLE_COUNTRY_HOSTS: dict = {
    "gb": "uk.jooble.org", "ca": "ca.jooble.org", "au": "au.jooble.org",
    "in": "in.jooble.org", "de": "de.jooble.org", "fr": "fr.jooble.org",
    "es": "es.jooble.org", "it": "it.jooble.org", "nl": "nl.jooble.org",
    "pl": "pl.jooble.org", "br": "br.jooble.org", "mx": "mx.jooble.org",
    "at": "at.jooble.org", "be": "be.jooble.org", "ch": "ch.jooble.org",
    "nz": "nz.jooble.org", "za": "za.jooble.org", "sg": "sg.jooble.org",
}


def careerjet_locale_for(country: str | None = None) -> str | None:
    """Careerjet `locale_code` for a two-letter country code, or None (omit the
    param — US/default behavior) when unmapped or 'us'."""
    cc = (country or "us").strip().lower()
    if cc == "us":
        return None
    return CAREERJET_LOCALES.get(cc)


def jooble_host_for(country: str | None = None) -> str:
    """Jooble API hostname for a two-letter country code; the bare 'jooble.org'
    default (US/international) when unmapped or 'us'."""
    cc = (country or "us").strip().lower()
    if cc == "us":
        return "jooble.org"
    return JOOBLE_COUNTRY_HOSTS.get(cc, "jooble.org")

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
# The fast/cheap model for light one-shot calls (industry-profile enrichment).
# Resolvable so a BYO-AI backend that lacks the haiku id can point it elsewhere;
# defaults to the current hardcoded value so behavior is byte-identical.
ANTHROPIC_FAST_MODEL = os.getenv("ANTHROPIC_FAST_MODEL", "claude-haiku-4-5-20251001")


def anthropic_base_url():
    """Provider-agnostic API base URL for ALL five AI call sites (ranker /
    gui / resume-generator / company-enumeration / industry-profile). Resolves
    env-then-secret ('base_url'): the ANTHROPIC_BASE_URL env var wins, else the
    plaintext file the in-app 'Connect your AI' box writes to secrets/base_url,
    else None (the SDK's default = Anthropic's own endpoint, byte-identical for
    Alex). Any Anthropic-compatible endpoint works: Ollama v0.14+ native, GLM,
    DeepSeek, Kimi. Read as a function (not frozen at import) so a URL pasted
    into the box after startup takes effect without a restart, mirroring
    resolve_secret's laziness.

    None is returned for an empty/whitespace value so `anthropic.Anthropic(
    base_url=None)` falls through to the SDK default rather than a broken URL."""
    v = resolve_secret("ANTHROPIC_BASE_URL", "base_url")
    v = (v or "").strip()
    return v or None


# Frozen snapshot for back-compat / import-time readers; the callers prefer the
# function above so a mid-session paste is honored.
ANTHROPIC_BASE_URL = anthropic_base_url()

# Opt-in auto-rank: after a daily run scores + inboxes new jobs, optionally rank
# the top-K new qualified jobs via the direct API/local model so the user "wakes
# up to a ranked inbox". OFF by default (env AUTO_RANK / user_config 'auto_rank')
# so Alex's run stays byte-identical. Requires a configured key OR base_url.
AUTO_RANK = os.getenv("AUTO_RANK", "0") not in ("", "0", "false", "False", "no")
# How many of the top new qualified jobs to auto-rank per run (a compact prompt,
# so ~trivial cost); overridable via user_config 'auto_rank_top_k'.
AUTO_RANK_TOP_K = int(os.getenv("AUTO_RANK_TOP_K", "25") or "25")


def auto_rank_enabled(cfg: dict | None = None) -> bool:
    """True when opt-in auto-rank should run this daily pass: the AUTO_RANK env
    flag OR user_config 'auto_rank' is truthy. Gating on a configured backend
    (key or base_url) is the caller's job. Default OFF."""
    if AUTO_RANK:
        return True
    return bool((cfg or {}).get("auto_rank"))

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
# Brave company-discovery (scrape/discoverer.py) used the generic 24h
# CACHE_TTL_HOURS, which sits right at daily_run's ~24h schedule boundary --
# in practice the cache was stale by the next scheduled run and re-fired a
# LIVE Brave API call for every (ats_site, keyword) pair, every day (S35 #25).
# New boards appearing on Greenhouse/Lever/etc. for a fixed keyword do not
# change hour-to-hour, so discovery gets its own, much longer TTL: 7 days.
DISCOVERY_CACHE_TTL_HOURS = 168
# discover/inbox_harvest.py had NO negative-cache at all: a company name whose
# domain-guess never resolves (very common -- multi-word names, name != domain,
# renamed companies) was re-probed with 3 live HTTP round-trips EVERY daily run,
# forever (S35 #26). 14 days: long enough that a bad guess isn't re-hammered
# daily, short enough that a company that later gets a real careers page (a
# renamed domain, a new ATS) is retried well within a month.
INBOX_HARVEST_NEGATIVE_TTL_HOURS = 336

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
#
# We query the `search` endpoint with `country=US` instead of the bare browse
# feed: the browse feed (/jobs/api) is unfiltered and ~45% of a page is
# region-locked NON-US postings (UK/Canada/India/Philippines — measured 9/20 on
# 2026-07-02), which are false positives for a US remote seeker (the
# marketing-remote persona's #1 gap). The `search` endpoint
# (/jobs/api/search?country=US) returns only US-eligible rows (0/20 non-US-only,
# same measurement) and honors a server-side `q=` keyword filter. Same JSON
# shape ({jobs, totalCount, offset, limit}), so parsing is unchanged.
# HIMALAYAS_URL stays the browse base for back-compat; HIMALAYAS_SEARCH_URL is
# the filtered endpoint the client actually calls. ATTRIBUTION/ToS: the job URL
# MUST remain the Himalayas link (link-back), and Himalayas rows must NEVER be
# forwarded into any Jooble/Google-Jobs path (each client queries its own API
# independently — no cross-source forwarding exists; pinned by a test).
HIMALAYAS_URL = "https://himalayas.app/jobs/api"
HIMALAYAS_SEARCH_URL = "https://himalayas.app/jobs/api/search"
# ISO-3166 alpha-2 the search endpoint filters on (US-eligible remote only).
HIMALAYAS_COUNTRY = "US"
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
                 "weworkremotely", "workingnomads", "jooble", "careerjet",
                 "higheredjobs", "rnjobsite", "reap", "edjoin", "jobsacuk"]
# weworkremotely + workingnomads (2026-07-01): free/keyless remote boards, same
# risk profile as remoteok/remotive — added to widen the daily net. They auto-gate
# OFF for non-knowledge-work fields (TECH_SKEWED_SOURCES). jsearch stays excluded:
# 10 keywords/day would blow the 200/month free tier in ~3 weeks (manual only).
# jooble + careerjet (aggregators) and careeronestop (US DOL, ~3.5M jobs/day) are
# now in the daily net but ALL THREE self-skip cleanly when their free key is
# unset (build_clients logs a one-line skip), so a keyless user's daily run is
# unchanged — they light up the moment a key is pasted into 'Connect job sources'.
# higheredjobs + rnjobsite (2026-07-01, E2): free/keyless SECTOR RSS feeds
# (education-family / nursing). They INDUSTRY-GATE at construction — inert (fetch
# nothing) for any field that doesn't map (an eng/finance/trade/Alex project polls
# neither), so adding them to the daily net is byte-identical for a non-education,
# non-nursing user. jobsacuk (UK academic, S35) IS now here: it registers on every
# run but self-gates via its OWN opt_in_active() (a truthy config flag OR a non-US
# adzuna_country_for(location)) — a US project (including Alex's) never satisfies
# either trigger, so `c.active` is False and search()/parse_results() make zero
# network calls (see jobsacuk_client.search: `if ... not self.active: return
# {"items": []}` before any request). Registering-but-inert is the SAME contract
# reap/edjoin/higheredjobs/rnjobsite already use above.
# reap + edjoin (2026-07-02, S32b): free/keyless K-12 EDUCATION sources — REAP
# (per-state public teacher portals; light HTML, robots.txt honored live) and
# EdJoin (public /Home/LoadJobs JSON, California-centric). Both INDUSTRY-GATE to
# education-family fields; REAP additionally self-skips outside its covered states
# (CT/MO/NM/OH/PA — routes by the user's location), EdJoin returns 0 gracefully
# for non-CA metros. Inert (no network, no jobs) for every non-education field, so
# adding them to the daily net is byte-identical for a non-education user. NEVER
# Frontline/AppliTrack or NEOGOV — those are ToS-blocked; REAP/EdJoin are the
# ToS-safe public applicant sites that route around them (plan §5 Education row).

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

# SerpApi REACH PROBE (E2 / review P1 Tier A): the daily run's reach % can only be
# certified when >=2 INDEPENDENT source families OVERLAP (a job seen by two of
# them). The free families are largely disjoint today (f2=0 -> "cannot certify").
# A tiny SerpApi Google-Jobs probe (1-2 queries/run, ~30-60/month, well inside the
# 250/month free tier) issued and MERGED into the run's raw results BEFORE
# estimate_reach gives capture-recapture the cross-family overlap it needs, so the
# reach badge finally lights up. The probe jobs are REAL postings and also flow
# into the normal scored pipeline (job_key dedup handles collisions).
#
# Default ON when a SerpApi key is present (Alex has one — intended). It never
# runs without a key, and the MonthlyQuota inside SerpApiClient still bounds spend.
# Turn OFF with REACH_PROBE=0 (env) or "reach_probe": false (user_config).
REACH_PROBE = os.getenv("REACH_PROBE", "1") not in ("", "0", "false", "False", "no")
# How many broadened-keyword probe queries to issue per run (1-2 recommended;
# each is one SerpApi search against the monthly quota). Overridable via
# user_config 'reach_probe_queries'.
REACH_PROBE_QUERIES = int(os.getenv("REACH_PROBE_QUERIES", "2") or "2")


def reach_probe_enabled(cfg: dict | None = None) -> bool:
    """True when the SerpApi reach probe should run this daily pass: the
    REACH_PROBE env flag (default ON) AND not explicitly disabled in user_config
    ('reach_probe': false). Gating on an actual SerpApi key is the caller's job
    (the probe self-skips without one). Read as a function so a test flipping the
    config value is honored."""
    if cfg is not None and "reach_probe" in cfg:
        return bool(cfg.get("reach_probe"))
    return REACH_PROBE

# Socrata / SODA municipal job boards — free, no key required. Optional
# X-App-Token (env SOCRATA_APP_TOKEN) raises the per-IP rate ceiling. City keys
# in SOCRATA_CITIES index into search.socrata_client.SOCRATA_DATASETS (currently
# "nyc"). Empty by default -> the client registers but is inert (no HTTP calls)
# until a user opts a city in; deliberately NOT in DAILY_SOURCES, so the
# automated daily run stays byte-identical for existing users.
SOCRATA_APP_TOKEN = os.getenv("SOCRATA_APP_TOKEN")
SOCRATA_CITIES: list[str] = []
