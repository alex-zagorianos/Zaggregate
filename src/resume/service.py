"""Shared resume-bundle orchestration used by the desktop GUI and the Flask
app, so the generate -> build-docx sequence lives in one place.

Two generation paths:
  * API     — generate_resume_and_cover_letter() (needs ANTHROPIC_API_KEY)
  * bridge  — build_prompt() -> user pastes into claude.ai -> data_from_paste()
Both feed the same save_bundle_from_data().
"""
import re
import sys
from datetime import date
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from config import ANTHROPIC_API_KEY
from resume.docx_builder import build_cover_letter_docx, build_resume_docx
from resume.experience_parser import load_experience


def api_available() -> bool:
    """True when an Anthropic key is configured — the env var OR a key the user
    pasted into the in-app Settings box (secrets/anthropic_key). Consulted live so
    the 'Generate via API' button lights up right after a key is saved."""
    return bool(config.ANTHROPIC_API_KEY or config.read_secret("anthropic_key"))


def _slug(text: str, max_len: int = 30) -> str:
    """Filesystem-safe fragment of a company name for output filenames."""
    s = re.sub(r"[^A-Za-z0-9]+", "_", (text or "").strip()).strip("_")
    return s[:max_len] or "job"


# ── Copy-paste bridge path (no API key) ───────────────────────────────────────

def _missing_skills_for(job_posting: str) -> list:
    """The JD's asked-for skills the candidate can't yet claim (match.skillgap's
    'missing'), so resume tailoring targets the posting's actual asks. Best-effort:
    [] on any failure so a resume prompt is never blocked."""
    try:
        from match.skillgap import skill_gap
        return skill_gap(job_posting).get("missing", []) or []
    except Exception:
        return []


def build_prompt(job_posting: str) -> str:
    """Full Claude prompt for one posting; caller copies it to the clipboard.
    Feeds the JD's skill-gap 'missing' terms into the prompt so tailoring targets
    what the posting actually asks for (item 8)."""
    from claude_bridge import build_resume_prompt
    if not (job_posting or "").strip():
        raise ValueError("Job posting is empty.")
    return build_resume_prompt(job_posting, load_experience(),
                               missing_skills=_missing_skills_for(job_posting))


def build_batch_prompt(postings: list[str]) -> str:
    """Claude prompt covering several postings in one paste round-trip."""
    from claude_bridge import build_batch_resume_prompt
    postings = [p for p in postings if (p or "").strip()]
    if not postings:
        raise ValueError("No job postings to include.")
    return build_batch_resume_prompt(postings, load_experience())


def data_from_paste(pasted: str) -> dict:
    """Validate a pasted Claude reply into resume data (raises BridgeParseError)."""
    from claude_bridge import parse_resume_response
    return parse_resume_response(pasted)


# ── Shared rendering ──────────────────────────────────────────────────────────

def build_bundle_from_data(data: dict) -> tuple[BytesIO, BytesIO]:
    return build_resume_docx(data), build_cover_letter_docx(data)


def save_bundle_from_data(data: dict, output_dir: Path,
                          company: str = "") -> tuple[Path, Path]:
    """Render and write resume + cover letter; company keeps same-day batch
    generations from overwriting each other. Returns (resume, cover) paths."""
    resume_buf, cover_buf = build_bundle_from_data(data)
    output_dir.mkdir(parents=True, exist_ok=True)
    tag = f"{_slug(company)}_{date.today().isoformat()}"
    # Two roles at the same company on the same day must not overwrite each
    # other — bump a numeric suffix until both filenames are free.
    suffix = ""
    n = 1
    while ((output_dir / f"resume_{tag}{suffix}.docx").exists()
           or (output_dir / f"cover_letter_{tag}{suffix}.docx").exists()):
        n += 1
        suffix = f"_{n}"
    resume_path = output_dir / f"resume_{tag}{suffix}.docx"
    cover_path = output_dir / f"cover_letter_{tag}{suffix}.docx"
    resume_path.write_bytes(resume_buf.read())
    cover_path.write_bytes(cover_buf.read())
    return resume_path, cover_path


# ── MCP / cycle helpers (job row -> prompt; data -> docx) ─────────────────────

def job_posting_from_row(row: dict) -> str:
    """Assemble a job-posting text block from an inbox/application row dict for
    resume tailoring: a Title/Company/Location header + the saved JD snapshot
    (inbox 'description'). Used by the MCP get_resume_prompt tool."""
    if not row:
        raise ValueError("No such job.")
    header = (f"Title: {row.get('title', '')}\n"
              f"Company: {row.get('company', '')}\n"
              f"Location: {row.get('location', '')}\n"
              f"Salary: {row.get('salary_text', '')}\n")
    desc = (row.get("description", "") or "").strip()
    return (header + "\n" + desc).strip()


def resume_prompt_for_row(row: dict) -> str:
    """The clipboard resume prompt for one inbox/application row (JD snapshot +
    experience + skill-gap). Thin wrapper over build_prompt."""
    return build_prompt(job_posting_from_row(row))


def save_resume_docx(data: dict, company: str = "") -> tuple[Path, Path]:
    """Render + write resume/cover DOCX from resume data into OUTPUT_DIR/resumes.
    Returns (resume_path, cover_path). Used by the MCP save_resume tool so an AI
    that produced the structured resume JSON can persist the actual documents."""
    out_dir = Path(config.OUTPUT_DIR) / "resumes"
    return save_bundle_from_data(data, out_dir, company=company)


# ── API path (kept for when ANTHROPIC_API_KEY is set) ─────────────────────────

def build_bundle(job_posting: str) -> tuple[dict, BytesIO, BytesIO]:
    """Generate via the Anthropic API and render both DOCX buffers."""
    from resume.generator import generate_resume_and_cover_letter
    data = generate_resume_and_cover_letter(job_posting)
    resume_buf, cover_buf = build_bundle_from_data(data)
    return data, resume_buf, cover_buf


def save_bundle(job_posting: str, output_dir: Path,
                company: str = "") -> tuple[Path, Path]:
    """API path: generate and write resume + cover letter; return paths."""
    data, _, _ = build_bundle(job_posting)
    return save_bundle_from_data(data, output_dir, company=company)
