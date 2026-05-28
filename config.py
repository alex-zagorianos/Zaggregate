import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent


BASE_DIR = _get_base_dir()
EXPERIENCE_FILE = BASE_DIR / "experience.md"
CACHE_DIR = BASE_DIR / "cache"
OUTPUT_DIR = BASE_DIR / "output"
COMPANIES_JSON = BASE_DIR / "companies.json"
USER_CONFIG_JSON = BASE_DIR / "user_config.json"

CACHE_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# Adzuna
ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY")
ADZUNA_BASE_URL = "https://api.adzuna.com/v1/api/jobs/us/search"
ADZUNA_RATE_LIMIT = 25
ADZUNA_RESULTS_PER_PAGE = 50

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = "claude-sonnet-4-6"

# JSearch (RapidAPI) — aggregates Indeed, LinkedIn, Glassdoor
JSEARCH_RAPIDAPI_KEY = os.getenv("JSEARCH_RAPIDAPI_KEY")
JSEARCH_RAPIDAPI_HOST = "jsearch.p.rapidapi.com"
JSEARCH_BASE_URL = "https://jsearch.p.rapidapi.com/search"
JSEARCH_RATE_LIMIT = 5       # per minute (free tier: 200 req/month total)
JSEARCH_RESULTS_PER_PAGE = 10

# USAJobs — federal job board (requires registration at usajobs.gov)
USAJOBS_API_KEY = os.getenv("USAJOBS_API_KEY")
USAJOBS_USER_AGENT = os.getenv("USAJOBS_USER_AGENT")  # must be your email
USAJOBS_BASE_URL = "https://data.usajobs.gov/api/search"
USAJOBS_RATE_LIMIT = 50
USAJOBS_RESULTS_PER_PAGE = 25

# Search defaults
DEFAULT_LOCATION = "Cincinnati"
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

# Flask server ports
PORT_RESUME   = 5000
PORT_TRACKER  = 5001
PORT_RECEIVER = 5002

# Brave Search API — free tier: 2,000 req/month at api.search.brave.com
# Sign up at https://api.search.brave.com/ and add to .env to enable company discovery.
BRAVE_SEARCH_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY")
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"

# Careers scraper
CAREERS_MAX_WORKERS = 8
CAREERS_REQUEST_TIMEOUT = 20
