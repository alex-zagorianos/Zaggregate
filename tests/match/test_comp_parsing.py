"""P2 item 7: richer comp parsing -- hourly/weekly/monthly periods, bare k-ranges,
GBP/EUR currencies, context-aware floor, and currency/period-aware display.
salary_from_text keeps its annual (min,max) contract; parse_comp exposes the
currency + native-period figures the GUI comp column renders."""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from match.scorer import parse_comp, salary_from_text
from match.comp import normalize_comp
from models import JobResult


def _job(**over) -> JobResult:
    base = dict(title="X", company="A", location="Cincinnati, OH", salary_min=None,
                salary_max=None, description="", url="http://x/1", source_keyword="",
                created="2026-06-01", source_api="t")
    base.update(over)
    return JobResult(**base)


# ── parse_comp: periods (annualized min/max + native raw + label) ─────────────
def test_hourly_annualizes_and_keeps_raw():
    c = parse_comp("$14.50/hr")
    assert c["min"] == 14.5 * 2080
    assert c["raw_min"] == 14.5
    assert c["period"] == "hour" and c["currency"] == "USD"


def test_low_hourly_wage_survives_context_aware_floor():
    # $7.25/hr annualizes to ~15,080 -- below the 30k annual floor but above the
    # 15k sub-annual floor, so min-wage retail/food-service pay is no longer invisible.
    c = parse_comp("Pay: $7.25 per hour")
    assert c is not None and c["min"] == 7.25 * 2080


def test_monthly_period():
    c = parse_comp("$5,000/month")
    assert c["min"] == 60000.0 and c["period"] == "month" and c["raw_min"] == 5000.0


def test_weekly_period():
    c = parse_comp("$1,500 per week")
    assert c["min"] == 78000.0 and c["period"] == "week"


# ── parse_comp: bare k-range (no currency) ────────────────────────────────────
def test_bare_k_range():
    c = parse_comp("80k-100k")
    assert (c["min"], c["max"]) == (80000.0, 100000.0)
    assert c["currency"] == "USD" and c["period"] == "year"


# ── parse_comp: currencies ────────────────────────────────────────────────────
def test_gbp_currency_parsed_and_tagged():
    c = parse_comp("£90,000 - £110,000")
    assert c["currency"] == "GBP" and (c["min"], c["max"]) == (90000.0, 110000.0)


def test_eur_currency_parsed_and_tagged():
    c = parse_comp("€60,000 to €70,000")
    assert c["currency"] == "EUR" and c["min"] == 60000.0


# ── conservative: ambiguous / non-salary stays None ──────────────────────────
def test_non_salary_context_none():
    assert parse_comp("$2,000 relocation stipend") is None
    assert parse_comp("Competitive salary and benefits") is None
    assert parse_comp("401(k) match up to 6%") is None


# ── salary_from_text back-compat contract ─────────────────────────────────────
def test_salary_from_text_still_returns_annual_pair():
    assert salary_from_text("$120,000 - $140,000") == (120000.0, 140000.0)
    assert salary_from_text("Pay range: 120,000 - 150,000") == (120000.0, 150000.0)
    assert salary_from_text("No pay listed") == (None, None)


# ── comp.display renders period + currency ────────────────────────────────────
def test_display_hourly_from_description():
    out = normalize_comp(_job(description="Compensation: $14.50/hr DOE"))
    assert out["display"] == "$14.50/hr"
    assert out["period"] == "hour"
    assert out["min"] == 14.5 * 2080  # annualized for the floor filter


def test_display_gbp_range_uses_pound_symbol():
    row = {"title": "x", "salary_text": "£90,000 - £110,000", "description": ""}
    out = normalize_comp(row)
    assert out["display"] == "£90,000–£110,000"
    assert out["currency"] == "GBP"


def test_display_monthly_single():
    out = normalize_comp({"title": "x", "salary_text": "$5,000/month", "description": ""})
    assert out["display"] == "$5,000/mo"


def test_explicit_annual_fields_unchanged():
    out = normalize_comp(_job(salary_min=120000.0, salary_max=140000.0))
    assert out["display"] == "$120,000–$140,000"
    assert out["currency"] == "USD" and out["period"] == "year"
