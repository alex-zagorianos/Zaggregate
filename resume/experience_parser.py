from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import workspace

# Single source of truth for the experience-section name contract: dict key ->
# canonical markdown heading. Imported by generator.py and claude_bridge.py so
# the corpus builders stay in lockstep with the parser. (RESUME-6)
EXPERIENCE_SECTIONS: dict[str, str] = {
    "contact":         "CONTACT",
    "education":       "EDUCATION",
    "skills":          "TECHNICAL SKILLS",
    "work_experience": "WORK EXPERIENCE",
    "notes":           "NOTES FOR RESUME GENERATION",
}

# Common drift aliases -> canonical heading (normalized: upper, stripped of a
# trailing ':'). Lets a renamed/abbreviated heading still parse instead of
# silently dropping the whole section. (RESUME-1)
# Note: a bare "EXPERIENCE" is deliberately NOT aliased — it is commonly the
# document's H1 title (the seed uses '# Experience'), and mapping it to WORK
# EXPERIENCE would let that banner shadow the real '## WORK EXPERIENCE' section.
_HEADING_ALIASES: dict[str, str] = {
    "CONTACT INFO":            "CONTACT",
    "CONTACT INFORMATION":     "CONTACT",
    "SKILLS":                  "TECHNICAL SKILLS",
    "TECHNICAL SKILL":         "TECHNICAL SKILLS",
    "WORK HISTORY":            "WORK EXPERIENCE",
    "WORK EXPERIENCES":        "WORK EXPERIENCE",
    "PROFESSIONAL EXPERIENCE": "WORK EXPERIENCE",
    "EMPLOYMENT":              "WORK EXPERIENCE",
    "EMPLOYMENT HISTORY":      "WORK EXPERIENCE",
    "NOTES":                   "NOTES FOR RESUME GENERATION",
    "RESUME NOTES":            "NOTES FOR RESUME GENERATION",
    "NOTES FOR RESUME":        "NOTES FOR RESUME GENERATION",
}

# Cache parsed sections keyed by (path, mtime) so repeated generations in one
# session don't re-read and re-regex the file; auto-invalidates if it's edited.
_cache: dict[tuple[str, float], dict] = {}


def _normalize_heading(heading: str) -> str:
    """Canonicalize a raw heading: uppercase, collapse inner whitespace, drop a
    trailing ':', then map through the alias table to a known section name."""
    norm = re.sub(r"\s+", " ", heading.strip().upper()).rstrip(":").strip()
    return _HEADING_ALIASES.get(norm, norm)


def load_experience(path=None) -> dict:
    """Parse experience.md into sections by heading (memoized on mtime).

    Tolerates case/colon/space drift and H1-vs-H2 headings via an alias map. If
    ZERO known sections are found, raises ValueError naming the expected
    headings rather than returning an all-empty dict (which would yield a blank
    or hallucinated resume). (RESUME-1)"""
    target = Path(path) if path else workspace.experience_file()
    key = (str(target), target.stat().st_mtime)
    if key not in _cache:
        sections = _split_by_heading(target.read_text(encoding="utf-8"))
        # A known section counts as "found" if its canonical heading is present,
        # even with an empty body (the seed ships empty sections on purpose).
        found = [canon for canon in EXPERIENCE_SECTIONS.values()
                 if canon in sections]
        if not found:
            expected = ", ".join(f"## {h}" for h in EXPERIENCE_SECTIONS.values())
            raise ValueError(
                "experience.md has no recognizable sections. Expected one or "
                f"more '## ' headings from: {expected}. Found headings: "
                f"{sorted(sections) or 'none'}."
            )
        _cache[key] = {dk: sections.get(canon, "")
                       for dk, canon in EXPERIENCE_SECTIONS.items()}
    return _cache[key]


# Corpus section labels (display headings used in the prompt corpus). Keyed by
# the same dict keys as EXPERIENCE_SECTIONS so generator.py and claude_bridge.py
# render an identical corpus from one definition. (RESUME-6)
CORPUS_LABELS: dict[str, str] = {
    "contact":         "Contact",
    "education":       "Education",
    "skills":          "Technical Skills",
    "work_experience": "Work Experience",
    "notes":           "Guidance Notes",
}


def experience_corpus(experience: dict) -> str:
    """Render the parsed experience dict into the prompt corpus block shared by
    the API generator and the copy-paste bridge."""
    return "## CANDIDATE EXPERIENCE\n\n" + "\n\n".join(
        f"### {label}\n{experience.get(dk, '')}"
        for dk, label in CORPUS_LABELS.items()
    )


def contact_name(experience: dict) -> str:
    """Candidate name from the parsed CONTACT section, taken only from an
    explicit 'Name:' line (markdown list or plain). Returns '' when none is
    present, so callers can fall back to a generic filename rather than guess
    from an unrelated line (e.g. Email:). Used to derive the output resume
    filename instead of a hardcoded identity. (RESUME-6)"""
    contact = experience.get("contact", "") or ""
    m = re.search(r"(?im)^\s*[-*]?\s*name\s*:\s*(.+?)\s*$", contact)
    if m and m.group(1).strip():
        return m.group(1).strip()
    return ""


def _split_by_heading(text: str) -> dict:
    """Split on H1 or H2 headings (# or ## ...), keyed by normalized heading.
    Accepting H1 keeps a new-project seed's '# Experience' from masking the
    '## ' subsections below it."""
    pattern = re.compile(r"^#{1,2} (.+)$", re.MULTILINE)
    parts = pattern.split(text)
    result = {}
    for i in range(1, len(parts), 2):
        heading = _normalize_heading(parts[i])
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        # Only keep the first body for a given normalized heading so a top H1
        # banner doesn't clobber a real section of the same canonical name.
        if heading not in result or not result[heading]:
            result[heading] = body
    return result
