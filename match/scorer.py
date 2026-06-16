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
from search import query
from search.search_engine import _EPOCH, _location_score, _parse_created

# Words too generic to signal a title match on their own.
_STOPWORDS = {"engineer", "engineering", "senior", "junior", "lead", "staff",
              "and", "or", "of", "the", "i", "ii", "iii"}

# Skill terms shorter than this are too ambiguous to substring-match ("c", "qt").
_MIN_TERM_LEN = 3

# ── Auto-strict relevance — downrank off-target titles, never hide ────────────
# A title that satisfies none of the search queries (positive miss, or a NOT
# term present) takes a heavy penalty so it sinks below the noise but stays
# visible if you sort to it. exclude_titles / seniority_exclude are profile-
# specific blocklists (Alex excludes "AI Engineer"; Dad's health-informatics
# campaign may want data roles), so both default OFF here and are supplied per
# profile from user_config.json. Only the title-miss gate is on by default —
# it's relative to *your* keywords, so it's safe for every profile.
DEFAULT_TITLE_MISS_PENALTY = 35
DEFAULT_EXCLUDE_TITLES = ()      # per profile, e.g. ["ai", "machine learning", ...]
EXCLUDE_TITLE_PENALTY = 30
DEFAULT_SENIORITY_EXCLUDE = ()   # per profile, e.g. ["director", "manager", "intern"]
SENIORITY_PENALTY = 20

_cache: dict[tuple[str, float], frozenset[str]] = {}


def extract_skill_terms(experience_path=None) -> frozenset[str]:
    """Pull a lowercase skill-term set from experience.md's TECHNICAL SKILLS
    section (memoized on mtime). Terms come from comma/slash/bullet-separated
    fragments, e.g. 'SolidWorks 2024' -> 'solidworks 2024' and 'solidworks'."""
    from resume.experience_parser import load_experience
    import workspace
    target = Path(experience_path) if experience_path else workspace.experience_file()
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


def _term_present(term: str, tl: str) -> bool:
    """A positive query term in the (lowercased) title: phrases match contiguously,
    single words match as a substring with a trailing 's' stripped from long words."""
    if " " in term:
        return term in tl
    s = term[:-1] if len(term) > 3 and term.endswith("s") else term
    return s in tl


def _title_score(queries, tl: str) -> float:
    """1.0 = the title satisfies a whole search query; otherwise partial credit
    for significant positive-term overlap. `queries` are pre-parsed query.Query."""
    best = 0.0
    for q in queries:
        if q.matches(tl):
            return 1.0
        sig = [t for t in q.positive_terms()
               if t not in _STOPWORDS and len(t) >= _MIN_TERM_LEN]
        if not sig:
            continue
        hit = sum(1 for t in sig if _term_present(t, tl))
        best = max(best, hit / len(sig))
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


# Fallback for pay ranges printed WITHOUT a leading '$' (CA/CO/NY disclosure
# text: "Pay range: 120,000 - 150,000"). Both endpoints must be comma-grouped
# 5-6 digit numbers so a lone figure or a "401(k)" can't trigger it; the
# 30k-500k bound in _parse_money is the final guard.
_SALARY_RE_BARE = re.compile(
    r"(\d{2,3},\d{3})\s*(?:-|–|—|to)\s*(\d{2,3},\d{3})"
)


def salary_from_text(text: str) -> tuple[Optional[float], Optional[float]]:
    """Best-effort (min, max) annual salary parsed from free text."""
    for m in _SALARY_RE.finditer(text or ""):
        lo = _parse_money(m.group(1))
        hi = _parse_money(m.group(2))
        if lo and hi:
            return (min(lo, hi), max(lo, hi))
        if lo:
            return (lo, None)
    # No '$'-anchored hit -> try a bare comma-grouped range (both ends required).
    for m in _SALARY_RE_BARE.finditer(text or ""):
        lo = _parse_money(m.group(1))
        hi = _parse_money(m.group(2))
        if lo and hi:
            return (min(lo, hi), max(lo, hi))
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


