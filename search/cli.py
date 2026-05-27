import argparse
import json
import sys
import webbrowser
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DEFAULT_KEYWORDS, DEFAULT_LOCATION, OUTPUT_DIR, USER_CONFIG_JSON
from search.adzuna_client import AdzunaClient
from search.jsearch_client import JSearchClient
from search.usajobs_client import USAJobsClient
from search.base_client import JobAPIClient
from search.report_csv import generate_csv_report
from search.report_html import generate_html_report
from search.search_engine import SearchEngine

ALL_SOURCES = ["adzuna", "jsearch", "usajobs", "careers"]


def load_user_config(path=None) -> dict:
    """Load user_config.json. Returns {} if file missing or unreadable."""
    target = Path(path) if path else USER_CONFIG_JSON
    if not target.exists():
        return {}
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [config] Warning: could not load {target.name} — {e}")
        return {}


def build_clients(
    sources: list[str],
    cache_enabled: bool,
    top_n: int = 20,
    industry_filter: str | None = None,
    discovery_enabled: bool = True,
    companies_file: Path | None = None,
) -> list[JobAPIClient]:
    clients: list[JobAPIClient] = []

    for source in sources:
        if source == "adzuna":
            try:
                clients.append(AdzunaClient(cache_enabled=cache_enabled))
            except ValueError as e:
                print(f"  [adzuna] Skipping — {e}")

        elif source == "jsearch":
            try:
                clients.append(JSearchClient(cache_enabled=cache_enabled))
                print(
                    "  [jsearch] NOTE: Free tier is 200 req/month. "
                    "Each keyword/page costs 1 request."
                )
            except ValueError as e:
                print(f"  [jsearch] Skipping — {e}")

        elif source == "usajobs":
            try:
                clients.append(USAJobsClient(cache_enabled=cache_enabled))
            except ValueError as e:
                print(f"  [usajobs] Skipping — {e}")

        elif source == "careers":
            from scrape.careers_client import CareersClient
            clients.append(CareersClient(
                cache_enabled=cache_enabled,
                top_n=top_n,
                industry_filter=industry_filter,
                discovery_enabled=discovery_enabled,
                companies_file=companies_file,
            ))

        else:
            print(f"  Unknown source {source!r} — ignoring.")

    return clients


def main():
    parser = argparse.ArgumentParser(description="Job Search Scraper — multi-source")
    parser.add_argument(
        "--keywords",
        type=str,
        default=None,
        help="Comma-separated keywords (overrides user_config.json and defaults)",
    )
    parser.add_argument(
        "--location",
        type=str,
        default=None,
        help=f"Location to search (default: user_config.json or {DEFAULT_LOCATION})",
    )
    parser.add_argument(
        "--salary-min",
        type=int,
        default=None,
        help="Minimum salary filter (overrides user_config.json)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=2,
        help="Max pages per keyword per source (default: 2)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable response caching",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory (default: ./output)",
    )
    parser.add_argument(
        "--sources",
        type=str,
        default=",".join(ALL_SOURCES),
        help=f"Comma-separated sources to query (default: {','.join(ALL_SOURCES)})",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=20,
        help="Max companies to scrape from career pages (default: 20)",
    )
    parser.add_argument(
        "--industry",
        type=str,
        default=None,
        help="Filter career page registry by industry (e.g. 'health_informatics', 'controls_engineering')",
    )
    parser.add_argument(
        "--no-discover",
        action="store_true",
        help="Skip DuckDuckGo auto-discovery; use only curated registry",
    )
    parser.add_argument(
        "--companies-file",
        type=str,
        default=None,
        help="Path to a companies.json file to merge with the built-in registry",
    )
    parser.add_argument(
        "--user-config",
        type=str,
        default=None,
        help="Path to a user_config.json file (default: ./user_config.json)",
    )
    parser.add_argument(
        "--add-keyword",
        type=str,
        default=None,
        help="Append one keyword to the resolved list for this run (does not persist)",
    )
    parser.add_argument(
        "--sort-by",
        choices=["date", "location"],
        default="date",
        help="Sort results by 'date' (default) or 'location' proximity",
    )
    parser.add_argument(
        "--edit-csv",
        action="store_true",
        help="Open output CSV in default app after search completes (Windows only)",
    )
    args = parser.parse_args()

    # --- Resolve values: CLI flag > user_config.json > hardcoded defaults ---
    user_cfg = load_user_config(args.user_config)

    if args.keywords:
        keywords = [k.strip() for k in args.keywords.split(",")]
    elif user_cfg.get("keywords"):
        keywords = list(user_cfg["keywords"])
    else:
        keywords = list(DEFAULT_KEYWORDS)
    if args.add_keyword:
        keywords.append(args.add_keyword.strip())

    location = args.location or user_cfg.get("location") or DEFAULT_LOCATION

    if args.salary_min is not None:
        salary_min = args.salary_min
    elif user_cfg.get("salary_min") is not None:
        salary_min = int(user_cfg["salary_min"])
    else:
        salary_min = None

    industry = args.industry or user_cfg.get("industry") or None

    default_sources_str = ",".join(ALL_SOURCES)
    cfg_sources = user_cfg.get("sources", {})
    if args.sources != default_sources_str:
        sources = [s.strip().lower() for s in args.sources.split(",")]
    else:
        sources = [s for s in ALL_SOURCES if cfg_sources.get(s, True)]

    output_dir = Path(args.output_dir) if args.output_dir else OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    companies_file = Path(args.companies_file) if args.companies_file else None

    today = date.today().isoformat()

    print(f"Sources requested: {sources}")
    clients = build_clients(
        sources,
        cache_enabled=not args.no_cache,
        top_n=args.top_n,
        industry_filter=industry,
        discovery_enabled=not args.no_discover,
        companies_file=companies_file,
    )

    if not clients:
        print("Error: no sources could be initialized. Check your .env credentials.")
        sys.exit(1)

    active = [type(c).__name__ for c in clients]
    print(f"Active sources: {active}\n")

    engine = SearchEngine(clients)
    results = engine.run_full_search(
        keywords=keywords,
        location=location,
        salary_min=salary_min,
        max_pages_per_keyword=args.max_pages,
        sort_by=args.sort_by,
    )

    if not results:
        print("No results found.")
        sys.exit(0)

    search_params = {
        "date": today,
        "location": location,
        "keywords": keywords,
        "salary_min": salary_min,
        "sources": active,
    }

    html_path = output_dir / f"job_search_{today}.html"
    csv_path = output_dir / f"job_search_{today}.csv"

    generate_html_report(results, html_path, search_params)
    generate_csv_report(results, csv_path)

    print(f"\nHTML report: {html_path}")
    print(f"CSV report:  {csv_path}")

    if args.edit_csv:
        import os
        try:
            os.startfile(str(csv_path))  # Windows only
        except Exception:
            print(f"  [output] Could not open CSV automatically — find it at: {csv_path}")

    webbrowser.open(html_path.as_uri())


if __name__ == "__main__":
    main()
