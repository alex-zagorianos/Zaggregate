"""Offline skill-gap for a single job description: a 'you have' / 'the job also
wants' split, with zero AI and zero network. Powers a UI panel and feeds resume
tailoring with the concrete terms a JD asks for that the user can't yet claim.

    matched — user skill terms the JD actually mentions (word-boundary, case-
              insensitive), sorted and deduped.
    missing — salient skill-ish terms the JD asks for that are NOT in the user's
              skills: capitalized / tech tokens (Kubernetes, PyTorch, CUDA, ROS,
              PLC, SQL, .NET) plus phrases right after trigger leads ("experience
              with", "proficiency in", ...). User skills and a stoplist of non-
              skills (bachelor, degree, years, PTO, ...) are removed; the rest
              are returned most-frequent first, capped at ``limit``.

Deterministic. Stdlib + match.scorer only (reuses its skill set and the same
word-boundary _term_pattern so 'matched' agrees with the live scorer).
"""
import re
from collections import Counter

from match import scorer

# ── Candidate extraction ──────────────────────────────────────────────────────
# (a) Capitalized / tech tokens. Each alternative captures one "tech-shaped"
#     token without depending on sentence position:
#       .NET / .js         dotted-leading
#       C++ / C#           letter(s) + trailing symbol run
#       Kubernetes         Capitalized word
#       PyTorch / CamelCase mixed-case interior cap
#       CUDA / SQL / ROS   ALL-CAPS acronym (2+)
#       Node.js / scikit-learn  dotted / hyphenated compounds
_TECH_TOKEN_RE = re.compile(
    r"\.[A-Za-z][A-Za-z0-9]*"                 # .NET, .js
    r"|[A-Za-z]+(?:\+\+|#)"                    # C++, C#, F#
    r"|[A-Za-z][A-Za-z0-9]*(?:[.\-][A-Za-z0-9]+)+"  # Node.js, scikit-learn
    r"|[A-Z][a-z]+(?:[A-Z][a-z0-9]+)+"         # PyTorch, CamelCase
    r"|[A-Z][a-z]{1,}"                         # Kubernetes, Python (Capitalized word)
    r"|[A-Z]{2,}[0-9]*"                        # CUDA, SQL, ROS, PLC, S3
)

# (b) Phrases right after these trigger leads. Capture a short run of skill-ish
#     tokens (words / dotted / symboled), stopping at a clause break.
_TRIGGERS = (
    "experience with", "proficiency in", "proficient in", "knowledge of",
    "familiarity with", "expertise in", "skilled in",
)
_TRIGGER_RE = re.compile(
    r"(?:" + "|".join(re.escape(t) for t in _TRIGGERS) + r")\s+"
    r"([A-Za-z0-9.+#/\- ]+)",
    re.IGNORECASE,
)
# Inside a trigger tail, pull the individual skill-ish tokens.
_TAIL_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+#\-]*")

# Non-skill noise that surfaces as capitalized words / trigger tails but never
# belongs in a gap list. Lowercased compare.
_STOPLIST = frozenset({
    "bachelor", "bachelors", "master", "masters", "phd", "degree", "diploma",
    "year", "years", "experience", "ability", "able", "team", "teams",
    "strong", "excellent", "good", "great", "solid", "proven", "hands",
    "communication", "communications", "skill", "skills", "knowledge",
    "proficiency", "proficient", "familiarity", "expertise", "skilled",
    "pto", "benefits", "benefit", "salary", "401k", "company", "companies",
    "work", "working", "role", "position", "candidate", "candidates",
    "requirement", "requirements", "required", "preferred", "plus", "etc",
    # Generic role / seniority words (mirror scorer._STOPWORDS intent) — they are
    # title noise, not skills.
    "engineer", "engineering", "developer", "manager", "senior", "junior",
    "lead", "staff", "principal", "intern", "specialist", "analyst",
    "the", "and", "or", "of", "in", "with", "a", "an", "to", "for", "we",
    "you", "your", "our", "is", "are", "will", "must", "should", "including",
    # Common sentence-leading capitalized words that aren't tech.
    "we", "you", "this", "that", "these", "those", "also", "additionally",
    "responsibilities", "qualifications", "us", "as", "be", "have", "has",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
    "sunday", "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
    # Rubric/grade-scale boilerplate from long-form government/clinical postings
    # (S36 scenario MINOR-5: a VA JD surfaced "ii"/"education"/"practice"/
    # "dimension" as missing SKILLS). Structural section words + the common
    # grade-level roman numerals. "iv" is deliberately KEPT OUT — it is
    # ambiguous with intravenous (a real nursing skill); inclusion over
    # precision applies to the gap list too.
    "education", "practice", "practices", "dimension", "dimensions",
    "scope", "criteria", "criterion", "grade", "grades", "level", "levels",
    "ii", "iii", "vii", "viii",
})

_MIN_LEN = 2


def _clean(tok: str) -> str:
    """Lowercase and trim trailing separators, but keep a leading '.' so dotted
    tech names survive ('.NET' -> '.net', not 'net')."""
    return tok.strip().rstrip(".-").lower()


def _candidate_terms(description: str) -> Counter:
    """Lowercased candidate skill tokens with frequency, from both extraction
    paths over the original-case description."""
    counts: Counter = Counter()

    # (a) capitalized / tech-shaped tokens anywhere in the text.
    for m in _TECH_TOKEN_RE.finditer(description):
        tok = _clean(m.group(0))
        if len(tok) >= _MIN_LEN:
            counts[tok] += 1

    # (b) tails of trigger phrases ("experience with Rust and Go" -> rust, go).
    for m in _TRIGGER_RE.finditer(description):
        for tm in _TAIL_TOKEN_RE.finditer(m.group(1)):
            tok = _clean(tm.group(0))
            if len(tok) >= _MIN_LEN:
                counts[tok] += 1

    return counts


def skill_gap(description, skill_terms=None, experience_path=None, limit=12) -> dict:
    """Compare a job ``description`` to the user's skills.

    Returns ``{"matched": [...], "missing": [...]}``:
      matched — user skill terms the JD mentions (sorted, deduped).
      missing — JD skill terms the user lacks (most-frequent first, <= limit).

    ``skill_terms`` defaults to ``scorer.extract_skill_terms(experience_path)``.
    Defensive on missing/blank input — never raises.
    """
    text = description if isinstance(description, str) else ""
    if not text.strip():
        return {"matched": [], "missing": []}

    if skill_terms is None:
        skill_terms = scorer.extract_skill_terms(experience_path)
    skill_terms = frozenset(skill_terms or ())

    low = text.lower()

    # matched: user skills the JD actually mentions (word-boundary, deduped).
    matched = sorted({
        t for t in skill_terms
        if t and scorer._term_pattern(t).search(low)
    })

    # missing: JD skill candidates the user does NOT already have.
    counts = _candidate_terms(text)
    matched_set = set(matched)
    out_counts: Counter = Counter()
    for term, freq in counts.items():
        if len(term) < _MIN_LEN:
            continue
        if term in _STOPLIST:
            continue
        if term in skill_terms or term in matched_set:
            continue
        # Skip any candidate that a user skill already covers (e.g. user has
        # 'python', JD says 'Python') even if casing/derivation differs.
        if any(scorer._term_pattern(s).search(term) for s in skill_terms if s):
            continue
        out_counts[term] += freq

    # Most-frequent first; ties broken alphabetically for determinism.
    ordered = sorted(out_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    missing = [term for term, _ in ordered[:limit]]

    return {"matched": matched, "missing": missing}
