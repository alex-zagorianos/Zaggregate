import argparse
import sys
import webbrowser
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DEFAULT_KEYWORDS, DEFAULT_LOCATION, OUTPUT_DIR
from search.adzuna_client import AdzunaClient
from search.jsearch_client import JSearchClient
from search.usajobs_client import USAJobsClient
from search.base_client import JobAPIClient
from search.report_csv import generate_csv_report
from search.report_html import generate_html_report
from search.search_engine import SearchEngine

ALL_SOURCES = ["adzuna", "jsearch", "usajobs", "careers"]


def build_clients(
    sources: list[str],
    cache_enabled: bool,
    top_n: int = 20,
    industry_filter: str | None = None,
    discovery_enabled: bool = True,
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
        help="Comma-separated keywords (overrides defaults)",
    )
    parser.add_argument(
        "--location",
        type=str,
        default=DEFAULT_LOCATION,
        help=f"Location to search (default: {DEFAULT_LOCATION})",
    )
    parser.add_argument(
        "--salary-min",
        type=int,
        default=None,
        help="Minimum salary filter",
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
    args = parser.parse_args()

    keywords = (
        [k.strip() for k in args.keywords.split(",")]
        if args.keywords
        else DEFAULT_KEYWORDS
    )
    output_dir = Path(args.output_dir) if args.output_dir else OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    sources = [s.strip().lower() for s in args.sources.split(",")]

    today = date.today().isoformat()

    print(f"Sources requested: {sources}")
    clients = build_clients(
        sources,
        cache_enabled=not args.no_cache,
        top_n=args.top_n,
        industry_filter=args.industry,
        discovery_enabled=not args.no_discover,
    )

    if not clients:
        print("Error: no sources could be initialized. Check your .env credentials.")
        sys.exit(1)

    active = [type(c).__name__ for c in clients]
    print(f"Active sources: {active}\n")

    engine = SearchEngine(clients)
    results = engine.run_full_search(
        keywords=keywords,
        location=args.location,
        salary_min=args.salary_min,
        max_pages_per_keyword=args.max_pages,
    )

    if not results:
        print("No results found.")
        sys.exit(0)

    search_params = {
        "date": today,
        "location": args.location,
        "keywords": keywords,
        "salary_min": args.salary_min,
        "sources": active,
    }

    html_path = output_dir / f"job_search_{today}.html"
    csv_path = output_dir / f"job_search_{today}.csv"

    generate_html_report(results, html_path, search_params)
    generate_csv_report(results, csv_path)

    print(f"\nHTML report: {html_path}")
    print(f"CSV report:  {csv_path}")

    webbrowser.open(html_path.as_uri())


if __name__ == "__main__":
    main()
