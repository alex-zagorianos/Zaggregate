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
company's board (board_count) — <=30 +8, <=100 +4, <=250 -2, >250 -6.
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

# Terms too GENERIC to constitute a real title match by themselves. When a keyword
# degrades to only these (e.g. "VP Health IT" -> just "health" after 2-char tokens
# are dropped), any posting mentioning the word ("Healthcare Services", "Mercy
# Health") would otherwise get full title credit AND escape the miss-penalty. A
# match on ONLY generic words is capped to partial credit. Field-specific terms
# ("controls", "informatics", "analytics", "nurse", ...) are NOT here, so a genuine
# single-term field match (Alex's "controls") is unaffected.
_GENERIC_TITLE_TERMS = frozenset({
    "health", "care", "medical", "clinical", "services", "service", "business",
    "data", "systems", "system", "technology", "information", "digital",
    "management", "solutions", "general", "support", "operations", "global",
    "national", "corporate", "specialist", "associate",
})

# Skill terms shorter than this are too ambiguous to substring-match ("c", "qt").
_MIN_TERM_LEN = 3

# ── seniority / target-level fit ──────────────────────────────────────────────
# The deterministic score had NO seniority dimension, so it could not rank a
# candidate's actual target level (a VP/Director/CMIO seeker) above an otherwise
# keyword-matching but clearly-below role (a "Senior Manager"/IC title). This adds
# a bounded target-level adjustment, but ONLY when the user is explicitly targeting
# management/exec (target level >= manager) — an IC/senior search is unchanged
# (Alex byte-identical). Levels reuse match.facts._detect_seniority's buckets
# (director == director/VP/chief), mapped to an ordinal.
_LEVEL_ORD = {"intern": 0, "entry": 1, "mid": 2, "senior": 3, "lead": 3,
              "manager": 4, "director": 5}
_MANAGEMENT_MIN = 4  # target must be manager+ for the adjustment to engage

# The config's explicit `seniority_target` string (from the wizard / project
# config) mapped onto the SAME ordinal scale as _LEVEL_ORD, so a below-target
# posting can be down-nudged for a no-AI user. This is the honesty fix for P0-3:
# without it "Sr."/"II·III"/"8+ YOE" tie a plain entry title in the local Score.
# The wizard emits entry/mid/senior/senior-exec; the rubric also uses entry-mid.
# Only engages when the user set a seniority_target -> unset profiles unchanged.
_SENIORITY_TARGET_ORD = {
    "intern": 0, "entry": 1, "entry-mid": 2, "mid": 2, "senior": 3, "lead": 3,
    "manager": 4, "senior-exec": 4, "exec": 5, "director": 5,
}


def _level_of(title: str, desc: str = "") -> int:
    """Ordinal seniority of a title (0 intern … 5 director/VP/chief). Lazy import
    avoids the scorer<->facts import cycle; only called when exec-targeting."""
    from match.facts import _detect_seniority
    return _LEVEL_ORD.get(_detect_seniority(title or "", desc or ""), 2)


def _target_level(keywords) -> Optional[int]:
    """Highest seniority the user's own target keywords imply (their target
    ROLES). None when nothing management-level is targeted -> no adjustment."""
    best = None
    for kw in keywords:
        if not kw:
            continue
        lvl = _level_of(kw, "")
        if best is None or lvl > best:
            best = lvl
    return best


def _seniority_fit_adj(job_title: str, target_level: Optional[int]) -> int:
    """Bounded score nudge for how well a posting's level matches the target.

    Two symmetric branches:
    - EXEC seeker (target >= _MANAGEMENT_MIN): reward at/above-target roles, sink
      clearly-junior ones (byte-identical to the original behavior).
    - IC seeker (target present but < _MANAGEMENT_MIN): mirror-penalize roles that
      are clearly ABOVE the target into management -- a manager/director posting is
      off-target for someone seeking an IC role. Manager -> -10, director+ -> -14.
      An IC target of None (no keywords) stays neutral, and a same/lower-level
      posting is untouched, so an ordinary IC/senior search's non-management
      results are unchanged."""
    if target_level is None:
        return 0
    job_level = _level_of(job_title, "")
    if target_level >= _MANAGEMENT_MIN:
        delta = job_level - target_level
        if delta >= 0:
            return 15          # at or above the target level
        if delta == -1:
            return 4           # one tier below (e.g. manager when seeking director)
        if delta == -2:
            return -8
        return -16             # clearly junior for an exec seeker (mid/entry/intern)
    # IC seeker: penalize a role that overshoots into management.
    if job_level >= _LEVEL_ORD["director"]:
        return -14             # director/VP/chief -- well above an IC target
    if job_level >= _MANAGEMENT_MIN:
        return -10             # manager -- above an IC target
    return 0


def _target_ord_of(seniority_target: Optional[str]) -> Optional[int]:
    """Ordinal for the config's explicit seniority_target string, or None when the
    user set no target (feature OFF -> byte-identical). Unknown strings -> None."""
    if not seniority_target:
        return None
    return _SENIORITY_TARGET_ORD.get(str(seniority_target).strip().lower())


