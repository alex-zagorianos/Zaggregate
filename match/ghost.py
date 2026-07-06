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
  4) Expired validThrough — the posting's own schema.org publisher-declared
     expiry (JobResult.valid_through / inbox extras) is in the PAST. This is
     attested, not inferred, so it's the strongest single signal.

Repost/evergreen (C1): historically abstained because freshness kept no history.
search.freshness now persists a per-key presence history and exposes repost_info
({job_key: {'first_seen', 'repost', 'evergreen'}}). When the caller threads that
map in (optional; default None = abstain, exactly today's behavior), a job whose
job_key is flagged repost=True or evergreen=True gets a bump with a clear reason
('reposted' / 'evergreen listing'). The signal STILL abstains for any job not in
the map, so a source without history is never penalized.

Levels by final score: <30 fresh, 30-59 aging, >=60 stale. "unknown" is reserved
for the genuine no-signal case: ``created`` missing/unparseable AND no other
signal fired — there we report a low score (~15) and level "unknown" so the view
can show "no staleness signal" rather than a false "fresh".

Deterministic, no I/O, no network, stdlib only.
"""
import re
from datetime import datetime, timezone

from dateparse import parse_flex_iso

# ── tuning (all in "ghost points") ────────────────────────────────────────────
AGE_STRONG_DAYS = 45      # older than this = strong staleness bump
AGE_MILD_DAYS = 30        # 30-45 days = mild bump
AGE_FRESH_DAYS = 14       # <= this = genuinely fresh, small negative

AGE_STRONG_BUMP = 62      # >45 days alone clears the 60 "stale" line
AGE_MILD_BUMP = 35
AGE_FRESH_BUMP = -15      # fresh dated jobs pull the score down

MISSING_SALARY_BUMP = 12
EVERGREEN_BUMP = 62       # a perpetual-req title alone reads "stale"
EXPIRED_BUMP = 80         # publisher-declared validThrough in the past = strongest
                          # single signal; alone it clears "stale" decisively

# Repost/evergreen from persisted freshness history (C1). A history-attested
# reappearance is a strong staleness signal (the req keeps getting re-listed); a
# posting whose cumulative presence spans >90 days is a perpetual/evergreen req.
REPOST_BUMP = 45          # seen -> gone -> seen again: bump but below "expired"
EVERGREEN_HISTORY_BUMP = 62  # 90+ days of presence reads "stale" on its own

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

# Shares its parse loop with search.search_engine._parse_created via the
# stdlib-only dateparse.parse_flex_iso helper (finding #9) -- both derive the
# same tolerance (ISO with/without tz, ``Z`` suffix, or date-only). Importing
# ``dateparse`` keeps this module free of any search/scraper import chain
# (dateparse itself only imports ``datetime``).
_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


def _parse_created(value):
    """Parse a heterogeneous source date string into an aware datetime.
    Empty / unparseable -> ``_EPOCH`` (the caller treats that as 'no date')."""
    if not value or not isinstance(value, str):
        return _EPOCH
    return parse_flex_iso(value) or _EPOCH


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


def _extras_get(job, key):
    """Read a key from an inbox-row dict's `extras` JSON blob (where schema-free
    fields like valid_through are stored). None for JobResults / no extras."""
    if not isinstance(job, dict):
        return None
    raw = job.get("extras")
    if not raw:
        return None
    try:
        import json
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return None
    return data.get(key) if isinstance(data, dict) else None


def _expired_signal(job, reasons):
    """Strong bump when the posting's publisher-declared expiry (schema.org
    validThrough, carried on JobResult.valid_through or inbox-row extras) is in the
    PAST. Publisher-attested, not inferred -> the most reliable ghost marker.
    Abstains when validThrough is missing/unparseable or still in the future."""
    vt = (_get(job, "valid_through") or _get(job, "validThrough")
          or _extras_get(job, "valid_through"))
    dt = _parse_created(vt)
    if dt == _EPOCH:
        return 0, False
    days_past = (datetime.now(timezone.utc) - dt).days
    if days_past > 0:
        reasons.append(f"listing expired {days_past}d ago (validThrough)")
        return EXPIRED_BUMP, True
    return 0, False  # expiry still in the future -> no opinion here


def _evergreen_signal(job, reasons):
    """Strong bump for perpetual-req / pipeline title patterns."""
    title = (_get(job, "title") or "").lower()
    for pat in _EVERGREEN_PATTERNS:
        if pat in title:
            reasons.append(f"evergreen/pipeline title ('{pat}')")
            return EVERGREEN_BUMP, True
    return 0, False


def _repost_signal(job, reasons, repost_info):
    """History-attested repost/evergreen bump (C1). Abstains unless a repost_info
    map is threaded in AND this job's job_key is in it. Reads job_key off a
    JobResult attr or an inbox-row dict."""
    if not repost_info:
        return 0, False
    jk = _get(job, "job_key")
    if not jk:
        return 0, False
    info = repost_info.get(jk)
    if not isinstance(info, dict):
        return 0, False
    pts = 0
    fired = False
    if info.get("evergreen"):
        reasons.append("evergreen listing")
        pts += EVERGREEN_HISTORY_BUMP
        fired = True
    if info.get("repost"):
        reasons.append("reposted")
        pts += REPOST_BUMP
        fired = True
    return pts, fired


def _level_for(score, any_signal):
    """fresh < 30 <= aging < 60 <= stale; 'unknown' only when nothing fired."""
    if not any_signal:
        return "unknown"
    if score >= 60:
        return "stale"
    if score >= 30:
        return "aging"
    return "fresh"


def _ghost_score_uncached(job, repost_info=None):
    """The real computation, unwrapped from the cache. See :func:`ghost_score`."""
    reasons: list[str] = []

    age_pts, age_fired = _age_signal(job, reasons)
    sal_pts, sal_fired = _missing_salary_signal(job, reasons)
    evg_pts, evg_fired = _evergreen_signal(job, reasons)
    exp_pts, exp_fired = _expired_signal(job, reasons)
    rep_pts, rep_fired = _repost_signal(job, reasons, repost_info)

    any_signal = age_fired or sal_fired or evg_fired or exp_fired or rep_fired

    if not any_signal:
        # No date and no other signal: report the abstain case, not a false fresh.
        return {"score": UNKNOWN_BASE, "level": "unknown",
                "reasons": ["no staleness signal available"]}

    raw = age_pts + sal_pts + evg_pts + exp_pts + rep_pts
    score = int(max(0, min(100, round(raw))))
    level = _level_for(score, any_signal=True)
    return {"score": score, "level": level, "reasons": reasons}


# The exact set of job fields ``_ghost_score_uncached`` reads (via ``_get`` /
# ``_extras_get``), enumerated so the cache key can't silently miss a signal a
# future edit adds to the scoring functions above: created (age), title
# (missing-salary gate + evergreen pattern), salary_min/salary_max/salary_text
# (missing-salary), valid_through/validThrough + the same key inside the
# ``extras`` JSON blob (expired). ``job_key`` is deliberately EXCLUDED — it only
# matters when ``repost_info`` is passed, and that path always bypasses the cache
# (see ``ghost_score`` below).
_GHOST_KEY_FIELDS = (
    "created", "title", "salary_min", "salary_max", "salary_text",
    "valid_through", "validThrough",
)


def _today_ordinal() -> int:
    """Today's UTC day number — a seam so tests can roll the clock."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).date().toordinal()


