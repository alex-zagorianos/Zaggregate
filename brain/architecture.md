# Architecture

#phase1 #scraper

## Data Flow

```
cli.py
  └─ build_clients() → [AdzunaClient, JSearchClient, USAJobsClient]
       └─ SearchEngine(clients)
            └─ run_full_search()
                 ├─ client.search(keyword, location, page) → raw dict
                 ├─ client.parse_results(raw, keyword) → list[JobResult]
                 └─ _deduplicate() → sorted list[JobResult]
                      ├─ generate_html_report() → output/job_search_DATE.html
                      └─ generate_csv_report()  → output/job_search_DATE.csv
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
    job_id                  # prefixed: "adzuna_X", "jsearch_X", "usajobs_X"
    source_api              # "adzuna" | "jsearch" | "usajobs"
```

## Phase 2 (NOT STARTED)

Flask web app — paste job posting → generate tailored resume + cover letter via Claude API → download DOCX.
Files to build: `resume/experience_parser.py`, `resume/generator.py`, `resume/docx_builder.py`, `resume/app.py`