# Seniority buckets that come from an EXPLICIT marker in the title/desc (Sr./Roman/
# manager/director/lead...). "mid" is the DEFAULT for an unmarked title, so it must
# NOT trigger the over-target nudge -- otherwise an entry seeker would penalize every
# plain title (which reads as "mid"). Only an explicit over-level marker down-nudges.
_EXPLICIT_LEVELS = frozenset({"senior", "lead", "manager", "director"})


def _seniority_target_adj(job_title: str, desc: str, target_ord: Optional[int],
                          years_cap: Optional[int]) -> tuple[int, Optional[str]]:
    """Bounded down-nudge (0..-12) for a posting that OVERSHOOTS the user's stated
    seniority_target -- the honesty fix so a keyless user's 'Sr.'/'II·III'/'IV'/
    '8+ YOE' rows stop tying a plain entry title. Returns (delta, level_label).

    Reuses match.facts._detect_seniority (handles Sr./Roman/8+; correct) and
    _detect_required_years. ONLY engages when target_ord is not None (the user set
    a seniority_target); an unset profile passes None -> (0, None) -> byte-identical.

    Crucially the nudge fires ONLY on an EXPLICIT over-level marker (senior/lead/
    manager/director/Roman III·IV) or a required-years-over-cap read -- NOT on the
    unmarked 'mid' default, so a plain 'Software Engineer' is untouched for an entry
    seeker (it would otherwise read as 'mid' and be penalized). A same/below-target
    posting is untouched (delta 0)."""
    if target_ord is None:
        return 0, None
    from match.facts import _detect_seniority, _detect_required_years
    # TITLE-ONLY seniority for the nudge: the over-leveling markers that matter
    # ("Sr."/"III"/"IV"/"Manager") live in the title. Reading the description
    # mis-fires on incidental prose ("join our team of senior engineers",
    # "reports to a director"), so pass an empty desc here. Required YEARS, by
    # contrast, legitimately live in the body, so that check reads the full text.
    level = _detect_seniority(job_title or "", "")
    job_ord = _LEVEL_ORD.get(level, 2)
    delta = 0
    over = job_ord - target_ord
    if level in _EXPLICIT_LEVELS and over >= 1:
        if over == 1:
            delta = -8        # one tier over (e.g. senior for a mid target)
        elif over == 2:
            delta = -10       # two tiers over (manager for an entry target)
        else:
            delta = -12       # far above (director+ for an entry target)
    # A posting demanding more years than the cap is also over-leveled; add a small
    # extra nudge, bounded so the total never exceeds -12. This catches an explicit
    # '8+ YOE' even when the title carries no seniority word.
    if years_cap:
        yrs = _detect_required_years(f"{job_title or ''}\n{desc or ''}")
        if yrs and yrs > years_cap:
            delta = max(-12, delta - 8)
    return delta, (level if delta else None)

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

# Semantic-similarity component weight (match/semantic.py, Model2Vec). Only ever
# ACTIVE when semantic ranking is enabled AND the model loaded AND both profile &
# job text exist — otherwise it's not a present component and the score is
# byte-identical to the keyword-only scorer. Capped low (mirrors Huntr's <20% of
# score keyword-cap discipline) so it nudges ranking without dominating it.
SEM_WEIGHT = 12

_cache: dict[tuple[str, float], frozenset[str]] = {}
_profile_cache: dict[tuple[str, float], str] = {}


def profile_text(experience_path=None) -> str:
    """Compact candidate-profile text for semantic comparison: the concatenated
    experience.md sections (skills + prose), memoized on mtime, capped. '' when
    there's no experience file (semantic then abstains -> keyword-only score)."""
    from resume.experience_parser import load_experience
    import workspace
    target = Path(experience_path) if experience_path else workspace.experience_file()
    if not target.exists():
        return ""
    key = (str(target), target.stat().st_mtime)
    if key in _profile_cache:
        return _profile_cache[key]
    try:
        data = load_experience(target)
        text = " ".join(str(v) for v in data.values() if v)[:4000]
    except Exception:
        text = ""
    _profile_cache[key] = text
    return text


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

    # Defense-in-depth: a malformed experience.md (e.g. a wizard plain-text paste
    # with no '## ' headings) makes load_experience raise ValueError. Degrade to a
    # neutral EMPTY skill set instead of crashing the whole scoring/daily run --
    # the scorer treats no-profile as neutral. The parser itself is fixed
    # elsewhere; this just guarantees a bad file never kills a run.
    try:
        skills_md = load_experience(target).get("skills", "")
    except Exception:
        skills_md = ""
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
    """A positive query term in the (lowercased) title, matched at a WORD START
    (mirrors query._Leaf) instead of raw substring, which killed false hits like
    'rn' inside 'internship' while still letting a term prefix a longer word
    ('robot' -> 'Robotics'). A long word's trailing 's' folds to optional so
    'controls' still matches both 'Control Systems' and 'Controls'."""
    stem = term[:-1] if (" " not in term and len(term) > 3 and term.endswith("s")) else term
    fold = stem != term
    return bool(_word_start_pattern(stem, fold).search(tl))


