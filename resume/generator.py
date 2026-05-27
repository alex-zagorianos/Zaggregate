import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anthropic
from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL
from resume.experience_parser import load_experience


class ResumeGenerationError(Exception):
    pass


def generate_resume_and_cover_letter(job_posting: str) -> dict:
    """
    Call Claude API with job posting + candidate experience.
    Returns structured dict with resume sections and cover letter.
    Raises ResumeGenerationError on any failure.
    """
    if not ANTHROPIC_API_KEY:
        raise ResumeGenerationError(
            "ANTHROPIC_API_KEY is not set. Add it to .env as: ANTHROPIC_API_KEY=sk-ant-..."
        )

    experience = load_experience()
    prompt = _build_prompt(job_posting, experience)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        message = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.AuthenticationError:
        raise ResumeGenerationError("Invalid Anthropic API key. Check ANTHROPIC_API_KEY in .env.")
    except anthropic.RateLimitError:
        raise ResumeGenerationError("Anthropic rate limit hit. Wait a moment and try again.")
    except anthropic.APIError as e:
        raise ResumeGenerationError(f"Anthropic API error: {e}")

    return _parse_response(message.content[0].text)


def _build_prompt(job_posting: str, experience: dict) -> str:
    return f"""You are a professional resume writer. Using the candidate's full experience below, generate a tailored resume and cover letter for the job posting provided.

## CANDIDATE EXPERIENCE
### Contact
{experience["contact"]}

### Education
{experience["education"]}

### Technical Skills
{experience["skills"]}

### Work Experience
{experience["work_experience"]}

### Guidance Notes
{experience["notes"]}

## JOB POSTING
{job_posting}

## INSTRUCTIONS
1. Select the most relevant experience, skills, and achievements for this specific role.
2. Tailor bullet points to mirror the job posting's language and priorities.
3. Keep the resume to one page equivalent (6 bullets max per role, 3-4 roles max).
4. Write a 3-paragraph cover letter: opening (role + why), middle (top 2-3 relevant achievements with numbers), closing (call to action).
5. Return ONLY a JSON object matching this exact schema — no markdown fences, no explanation outside the JSON:

{{
  "contact": {{
    "name": "Alex Zagorianos",
    "email": "alexzagorianos@gmail.com",
    "phone": "[REDACTED-PHONE]",
    "location": "Cincinnati, OH"
  }},
  "summary": "2-3 sentence professional summary tailored to the role",
  "skills": ["skill1", "skill2"],
  "experience": [
    {{
      "company": "Company Name",
      "title": "Job Title",
      "duration": "Start - End",
      "location": "City, State",
      "bullets": ["Achievement 1", "Achievement 2"]
    }}
  ],
  "education": [
    {{
      "institution": "NC State University",
      "degree": "BS Mechanical Engineering",
      "graduated": "May 2025",
      "details": []
    }}
  ],
  "cover_letter": "Full cover letter text. Use \\n\\n to separate paragraphs."
}}"""


def _parse_response(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[1:end])
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ResumeGenerationError(
            f"Claude returned malformed JSON: {e}\n\nFirst 500 chars:\n{raw[:500]}"
        )
