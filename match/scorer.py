"""Local match scorer — ranks JobResults against the user's profile with zero
API calls so every search (CLI, GUI, daily run) surfaces best-fit jobs first.

Composite 0-100:
    title match      35  — search keywords found in the job title
    skill overlap    25  — terms from experience.md TECHNICAL SKILLS in the
                           description (missing description = neutral)
    salary           15  — posted floor vs the user's salary_min (missing = neutral;
                           ranges printed inside descriptions are parsed out first)
    location         15  — token proximity to the target location
    recency          10  — posting age, exponential decay (10-day half-life);
                           unknown dates are neutral, not penalized
Company-size modifier: careers-scraper jobs carry the total postings on the
company's board (board_count) — small boards get +8/+4, mega boards −6.
Exclude-keywords (user_config "exclude_keywords") subtract 30 each, floor 0.

Claude-assisted "fit" scoring (claude_bridge) is a separate, optional second
pass on the top of this ranking.
"""
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models import JobResult
from search.search_engine import _EPOCH, _location_score, _parse_created

# Words too generic to signal a title match on their own.
_STOPWORDS = {"engineer", "engineering", "senior", "junior", "lead", "staff",
              "and", "or", "of", "the", "i", "ii", "iii"}

# Skill terms shorter than this are too ambiguous to substring-match ("c", "qt").
_MIN_TERM_LEN = 3

_cache: dict[tuple[str, float], frozenset[str]] = {}


def extract_skill_terms(experience_path=None) -> frozenset[str]:
    """Pull a lowercase skill-term set from experience.md's TECHNICAL SKILLS
    section (memoized on mtime). Terms come from comma/slash/bullet-separated
    fragments, e.g. 'SolidWorks 2024' -> 'solidworks 2024' and 'solidworks'."""
    from resume.experience_parser import load_experience
    from config import EXPERIENCE_FILE
    target = Path(experience_path) if experience_path else EXPERIENCE_FILE
    if not target.exists():
        return frozenset()
    key = (str(target), target.stat().st_mtime)
    if key in _cache:
        return _cache[key]

    skills_md = load_experience(target).get("skills", "")
    terms: set[str] = set()
    for line in skills_md.splitlines():
        line = line.strip().lstrip("-*").strip()
        if not line or line.startswith("#"):
            continue
        # "CAD / Simulation: SolidWorks 2024, CadQuery" -> right side of colon
        if ":" in line:
            line = line.split(":", 1)[1]
        for frag in re.split(r"[,/;()]", line):
            frag = frag.strip().lower()
            if len(frag) >= _MIN_TERM_LEN and frag not in _STOPWORDS:
                terms.add(frag)
                # also index the first word of multiword terms ("solidworks 2024")
                head = frag.split()[0]
                if len(head) >= _MIN_TERM_LEN and head not in _STOPWORDS:
                    terms.add(head)
    _cache[key] = frozenset(terms)
    return _cache[key]


def _title_score(title: str, keywords: Iterable[str]) -> float:
    """1.0 = a search keyword appears (nearly) whole in the title;
    partial credit for significant-token overlap."""
    tl = (title or "").lower()
    best = 0.0
    for kw in keywords:
        kwl = kw.lower().strip()
        if not kwl:
            continue
        if kwl in tl:
            return 1.0
        toks = [t for t in re.split(r"\W+", kwl) if t and t not in _STOPWORDS]
        if not toks:
            continue
        hit = sum(1 for t in toks if t in tl)
        best = max(best, hit / len(toks))
    return best


_term_pattern_cache: dict[str, re.Pattern] = {}


def _term_pattern(term: str) -> re.Pattern:
    """Word-boundary pattern for a skill term. Plain ``in`` matching produced
    false hits ('pid' in 'rapid', 'ros' in 'process'). Lookarounds instead of
    \\b so terms ending in non-word chars ('c++', '.net') still anchor."""
    pat = _term_pattern_cache.get(term)
    if pat is None:
        pat = re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)")
        _term_pattern_cache[term] = pat
    return pat


def _skill_score(description: str, skill_terms: frozenset[str]) -> float:
    """Fraction of matched skill terms, saturating at 8 hits = 1.0."""
    if not skill_terms:
        return 0.5  # neutral when no profile available
    if not (description or "").strip():
        # No description to read (HN/browser-harvest/direct scrapes) — neutral,
        # same as unknown recency. A 0 here buried whole sources 25 pts under
        # described jobs for a data gap, not a real signal.
        return 0.5
    dl = description.lower()
    hits = sum(1 for t in skill_terms if _term_pattern(t).search(dl))
    return min(hits / 8.0, 1.0)