def _title_score(queries, tl: str) -> float:
    """1.0 = the title satisfies a whole search query; otherwise partial credit
    for significant positive-term overlap. `queries` are pre-parsed query.Query.

    A partial match on ONLY generic words (health/care/data/...) is capped at 0.5:
    a keyword that degrades to a single generic term ("VP Health IT" -> "health")
    must not award full title credit to every posting that merely says "health"."""
    best = 0.0
    for q in queries:
        if q.matches(tl):
            return 1.0
        sig = [t for t in q.positive_terms()
               if t not in _STOPWORDS and len(t) >= _MIN_TERM_LEN]
        if not sig:
            continue
        matched = [t for t in sig if _term_present(t, tl)]
        if not matched:
            continue
        frac = len(matched) / len(sig)
        # A match on a SINGLE generic word ("health" alone) isn't a real title
        # match; cap it. Two+ terms ("health data") or any specific term keep credit.
        if len(matched) == 1 and matched[0] in _GENERIC_TITLE_TERMS:
            frac = min(frac, 0.5)
        best = max(best, frac)
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


_word_start_pattern_cache: dict[tuple[str, bool], re.Pattern] = {}


def _word_start_pattern(stem: str, fold_s: bool) -> re.Pattern:
    """Word-START matcher for a POSITIVE title term (leading boundary, no trailing
    anchor) so a term may prefix a longer word ('robot' -> 'Robotics') -- kills the
    mid/end substring false hits ('rn' in 'internship') without cutting keyword
    recall. Mirrors search.query._bound. `fold_s` makes a trailing 's' optional.
    Deliberately looser than _term_pattern (full \\b, used for blocklists/skills,
    where precision matters)."""
    key = (stem, fold_s)
    pat = _word_start_pattern_cache.get(key)
    if pat is None:
        body = re.escape(stem) + ("s?" if fold_s else "")
        pat = re.compile(r"(?<!\w)" + body)
        _word_start_pattern_cache[key] = pat
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
# common on exactly the boards that never fill the salary API fields). A leading
# currency symbol ($, GBP, EUR) is captured so non-USD postings display the right
# symbol instead of being silently read as dollars.
_CUR_SYM = "$£€"  # $ GBP EUR
_MONEY = r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?\s?[kK]|\d+(?:\.\d+)?)"
_SALARY_RE = re.compile(
    r"([" + _CUR_SYM + r"])\s?" + _MONEY +
    r"(?:\s*(?:-|–|—|to)\s*[" + _CUR_SYM + r"]?\s?" + _MONEY + r")?"
)

# Currency symbol -> ISO code used for display/storage.
_CUR_CODE = {"$": "USD", "£": "GBP", "€": "EUR"}

# Period markers near a figure: annualization multiplier + a canonical label.
# Hourly 2080 = 40h*52w; weekly 52; monthly 12; annual 1. The FIRST matching
# marker in the surrounding context wins (checked most-specific-first).
_PERIOD_CTX = [
    ("hour",  2080.0, re.compile(r"/\s?hr\b|/\s?hour\b|\bper\s?hour\b|\bhourly\b|\ban\s?hour\b", re.I)),
    ("week",    52.0, re.compile(r"/\s?wk\b|/\s?week\b|\bper\s?week\b|\bweekly\b|\ba\s?week\b", re.I)),
    ("month",   12.0, re.compile(r"/\s?mo\b|/\s?month\b|\bper\s?month\b|\bmonthly\b|\ba\s?month\b", re.I)),
    ("year",     1.0, re.compile(r"/\s?yr\b|/\s?year\b|\bper\s?year\b|\bannual(?:ly)?\b|\ba\s?year\b|\bp\.?a\.?\b", re.I)),
]


def _period_of(ctx: str) -> tuple[str, float]:
    """(label, annualize_multiplier) for the pay period named near a figure.
    Defaults to ('year', 1.0) when no marker is present (a bare 5-6 digit figure
    is almost always an annual salary)."""
    for label, mult, pat in _PERIOD_CTX:
        if pat.search(ctx):
            return label, mult
    return "year", 1.0


def _raw_money(tok: Optional[str]) -> Optional[float]:
    """'$165,000' / '95k' / '45.50' -> a raw float in its OWN period (no
    annualization, no bounds), or None if non-numeric."""
    if not tok:
        return None
    t = tok.lower().replace(",", "").strip()
    mult = 1000.0 if t.endswith("k") else 1.0
    t = t.rstrip("k").strip()
    try:
        return float(t) * mult
    except ValueError:
        return None


