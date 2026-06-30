"""
Job Application Tracker
Run: py -m tracker.app
Open: http://localhost:5001
"""
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, request, redirect, url_for, render_template, jsonify
from tracker.db import (
    init_db, add_job, get_all, get_counts, update_job, delete_job,
    STATUSES, STATUS_LABELS,
)
from config import PORT_TRACKER

app = Flask(__name__, template_folder="templates")
init_db()


def _cors(r):
    """Reflect only the browser-extension origin on the write API, instead of a
    wildcard that let any visited page POST into the tracker DB."""
    origin = request.headers.get("Origin", "")
    if urlparse(origin).scheme == "chrome-extension":
        r.headers["Access-Control-Allow-Origin"] = origin
        r.headers["Vary"] = "Origin"
    r.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return r


def _write_origin_ok() -> bool:
    """For a mutating request, allow the tracker's own loopback pages and the
    browser extension; reject a present-but-foreign Origin/Referer (CSRF). When
    BOTH headers are absent it's not a browser CSRF (curl/direct) -> allow."""
    for hdr in ("Origin", "Referer"):
        val = request.headers.get(hdr, "")
        if not val:
            continue
        p = urlparse(val)
        if p.scheme == "chrome-extension":
            return True
        if p.hostname in ("localhost", "127.0.0.1", "::1"):
            return True
        return False  # present but foreign -> reject
    return True  # no Origin and no Referer


@app.before_request
def _csrf_guard():
    from flask import abort
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and not _write_origin_ok():
        abort(403)

PORT = PORT_TRACKER


# ── Main dashboard ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    status_filter = request.args.get("status", "all")
    jobs   = get_all(status_filter)
    counts = get_counts()
    return render_template(
        "tracker.html",
        jobs=jobs,
        counts=counts,
        active_status=status_filter,
        statuses=STATUSES,
        status_labels=STATUS_LABELS,
        today=date.today().isoformat(),
    )


# ── Add (form POST or pre-filled GET) ────────────────────────────────────────

@app.route("/add", methods=["GET", "POST"])
def add():
    if request.method == "POST":
        add_job(
            title       = request.form.get("title", "").strip(),
            company     = request.form.get("company", "").strip(),
            location    = request.form.get("location", "").strip(),
            url         = request.form.get("url", "").strip(),
            salary_text = request.form.get("salary_text", "").strip(),
            source      = request.form.get("source", "manual"),
            status      = request.form.get("status", "interested"),
            date_applied= request.form.get("date_applied", "").strip(),
            notes       = request.form.get("notes", "").strip(),
        )
        return redirect(url_for("index"))

    # GET — pre-fill from query params (linked from search report / browser ext)
    prefill = {
        "title":       request.args.get("title", ""),
        "company":     request.args.get("company", ""),
        "location":    request.args.get("location", ""),
        "url":         request.args.get("url", ""),
        "salary_text": request.args.get("salary", ""),
        "status":      request.args.get("status", "interested"),
        "notes":       request.args.get("notes", ""),
    }
    counts = get_counts()
    return render_template(
        "tracker.html",
        jobs=get_all(),
        counts=counts,
        active_status="all",
        statuses=STATUSES,
        status_labels=STATUS_LABELS,
        today=date.today().isoformat(),
        prefill=prefill,
        show_form=True,
    )


# ── Update ────────────────────────────────────────────────────────────────────

@app.route("/update/<int:job_id>", methods=["POST"])
def update(job_id):
    fields = {}
    for field in ("status", "notes", "date_applied", "title", "company",
                  "location", "url", "salary_text"):
        val = request.form.get(field)
        if val is not None:
            fields[field] = val.strip()
    update_job(job_id, **fields)
    # Return to same status tab
    return redirect(request.referrer or url_for("index"))


# ── Delete ────────────────────────────────────────────────────────────────────

@app.route("/delete/<int:job_id>", methods=["POST"])
def delete(job_id):
    delete_job(job_id)
    return redirect(request.referrer or url_for("index"))


# ── JSON API (for browser extension / search report integration) ──────────────

@app.route("/api/jobs")
def api_jobs():
    return jsonify(get_all())


@app.route("/api/add", methods=["POST", "OPTIONS"])
def api_add():
    if request.method == "OPTIONS":
        return _cors(jsonify({})), 200
    data = request.get_json(force=True, silent=True) or {}
    title   = (data.get("title") or "").strip()
    company = (data.get("company") or "").strip()
    if not title or not company:
        return jsonify({"error": "title and company are required"}), 400
    job_id = add_job(
        title       = title,
        company     = company,
        location    = (data.get("location") or "").strip(),
        url         = (data.get("url") or "").strip(),
        salary_text = (data.get("salary_text") or "").strip(),
        source      = data.get("source", "api"),
        status      = data.get("status", "interested"),
        date_applied= (data.get("date_applied") or "").strip(),
        notes       = (data.get("notes") or "").strip(),
    )
    return _cors(jsonify({"id": job_id, "status": "added"})), 201


@app.route("/api/status")
def api_status():
    return jsonify({"status": "ok", "port": PORT})


if __name__ == "__main__":
    print(f"Job Tracker running at http://localhost:{PORT}")
    app.run(port=PORT, debug=False)
