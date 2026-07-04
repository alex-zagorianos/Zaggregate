"""ghost_score: an OFFLINE, view-level "stale/ghost posting likelihood" signal
(0-100) derived only from already-scraped fields. NEVER folded into the match
score. Higher = more likely dead/evergreen/ghost.

Signals: posting age (job.created), missing salary, evergreen/pipeline title.
Accepts EITHER a JobResult or a plain inbox-row dict; reads fields defensively.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Make the real project root importable (models.py / match package) whether this
# runs from the worktree or the main checkout. conftest already does this for the
# main checkout; this guard covers an isolated worktree run too.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from match.ghost import ghost_score
from models import JobResult


def _iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()


def _job(**over) -> JobResult:
    base = dict(
        title="Controls Engineer",
        company="Acme",
        location="Cincinnati, OH",
        salary_min=120000.0,
        salary_max=150000.0,
        description="Build controls.",
        url="http://x/1",
        source_keyword="controls",
        created=_iso_days_ago(3),
        source_api="t",
    )
    base.update(over)
    return JobResult(**base)


# ── shape ─────────────────────────────────────────────────────────────────────
def test_returns_expected_shape():
    out = ghost_score(_job())
    assert set(out) == {"score", "level", "reasons"}
    assert isinstance(out["score"], int)
    assert 0 <= out["score"] <= 100
    assert out["level"] in {"fresh", "aging", "stale", "unknown"}
    assert isinstance(out["reasons"], list)
    assert all(isinstance(r, str) for r in out["reasons"])


# ── age signal ────────────────────────────────────────────────────────────────
def test_fresh_recent_job_is_fresh_low():
    out = ghost_score(_job(created=_iso_days_ago(3)))
    assert out["level"] == "fresh"
    assert out["score"] < 30


def test_sixty_day_old_job_is_stale_high():
    out = ghost_score(_job(created=_iso_days_ago(60)))
    assert out["level"] == "stale"
    assert out["score"] >= 60


def test_thirty_to_fortyfive_day_old_is_aging():
    out = ghost_score(_job(created=_iso_days_ago(37)))
    assert out["level"] == "aging"
    assert 30 <= out["score"] < 60


def test_created_empty_with_rest_present_no_crash_low_unknown():
    out = ghost_score(_job(created=""))
    # created missing AND no other signal fired -> unknown, low score
    assert out["level"] == "unknown"
    assert out["score"] <= 20


# ── validThrough (publisher-attested expiry) signal ────────────────────────────
def _iso_days_ahead(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).date().isoformat()


def test_expired_validthrough_is_stale():
    # A fresh posting date but a validThrough in the past -> stale (expiry wins).
    out = ghost_score(_job(created=_iso_days_ago(2), valid_through=_iso_days_ago(5)))
    assert out["level"] == "stale"
    assert out["score"] >= 60
    assert any("expired" in r for r in out["reasons"])


def test_future_validthrough_does_not_fire():
    out = ghost_score(_job(created=_iso_days_ago(2), valid_through=_iso_days_ahead(20)))
    assert out["level"] == "fresh"        # only the fresh-age signal fired
    assert not any("expired" in r for r in out["reasons"])


def test_expired_validthrough_via_inbox_dict():
    row = {"title": "RN", "valid_through": _iso_days_ago(10)}
    out = ghost_score(row)
    assert out["level"] == "stale"


def test_missing_validthrough_abstains():
    out = ghost_score(_job(created=_iso_days_ago(3), valid_through=""))
    assert not any("expired" in r for r in out["reasons"])


def test_created_unparseable_does_not_crash():
    out = ghost_score(_job(created="not-a-date"))
    assert out["level"] == "unknown"
    assert out["score"] <= 20


def test_tz_suffixed_iso_datetime_parses():
    dt = (datetime.now(timezone.utc) - timedelta(days=70)).isoformat().replace(
        "+00:00", "Z"
    )
    out = ghost_score(_job(created=dt))
    assert out["level"] == "stale"


# ── missing-salary signal ─────────────────────────────────────────────────────
def test_missing_salary_nudges_up():
    have = ghost_score(_job(created="", salary_min=120000.0, salary_max=150000.0))
    none = ghost_score(_job(created="", salary_min=None, salary_max=None))
    assert none["score"] > have["score"]
    assert any("salary" in r.lower() for r in none["reasons"])


def test_missing_salary_alone_fires_a_signal_not_unknown():
    # No date, but missing salary IS a signal -> not "unknown".
    out = ghost_score(_job(created="", salary_min=None, salary_max=None))
    assert out["level"] != "unknown"


def test_dollar_in_salary_text_counts_as_having_salary():
    # inbox-row style: no salary_min/max but salary_text carries a $ figure.
    row_with = ghost_score(
        {"title": "Controls Engineer", "created": "", "salary_text": "$130k"}
    )
    row_without = ghost_score({"title": "Controls Engineer", "created": ""})
    assert row_without["score"] > row_with["score"]


# ── evergreen / pipeline title signal ─────────────────────────────────────────
def test_evergreen_title_is_stale():
    out = ghost_score(_job(title="Engineering Talent Community", created=""))
    assert out["level"] == "stale"
    assert any("evergreen" in r.lower() or "pipeline" in r.lower()
               for r in out["reasons"])


def test_general_application_title_flags():
    out = ghost_score(_job(title="General Application", created=_iso_days_ago(2)))
    # evergreen bump is strong enough to lift even a fresh-dated job
    assert out["score"] >= 30


def test_evergreen_match_is_case_insensitive():
    out = ghost_score(_job(title="ALWAYS HIRING — Software Engineers", created=""))
    assert out["level"] == "stale"


def test_normal_title_not_flagged_evergreen():
    out = ghost_score(_job(title="Senior Controls Engineer"))
    assert not any("evergreen" in r.lower() for r in out["reasons"])


# ── dict (inbox row) vs JobResult parity ──────────────────────────────────────
def test_accepts_plain_dict_inbox_row():
    row = {
        "title": "Controls Engineer",
        "company": "Acme",
        "location": "Cincinnati, OH",
        "salary_min": None,
        "salary_max": None,
        "salary_text": "Not listed",
        "created": _iso_days_ago(60),
    }
    out = ghost_score(row)
    assert out["level"] == "stale"
    assert out["score"] >= 60


def test_jobresult_and_equivalent_dict_agree():
    created = _iso_days_ago(50)
    jr = _job(title="Controls Engineer", created=created,
              salary_min=None, salary_max=None)
    row = {"title": "Controls Engineer", "created": created,
           "salary_min": None, "salary_max": None}
    assert ghost_score(jr)["level"] == ghost_score(row)["level"]


def test_empty_dict_does_not_crash():
    out = ghost_score({})
    assert out["level"] == "unknown"
    assert 0 <= out["score"] <= 100


def test_none_safe_does_not_crash():
    # Wildly defensive: a row missing every field, including title.
    out = ghost_score({"title": None, "created": None, "salary_text": None})
    assert out["level"] == "unknown"


# ── module-level cache (bounded, keyed on ghost-relevant fields only) ──────────
import match.ghost as _ghost_mod  # noqa: E402 — appended block, avoid reordering above


def _reset_ghost_cache():
    _ghost_mod._GHOST_CACHE.clear()
    _ghost_mod._ghost_cache_hits = 0


def setup_function(_fn):
    # Every test in this module starts with a clean, empty cache so a prior
    # test's rows can't produce a spurious hit/miss here.
    _reset_ghost_cache()


def test_repeat_call_on_identical_row_is_a_cache_hit():
    row = {"title": "Controls Engineer", "created": _iso_days_ago(60),
           "salary_min": None, "salary_max": None}
    first = ghost_score(row)
    hits_after_first = _ghost_mod._ghost_cache_hits
    second = ghost_score(row)
    assert second == first
    # The second identical call must have hit the cache (counter advanced).
    assert _ghost_mod._ghost_cache_hits == hits_after_first + 1


def test_changed_field_is_a_cache_miss_not_a_stale_hit():
    row_a = {"title": "Controls Engineer", "created": _iso_days_ago(60)}
    row_b = {"title": "Controls Engineer", "created": _iso_days_ago(3)}
    out_a = ghost_score(row_a)
    out_b = ghost_score(row_b)
    # Genuinely different inputs -> genuinely different (and correct) outputs —
    # a stale-hit bug would return row_a's stale result for row_b's fresh dict.
    assert out_a["level"] == "stale"
    assert out_b["level"] == "fresh"
    assert out_a != out_b


def test_mutating_returned_dict_does_not_poison_next_call():
    row = {"title": "Controls Engineer", "created": _iso_days_ago(60)}
    first = ghost_score(row)
    first["reasons"].append("INJECTED-BY-CALLER")
    first["score"] = -999
    second = ghost_score(row)
    assert "INJECTED-BY-CALLER" not in second["reasons"]
    assert second["score"] != -999
    assert second["score"] == first["score"] or True  # sanity: no crash either way
    # Precisely: second must equal a fresh, uncorrupted computation.
    third = _ghost_mod._ghost_score_uncached(row)
    assert second == third


def test_repost_info_bypasses_cache_every_call():
    """A repost_info-bearing call must never be served from (or land in) the
    module cache -- it's an external, non-hashable-by-design map."""
    row = {"title": "Controls Engineer", "created": _iso_days_ago(60),
           "job_key": "acme:controls-engineer"}
    repost_info = {"acme:controls-engineer": {"repost": True}}
    before = len(_ghost_mod._GHOST_CACHE)
    out = ghost_score(row, repost_info=repost_info)
    assert any("reposted" in r for r in out["reasons"])
    # Cache size unchanged -- the repost_info path never touches _GHOST_CACHE.
    assert len(_ghost_mod._GHOST_CACHE) == before


def test_cache_key_ignores_irrelevant_fields():
    """Two rows differing ONLY in a field ghost_score never reads (e.g. `url`)
    must be treated as the same cache entry -- a hit, not a miss."""
    row_a = {"title": "Controls Engineer", "created": _iso_days_ago(60),
             "url": "http://x/1"}
    row_b = {"title": "Controls Engineer", "created": _iso_days_ago(60),
             "url": "http://x/2-totally-different"}
    ghost_score(row_a)
    hits_before = _ghost_mod._ghost_cache_hits
    ghost_score(row_b)
    assert _ghost_mod._ghost_cache_hits == hits_before + 1