def _annualize(raw: Optional[float], mult: float) -> Optional[float]:
    """Annualize a raw figure and sanity-bound it. The floor is context-aware: a
    sub-annual period (hourly/weekly/monthly) annualizes to a lower legitimate
    floor (~15k, min-wage tier) than a stated annual salary (30k), so retail /
    food-service / PRN wages stop being invisible. Upper bound 500k."""
    if raw is None:
        return None
    val = raw * mult
    floor = 15_000 if mult > 1.0 else 30_000
    return val if floor <= val <= 500_000 else None


def _parse_money(tok: Optional[str], hourly: bool = False) -> Optional[float]:
    """Back-compat shim (used by tests / callers): '$165,000' / '95k' / '45.50' ->
    annual dollars or None, with the original 30k-500k bound. A bare small value is
    annualized ONLY under an explicit hourly context."""
    raw = _raw_money(tok)
    if raw is None:
        return None
    if hourly and raw < 200:
        val = raw * 2080
        return val if 15_000 <= val <= 500_000 else None
    return raw if 30_000 <= raw <= 500_000 else None


# Fallback for pay ranges printed WITHOUT a leading currency symbol: either
# comma-grouped 5-6 digit numbers ("Pay range: 120,000 - 150,000") or a bare
# k-range ("80k-100k"). Both endpoints required so a lone figure / "401(k)" can't
# trigger it; the annualization bound is the final guard.
_SALARY_RE_BARE = re.compile(
    r"(\d{2,3},\d{3}|\d{2,3}\s?[kK])\s*(?:-|–|—|to)\s*(\d{2,3},\d{3}|\d{2,3}\s?[kK])"
)

# Kept for external callers that imported these context regexes.
_HOURLY_CTX = _PERIOD_CTX[0][2]
_NON_SALARY_CTX = re.compile(
    r"\bstipend\b|\bgift\s?card\b|\binsurance\b|401\s?\(?k\)?|\breimburs\w*|"
    r"\brelocation\b|\bper diem\b|\ballowance\b|\bsign[- ]?on\b|"
    # Incentive pay (bonus / commission / signing bonus) is NOT base salary: a
    # body like "Base is competitive. Plus up to $2,500/month bonus" must not
    # annualize the bonus figure and hard-drop a legit role past a salary floor.
    r"\bbonus\b|\bcommissions?\b|\bsigning\s+bonus\b", re.I)


def parse_comp(text: str) -> Optional[dict]:
    """Rich compensation parse of free text. Returns::

        {"min": float|None, "max": float|None,          # ANNUALIZED
         "raw_min": float|None, "raw_max": float|None,   # in the native period
         "currency": "USD"|"GBP"|"EUR", "period": "year"|"hour"|"week"|"month"}

    or None when nothing usable is found. Conservative: a figure in a clearly
    non-salary context (stipend/401k/insurance/...) is skipped; ambiguous input
    yields None. min/max are annualized (USD-or-native amount * period multiplier)
    for scoring; raw_min/raw_max keep the disclosed period figure for display."""
    text = text or ""
    for m in _SALARY_RE.finditer(text):
        ctx = text[max(0, m.start() - 30): m.end() + 30]
        if _NON_SALARY_CTX.search(ctx):
            continue
        currency = _CUR_CODE.get(m.group(1), "USD")
        period, mult = _period_of(ctx)
        rlo, rhi = _raw_money(m.group(2)), _raw_money(m.group(3))
        alo, ahi = _annualize(rlo, mult), _annualize(rhi, mult)
        if alo and ahi:
            lo_pair, hi_pair = sorted([(alo, rlo), (ahi, rhi)])
            return {"min": lo_pair[0], "max": hi_pair[0],
                    "raw_min": lo_pair[1], "raw_max": hi_pair[1],
                    "currency": currency, "period": period}
        if alo:
            return {"min": alo, "max": None, "raw_min": rlo, "raw_max": None,
                    "currency": currency, "period": period}
    # No currency-anchored hit -> bare comma/k range (USD, annual assumed).
    for m in _SALARY_RE_BARE.finditer(text):
        ctx = text[max(0, m.start() - 30): m.end() + 30]
        if _NON_SALARY_CTX.search(ctx):
            continue
        period, mult = _period_of(ctx)
        rlo, rhi = _raw_money(m.group(1)), _raw_money(m.group(2))
        alo, ahi = _annualize(rlo, mult), _annualize(rhi, mult)
        if alo and ahi:
            lo_pair, hi_pair = sorted([(alo, rlo), (ahi, rhi)])
            return {"min": lo_pair[0], "max": hi_pair[0],
                    "raw_min": lo_pair[1], "raw_max": hi_pair[1],
                    "currency": "USD", "period": period}
    return None


