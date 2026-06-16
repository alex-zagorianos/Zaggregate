import csv
from pathlib import Path

from models import JobResult


def _csv_safe(value):
    """Guard against CSV/formula injection: a field starting with = + - @ (or a
    control char) is prefixed with a single quote so spreadsheets don't execute
    it. Non-string / empty values pass through unchanged."""
    if isinstance(value, str) and value and value[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def generate_csv_report(results: list[JobResult], output_path: Path) -> Path:
    fieldnames = [
        "score",
        "title",
        "company",
        "location",
        "salary_min",
        "salary_max",
        "url",
        "source_api",
        "source_keyword",
        "created",
        "description",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for job in results:
            writer.writerow(
                {
                    "score": job.score if job.score >= 0 else "",
                    "title": _csv_safe(job.title),
                    "company": _csv_safe(job.company),
                    "location": _csv_safe(job.location),
                    "salary_min": job.salary_min or "",
                    "salary_max": job.salary_max or "",
                    "url": job.url,
                    "source_api": job.source_api,
                    "source_keyword": job.source_keyword,
                    "created": job.created,
                    "description": _csv_safe(job.description[:500]),
                }
            )

    return output_path
