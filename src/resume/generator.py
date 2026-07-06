import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anthropic
import config
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
                    "links": {"type": "string", "description": "Optional: visible LinkedIn/GitHub/portfolio URLs, ' | '-separated (shown verbatim, not hidden behind link text)."},
                },
                "required": ["name", "email", "phone", "location"],
            },
            "headline": {"type": "string", "description": "Short target-track line under the name: role family + 3-4 core specialties, e.g. 'Software / Controls Engineer — Embedded · Real-Time Control · Applied AI'."},
            "summary": {"type": "string", "description": "2-3 line summary: level, core stack, and 1-2 quantified wins, tailored to the role"},
            "skills": {"type": "array", "items": {"type": "string"}, "description": "Grouped strings 'Category: item, item, item' (e.g. 'Languages: Python, C++17, C#, TypeScript')."},
            "certifications": {"type": "array", "items": {"type": "string"}, "description": "Optional. Licenses & certifications relevant to the role, one per string (e.g. 'RN - Ohio Board of Nursing', 'BLS/ACLS (AHA)', 'PMP', 'CDL Class A', 'PE'). The load-bearing credential list for nurses/trades/teachers/drivers/accountants. Omit if none apply."},
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
            "projects": {
                "type": "array",
                "description": "Optional. Personal/independent projects that strengthen fit (treat like experience with XYZ bullets). Omit if none are relevant.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string", "description": "Optional one-line descriptor."},
                        "bullets": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["name", "bullets"],
                },
            },
            "cover_letter": {"type": "string", "description": "Use \\n\\n between paragraphs."},
        },
        "required": ["contact", "summary", "skills", "experience", "education", "cover_letter"],
    },
}

_INSTRUCTIONS = """You are a professional resume writer. Using the candidate's \
full experience (provided below), produce a ONE-PAGE resume and cover letter \
tailored to the job posting in the user's message, by calling the emit_resume tool.

The candidate may be in ANY field -- nursing, teaching, a skilled trade, finance, \
sales, engineering, software, hospitality. Derive the target track and its \
vocabulary from the candidate's own experience and the posting; never assume a \
tech/engineering framing. Optimize for AI/ATS screening AND a human 6-second skim:
1. Relevance first: select the most relevant experience, skills, certifications, \
projects, and achievements for THIS role; mirror the posting's language as natural \
prose -- never keyword-stuff or repeat terms unnaturally (modern semantic screeners \
penalize it).
2. headline: a short target line -- the candidate's role family + 3-4 core \
strengths, drawn from their actual experience (e.g. "Registered Nurse - Critical \
Care - ACLS - Charge Nurse", or "Controls Engineer - Embedded - Real-Time Control").
3. summary: 2-3 lines -- level, core strengths, and 1-2 quantified wins.
4. skills: return GROUPED strings "Category: a, b, c" using categories natural to \
the field (e.g. "Clinical: ICU, telemetry, wound care" or "Languages: Python, \
C++17"). Spell out a field acronym once with its short form.
5. certifications: list licenses/certifications relevant to the role, one per \
string (e.g. "RN - Ohio Board of Nursing", "BLS/ACLS (AHA)", "PMP", "CDL Class A", \
"PE"). Omit only if the candidate has none. For licensed fields (nursing, trades, \
teaching, driving, accounting) these are often the single most important screen.
6. Bullets (experience + projects): result-first XYZ form -- "Accomplished [X] as \
measured by [Y] by doing [Z]". Start each with a strong past-tense verb (Led, \
Managed, Reduced, Improved, Trained, Built); never "Responsible for". Put the \
strongest, most-quantified bullet FIRST in each role. Aim for a hard number in most \
bullets where the field allows it. 3-5 bullets for recent/relevant roles, 2-3 for older.
7. projects: include when the candidate's projects strengthen fit for the role; \
omit otherwise.
8. One page: at most ~4 roles; trim the weakest bullets to fit. Use one consistent \
date format ("Month YYYY").
9. Lead with whatever the posting most values, drawn from the candidate's own \
tracks/roles - do not impose a fixed set of tracks.
10. Cover letter: 3 paragraphs - opening (role + why), middle (2-3 quantified \
achievements), closing (call to action).
Draw contact/education/certification facts only from the candidate experience; do \
not invent."""


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
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY,
                                 base_url=config.anthropic_base_url())
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
