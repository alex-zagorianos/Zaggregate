"""normalize_comp / meets_floor: a single OFFLINE compensation normalizer that
surfaces the pay a job DISCLOSES, for a GUI comp column + a "meets my floor"
filter. Zero API calls — reads only already-scraped fields.

normalize_comp(job) -> {"min", "max", "disclosed", "display"}
meets_floor(job, floor) -> bool

Accepts EITHER a JobResult or a plain inbox-row dict; reads fields defensively.
Prefers explicit salary_min/max, else recovers from salary_text (inbox rows)
then description via match.scorer.salary_from_text.
"""
import sys
from pathlib import Path

# Make the real project root importable (models.py / match package) whether this
# runs from the worktree or the main checkout. conftest already does this for the
# main checkout; this guard covers an isolated worktree run too.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from match.comp import normalize_comp, meets_floor
from models import JobResult


def _job(**over) -> JobResult:
    base = dict(
        title="Controls Engineer",
        company="Acme",
        location="Cincinnati, OH",
        salary_min=None,
        salary_max=None,
        description="Build controls.",
        url="http://x/1",
        source_keyword="controls",
        created="2026-06-01",
        source_api="t",
    )
    base.update(over)
    return JobResult(**base)


# ── shape ─────────────────────────────────────────────────────────────────────
def test_returns_expected_shape():
    out = normalize_comp(_job(salary_min=120000.0, salary_max=140000.0))
    assert set(out) == {"min", "max", "disclosed", "display"}
    assert isinstance(out["disclosed"], bool)
    assert isinstance(out["display"], str)


# ── explicit min/max formatting ───────────────────────────────────────────────
def test_explicit_range_displays_as_dash():
    out = normalize_comp(_job(salary_min=120000.0, salary_max=140000.0))
    assert out["min"] == 120000.0
    assert out["max"] == 140000.0
    assert out["disclosed"] is True
    assert out["display"] == "$120,000–$140,000"


def test_explicit_min_only_displays_plus():
    out = normalize_comp(_job(salary_min=120000.0, salary_max=None))
    assert out["min"] == 120000.0
    assert out["max"] is None
    assert out["disclosed"] is True
    assert out["display"] == "$120,000+"


def test_explicit_max_only_displays_plus():
    # max present, min absent -> still a disclosed figure, shown as "max+".
    out = normalize_comp(_job(salary_min=None, salary_max=140000.0))
    assert out["disclosed"] is True
    assert out["max"] == 140000.0
    assert out["display"] == "$140,000+"


def test_rounds_to_whole_dollars_in_display():
    out = normalize_comp(_job(salary_min=120499.0, salary_max=140500.0))
    assert out["display"] == "$120,499–$140,500"


# ── recovery from salary_text (inbox rows) ────────────────────────────────────
def test_recovers_range_from_salary_text():
    row = {"title": "Controls Engineer", "salary_text": "$120,000 - $140,000",
           "description": ""}
    out = normalize_comp(row)
    assert out["min"] == 120000.0
    assert out["max"] == 140000.0
    assert out["disclosed"] is True
    assert out["display"] == "$120,000–$140,000"


def test_recovers_single_figure_from_salary_text_as_plus():
    row = {"title": "Controls Engineer", "salary_text": "around $130k",
           "description": ""}
    out = normalize_comp(row)
    assert out["min"] == 130000.0
    assert out["max"] is None
    assert out["disclosed"] is True
    assert out["display"] == "$130,000+"


def test_explicit_fields_win_over_salary_text():
    row = {"title": "x", "salary_min": 100000.0, "salary_max": 110000.0,
           "salary_text": "$200,000 - $300,000", "description": ""}
    out = normalize_comp(row)
    assert out["min"] == 100000.0
    assert out["max"] == 110000.0


# ── recovery from description ─────────────────────────────────────────────────
def test_recovers_from_description_when_no_fields_or_text():
    out = normalize_comp(_job(description="Comp range: $115,000 to $145,000 DOE."))
    assert out["min"] == 115000.0
    assert out["max"] == 145000.0
    assert out["disclosed"] is True


def test_salary_text_preferred_over_description():
    row = {"title": "x", "salary_text": "$120,000 - $140,000",
           "description": "Comp range: $200,000 to $300,000."}
    out = normalize_comp(row)
    assert out["min"] == 120000.0
    assert out["max"] == 140000.0


# ── nothing disclosed ─────────────────────────────────────────────────────────
def test_no_comp_anywhere_is_not_listed():
    out = normalize_comp(_job(description="Competitive salary and benefits."))
    assert out["min"] is None
    assert out["max"] is None
    assert out["disclosed"] is False
    assert out["display"] == "Not listed"


def test_empty_dict_row_is_not_listed():
    out = normalize_comp({})
    assert out["disclosed"] is False
    assert out["display"] == "Not listed"


# ── meets_floor ───────────────────────────────────────────────────────────────
def test_floor_none_is_always_true_even_undisclosed():
    assert meets_floor(_job(), None) is True


def test_floor_zero_is_always_true_even_undisclosed():
    assert meets_floor(_job(), 0) is True


def test_undisclosed_fails_a_positive_floor():
    # undisclosed != meets — a job with no disclosed comp returns False.
    assert meets_floor(_job(description="Competitive."), 100000) is False


def test_max_at_floor_passes():
    assert meets_floor(_job(salary_min=90000.0, salary_max=120000.0), 120000) is True


def test_max_above_floor_passes():
    assert meets_floor(_job(salary_min=90000.0, salary_max=140000.0), 120000) is True


def test_max_below_floor_fails():
    assert meets_floor(_job(salary_min=90000.0, salary_max=110000.0), 120000) is False


def test_min_only_used_when_no_max():
    # No max -> compare the min figure to the floor.
    assert meets_floor(_job(salary_min=125000.0, salary_max=None), 120000) is True
    assert meets_floor(_job(salary_min=115000.0, salary_max=None), 120000) is False


def test_max_only_used_when_no_min():
    assert meets_floor(_job(salary_min=None, salary_max=130000.0), 120000) is True


def test_floor_against_recovered_salary_text():
    row = {"title": "x", "salary_text": "$120,000 - $140,000", "description": ""}
    assert meets_floor(row, 130000) is True
    assert meets_floor(row, 150000) is False