def salary_from_text(text: str) -> tuple[Optional[float], Optional[float]]:
    """Best-effort (min, max) ANNUAL salary parsed from free text (back-compat
    contract). Delegates to parse_comp and returns just the annualized pair, so
    every existing caller keeps working while gaining hourly/weekly/monthly and
    bare-k parsing. Currency/period detail is available via parse_comp."""
    comp = parse_comp(text)
    if comp is None:
        return (None, None)
    return (comp["min"], comp["max"])


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


def _title_context_cap(t: float, tl: str, desc: str, queries,
                       context_required) -> tuple[float, bool]:
    """Item 5 (opt-in title-family disambiguation): when a whole-query title match
    is on an ambiguous head term ("engagement manager" -> consulting vs AWS/CSM),
    require a domain-context token (e.g. "consulting","strategy","advisory") to
    co-occur in the title or description; otherwise cap title credit to 0.6.

    Returns (title_score, capped?). Only ever LOWERS a full match; a match that has
    context, or a profile with no context_required list, is untouched. This is the
    cheap local half-measure from review-ranking.md §4 -- the real fix stays the
    BYO-AI Fit pass, but a keyless consultant no longer sees 5 unrelated 94s."""
    ctx = [c.lower().strip() for c in (context_required or []) if c and c.strip()]
    if not ctx:
        return t, False
    blob = f"{tl} {(desc or '').lower()}"
    if any(_term_pattern(c).search(blob) for c in ctx):
        return t, False   # domain context present -> genuine match, full credit
    return min(t, 0.6), True


# First "City, ST" (US 2-letter state) named in free text -> the ST, uppercased.
_CITY_STATE_RE = re.compile(r"\b[A-Z][A-Za-z.\-]+(?:\s+[A-Z][A-Za-z.\-]+)*,\s*([A-Z]{2})\b")
_US_STATES_UP = frozenset({
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT",
    "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
})


def _first_us_state(text: str) -> Optional[str]:
    """The 2-letter US state of the first 'City, ST' in text, or None."""
    for m in _CITY_STATE_RE.finditer(text or ""):
        st = m.group(1).upper()
        if st in _US_STATES_UP:
            return st
    return None


def _all_us_states(text: str) -> set:
    """Every distinct 2-letter US state named as 'City, ST' in text."""
    out = set()
    for m in _CITY_STATE_RE.finditer(text or ""):
        st = m.group(1).upper()
        if st in _US_STATES_UP:
            out.add(st)
    return out


def _label_city(label: str) -> Optional[str]:
    """The bare CITY of the label (the text before its FIRST comma), or None when
    the label carries no US-state 'City, ST' pair. Used to confirm a genuinely-
    local role whose body names the home city in bare prose without its state
    abbrev ('based in Cincinnati' for a 'Cincinnati, OH' label)."""
    if not _first_us_state(label):
        return None
    head = (label or "").split(",", 1)[0].strip()
    return head or None


