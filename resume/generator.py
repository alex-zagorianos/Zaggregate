import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anthropic
from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL
from resume.experience_parser import experience_corpus, load_experience


class ResumeGenerationError(Exception):
    pass


# Forced structured output: the model must call this tool, so its `input` is
# already a validated dict — no prose-stripping or json.loads guesswork, which
# was the old failure mode.
RESUME_TOOL = {
    "name": "emit_resume",
    "description": "Return the tailored resume and cover letter as structured data.",
    "input_schema": {
        "type": "object",
        "properties": {
            "contact": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": "string"},
                    "phone": {"type": "string"},
                    "location": {"type": "string"},
                },
                "required": ["name", "email", "phone", "location"],
            },
            "summary": {"type": "string", "description": "2-3 sentence summary tailored to the role"},
            "skills": {"type": "array", "items": {"type": "string"}},
            "experience": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "company": {"type": "string"},
                        "title": {"type": "string"},
                        "duration": {"type": "string"},
                        "location": {"type": "string"},
                        "bullets": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["company", "title", "bullets"],
                },
            },
            "education": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "institution": {"type": "string"},
                        "degree": {"type": "string"},
                        "graduated": {"type": "string"},
                        "details": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["institution", "degree"],
                },
            },
            "cover_letter": {"type": "string", "description": "Use \\n\\n between paragraphs."},
        },
        "required": ["contact", "summary", "skills", "experience", "education", "cover_letter"],
    },
}

_INSTRUCTIONS = """You are a professional resume writer. Using the candidate's \
full experience (provided below), produce a resume and cover letter tailored to \
the job posting in the user's message, by calling the emit_resume tool.

Guidelines:
1. Select the most relevant experience, skills, and achievements for the role.
2. Mirror the posting's language and priorities in the bullet points.
3. One-page resume: max 6 bullets per role, max 3-4 roles.
4. Cover letter: 3 paragraphs — opening (role + why), middle (2-3 quantified \
achievements), closing (call to action).
Draw contact/education facts only from the candidate experience; do not invent."""


def _build_system(experience: dict) -> list[dict]:
    """System prompt as cacheable blocks. The candidate corpus is static across
    generations, so we mark the prefix with cache_control — repeat runs read it
    from cache instead of re-billing the full experience each time."""
    corpus = experience_corpus(experience)  # RESUME-6: shared corpus contract
    return [
        {"type": "text", "text": _INSTRUCTIONS},
        {"type": "text", "text": corpus, "cache_control": {"type": "ephemeral"}},
    ]


def generate_resume_and_cover_letter(job_posting: str) -> dict:
    """Call Claude with the job posting + cached candidate experience and return
    a structured dict (resume sections + cover letter). Raises
    ResumeGenerationError on any failure."""
    if not ANTHROPIC_API_KEY:
        raise ResumeGenerationError(
            "ANTHROPIC_API_KEY is not set. Add it to .env as: ANTHROPIC_API_KEY=sk-ant-..."
        )
    if not (job_posting or "").strip():
        raise ResumeGenerationError("Job posting is empty.")

    system = _build_system(load_experience())
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        message = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=8192,
            system=system,
            tools=[RESUME_TOOL],
            tool_choice={"type": "tool", "name": "emit_resume"},
            messages=[{"role": "user", "content": f"JOB POSTING:\n\n{job_posting}"}],
        )
    except anthropic.AuthenticationError:
        raise ResumeGenerationError("Invalid Anthropic API key. Check ANTHROPIC_API_KEY in .env.")
    except anthropic.RateLimitError:
        raise ResumeGenerationError("Anthropic rate limit hit. Wait a moment and try again.")
    except anthropic.APIError as e:
        raise ResumeGenerationError(f"Anthropic API error: {e}")

    if message.stop_reason == "max_tokens":
        raise ResumeGenerationError(
            "Response hit the token limit before completing. Try a shorter job posting."
        )

    for block in message.content:
        if getattr(block, "type", None) == "tool_use" and block.name == "emit_resume":
            return block.input

    raise ResumeGenerationError("Claude did not return structured resume data.")
