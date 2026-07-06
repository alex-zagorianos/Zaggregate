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
    "summary":         "SUMMARY",
    "education":       "EDUCATION",
    "skills":          "TECHNICAL SKILLS",
    "certifications":  "LICENSES & CERTIFICATIONS",
    "work_experience": "WORK EXPERIENCE",
    "projects":        "PROJECTS",
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
    # Non-engineering resumes rarely use "TECHNICAL SKILLS"; without these the
    # skill-overlap component (25% of the match score) silently goes neutral for a
    # health-IT exec / nurse / accountant profile. (finding #17)
    "CORE COMPETENCIES":       "TECHNICAL SKILLS",
    "CORE COMPETENCY":         "TECHNICAL SKILLS",
    "COMPETENCIES":            "TECHNICAL SKILLS",
    "AREAS OF EXPERTISE":      "TECHNICAL SKILLS",
    "KEY SKILLS":              "TECHNICAL SKILLS",
    "SKILLS & EXPERTISE":      "TECHNICAL SKILLS",
    "SKILLS AND EXPERTISE":    "TECHNICAL SKILLS",
    "PROFESSIONAL SKILLS":     "TECHNICAL SKILLS",
    "TECHNICAL PROFICIENCIES": "TECHNICAL SKILLS",
    "WORK HISTORY":            "WORK EXPERIENCE",
    "WORK EXPERIENCES":        "WORK EXPERIENCE",
    "PROFESSIONAL EXPERIENCE": "WORK EXPERIENCE",
    "EMPLOYMENT":              "WORK EXPERIENCE",
    "EMPLOYMENT HISTORY":      "WORK EXPERIENCE",
    "NOTES":                   "NOTES FOR RESUME GENERATION",
    "RESUME NOTES":            "NOTES FOR RESUME GENERATION",
    "NOTES FOR RESUME":        "NOTES FOR RESUME GENERATION",
    # Licenses/certifications: the load-bearing section for nurses, welders,
    # teachers, drivers, accountants, PMs. Previously silently dropped (no
    # canonical key), so a nurse's "RN, BLS, ACLS" never reached the scorer's
    # skill-term extraction. (P3)
    "CERTIFICATIONS":          "LICENSES & CERTIFICATIONS",
    "CERTIFICATES":            "LICENSES & CERTIFICATIONS",
    "CERTIFICATION":           "LICENSES & CERTIFICATIONS",
    "LICENSES":                "LICENSES & CERTIFICATIONS",
    "LICENSURE":               "LICENSES & CERTIFICATIONS",
    "LICENSE":                 "LICENSES & CERTIFICATIONS",
    "CREDENTIALS":             "LICENSES & CERTIFICATIONS",
    "LICENSES AND CERTIFICATIONS":     "LICENSES & CERTIFICATIONS",
    "LICENSES & CERTIFICATES":          "LICENSES & CERTIFICATIONS",
    "CERTIFICATIONS & LICENSES":        "LICENSES & CERTIFICATIONS",
    "CERTIFICATIONS AND LICENSES":      "LICENSES & CERTIFICATIONS",
    "LICENSES CERTIFICATIONS":          "LICENSES & CERTIFICATIONS",
    # Summary / objective / profile -- the top-of-resume prose block. Feeds the
    # resume-generation corpus so a candidate's own positioning isn't dropped.
    "SUMMARY":                 "SUMMARY",
    "PROFESSIONAL SUMMARY":    "SUMMARY",
    "SUMMARY OF QUALIFICATIONS": "SUMMARY",
    "CAREER SUMMARY":          "SUMMARY",
    "OBJECTIVE":               "SUMMARY",
    "CAREER OBJECTIVE":        "SUMMARY",
    "PROFILE":                 "SUMMARY",
    "PROFESSIONAL PROFILE":    "SUMMARY",
}

# Cache parsed sections keyed by (path, mtime) so repeated generations in one
# session don't re-read and re-regex the file; auto-invalidates if it's edited.
_cache: dict[tuple[str, float], dict] = {}