def _title_blocklist_penalty(tl: str, terms) -> tuple[int, list[str]]:
    """Word-boundary blocklist over the title. Returns (count, hits)."""
    hits = [b for b in (t.lower().strip() for t in terms)
            if b and _term_pattern(b).search(tl)]
    return len(hits), hits


def score_job(
    job: JobResult,
    *,
    keywords: Iterable[str],
    location: str,
    salary_floor: Optional[int] = None,
    skill_terms: Optional[frozenset[str]] = None,
    exclude_keywords: Iterable[str] = (),
    exclude_titles: Optional[Iterable[str]] = None,
    title_miss_penalty: Optional[int] = None,
    seniority_exclude: Optional[Iterable[str]] = None,
) -> tuple[int, str]:
    """Return (score 0-100, short breakdown string)."""
    if skill_terms is None:
        skill_terms = extract_skill_terms()
    if exclude_titles is None:
        exclude_titles = DEFAULT_EXCLUDE_TITLES
    if title_miss_penalty is None:
        title_miss_penalty = DEFAULT_TITLE_MISS_PENALTY
    if seniority_exclude is None:
        seniority_exclude = DEFAULT_SENIORITY_EXCLUDE

    # Recover pay ranges printed in the description when the API fields are
    # empty (fills the GUI salary column too, via salary_display()).
    if job.salary_min is None and job.salary_max is None and job.description:
        lo, hi = salary_from_text(job.description)
        if lo or hi:
            job.salary_min, job.salary_max = lo, hi

    tl = (job.title or "").lower()
    queries = [query.parse(kw) for kw in keywords if kw]
    title_hit = any(q.matches(tl) for q in queries)  # full boolean (honors NOT)
    t = _title_score(queries, tl)                     # graded positive overlap
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

    notes_extra = []

    # Relevance gate: the title satisfies no search query (positive miss, or a
    # NOT term present). Heavy penalty so off-target sinks but stays visible.
    if queries and not title_hit:
        score -= title_miss_penalty
        notes_extra.append(f"title-miss -{title_miss_penalty}")

    # Always-on role blocklist (kills "AI Engineer", "Data Scientist", ...).
    n_block, block_hits = _title_blocklist_penalty(tl, exclude_titles)
    if n_block:
        score -= EXCLUDE_TITLE_PENALTY * n_block
        notes_extra.append(f"excl-title({','.join(block_hits)}) -{EXCLUDE_TITLE_PENALTY * n_block}")

    # Opt-in seniority blocklist.
    n_sen, sen_hits = _title_blocklist_penalty(tl, seniority_exclude)
    if n_sen:
        score -= SENIORITY_PENALTY * n_sen
        notes_extra.append(f"seniority({','.join(sen_hits)}) -{SENIORITY_PENALTY * n_sen}")

    penalties = []
    blob = f"{tl} {(job.description or '').lower()}"
    for bad in exclude_keywords:
        b = (bad or "").lower().strip()
        if b and b in blob:
            score -= 30
            penalties.append(b)

    score = int(max(0, min(100, round(score))))
    notes = f"title {t:.0%} | skills {k:.0%} | salary {s:.0%} | loc {l:.0%} | new {r:.0%}"
    if size_adj:
        notes += f" | size {size_adj:+d} ({bc} on board)"
    for ne in notes_extra:
        notes += f" | {ne}"
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
    exclude_titles: Optional[Iterable[str]] = None,
    title_miss_penalty: Optional[int] = None,
    seniority_exclude: Optional[Iterable[str]] = None,
) -> list[JobResult]:
    """Score in place and return the same list sorted best-first."""
    terms = extract_skill_terms()
    kws = list(keywords)
    for job in jobs:
        job.score, job.score_notes = score_job(
            job, keywords=kws, location=location,
            salary_floor=salary_floor, skill_terms=terms,
            exclude_keywords=exclude_keywords, exclude_titles=exclude_titles,
            title_miss_penalty=title_miss_penalty, seniority_exclude=seniority_exclude,
        )
    jobs.sort(key=lambda j: j.score, reverse=True)
    return jobs