def _location_contradicts(label: str, desc: str, target: str) -> bool:
    """Item 4: True when the source LABEL state is contradicted by the body -- the
    Adzuna 'stamp the query metro' family (a Butte, MT role labeled 'Seattle, King
    County'). Deliberately conservative to protect the wide net:

    - the label must carry a US state AND echo the search target's state (a query
      echo is exactly the mislabel we distrust);
    - the body must name a state, that state must differ from the label, AND the
      label's own state must appear NOWHERE in the body. A posting whose body
      confirms the label metro anywhere (multi-office / 'HQ in X supports this Y
      role') is trusted -> False.

    A remote label or an un-parseable body -> False (kept). Never hard-drops -- the
    caller only caps the 15%-weight location component."""
    if "remote" in (label or "").lower():
        return False
    label_st = _first_us_state(label)
    if not label_st:
        return False
    target_st = _first_us_state(target) or ""
    if target_st and label_st != target_st:
        return False   # label doesn't echo the query metro -> don't distrust it
    body_states = _all_us_states(desc)
    if not body_states or label_st in body_states:
        return False   # body confirms the label state somewhere -> trust it
    # A JD body routinely writes the home city as bare prose ("based in
    # Cincinnati") while naming other plants/travel as 'City, ST'. That is
    # confirmation too: if the label's own CITY appears (word-boundary) in the
    # body, trust the label even though its state wasn't literally re-stated.
    label_city = _label_city(label)
    if label_city and re.search(r"\b" + re.escape(label_city) + r"\b", desc or "", re.I):
        return False   # body names the label's home city in bare prose -> trust it
    return True        # body names only OTHER state(s) -> contradiction


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
    remote_ok: bool = True,
    queries: Optional[list] = None,
    target_level: Optional[int] = None,
    semantic_profile: Optional[str] = None,
    seniority_target: Optional[str] = None,
    years_cap: Optional[int] = None,
    remote_regions_ok: bool = False,
    title_context_required: Optional[Iterable[str]] = None,
) -> tuple[int, str]:
    """Return (score 0-100, short breakdown string).

    `queries` may be pre-parsed (score_jobs parses once and reuses across the
    batch); when None they are parsed from `keywords` as before — identical
    result, just avoids re-parsing the same keywords for every job.

    `seniority_target`/`years_cap` (from the project config) drive a bounded local
    down-nudge on postings that OVERSHOOT the target (P0-3 honesty fix). Both
    default None -> a profile that set no seniority_target scores byte-identical.
    `remote_regions_ok` (default False) is the escape hatch for a user who can
    genuinely take non-US-only remote roles -> the country-blind-remote location
    cap is skipped. `title_context_required` (default None/empty) is an opt-in
    per-profile disambiguation list; when set, an ambiguous title head term keeps
    full credit only if a context token co-occurs -> unset profiles unchanged.
    """
    if skill_terms is None:
        skill_terms = extract_skill_terms()
    if exclude_titles is None:
        exclude_titles = DEFAULT_EXCLUDE_TITLES
    if title_miss_penalty is None:
        title_miss_penalty = DEFAULT_TITLE_MISS_PENALTY
    if seniority_exclude is None:
        seniority_exclude = DEFAULT_SENIORITY_EXCLUDE

    # Recover pay ranges printed in the description when the API fields are
    # empty (fills the GUI salary column too, via salary_display()). Intentional
    # in-place mutation: the GUI salary column reads job.salary_min/max. Guarded
    # to only fill when BOTH are None, so it is idempotent -- re-scoring the same
    # job never compounds or overwrites a recovered value.
    if job.salary_min is None and job.salary_max is None and job.description:
        lo, hi = salary_from_text(job.description)
        if lo or hi:
            job.salary_min, job.salary_max = lo, hi

    tl = (job.title or "").lower()
    if queries is None:
        queries = [query.parse(kw) for kw in keywords if kw]
    title_hit = any(q.matches(tl) for q in queries)  # full boolean (honors NOT)
    t = _title_score(queries, tl)                     # graded positive overlap
    # Item 5 (opt-in): an ambiguous title head term ("engagement manager") keeps
    # full title credit only if a required context token co-occurs in title/desc.
    # Default (no title_context_required) -> byte-identical.
    title_ctx_capped = False
    if title_context_required and t >= 1.0:
        t, title_ctx_capped = _title_context_cap(
            t, tl, job.description or "", queries, title_context_required)
    k = _skill_score(job.description, skill_terms)
    s = _salary_score(job, salary_floor)
    loc_raw = _location_score(job.location, location, remote_ok=remote_ok,
                              remote_regions_ok=remote_regions_ok)
    l = min(loc_raw / 3.0, 1.0)  # 3+ token hits = full marks
    # Item 4 (location-label distrust): Adzuna stamps the query metro on postings,
    # so an out-of-state role is labeled the target and earns full location credit.
    # When the label's state and a DIFFERENT state named in the body confidently
    # contradict, cap location credit + flag. Never hard-drops (best-effort parse).
    loc_unverified = False
    if l > 0.5 and _location_contradicts(job.location or "", job.description or "", location):
        l = min(l, 0.34)
        loc_unverified = True
    r = _recency_score(job.created)

    # Optional local semantic-similarity component (match/semantic.py). Compares
    # the candidate profile to the job's title+description via a small local
    # embedding. m is None (abstains) unless semantic ranking is enabled, the
    # model loaded, and both texts exist -> then it's a present component; else
    # the score is byte-identical to the keyword-only scorer.
    m = None
    if semantic_profile:
        try:
            from match import semantic
            job_text = f"{job.title or ''} {job.description or ''}".strip()
            m = semantic.similarity(semantic_profile, job_text)
        except Exception:
            m = None

    # Semantic veto of generic-token full title matches: when semantic ranking is
    # ACTIVE (m is not None) and the profile<->job similarity is very low, a full
    # keyword title match (e.g. a QA role earning title-100% for "automation
    # engineer") is treated as generic-token noise and the title component is
    # capped. Abstain-safe: m is None whenever semantic is off / model absent /
    # texts missing, so the keyword-only score stays byte-identical.
    title_capped = False
    if m is not None:
        import config as _cfg
        veto = getattr(_cfg, "SEMANTIC_TITLE_VETO_SIM", 0.35)
        cap = getattr(_cfg, "SEMANTIC_TITLE_CAP", 0.6)
        if m < veto and t > cap:
            t = cap
            title_capped = True

    # Weight-renormalization over data-PRESENT components. Title + location are
    # always present; skill/salary/recency emit a neutral 0.5 when their data is
    # missing, which used to inflate data-poor jobs. Drop the missing components'
    # weight and spread the freed 100 total proportionally over present ones, so
    # a job is judged only on what we actually know about it.
    skill_present = bool(skill_terms) and bool((job.description or "").strip())
    salary_present = bool(salary_floor) and (job.salary_max or job.salary_min) is not None
    recency_present = _parse_created(job.created) != _EPOCH
    sem_present = m is not None
    present = 2 + skill_present + salary_present + recency_present  # title+loc always

    base_w = {"t": 35, "k": 25, "s": 15, "l": 15, "r": 10, "m": SEM_WEIGHT}
    active = {"t": True, "l": True, "k": skill_present,
              "s": salary_present, "r": recency_present, "m": sem_present}
    live_total = sum(base_w[c] for c, on in active.items() if on)
    scale = 100.0 / live_total
    score = (
        base_w["t"] * scale * t
        + (base_w["k"] * scale * k if skill_present else 0.0)
        + (base_w["s"] * scale * s if salary_present else 0.0)
        + base_w["l"] * scale * l
        + (base_w["r"] * scale * r if recency_present else 0.0)
        + (base_w["m"] * scale * m if sem_present else 0.0)
    )

    # Confidence shrinkage (P2): renormalization can push a 2-of-5-component job to
    # 100, so a title-only match outranks a data-rich 92. Damp the distance from 50
    # by how much data we actually have (present/5): a full-data job is untouched
    # (factor 1.0), a title+loc-only job's spread shrinks to 0.82. This keeps the
    # composite HONEST -- data-poor extremes pull toward the neutral midpoint -- so
    # title-only 100s no longer outrank data-rich 92s. The breakdown/notes stay
    # truthful: components are reported as-computed; only the aggregate is damped.
    conf_factor = 0.7 + 0.3 * (present / 5.0)
    score = 50.0 + (score - 50.0) * conf_factor

    # Company-size modifier from the careers boards' total-postings proxy.
    size_adj = 0
    bc = getattr(job, "board_count", -1)
    if bc >= 0:
        if bc <= 30:
            size_adj = 8      # small shop
        elif bc <= 100:
            size_adj = 4      # mid-size
        elif bc <= 250:
            size_adj = -2     # large board (was a silent dead zone)
        else:
            size_adj = -6     # mega board
    score += size_adj

    notes_extra = []
    if title_capped:
        notes_extra.append("sem-title-cap")
    if title_ctx_capped:
        notes_extra.append("title-context-cap")
    if loc_unverified:
        notes_extra.append("loc-unverified")

    # Target-level fit: nudge roles toward the user's target seniority when they
    # are explicitly targeting management/exec. Neutral for IC/senior searches.
    sen_adj = _seniority_fit_adj(job.title or "", target_level)
    if sen_adj:
        score += sen_adj
        notes_extra.append(f"level {sen_adj:+d}")

    # P0-3 honesty: down-nudge a posting that OVERSHOOTS the config's explicit
    # seniority_target (Sr./II·III/IV/8+ YOE), so a keyless user's inbox stops
    # tying an over-leveled role with a plain entry title. OFF (byte-identical)
    # unless seniority_target is set. Applied after (and independent of) the
    # exec-branch adjustment above.
    target_ord = _target_ord_of(seniority_target)
    st_adj, st_level = _seniority_target_adj(
        job.title or "", job.description or "", target_ord, years_cap)
    if st_adj:
        score += st_adj
        notes_extra.append(f"over-target({st_level}) {st_adj:+d}")

    # Relevance gate: the title satisfies no search query (positive miss, or a
    # NOT term present). Penalty scales with the graded overlap t -- a true zero
    # (t=0) takes the full hit, a near-miss (high t) is penalized lightly so a
    # "Process Controls Specialist" no longer craters like an unrelated title.
    if queries and not title_hit:
        miss_pen = round(title_miss_penalty * (1 - t))
        score -= miss_pen
        notes_extra.append(f"title-miss -{miss_pen}")

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
        if b and _term_pattern(b).search(blob):
            score -= 30
            penalties.append(b)

    score = int(max(0, min(100, round(score))))
    # #38: only report the "skills" component when skill data was actually
    # present (skill_present -- same gate the renormalization already uses to
    # exclude its weight from the composite). A thin/malformed resume with no
    # skill_terms contributes 0.0 to the score (verified above), but previously
    # the notes string still always printed "skills 50%" -- implying a real
    # neutral MEASUREMENT rather than "no data to measure," which is dishonest
    # about data-presence and would render a misleading "Skills 50%" chip in the
    # GUI scorecard (score_breakdown parses whatever tokens are present). Mirrors
    # how "sem" is already conditionally appended only when sem_present. A
    # rich-resume profile (skill_present True, e.g. Alex's eng profile) is
    # completely unaffected -- the token still always appears (parity).
    notes = f"title {t:.0%}"
    if skill_present:
        notes += f" | skills {k:.0%}"
    notes += f" | salary {s:.0%} | loc {l:.0%} | new {r:.0%}"
    if sem_present:
        notes += f" | sem {m:.0%}"
    notes += f" | conf {present}/5"
    if size_adj:
        notes += f" | size {size_adj:+d} ({bc} on board)"
    for ne in notes_extra:
        notes += f" | {ne}"
    if penalties:
        notes += f" | PENALTY: {', '.join(penalties)}"
    return score, notes


