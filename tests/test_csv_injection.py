"""CSV export must neutralize spreadsheet formula injection (2026-06 review)."""
from search.report_csv import generate_csv_report
from models import JobResult


def test_dangerous_leading_chars_are_quoted(tmp_path):
    job = JobResult(
        title='=HYPERLINK("http://evil")', company="@SUM(A1:A2)",
        location="-2+3", salary_min=None, salary_max=None,
        description="ok", url="http://x", source_keyword="k", created="",
    )
    out = generate_csv_report([job], tmp_path / "r.csv")
    text = out.read_text(encoding="utf-8")
    assert "'=HYPERLINK" in text
    assert "'@SUM" in text
    assert "'-2+3" in text
