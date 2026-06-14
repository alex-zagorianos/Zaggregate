"""
Local Flask server that receives jobs from the browser extension.
Run with: py -m scrape.browser_receiver
Then click "Send to Tool" in the extension popup.
Report opens automatically in your browser.
"""
import hashlib
import re
import sys
import webbrowser
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, request, jsonify

from models import JobResult
from search.report_html import generate_html_report
from search.report_csv import generate_csv_report
import workspace
from config import PORT_RECEIVER

app = Flask(__name__)
PORT = PORT_RECEIVER

# Only the unpacked browser extension talks to this server. A chrome-extension://
# origin is unguessable per-install, so we reflect exactly that scheme rather
# than the old wildcard, which let *any* site the user visited POST job data here.
_ALLOWED_ORIGIN_SCHEME = "chrome-extension"


def _add_cors(response):
    origin = request.headers.get("Origin", "")
    if urlparse(origin).scheme == _ALLOWED_ORIGIN_SCHEME:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    response.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

app.after_request(_add_cors)


def _safe_http_url(url: str) -> bool:
    """Reject javascript:/data: and other non-web schemes before a URL is ever
    written into an HTML report's href."""
    try:
        return urlparse(url).scheme in ("http", "https")
    except ValueError:
        return False


@app.route("/status")
def status():
    return jsonify({"status": "ok", "port": PORT})


@app.route("/harvest", methods=["POST", "OPTIONS"])
def harvest():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.get_json(force=True, silent=True)
    if not data or "jobs" not in data:
        return jsonify({"error": "Expected JSON with 'jobs' array"}), 400

    raw_jobs = data["jobs"]
    if not isinstance(raw_jobs, list) or len(raw_jobs) == 0:
        return jsonify({"error": "No jobs received"}), 400

    results = [_to_job_result(j) for j in raw_jobs]
    results = [r for r in results if r is not None]

    if not results:
        return jsonify({"error": "No valid jobs could be parsed"}), 400

    today = date.today().isoformat()
    sources_used = sorted({r.source_api for r in results})
    search_params = {
        "date": today,
        "location": "Browser harvest",
        "keywords": ["(collected while browsing)"],
        "salary_min": None,
        "sources": sources_used,
    }

    html_path = workspace.output_dir() / f"browser_harvest_{today}.html"
    csv_path  = workspace.output_dir() / f"browser_harvest_{today}.csv"

    generate_html_report(results, html_path, search_params)
    generate_csv_report(results, csv_path)

    # Route harvested jobs into the same scored-inbox funnel as daily_run, so
    # browse-collected postings get triaged alongside API results instead of
    # living only in this one-off report. No min-score floor: the user picked
    # these by hand while browsing. (Note: descriptions are empty — card
    # scraping can't see the posting body — so the skill component scores 0
    # and the Claude fit prompt is the better ranking signal for these.)
    inboxed = 0
    try:
        from config import DEFAULT_KEYWORDS, DEFAULT_LOCATION
        from match.scorer import score_jobs
        from search.cli import load_user_config
        from tracker.db import inbox_add_many, init_db
        cfg = load_user_config()
        scored = score_jobs(
            results,
            keywords=cfg.get("keywords") or DEFAULT_KEYWORDS,
            location=cfg.get("location") or DEFAULT_LOCATION,
            salary_floor=cfg.get("salary_min"),
            exclude_keywords=cfg.get("exclude_keywords", []),
            exclude_titles=cfg.get("exclude_titles"),
            title_miss_penalty=cfg.get("title_miss_penalty"),
            seniority_exclude=cfg.get("seniority_exclude"),
        )
        init_db()
        inboxed = inbox_add_many(scored)
    except Exception as e:
        # The report already saved; a scoring/DB hiccup shouldn't lose the run.
        print(f"[receiver] inbox routing failed - {e}")

    webbrowser.open(html_path.as_uri())

    print(f"\n[receiver] {len(results)} jobs received -> {html_path.name} "
          f"({inboxed} new to inbox)")

    return jsonify({
        "received": len(results),
        "inboxed": inboxed,
        "html": str(html_path),
        "csv":  str(csv_path),
    })


def _to_job_result(j) -> JobResult | None:
    if not isinstance(j, dict):
        return None
    title = (j.get("title") or "").strip()
    url   = (j.get("url")   or "").strip()
    if not title or not url or not _safe_http_url(url):
        return None

    company  = (j.get("company")  or "").strip()
    location = (j.get("location") or "").strip()
    source   = j.get("source", "browser")

    salary_min = j.get("salary_min")
    salary_max = j.get("salary_max")

    # Fallback: try to parse salary from text if numerics weren't sent
    if salary_min is None:
        salary_min, salary_max = _parse_salary(j.get("salary_text", ""))

    created = j.get("captured_at") or datetime.now(timezone.utc).isoformat()

    uid = hashlib.md5(url.encode()).hexdigest()[:10]
    job_id = f"browser_{uid}"

    return JobResult(
        title=title,
        company=company,
        location=location,
        salary_min=salary_min,
        salary_max=salary_max,
        description="",
        url=url,
        source_keyword="(browser harvest)",
        created=created,
        job_id=job_id,
        source_api=f"{source}_browser",
    )


# Hourly only when a rate unit is actually attached to a number — anchored so
# stray "hr"/"hour" substrings in company/location text ("Pittsburgh", "Amherst",
# "HR Manager") can't trigger the x2080 annualization on real salaries.
_HOURLY_RE = re.compile(r"(?:/|\bper\s+)\s*(?:hr|hour)\b|\bhourly\b|/hr\b", re.I)
_MONEY_RE = re.compile(r"\$\s*\d[\d,]*(?:\.\d+)?\s*[Kk]?")


def _parse_salary(text: str):
    """Single source of truth for salary text -> (min, max) annual floats.
    The browser extension sends raw ``salary_text`` and lets this parse it, so
    the JS side no longer maintains a divergent numeric parser."""
    if not text:
        return None, None
    hourly = bool(_HOURLY_RE.search(text))
    parsed = []
    for token in _MONEY_RE.findall(text):
        n = token.replace("$", "").replace(",", "").replace(" ", "")
        try:
            if n[-1:].lower() == "k":
                parsed.append(float(n[:-1]) * 1000)
            else:
                val = float(n)
                if hourly and val < 500:  # looks like an hourly rate -> annualize
                    val *= 2080
                parsed.append(val)
        except ValueError:
            continue
    if len(parsed) >= 2:
        return parsed[0], parsed[1]
    if len(parsed) == 1:
        return parsed[0], None
    return None, None


if __name__ == "__main__":
    print(f"Job Harvester receiver running on http://localhost:{PORT}")
    print("Load the browser extension, browse LinkedIn/Indeed, then click 'Send to Tool'.\n")
    app.run(port=PORT, debug=False)
