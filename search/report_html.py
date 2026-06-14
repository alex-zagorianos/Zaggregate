from pathlib import Path
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader

from config import BASE_DIR, PORT_TRACKER
from models import JobResult


def safe_url(url: str) -> str:
    """Jinja filter: pass through only http(s) URLs, else '#'. Autoescape stops
    tag injection but not javascript:/data: schemes inside an href."""
    try:
        return url if urlparse(url or "").scheme in ("http", "https") else "#"
    except ValueError:
        return "#"


def generate_html_report(
    results: list[JobResult], output_path: Path, search_params: dict
) -> Path:
    template_dir = BASE_DIR / "search" / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)
    env.filters["safe_url"] = safe_url
    template = env.get_template("report.html")

    keyword_counts: dict[str, int] = {}
    for job in results:
        keyword_counts[job.source_keyword] = keyword_counts.get(job.source_keyword, 0) + 1

    html = template.render(
        results=results,
        search_params=search_params,
        keyword_counts=keyword_counts,
        total=len(results),
        tracker_port=PORT_TRACKER,
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return output_path