def _ghost_cache_key(job):
    """A hashable tuple of every ghost-relevant field on ``job`` (JobResult attr or
    inbox-row dict), or ``None`` when ``job`` can't be safely keyed (unhashable
    field value, e.g. a non-JSON-string ``extras`` dict) — the caller then skips
    the cache entirely rather than risk a stale/incorrect hit.

    The key includes TODAY'S UTC day ordinal: the age/expiry signals depend on
    wall-clock time (``datetime.now() - created``), so an entry cached from
    immutable row fields alone would freeze a row's staleness level for the
    whole process lifetime (review-confirmed — a --desktop window left open for
    weeks would never see a row cross the 30/45-day aging thresholds). Day
    granularity matches the signals' own day-based thresholds; stale day-keyed
    entries age out via the existing size bound."""
    try:
        values = tuple(_get(job, name) for name in _GHOST_KEY_FIELDS)
        extras = job.get("extras") if isinstance(job, dict) else None
        # extras is normally a JSON string (hashable) on a real inbox row; only
        # hash it directly when it's already a plain hashable scalar/string, else
        # fall back to the parsed valid_through field alone (still exact for the
        # signal that reads extras) so a dict-shaped extras never blows up hash().
        if isinstance(extras, dict):
            extras_key = ("valid_through", extras.get("valid_through"))
        else:
            extras_key = extras
        key = (type(job).__name__, _today_ordinal()) + values + (extras_key,)
        hash(key)
    except TypeError:
        return None
    return key


