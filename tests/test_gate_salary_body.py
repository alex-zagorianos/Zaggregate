"""S32 item 3 (QW-3, review #5): sub-floor comp in the JD BODY must not slip a
salary hard-gate when the API salary fields are empty. Drop only on a CONFIDENT
sub-floor parse; ambiguous / no-comp / at-floor bodies are kept.
"""
from models import JobResult
import preferences


def _job(title="Marketing Manager", desc="", smin=None, smax=None, loc="Remote"):
    return JobResult(title=title, company="X", location=loc, salary_min=smin,
                     salary_max=smax, description=desc,
                     url="http://x/" + str(hash(desc)), source_keyword="",
                     created="", job_id=str(hash(desc)), source_api="t")


HARD = {"salary_min": 90000, "locations": [], "remote_ok": True}


def test_monthly_body_below_floor_dropped():
    j = _job(desc="Compensation: US$1,500 per Month. Fully remote.")
    kept = preferences.hard_gate([j], HARD)
    assert kept == []  # ~$18k annualized < $90k floor


def test_hourly_body_below_floor_dropped():
    j = _job(desc="Pay: $12 per hour, part of a great team.")
    assert preferences.hard_gate([j], HARD) == []  # ~$25k < 90k


def test_body_at_or_above_floor_kept():
    j = _job(desc="Salary: $120,000 - $150,000 per year.")
    assert preferences.hard_gate([j], HARD) == [j]


def test_no_comp_body_kept():
    # No parseable comp -> never over-cut (wide net preserved).
    j = _job(desc="A wonderful opportunity with great benefits and growth.")
    assert preferences.hard_gate([j], HARD) == [j]


def test_ambiguous_non_salary_context_kept():
    # A 401(k) / stipend mention must not be read as sub-floor comp.
    j = _job(desc="We offer a $5,000 relocation stipend and 401(k) match.")
    assert preferences.hard_gate([j], HARD) == [j]


def test_api_salary_present_path_unchanged():
    # When API fields ARE present, the original range-floor logic still governs
    # (body is not consulted) -> byte-identical to pre-S32.
    below = _job(smin=50000, smax=60000, desc="Salary: $200,000 in the body")
    assert preferences.hard_gate([below], HARD) == []          # API max 60k < 90k
    above = _job(smin=95000, smax=130000, desc="ignore me $1,000/mo")
    assert preferences.hard_gate([above], HARD) == [above]     # API range clears floor


def test_no_floor_keeps_everything():
    # No salary_min set -> body comp is never gated.
    j = _job(desc="Compensation: US$1,500 per Month")
    assert preferences.hard_gate([j], {"salary_min": None}) == [j]


def test_bonus_figure_not_read_as_base_salary_kept():
    # A competitive-but-unstated base plus a monthly BONUS figure must not be
    # annualized as if it were the salary and hard-dropped. Common in sales/AE.
    j = _job(desc="Base salary is competitive. Plus up to $2,500/month bonus.")
    assert preferences.hard_gate([j], HARD) == [j]


def test_commission_figure_not_read_as_base_salary_kept():
    j = _job(desc="Strong base. Plus up to $5,000 per month in commissions.")
    assert preferences.hard_gate([j], HARD) == [j]


def test_signing_bonus_figure_not_read_as_base_salary_kept():
    j = _job(desc="Competitive base. Signing bonus of $3,000 per month for year one.")
    assert preferences.hard_gate([j], HARD) == [j]
