import csv
from pathlib import Path

from models import JobResult


def generate_csv_report(results: list[JobResult], output_path: Path) -> Path:
    fieldnames = [
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
                    "title": job.title,
                    "company": job.company,
                    "location": job.location,
                    "salary_min": job.salary_min or "",
                    "salary_max": job.salary_max or "",
                    "url": job.url,
                    "source_api": job.source_api,
                    "source_keyword": job.source_keyword,
                    "created": job.created,
                    "description": job.description[:500],
                }
            )

    return output_path
