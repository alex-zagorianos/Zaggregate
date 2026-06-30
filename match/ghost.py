"""Ghost / stale-posting likelihood — a pure OFFLINE advisory signal (0-100)
read off already-scraped fields, with zero API calls.

This is a VIEW-LEVEL hint surfaced next to a job ("this listing looks aged /
evergreen / likely dead"). It is deliberately kept OUT of the 0-100 match score
in match.scorer — match quality and liveness are orthogonal, and folding a
guess about staleness into relevance would silently bury good-fit jobs on a
data gap. Higher ghost score = more likely dead/evergreen/ghost.

Signals (additive, clamped 0..100):
  1) Posting age from ``created`` (ISO date, tz-tolerant). >45 days = strong
     bump, 30-45 = mild, <=14 = a small negative (genuinely fresh). An empty or
     unparseable date contributes NOTHING (abstains) — we never penalize a job
     for a source that simply doesn't expose a date.
  2) Missing salary — no salary_min AND no salary_max AND no '$' in salary_text
     (inbox rows) — a small bump; ghost/evergreen reposts often omit pay.
  3) Evergreen / pipeline title pattern ("always hiring", "talent community",
     "general application", ...) — a strong bump; these are perpetual reqs.

Repost-count is intentionally NOT implemented: freshness history isn't retained
yet, so there's nothing to read — the signal abstains rather than guess.

Levels by final score: <30 fresh, 30-59 aging, >=60 stale. "unknown" is reserved
for the genuine no-signal case: ``created`` missing/unparseable AND no other
signal fired — there we report a low score (~15) and level "unknown" so the view
can show "no staleness signal" rather than a false "fresh".

Deterministic, no I/O, no network, stdlib only.
"""
import re
from datetime import datetime, timezone

# ── tuning (all in "ghost points") ────────────────────────────────────────────
AGE_STRONG_DAYS = 45      # older than this = strong staleness bump
AGE_MILD_DAYS = 30        # 30-45 days = mild bump
AGE_FRESH_DAYS = 14       # <= this = genuinely fresh, small negative

AGE_STRONG_BUMP = 62      # >45 days alone clears the 60 "stale" line
AGE_MILD_BUMP = 35
AGE_FRESH_BUMP = -15      # fresh dated jobs pull the score down

MISSING_SALARY_BUMP = 12
EVERGREEN_BUMP = 62       # a perpetual-req title alone reads "stale"

UNKNOWN_BASE = 10         # score for the genuine no-signal case (kept below the
                          # smallest real signal so any fired signal outscores it)

# Evergreen / pipeline / "perpetual req" title markers (case-insensitive).
_EVERGREEN_PATTERNS = (
    "always hiring",
    "evergreen",
    "pipeline",
    "talent community",
    "talent network",
    "general application",
    "multiple openings",
    "future opportunities",
)

# Mirror of search.search_engine._parse_created: ISO with/without tz, ``Z``
# suffix, or date-only. Inlined (not imported) to keep this module stdlib-only
# and free of any search/scraper import chain.
_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


def _parse_created(value):
    """Parse a heterogeneous source date string into an aware datetime.
    Empty / unparseable -> ``_EPOCH`` (the caller treats that as 'no date')."""
    if not value or not isinstance(value, str):
        return _EPOCH
    s = value.strip().replace("Z", "+00:00")
    for candidate in (s, s[:19], s[:10]):
        try:
            dt = datetime.fromisoformat(candidate)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return _EPOCH


def _get(job, key):
    """Read ``key`` off either a JobResult (attr) or an inbox-row dict, returning
    None when absent. Never raises — every signal degrades to 'abstain'."""
    if job is None:
        return None
    if isinstance(job, dict):
        return job.get(key)
    return getattr(job, key, None)


def _age_signal(job, reasons):
    """Posting-age bump. Returns (points, fired) where ``fired`` is False when
    the date is missing/unparseable (the signal abstains entirely)."""
    dt = _parse_created(_get(job, "created"))
    if dt == _EPOCH:
        return 0, False
    age_days = max(0, (datetime.now(timezone.utc) - dt).days)
    if age_days > AGE_STRONG_DAYS:
        reasons.append(f"posted {age_days}d ago (stale)")
        return AGE_STRONG_BUMP, True
    if age_days >= AGE_MILD_DAYS:
        reasons.append(f"posted {age_days}d ago (aging)")
        return AGE_MILD_BUMP, True
    if age_days <= AGE_FRESH_DAYS:
        reasons.append(f"posted {age_days}d ago (fresh)")
        return AGE_FRESH_BUMP, True
    # 15-29 days: known date but no strong opinion either way.
    reasons.append(f"posted {age_days}d ago")
    return 0, True


def _missing_salary_signal(job, reasons):
    """Small bump when no pay is exposed anywhere (API fields or inbox text).

    Gated on a title being present: a row with no title isn't a real posting,
    so 'no salary' there is an empty-row artifact, not a staleness signal — we
    abstain instead, leaving the overall result 'unknown'."""
    if not (_get(job, "title") or "").strip():
        return 0, False
    smin = _get(job, "salary_min")
    smax = _get(job, "salary_max")
    salary_text = _get(job, "salary_text") or ""
    has_text_dollar = "$" in salary_text
    if smin is None and smax is None and not has_text_dollar:
        reasons.append("no salary disclosed")
        return MISSING_SALARY_BUMP, True
    return 0, False


def _evergreen_signal(job, reasons):
    """Strong bump for perpetual-req / pipeline title patterns."""
    title = (_get(job, "title") or "").lower()
    for pat in _EVERGREEN_PATTERNS:
        if pat in title:
            reasons.append(f"evergreen/pipeline title ('{pat}')")
            return EVERGREEN_BUMP, True
    return 0, False


def _level_for(score, any_signal):
    """fresh < 30 <= aging < 60 <= stale; 'unknown' only when nothing fired."""
    if not any_signal:
        return "unknown"
    if score >= 60:
        return "stale"
    if score >= 30:
        return "aging"
    return "fresh"


def ghost_score(job):
    """Offline stale/ghost likelihood for a JobResult OR an inbox-row dict.

    Returns ``{"score": int 0..100, "level": "fresh"|"aging"|"stale"|"unknown",
    "reasons": list[str]}``. Pure, deterministic, never raises on missing fields.
    """
    reasons: list[str] = []

    age_pts, age_fired = _age_signal(job, reasons)
    sal_pts, sal_fired = _missing_salary_signal(job, reasons)
    evg_pts, evg_fired = _evergreen_signal(job, reasons)

    any_signal = age_fired or sal_fired or evg_fired

    if not any_signal:
        # No date and no other signal: report the abstain case, not a false fresh.
        return {"score": UNKNOWN_BASE, "level": "unknown",
                "reasons": ["no staleness signal available"]}

    raw = age_pts + sal_pts + evg_pts
    score = int(max(0, min(100, round(raw))))
    level = _level_for(score, any_signal=True)
    return {"score": score, "level": level, "reasons": reasons}
