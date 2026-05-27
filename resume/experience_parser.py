from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import EXPERIENCE_FILE


def load_experience(path=None) -> dict:
    """Parse experience.md into sections by ## heading."""
    text = (Path(path) if path else EXPERIENCE_FILE).read_text(encoding="utf-8")
    sections = _split_by_h2(text)
    return {
        "contact":         sections.get("CONTACT", ""),
        "education":       sections.get("EDUCATION", ""),
        "skills":          sections.get("TECHNICAL SKILLS", ""),
        "work_experience": sections.get("WORK EXPERIENCE", ""),
        "notes":           sections.get("NOTES FOR RESUME GENERATION", ""),
    }


def _split_by_h2(text: str) -> dict:
    pattern = re.compile(r"^## (.+)$", re.MULTILINE)
    parts = pattern.split(text)
    result = {}
    for i in range(1, len(parts), 2):
        heading = parts[i].strip().upper()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        result[heading] = body
    return result