# Pay ranges printed in descriptions (CA/CO/NY disclosure laws make these
# common on exactly the boards that never fill the salary API fields).
_SALARY_RE = re.compile(
    r"\$\s?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?\s?[kK]|\d+(?:\.\d+)?)"
    r"(?:\s*(?:-|–|—|to)\s*\$?\s?(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?\s?[kK]|\d+(?:\.\d+)?))?"
)


def _parse_money(tok: Optional[str]) -> Optional[float]:
    """'$165,000' / '95k' / '45.50' (hourly) -> annual dollars, or None if it
    fails sanity bounds (30k-500k) — filters out 401k figures, fees, etc."""
    if not tok:
        return None
    t = tok.lower().replace(",", "").strip()
    mult = 1000.0 if t.endswith("k") else 1.0
    t = t.rstrip("k").strip()
    try:
        val = float(t) * mult
    except ValueError:
        return None
    if val < 200:  # plausible hourly rate -> annualize
        val *= 2080
    return val if 30_000 <= val <= 500_000 else None


def salary_from_text(text: str) -> tuple[Optional[float], Optional[float]]:
    """Best-effort (min, max) annual salary parsed from free text."""
    for m in _SALARY_RE.finditer(text or ""):
        lo = _parse_money(m.group(1))
        hi = _parse_money(m.group(2))
        if lo and hi:
            return (min(lo, hi), max(lo, hi))
        if lo:
            return (lo, None)
    return (None, None)


def _salary_score(job: JobResult, floor: Optional[int]) -> float:
    if not floor:
        return 1.0
    top = job.salary_max or job.salary_min
    if top is None:
        return 0.5  # unlisted — neutral, don't bury it
    if top >= floor:
        return 1.0
    return max(0.0, top / floor - 0.25)  # near-misses keep partial credit


def _recency_score(created: str) -> float:
    dt = _parse_created(created)
    if dt == _EPOCH:
        # Unknown date (Workday/direct scrapes) — neutral instead of a flat
        # -10 penalty against whole sources.
        return 0.5
    age_days = max(0, (datetime.now(timezone.utc) - dt).days)
    return 0.5 ** (age_days / 10.0)  # 10-day half-life


def score_job(
    job: JobResult,
    *,
    keywords: Iterable[str],
    location: str,
    salary_floor: Optional[int] = None,
    skill_terms: Optional[frozenset[str]] = None,
    exclude_keywords: Iterable[str] = (),
) -> tuple[int, str]:
    """Return (score 0-100, short breakdown string)."""
    if skill_terms is None:
        skill_terms = extract_skill_terms()

    # Recover pay ranges printed in the description when the API fields are
    # empty (fills the GUI salary column too, via salary_display()).
    if job.salary_min is None and job.salary_max is None and job.description:
        lo, hi = salary_from_text(job.description)
        if lo or hi:
            job.salary_min, job.salary_max = lo, hi

    t = _title_score(job.title, keywords)
    k = _skill_score(job.description, skill_terms)
    s = _salary_score(job, salary_floor)
    loc_raw = _location_score(job.location, location)
    l = min(loc_raw / 3.0, 1.0)  # 3+ token hits = full marks
    r = _recency_score(job.created)

    score = 35 * t + 25 * k + 15 * s + 15 * l + 10 * r

    # Company-size modifier from the careers boards' total-postings proxy.
    size_adj = 0
    bc = getattr(job, "board_count", -1)
    if bc >= 0:
        if bc <= 30:
            size_adj = 8      # small shop
        elif bc <= 100:
            size_adj = 4      # mid-size
        elif bc > 250:
            size_adj = -6     # mega board
    score += size_adj

    penalties = []
    blob = f"{(job.title or '').lower()} {(job.description or '').lower()}"
    for bad in exclude_keywords:
        b = (bad or "").lower().strip()
        if b and b in blob:
            score -= 30
            penalties.append(b)

    score = int(max(0, min(100, round(score))))
    notes = f"title {t:.0%} | skills {k:.0%} | salary {s:.0%} | loc {l:.0%} | new {r:.0%}"
    if size_adj:
        notes += f" | size {size_adj:+d} ({bc} on board)"
    if penalties:
        notes += f" | PENALTY: {', '.join(penalties)}"
    return score, notes


def score_jobs(
    jobs: list[JobResult],
    *,
    keywords: Iterable[str],
    location: str,
    salary_floor: Optional[int] = None,
    exclude_keywords: Iterable[str] = (),
) -> list[JobResult]:
    """Score in place and return the same list sorted best-first."""
    terms = extract_skill_terms()
    for job in jobs:
        job.score, job.score_notes = score_job(
            job, keywords=keywords, location=location,
            salary_floor=salary_floor, skill_terms=terms,
            exclude_keywords=exclude_keywords,
        )
    jobs.sort(key=lambda j: j.score, reverse=True)
    return jobs