# --- Structured breakdown of the score_notes string (for the GUI scorecard) ---
# score_job emits a fixed, parseable notes string; rather than change its return
# signature (and every caller), parse that string into a structured dict the GUI
# can render as labeled chips/bars. Pure and forgiving: unknown/missing tokens
# are skipped, so it never throws on an old or partial notes string.
_COMPONENT_META = [
    ("title", "Title", 35), ("skills", "Skills", 25), ("salary", "Salary", 15),
    ("loc", "Location", 15), ("new", "Recency", 10), ("sem", "Semantic", SEM_WEIGHT),
]
_BD_PCT_RE = re.compile(r"^(title|skills|salary|loc|new|sem)\s+(-?\d+)%$")
_BD_CONF_RE = re.compile(r"^conf\s+(\d+)/(\d+)$")
_BD_SIZE_RE = re.compile(r"^size\s+([+-]\d+)\s+\((-?\d+) on board\)$")
_BD_PEN_RE = re.compile(r"^(.*?)\s+(-\d+)$")


def score_breakdown(notes: str) -> dict:
    """Parse a score_notes string (as built by score_job) into a structured
    breakdown for display: weighted components, confidence (present/total),
    company-size modifier, and penalties. Returns:

        {"components": [{"key","label","pct","weight"}, ...],
         "confidence": {"present": int, "total": int} | None,
         "size_adj": int | None, "board_count": int | None,
         "penalties": [{"label": str, "value": int}, ...]}
    """
    labels = {k: lbl for k, lbl, _ in _COMPONENT_META}
    weights = {k: w for k, _, w in _COMPONENT_META}
    out = {"components": [], "confidence": None, "size_adj": None,
           "board_count": None, "penalties": []}
    for tok in (notes or "").split("|"):
        tok = tok.strip()
        if not tok:
            continue
        m = _BD_PCT_RE.match(tok)
        if m:
            key = m.group(1)
            out["components"].append({"key": key, "label": labels[key],
                                      "pct": int(m.group(2)) / 100.0,
                                      "weight": weights[key]})
            continue
        m = _BD_CONF_RE.match(tok)
        if m:
            out["confidence"] = {"present": int(m.group(1)), "total": int(m.group(2))}
            continue
        m = _BD_SIZE_RE.match(tok)
        if m:
            out["size_adj"] = int(m.group(1))
            out["board_count"] = int(m.group(2))
            continue
        if tok.startswith("PENALTY:"):
            for kw in tok[len("PENALTY:"):].split(","):
                kw = kw.strip()
                if kw:
                    out["penalties"].append({"label": kw, "value": -30})
            continue
        m = _BD_PEN_RE.match(tok)  # title-miss -12 | excl-title(ai) -45 | seniority(sr) -20
        if m:
            out["penalties"].append({"label": m.group(1).strip(),
                                     "value": int(m.group(2))})
    return out


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
    remote_ok: bool = True,
    seniority_target: Optional[str] = None,
    years_cap: Optional[int] = None,
    remote_regions_ok: bool = False,
    title_context_required: Optional[Iterable[str]] = None,
) -> list[JobResult]:
    """Score in place and return the same list sorted best-first.

    `seniority_target`/`years_cap`/`remote_regions_ok`/`title_context_required` are
    the S32 honesty levers; all default to their neutral values so a profile that
    sets none of them scores byte-identically to before (proved in tests)."""
    terms = extract_skill_terms()
    kws = list(keywords)
    # Parse the queries once for the whole batch instead of re-parsing the same
    # keywords inside every score_job call (SCORE-8).
    queries = [query.parse(kw) for kw in kws if kw]
    # Derive the target seniority once from the user's own target keywords; passed
    # to every score_job so target-level roles can outrank clearly-below ones.
    # None / below-manager => no adjustment (IC + engineering searches unchanged).
    target_level = _target_level(kws)
    # Freeze the context list once so every job sees the same (avoids re-iterating a
    # generator to empty after the first job).
    ctx_req = list(title_context_required) if title_context_required else None
    # Resolve the candidate profile text ONCE (only when semantic ranking is
    # actually available), so the model is warmed once and the profile embedding
    # is cached across the batch. None -> the semantic component abstains.
    semantic_profile = None
    try:
        from match import semantic
        if semantic.available():
            semantic_profile = profile_text() or None
    except Exception:
        semantic_profile = None
    for job in jobs:
        job.score, job.score_notes = score_job(
            job, keywords=kws, location=location,
            salary_floor=salary_floor, skill_terms=terms,
            exclude_keywords=exclude_keywords, exclude_titles=exclude_titles,
            title_miss_penalty=title_miss_penalty, seniority_exclude=seniority_exclude,
            remote_ok=remote_ok, queries=queries, target_level=target_level,
            semantic_profile=semantic_profile,
            seniority_target=seniority_target, years_cap=years_cap,
            remote_regions_ok=remote_regions_ok, title_context_required=ctx_req,
        )
    jobs.sort(key=lambda j: j.score, reverse=True)
    return jobs
