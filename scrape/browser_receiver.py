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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, request, jsonify

from models import JobResult
from search.report_html import generate_html_report
from search.report_csv import generate_csv_report
from config import OUTPUT_DIR, PORT_RECEIVER

app = Flask(__name__)
PORT = PORT_RECEIVER


def _add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

app.after_request(_add_cors)


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

    html_path = OUTPUT_DIR / f"browser_harvest_{today}.html"
    csv_path  = OUTPUT_DIR / f"browser_harvest_{today}.csv"

    generate_html_report(results, html_path, search_params)
    generate_csv_report(results, csv_path)

    webbrowser.open(html_path.as_uri())

    print(f"\n[receiver] {len(results)} jobs received -> {html_path.name}")

    return jsonify({
        "received": len(results),
        "html": str(html_path),
        "csv":  str(csv_path),
    })


def _to_job_result(j: dict) -> JobResult | None:
    title = (j.get("title") or "").strip()
    url   = (j.get("url")   or "").strip()
    if not title or not url:
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


def _parse_salary(text: str):
    if not text:
        return None, None
    nums = re.findall(r"\$[\d,]+\.?\d*[Kk]?", text)
    parsed = []
    for n in nums:
        n = n.replace("$", "").replace(",", "")
        if n.lower().endswith("k"):
            parsed.append(float(n[:-1]) * 1000)
        else:
            try:
                val = float(n)
                # Convert hourly to annual if text mentions it
                if re.search(r"hr|hour", text, re.I) and val < 500:
                    val *= 2080
                parsed.append(val)
            except ValueError:
                pass
    if len(parsed) >= 2:
        return parsed[0], parsed[1]
    if len(parsed) == 1:
        return parsed[0], None
    return None, None


if __name__ == "__main__":
    print(f"Job Harvester receiver running on http://localhost:{PORT}")
    print("Load the browser extension, browse LinkedIn/Indeed, then click 'Send to Tool'.\n")
    app.run(port=PORT, debug=False)
