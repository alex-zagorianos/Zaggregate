"""Claude copy-paste bridge — use Claude (claude.ai web chat) without an API
key. The app builds a prompt and puts it on the clipboard; the user pastes it
into a Claude chat, copies the JSON reply, and pastes it back into the app.

Two workflows:
  * batch fit-scoring   — build_fit_prompt / parse_fit_response
  * resume generation   — build_resume_prompt / parse_resume_response

If ANTHROPIC_API_KEY is present the callers may skip this module and hit the
API directly (resume/generator.py); this is the zero-cost default path.
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from models import JobResult
from resume.experience_parser import EXPERIENCE_SECTIONS


class BridgeParseError(Exception):
    """The pasted Claude response couldn't be parsed — usually a stray
    explanation around the JSON or a truncated copy."""


def to_clipboard(text: str) -> bool:
    """Copy text to the OS clipboard. Windows: clip.exe (UTF-16). macOS: pbcopy.
    Linux: xclip then xsel. Returns False if no backend succeeded."""
    if sys.platform.startswith("win"):
        try:
            subprocess.run("clip", input=text.encode("utf-16"), check=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
            return True
        except Exception:
            return False
    data = text.encode("utf-8")
    if sys.platform == "darwin":
        cmds = [["pbcopy"]]
    else:
        cmds = [["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]
    for cmd in cmds:
        try:
            subprocess.run(cmd, input=data, check=True)
            return True
        except Exception:
            continue
    return False


def _strip_trailing_commas(text: str) -> str:
    """Remove commas that immediately precede a closing } or ] (allowing
    whitespace between). A single stray trailing comma is the most common way a
    pasted reply fails strict json.loads, so we drop them before retrying."""
    return re.sub(r",(\s*[}\]])", r"\1", text)


def _balanced_span(s: str, opener: str, closer: str):
    """The first balanced opener..closer substring, respecting JSON strings and
    escapes. Handles a reply whose surrounding prose contains stray brackets
    better than a greedy first-opener/last-closer slice. None if no balanced run."""
    start = s.find(opener)
    if start == -1:
        return None
    depth = 0
    in_str = esc = False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return s[start:i + 1]
    return None


def _extract_json(text: str, prefer: str = "object") -> str:
    """Pull the JSON payload out of a pasted reply: strips ```json fences and
    any prose before/after the outermost JSON value. ``prefer`` ('object' or
    'array') chooses which container to try first, so a resume object that
    contains an array field isn't mistaken for the whole payload.

    Tries a bracket-balanced span first (robust to stray brackets in prose), then
    falls back to the greedy first-opener/last-closer slice. If a candidate fails
    strict json.loads, retry once with trailing commas stripped before moving on."""
    t = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", t, re.DOTALL)
    if fence:
        t = fence.group(1).strip()
    spans = (("[", "]"), ("{", "}")) if prefer == "array" else (("{", "}"), ("[", "]"))
    for opener, closer in spans:
        candidates = []
        bal = _balanced_span(t, opener, closer)
        if bal:
            candidates.append(bal)
        start, end = t.find(opener), t.rfind(closer)
        if not (start == -1 or end == -1 or end <= start):
            candidates.append(t[start:end + 1])  # greedy fallback
        for candidate in candidates:
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                repaired = _strip_trailing_commas(candidate)
                if repaired != candidate:
                    try:
                        json.loads(repaired)
                        return repaired
                    except json.JSONDecodeError:
                        pass
    return t


# ── Batch fit-scoring ─────────────────────────────────────────────────────────

# Candidate preference woven into the fit prompt. NEUTRAL by default ('') so no
# bias sentence is baked into everyone's ranking; a per-profile fit_preference
# (preferences.load()['fit_preference'], from preferences.json) is passed through
# by ranker.build_request/build_compact_request. The old app-wide "prefers smaller
# companies" text is no longer the default — a user who wants it sets it in their
# preferences. Callers may still override via build_fit_prompt(preference=...).
DEFAULT_FIT_PREFERENCE = ""

_FIT_INSTRUCTIONS = """\
You are screening job postings for the candidate profiled below. For EACH \
numbered job, judge how well the candidate fits and how attractive the job is.

Respond with ONLY a JSON array (no prose, no markdown fences), one object per \
job. Echo back the "token" exactly as given for each job so scores can't be \
mis-assigned if you reorder or skip any:
  [{"i": <job number>, "token": "<the job's token>", "fit": <0-100>, \
"why": "<max 2 sentences>", \
"flags": "<red flags: clearance required, misleading title, contract-only, \
etc. Empty string if none>"}]

Scoring guide: 90+ apply today; 70-89 strong; 50-69 plausible stretch; \
<50 skip. Judge against the candidate's real experience level — do not \
inflate. A job requiring 10+ years or an active clearance the candidate \
lacks caps at 40.

__PREFERENCE__
"""


def fit_token(job: JobResult) -> str:
    """Stable 8-char token identifying a job in a fit batch: first 8 of
    md5(url) when a URL exists, else md5(title|company). Used to echo scores
    back to the right job even if the model reorders or skips entries."""
    basis = (getattr(job, "url", "") or "").strip()
    if not basis:
        basis = f"{(job.title or '').strip()}|{(job.company or '').strip()}"
    return hashlib.md5(basis.encode("utf-8")).hexdigest()[:8]


def _apply_preference(preference: str) -> str:
    """Fill the __PREFERENCE__ slot in the fit instructions. Empty/whitespace
    preference => the placeholder (and its trailing blank line) is dropped
    entirely, so a neutral profile carries NO bias sentence."""
    # .replace (not .format): the template carries literal JSON braces.
    pref = (preference or "").strip()
    if not pref:
        return _FIT_INSTRUCTIONS.replace("__PREFERENCE__\n", "").replace("__PREFERENCE__", "")
    return _FIT_INSTRUCTIONS.replace("__PREFERENCE__", pref)


def build_fit_prompt(jobs: list[JobResult], profile_md: str,
                     preference: str = DEFAULT_FIT_PREFERENCE) -> str:
    """One prompt scoring up to ~20 jobs in a single Claude reply. ``preference``
    is the candidate's per-profile bias text (default '' = neutral, no bias
    sentence); pass a per-project string to override."""
    instructions = _apply_preference(preference)
    lines = [instructions, "\n## CANDIDATE PROFILE\n", profile_md.strip(),
             "\n## JOBS\n"]
    for n, j in enumerate(jobs, 1):
        desc = re.sub(r"\s+", " ", (j.description or ""))[:1200]
        bc = getattr(j, "board_count", -1)
        size = f"Board openings: {bc}\n" if bc >= 0 else ""
        lines.append(
            f"### Job {n}\n"
            f"Token: {fit_token(j)}\n"
            f"Title: {j.title}\nCompany: {j.company}\nLocation: {j.location}\n"
            f"Salary: {j.salary_display()}\n{size}Description: {desc}\n"
        )
    return "\n".join(lines)


def build_fit_prompt_compact(jobs: list[JobResult], facts_list: list[dict],
                             profile_md: str,
                             preference: str = DEFAULT_FIT_PREFERENCE) -> str:
    """Like build_fit_prompt, but feeds each job's compact extracted FACTS
    (match.facts.facts_summary) instead of its raw description — ~15x less context
    per job. ``facts_list[i]`` is the JobFacts dict for ``jobs[i]``. Output
    contract is identical, so parse_fit_response/match_fit_to_jobs are unchanged."""
    from match.facts import facts_summary
    instructions = _apply_preference(preference)
    lines = [instructions, "\n## CANDIDATE PROFILE\n", profile_md.strip(), "\n## JOBS\n"]
    for n, (j, facts) in enumerate(zip(jobs, facts_list), 1):
        bc = getattr(j, "board_count", -1)
        size = f"Board openings: {bc}\n" if bc >= 0 else ""
        lines.append(
            f"### Job {n}\n"
            f"Token: {fit_token(j)}\n"
            f"Title: {j.title}\nCompany: {j.company}\nLocation: {j.location}\n"
            f"Salary: {j.salary_display()}\n{size}Facts: {facts_summary(facts)}\n"
        )
    return "\n".join(lines)


def parse_fit_response(text: str, expected_count: int | None = None) -> list[dict]:
    """Parse the pasted reply into a list of {i, token, fit_score, rationale,
    flags} dicts — one per valid entry, preserving the reply's order. Malformed
    entries are skipped. ``rationale`` folds the model's "why" together with any
    "flags" (so callers writing a single rationale field keep the red flags);
    ``flags`` is also exposed on its own. Map results onto jobs with
    match_fit_to_jobs()."""
    try:
        data = json.loads(_extract_json(text, prefer="array"))
    except json.JSONDecodeError as e:
        raise BridgeParseError(f"Could not parse JSON from the pasted text: {e}")
    if isinstance(data, dict):  # tolerate a single-object reply
        data = [data]
    if not isinstance(data, list):
        raise BridgeParseError("Expected a JSON array of job scores.")
    out: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            fit_score = max(0, min(100, int(item["fit"])))
        except (KeyError, TypeError, ValueError):
            continue  # a score is mandatory; skip entries without one
        try:
            i = int(item["i"])
        except (KeyError, TypeError, ValueError):
            i = None  # positional index optional; token can still map it
        token = item.get("token")
        token = str(token).strip() if token else ""
        why = str(item.get("why", "")).strip()
        flags = str(item.get("flags", "")).strip()
        out.append({
            "i": i,
            "token": token,
            "fit_score": fit_score,
            "rationale": f"{why} {flags}".strip(),
            "flags": flags,
        })
    if not out:
        raise BridgeParseError("No valid job scores found in the pasted text.")
    if expected_count and len(out) < expected_count:
        print(f"  [bridge] Warning: got {len(out)}/{expected_count} scores.")
    return out


def match_fit_to_jobs(jobs: list, parsed: list) -> list:
    """Map parsed fit results onto jobs, preferring the echoed token and only
    falling back to the 1-based positional "i" when a token is missing.
    Mismatches (unknown token, out-of-range i, no usable key) are skipped.

    Returns a list of (job, fit_score, rationale) tuples in jobs order for the
    jobs that got a score."""
    by_token = {fit_token(j): j for j in jobs}
    # Per-result: resolve to a job, then collect by job identity so we emit in
    # jobs order. id() is stable for the lifetime of this call.
    resolved: dict[int, tuple] = {}
    for item in parsed:
        if not isinstance(item, dict):
            continue
        job = None
        token = (item.get("token") or "").strip()
        if token:
            job = by_token.get(token)  # None on unknown token -> skip below
        else:
            i = item.get("i")
            if isinstance(i, int) and 1 <= i <= len(jobs):
                job = jobs[i - 1]
        if job is None:
            continue  # mismatch: unknown token or out-of-range/missing index
        resolved[id(job)] = (job, item.get("fit_score", 0),
                             item.get("rationale", ""))
    return [resolved[id(j)] for j in jobs if id(j) in resolved]


# ── Resume generation ─────────────────────────────────────────────────────────

_RESUME_KEYS = ("contact", "summary", "skills", "experience", "education",
                "cover_letter")

# Expected JSON types per key. Lists must stay lists and strings strings, or the
# docx builder silently emits garbage (e.g. a string where it iterates roles).
_RESUME_FIELD_TYPES: dict[str, type | tuple] = {
    "contact":      dict,
    "summary":      str,
    "skills":       list,
    "experience":   list,
    "education":    list,
    "cover_letter": str,
}


def _looks_truncated(text: str) -> bool:
    """Heuristic for a cut/copy-truncated reply: a JSON object/array was opened
    but the matching closer never appears, so json.loads would choke past the
    cut point. Cheap brace/bracket balance check on the extracted candidate."""
    t = (text or "").strip()
    if not t:
        return False
    opens = t.count("{") + t.count("[")
    closes = t.count("}") + t.count("]")
    return opens > closes


def _validate_resume_types(data: dict) -> None:
    """Raise BridgeParseError if any present resume field has the wrong type."""
    wrong = [k for k, typ in _RESUME_FIELD_TYPES.items()
             if k in data and not isinstance(data[k], typ)]
    if wrong:
        detail = ", ".join(
            f"{k} (expected {_RESUME_FIELD_TYPES[k].__name__}, "
            f"got {type(data[k]).__name__})" for k in wrong
        )
        raise BridgeParseError(f"Pasted JSON has wrong field types: {detail}")

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
    # Single source of truth for the corpus/section contract (RESUME-6).
    from resume.experience_parser import experience_corpus
    return experience_corpus(experience)


def build_resume_prompt(job_posting: str, experience: dict,
                        missing_skills=None) -> str:
    """Resume prompt for one posting. `missing_skills` (from match.skillgap's
    'missing' list, threaded in by resume/service) names the concrete terms the
    JD asks for that the candidate can't yet claim, so tailoring targets the
    posting's ACTUAL asks (feature computed but previously never consumed).
    Empty/None => no gap block (unchanged prompt)."""
    gap = ""
    terms = [str(t).strip() for t in (missing_skills or []) if str(t).strip()]
    if terms:
        gap = ("\n\n## SKILLS THE POSTING EMPHASIZES\n\n"
               "Surface any of the candidate's real experience that speaks to "
               "these (do NOT fabricate any they lack): " + ", ".join(terms))
    return (f"{_RESUME_INSTRUCTIONS}\n{_experience_corpus(experience)}\n\n"
            f"## JOB POSTING\n\n{job_posting.strip()}{gap}")


def parse_resume_response(text: str) -> dict:
    """Parse and validate a pasted resume JSON reply. Detects a truncated/cut
    copy and raises a clear parse error rather than emitting a wrong-company or
    half-empty doc; type-checks the six fields (RESUME-2)."""
    extracted = _extract_json(text, prefer="object")
    try:
        data = json.loads(extracted)
    except json.JSONDecodeError as e:
        if _looks_truncated(extracted):
            raise BridgeParseError(
                "The pasted reply looks cut off (unbalanced JSON) — recopy the "
                "full Claude response and try again."
            )
        raise BridgeParseError(f"Could not parse JSON from the pasted text: {e}")
    if not isinstance(data, dict):
        raise BridgeParseError("Expected a JSON object with resume fields.")
    missing = [k for k in _RESUME_KEYS if k not in data]
    if missing:
        raise BridgeParseError(f"Pasted JSON is missing: {', '.join(missing)}")
    _validate_resume_types(data)
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


def parse_batch_resume_response(text: str,
                                expected_count: int | None = None) -> dict[int, dict]:
    """Parse a pasted batch reply into {job_number: resume_data}. Malformed,
    wrong-typed, or out-of-range entries are skipped so one bad object doesn't
    sink the rest; raises BridgeParseError only when nothing usable was found.

    The echoed "i" is REQUIRED and (when expected_count is given) must be in
    1..expected_count — we no longer fall back to array position, since a
    reordered/skipped reply would otherwise emit a doc under the wrong job's
    company. (RESUME-2)"""
    extracted = _extract_json(text, prefer="array")
    try:
        data = json.loads(extracted)
    except json.JSONDecodeError as e:
        if _looks_truncated(extracted):
            raise BridgeParseError(
                "The pasted reply looks cut off (unbalanced JSON) — recopy the "
                "full Claude response and try again."
            )
        raise BridgeParseError(f"Could not parse JSON from the pasted text: {e}")
    if isinstance(data, dict):  # tolerate a single-object reply
        data = [data]
    if not isinstance(data, list):
        raise BridgeParseError("Expected a JSON array of resume objects.")
    out: dict[int, dict] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        if "i" not in item:  # echoed index is mandatory — no positional guess
            continue
        try:
            i = int(item["i"])
        except (TypeError, ValueError):
            continue
        if expected_count is not None and not (1 <= i <= expected_count):
            continue  # out-of-range index -> would map to the wrong job
        if any(k not in item for k in _RESUME_KEYS):
            continue
        try:
            _validate_resume_types(item)
        except BridgeParseError:
            continue  # wrong field types -> skip this one, keep the rest
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