def _normalize_heading(heading: str) -> str:
    """Canonicalize a raw heading: uppercase, collapse inner whitespace, drop a
    trailing ':', then map through the alias table to a known section name."""
    norm = re.sub(r"\s+", " ", heading.strip().upper()).rstrip(":").strip()
    return _HEADING_ALIASES.get(norm, norm)


def load_experience(path=None, *, lenient=False) -> dict:
    """Parse experience.md into sections by heading (memoized on mtime).

    Tolerates case/colon/space drift and H1-vs-H2 headings via an alias map.

    Strict mode (default): if ZERO known sections are found, raises ValueError
    naming the expected headings rather than returning an all-empty dict (which
    would yield a blank or hallucinated resume). (RESUME-1)

    Lenient mode (`lenient=True`): NEVER raises. When no known section is found
    (a plain-text paste with no '## ' headings -- the wizard's most common input),
    the whole document is returned under 'work_experience' so scoring/generation
    still have the candidate's text to work with instead of crashing. This is the
    P0 guard that keeps a pasted nurse/welder/teacher resume from erroring every
    subsequent search. (P0 #1)

    Certifications reach the scorer: LICENSES & CERTIFICATIONS terms (RN, BLS,
    ACLS, CDL, PE, CPA, ...) are folded into the 'skills' value the scorer's
    match.scorer.extract_skill_terms already reads (`.get("skills")`) so they
    count toward skill overlap WITHOUT any change in match/. They also render as
    their own labeled corpus block via CORPUS_LABELS. (P3)"""
    target = Path(path) if path else workspace.experience_file()
    ck = (str(target), target.stat().st_mtime, lenient)
    if ck not in _cache:
        sections = _split_by_heading(target.read_text(encoding="utf-8"))
        # A known section counts as "found" if its canonical heading is present,
        # even with an empty body (the seed ships empty sections on purpose).
        found = [canon for canon in EXPERIENCE_SECTIONS.values()
                 if canon in sections]
        if not found:
            if lenient:
                # Structure-free paste: keep the whole body as work experience so
                # downstream never sees an all-empty dict (nor a crash).
                raw = target.read_text(encoding="utf-8").strip()
                parsed = {dk: "" for dk in EXPERIENCE_SECTIONS}
                parsed["work_experience"] = raw
                _cache[ck] = _fold_certs_into_skills(parsed)
                return _cache[ck]
            expected = ", ".join(f"## {h}" for h in EXPERIENCE_SECTIONS.values())
            raise ValueError(
                "experience.md has no recognizable sections. Expected one or "
                f"more '## ' headings from: {expected}. Found headings: "
                f"{sorted(sections) or 'none'}."
            )
        parsed = {dk: sections.get(canon, "")
                  for dk, canon in EXPERIENCE_SECTIONS.items()}
        _cache[ck] = _fold_certs_into_skills(parsed)
    return _cache[ck]


def _fold_certs_into_skills(parsed: dict) -> dict:
    """Append the certifications text to the 'skills' value so the scorer's
    skill-term extraction (which reads only the 'skills' key) also picks up
    licenses/certifications. Non-destructive: the standalone 'certifications'
    key is kept intact for the labeled corpus block. No-op when either section
    is empty, so an engineering profile with no certs is byte-identical."""
    certs = (parsed.get("certifications") or "").strip()
    if not certs:
        return parsed
    skills = (parsed.get("skills") or "").strip()
    parsed["skills"] = f"{skills}\n{certs}".strip() if skills else certs
    return parsed


# Corpus section labels (display headings used in the prompt corpus). Keyed by
# the same dict keys as EXPERIENCE_SECTIONS so generator.py and claude_bridge.py
# render an identical corpus from one definition. (RESUME-6)
CORPUS_LABELS: dict[str, str] = {
    "contact":         "Contact",
    "summary":         "Summary",
    "education":       "Education",
    "skills":          "Skills",
    "certifications":  "Licenses & Certifications",
    "work_experience": "Work Experience",
    "projects":        "Projects",
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