# key -> result cache. A plain dict (not `functools.lru_cache`) because the
# VALUE we need to return alongside a hit is the freshly-recomputed dict itself
# — lru_cache would require re-deriving `job` from the hashable `key` to call the
# real computation on a miss, which is exactly the coupling this avoids. Bounded
# manually (see `_ghost_cached`) to the same maxsize contract an lru_cache gives.
_GHOST_CACHE: dict[tuple, dict] = {}
_GHOST_CACHE_MAXSIZE = 4096
_ghost_cache_hits = 0  # test-observable counter, not part of the public API


def _ghost_cached(key, job):
    """Cache slot keyed on :func:`_ghost_cache_key`'s tuple. Only ever called on
    the ``repost_info=None`` path (see ``ghost_score``), so the key need not
    encode it. Returns the cached (or freshly-computed + stored) dict; the caller
    is responsible for copying it before handing it to anyone."""
    global _ghost_cache_hits
    hit = _GHOST_CACHE.get(key)
    if hit is not None:
        _ghost_cache_hits += 1
        return hit
    result = _ghost_score_uncached(job)
    if len(_GHOST_CACHE) >= _GHOST_CACHE_MAXSIZE:
        # Bounded, not LRU-precise: drop one arbitrary entry (dict insertion
        # order -> oldest) rather than let a long-lived process grow unbounded.
        _GHOST_CACHE.pop(next(iter(_GHOST_CACHE)))
    _GHOST_CACHE[key] = result
    return result


def ghost_score(job, repost_info=None):
    """Offline stale/ghost likelihood for a JobResult OR an inbox-row dict.

    ``repost_info`` (optional; default None = abstain, today's behavior exactly)
    is search.freshness.repost_info()'s {job_key: {'first_seen','repost',
    'evergreen'}} map. When passed, a job whose job_key is flagged bumps the score
    with reasons 'reposted' / 'evergreen listing'. A job absent from the map (or a
    None map) contributes nothing - the signal abstains, never penalizes.

    Returns ``{"score": int 0..100, "level": "fresh"|"aging"|"stale"|"unknown",
    "reasons": list[str]}``. Pure, deterministic, never raises on missing fields.

    Bounded module-level cache (:data:`_ghost_cached`, ``maxsize=4096``): the
    computation is pure over a small set of fields, and the inbox list route can
    recompute it for the same rows on every request when ``hide_stale`` view
    filtering is on. Keyed on exactly the fields the signals read (enumerated in
    :data:`_GHOST_KEY_FIELDS`), so a changed field is a cache MISS, not a stale
    hit. ``repost_info`` bypasses the cache (it's an external mutable map, not
    part of the row) — that call shape still recomputes every time, matching
    pre-cache behavior exactly. A row that can't be safely keyed (unhashable
    field) also bypasses the cache rather than risk a wrong hit. The cached path
    always returns a COPY of the cached dict so a caller mutating its result
    (e.g. ``ats["lines"] = ...``-style enrichment elsewhere) can never poison a
    later call.
    """
    if repost_info is not None:
        return _ghost_score_uncached(job, repost_info)
    key = _ghost_cache_key(job)
    if key is None:
        return _ghost_score_uncached(job)
    result = _ghost_cached(key, job)
    # Always return a COPY: the cache stores one shared dict per key, and a
    # caller mutating its returned result (adding a key, editing `reasons`, ...)
    # must never leak that mutation into a later call for the same row. `reasons`
    # is itself a mutable list, so a shallow `dict(result)` alone isn't enough —
    # copy it too (one level deep is all `ghost_score`'s shape ever needs).
    out = dict(result)
    out["reasons"] = list(result["reasons"])
    return out
