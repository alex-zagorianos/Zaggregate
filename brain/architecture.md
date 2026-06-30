# Architecture

#scraper #tracker #resume #gui

## Search Data Flow

```
cli.py
  └─ build_clients() → [AdzunaClient, JSearchClient, USAJobsClient, CareersClient]
       └─ SearchEngine(clients)
            └─ run_full_search()
                 ├─ client.search_and_parse(keyword, location, salary_min, page) → list[JobResult]
                 │     ├─ API clients: default impl = search() + parse_results()
                 │     └─ CareersClient: overrides directly (no dict roundtrip)
                 └─ _deduplicate() → sorted list[JobResult]   (--sort-by date|location)
                      ├─ generate_html_report() → output/job_search_DATE.html
                      └─ generate_csv_report()  → output/job_search_DATE.csv
```

## Two more job ingestion paths feed the same model

```
Browser extension (browser_ext/)              Career-page scraping (scrape/)
  └─ harvests jobs off 5 sites                   ├─ Greenhouse / Lever  (public JSON)
  ├─ "Send to Tool"                              ├─ Workday             (slug tenant:N:site)
  │    └─ browser_receiver.py :5002 → report     └─ direct (BeautifulSoup best-effort)
  └─ "Track All as Interested"                  CareersClient wraps these into the
       └─ tracker /api/add :5001                 SearchEngine pipeline via companies.json
                                                 + REGISTRIES (controls / health_informatics)
```

## Key Design Decisions

- **Each client owns its own parsing** — `parse_results()` lives on the client, not SearchEngine. This keeps source-specific field mapping isolated.
- **Dedup is cross-source** — MD5(title+company+location). Same job appearing in Adzuna AND JSearch is deduplicated.
- **`source_api` field** — tracks which API returned each result. Used for filtering in HTML report.
- **Graceful degradation** — missing credentials skip that source with a warning, don't crash.
- **Caching per-source** — `cache/adzuna/`, `cache/jsearch/`, `cache/usajobs/`, 24-hour TTL.

## Client Abstraction

```python
# search/base_client.py
class JobAPIClient(ABC):
    def search(keyword, location, salary_min, page) -> dict
    def parse_results(raw, source_keyword) -> list[JobResult]
```

Adding a new source = create a new file inheriting `JobAPIClient`. Everything else picks it up automatically once added to `build_clients()` in cli.py.

## Model

```python
# models.py
@dataclass
class JobResult:
    title, company, location
    salary_min, salary_max  # Optional[float]
    description, url
    source_keyword          # which search term matched
    created                 # ISO-8601 string
    job_id                  # prefixed: "adzuna_X", "jsearch_X", "usajobs_X", "careers_X"
    source_api              # "adzuna" | "jsearch" | "usajobs" | "greenhouse" | "lever" |
                            #   "workday" | "direct" | "<site>_browser"
```

## Phase 2 — Resume Generator ✅ COMPLETE (code)

Paste a job posting → generate a tailored resume + cover letter via Claude API → DOCX.

- `resume/experience_parser.py` — parses `experience.md` by `## ` headings
- `resume/generator.py` — single Claude call → structured JSON (`_parse_response()` strips ``` fences)
- `resume/docx_builder.py` — `build_resume_docx()` + `build_cover_letter_docx()`, navy `#1a1a2e` theme
- `resume/app.py` — Flask :5000, `POST /generate` → .zip of both DOCXs
  Needs `ANTHROPIC_API_KEY` in `.env` to run.

## UI surfaces — two ways to drive the tools

| Surface                 | Entry             | Covers                                           |
| ----------------------- | ----------------- | ------------------------------------------------ |
| **Desktop GUI** (newer) | `py gui.py`       | Tracker + Resume in one tkinter window, two tabs |
| **Web (Flask)**         | `run_servers.bat` | Resume :5000, Tracker :5001, Receiver :5002      |

`gui.py` talks to `tracker/db.py` directly and imports `resume.generator`/`resume.docx_builder`
in a worker thread — no HTTP, no servers needed for those two functions. The Flask apps remain
for the browser-extension receiver (:5002) and as a browser-based alternative.
