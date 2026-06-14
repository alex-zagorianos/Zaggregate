from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import EXPERIENCE_FILE

# Cache parsed sections keyed by (path, mtime) so repeated generations in one
# session don't re-read and re-regex the file; auto-invalidates if it's edited.
_cache: dict[tuple[str, float], dict] = {}


def load_experience(path=None) -> dict:
    """Parse experience.md into sections by ## heading (memoized on mtime)."""
    target = Path(path) if path else EXPERIENCE_FILE
    key = (str(target), target.stat().st_mtime)
    if key not in _cache:
        sections = _split_by_h2(target.read_text(encoding="utf-8"))
        _cache[key] = {
            "contact":         sections.get("CONTACT", ""),
            "education":       sections.get("EDUCATION", ""),
            "skills":          sections.get("TECHNICAL SKILLS", ""),
            "work_experience": sections.get("WORK EXPERIENCE", ""),
            "notes":           sections.get("NOTES FOR RESUME GENERATION", ""),
        }
    return _cache[key]


def _split_by_h2(text: str) -> dict:
    pattern = re.compile(r"^## (.+)$", re.MULTILINE)
    parts = pattern.split(text)
    result = {}
    for i in range(1, len(parts), 2):
        heading = parts[i].strip().upper()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        result[heading] = body
    return result
