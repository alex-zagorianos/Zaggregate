"""Claude copy-paste bridge — use Claude (claude.ai web chat) without an API
key. The app builds a prompt and puts it on the clipboard; the user pastes it
into a Claude chat, copies the JSON reply, and pastes it back into the app.

Two workflows:
  * batch fit-scoring   — build_fit_prompt / parse_fit_response
  * resume generation   — build_resume_prompt / parse_resume_response

If ANTHROPIC_API_KEY is present the callers may skip this module and hit the
API directly (resume/generator.py); this is the zero-cost default path.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from models import JobResult


class BridgeParseError(Exception):
    """The pasted Claude response couldn't be parsed — usually a stray
    explanation around the JSON or a truncated copy."""


def to_clipboard(text: str) -> bool:
    """Copy text to the Windows clipboard via clip.exe (UTF-16 handles any
    Unicode in postings). Returns False if the copy failed."""
    try:
        subprocess.run("clip", input=text.encode("utf-16"), check=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        return True
    except Exception:
        return False


def _extract_json(text: str, prefer: str = "object") -> str:
    """Pull the JSON payload out of a pasted reply: strips ```json fences and
    any prose before/after the outermost JSON value. ``prefer`` ('object' or
    'array') chooses which container to try first, so a resume object that
    contains an array field isn't mistaken for the whole payload."""
    t = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", t, re.DOTALL)
    if fence:
        t = fence.group(1).strip()
    spans = (("[", "]"), ("{", "}")) if prefer == "array" else (("{", "}"), ("[", "]"))
    for opener, closer in spans:
        start, end = t.find(opener), t.rfind(closer)
        if start != -1 and end > start:
            candidate = t[start:end + 1]
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                continue
    return t


# ── Batch fit-scoring ─────────────────────────────────────────────────────────

_FIT_INSTRUCTIONS = """\
You are screening job postings for the candidate profiled below. For EACH \
numbered job, judge how well the candidate fits and how attractive the job is.

Respond with ONLY a JSON array (no prose, no markdown fences), one object per \
job:
  [{"i": <job number>, "fit": <0-100>, "why": "<max 2 sentences>", \
"flags": "<red flags: clearance required, misleading title, contract-only, \
etc. Empty string if none>"}]

Scoring guide: 90+ apply today; 70-89 strong; 50-69 plausible stretch; \
<50 skip. Judge against the candidate's real experience level — do not \
inflate. A job requiring 10+ years or an active clearance the candidate \
lacks caps at 40.

The candidate prefers smaller companies: when fit is otherwise comparable, \
score the smaller firm higher. "Board openings" is a size proxy — under ~30 \
openings is a small shop, 300+ is a mega-corp.
"""


def build_fit_prompt(jobs: list[JobResult], profile_md: str) -> str:
    """One prompt scoring up to ~20 jobs in a single Claude reply."""
    lines = [_FIT_INSTRUCTIONS, "\n## CANDIDATE PROFILE\n", profile_md.strip(),
             "\n## JOBS\n"]
    for n, j in enumerate(jobs, 1):
        desc = re.sub(r"\s+", " ", (j.description or ""))[:1200]
        bc = getattr(j, "board_count", -1)
        size = f"Board openings: {bc}\n" if bc >= 0 else ""
        lines.append(
            f"### Job {n}\n"
            f"Title: {j.title}\nCompany: {j.company}\nLocation: {j.location}\n"
            f"Salary: {j.salary_display()}\n{size}Description: {desc}\n"
        )
    return "\n".join(lines)


def parse_fit_response(text: str, expected_count: int | None = None) -> dict[int, dict]:
    """Parse the pasted reply into {job_number: {fit, why, flags}}."""
    try:
        data = json.loads(_extract_json(text, prefer="array"))
    except json.JSONDecodeError as e:
        raise BridgeParseError(f"Could not parse JSON from the pasted text: {e}")
    if isinstance(data, dict):  # tolerate a single-object reply
        data = [data]
    if not isinstance(data, list):
        raise BridgeParseError("Expected a JSON array of job scores.")
    out: dict[int, dict] = {}
    for item in data:
        try:
            i = int(item["i"])
            out[i] = {
                "fit": max(0, min(100, int(item["fit"]))),
                "why": str(item.get("why", "")).strip(),
                "flags": str(item.get("flags", "")).strip(),
            }
        except (KeyError, TypeError, ValueError):
            continue  # skip malformed entries, keep the rest
    if not out:
        raise BridgeParseError("No valid job scores found in the pasted text.")
    if expected_count and len(out) < expected_count:
        print(f"  [bridge] Warning: got {len(out)}/{expected_count} scores.")
    return out


# ── Resume generation ─────────────────────────────────────────────────────────

_RESUME_KEYS = ("contact", "summary", "skills", "experience", "education",
                "cover_letter")

_RESUME_INSTRUCTIONS = """\
You are a professional resume writer. Using the candidate's full experience \
below, produce a resume and cover letter tailored to the job posting.

Respond with ONLY a JSON object (no prose, no markdown fences) shaped exactly:
{
  "contact": {"name": "", "email": "", "phone": "", "location": ""},
  "summary": "2-3 sentence summary tailored to the role",
  "skills": ["", ...],
  "experience": [{"company": "", "title": "", "duration": "", "location": "",
                  "bullets": ["", ...]}],
  "education": [{"institution": "", "degree": "", "graduated": "",
                 "details": ["", ...]}],
  "cover_letter": "Use \\n\\n between paragraphs."
}

Guidelines:
1. Select the most relevant experience, skills, and achievements for the role.
2. Mirror the posting's language and priorities in the bullet points.
3. One-page resume: max 6 bullets per role, max 3-4 roles.
4. Cover letter: 3 paragraphs — opening (role + why), middle (2-3 quantified \
achievements), closing (call to action).
Draw contact/education facts only from the candidate experience; do not invent.
"""


def _experience_corpus(experience: dict) -> str:
    return (
        "## CANDIDATE EXPERIENCE\n\n"
        f"### Contact\n{experience['contact']}\n\n"
        f"### Education\n{experience['education']}\n\n"
        f"### Technical Skills\n{experience['skills']}\n\n"
        f"### Work Experience\n{experience['work_experience']}\n\n"
        f"### Guidance Notes\n{experience['notes']}"
    )


def build_resume_prompt(job_posting: str, experience: dict) -> str:
    return (f"{_RESUME_INSTRUCTIONS}\n{_experience_corpus(experience)}\n\n"
            f"## JOB POSTING\n\n{job_posting.strip()}")


def parse_resume_response(text: str) -> dict:
    """Parse and validate a pasted resume JSON reply."""
    try:
        data = json.loads(_extract_json(text, prefer="object"))
    except json.JSONDecodeError as e:
        raise BridgeParseError(f"Could not parse JSON from the pasted text: {e}")
    if not isinstance(data, dict):
        raise BridgeParseError("Expected a JSON object with resume fields.")
    missing = [k for k in _RESUME_KEYS if k not in data]
    if missing:
        raise BridgeParseError(f"Pasted JSON is missing: {', '.join(missing)}")
    return data


# ── Batch resume generation ──────────────────────────────────────────────────
# One paste round-trip produces docs for several jobs; ~5 keeps each resume
# from getting attention-starved in a single Claude reply.

_BATCH_RESUME_INSTRUCTIONS = """\
You are a professional resume writer. Using the candidate's full experience \
below, produce a tailored resume and cover letter for EACH numbered job \
posting. Tailor each one individually — do not reuse the same summary or \
bullets across jobs unless they genuinely fit both.

Respond with ONLY a JSON array (no prose, no markdown fences), one object per \
job, each shaped exactly:
[
  {
    "i": <job number>,
    "contact": {"name": "", "email": "", "phone": "", "location": ""},
    "summary": "2-3 sentence summary tailored to the role",
    "skills": ["", ...],
    "experience": [{"company": "", "title": "", "duration": "", "location": "",
                    "bullets": ["", ...]}],
    "education": [{"institution": "", "degree": "", "graduated": "",
                   "details": ["", ...]}],
    "cover_letter": "Use \\n\\n between paragraphs."
  }
]

Guidelines (apply to every job):
1. Select the most relevant experience, skills, and achievements for the role.
2. Mirror the posting's language and priorities in the bullet points.
3. One-page resume: max 6 bullets per role, max 3-4 roles.
4. Cover letter: 3 paragraphs — opening (role + why), middle (2-3 quantified \
achievements), closing (call to action).
Draw contact/education facts only from the candidate experience; do not invent.
"""


def build_batch_resume_prompt(postings: list[str], experience: dict) -> str:
    """One prompt producing resume+cover JSON for several postings. Each
    posting string should already carry its Title/Company header lines."""
    parts = [_BATCH_RESUME_INSTRUCTIONS, "", _experience_corpus(experience),
             "\n## JOB POSTINGS\n"]
    for n, posting in enumerate(postings, 1):
        parts.append(f"### Job {n}\n\n{posting.strip()}\n")
    return "\n".join(parts)


def parse_batch_resume_response(text: str) -> dict[int, dict]:
    """Parse a pasted batch reply into {job_number: resume_data}. Malformed
    or incomplete entries are skipped so one bad object doesn't sink the
    rest; raises BridgeParseError only when nothing usable was found."""
    try:
        data = json.loads(_extract_json(text, prefer="array"))
    except json.JSONDecodeError as e:
        raise BridgeParseError(f"Could not parse JSON from the pasted text: {e}")
    if isinstance(data, dict):  # tolerate a single-object reply
        data = [data]
    if not isinstance(data, list):
        raise BridgeParseError("Expected a JSON array of resume objects.")
    out: dict[int, dict] = {}
    for pos, item in enumerate(data, 1):
        if not isinstance(item, dict):
            continue
        try:
            i = int(item.get("i", pos))  # fall back to array position
        except (TypeError, ValueError):
            continue
        if any(k not in item for k in _RESUME_KEYS):
            continue
        out[i] = item
    if not out:
        raise BridgeParseError("No valid resume objects found in the pasted text.")
    return out


# ── Profile summary for fit prompts ──────────────────────────────────────────

def profile_summary() -> str:
    """Compact candidate profile for fit-scoring prompts: skills + the job
    search criteria + condensed work history headers from experience.md."""
    from resume.experience_parser import load_experience
    exp = load_experience()
    work = exp.get("work_experience", "")
    # Keep headers and the first bullet of each role; full JDs aren't needed.
    condensed: list[str] = []
    bullet_budget = 0
    for line in work.splitlines():
        if line.startswith("###"):
            condensed.append(line)
            bullet_budget = 3
        elif line.strip().startswith(("-", "*")) and bullet_budget > 0:
            condensed.append(line)
            bullet_budget -= 1
    return (
        f"### Technical Skills\n{exp.get('skills', '')}\n\n"
        f"### Work History (condensed)\n" + "\n".join(condensed)
    )
