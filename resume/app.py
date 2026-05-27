import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, request, render_template, send_file, jsonify
from resume.generator import generate_resume_and_cover_letter, ResumeGenerationError
from resume.docx_builder import build_resume_docx, build_cover_letter_docx

app = Flask(__name__, template_folder="templates")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    job_posting = request.form.get("job_posting", "").strip()
    if not job_posting:
        return render_template("index.html", error="Please paste a job posting.")
    try:
        data = generate_resume_and_cover_letter(job_posting)
    except ResumeGenerationError as e:
        return render_template("index.html", error=str(e), job_posting=job_posting)

    resume_buf = build_resume_docx(data)
    cover_letter_buf = build_cover_letter_docx(data)

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("resume.docx", resume_buf.read())
        zf.writestr("cover_letter.docx", cover_letter_buf.read())
    zip_buf.seek(0)

    return send_file(
        zip_buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name="alex_zagorianos_application.zip",
    )


@app.route("/health")
def health():
    from config import ANTHROPIC_API_KEY
    return jsonify({"status": "ok", "api_key_set": bool(ANTHROPIC_API_KEY)})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
