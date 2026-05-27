import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class CompanyEntry:
    name: str
    ats_type: str       # "greenhouse" | "lever" | "direct"
    slug: str           # ATS slug for GH/Lever; full careers URL for direct
    industries: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Health Informatics
# Greenhouse slugs verified 2026-05-26 against boards-api.greenhouse.io
# Lever slugs verified 2026-05-26 against api.lever.co
# Direct = company uses Workday/Taleo/custom portal (best-effort scrape)
# ---------------------------------------------------------------------------
_HEALTH_INFORMATICS: list[CompanyEntry] = [
    # --- Confirmed Greenhouse ---
    CompanyEntry("Inovalon",         "greenhouse", "inovalon",      ["health_informatics", "analytics", "payer"]),
    CompanyEntry("Doximity",         "greenhouse", "doximity",      ["health_informatics", "clinical"]),
    CompanyEntry("Elation Health",   "greenhouse", "elationhealth", ["health_informatics", "ehr", "primary_care"]),
    CompanyEntry("athenahealth",     "greenhouse", "athena",        ["health_informatics", "ehr", "rcm"]),
    CompanyEntry("CareDx",           "greenhouse", "caredxinc",     ["health_informatics", "clinical"]),

    # --- Confirmed Lever ---
    CompanyEntry("PointClickCare",   "lever", "pointclickcare", ["health_informatics", "ehr", "ltpac"]),
    CompanyEntry("Arcadia",          "lever", "arcadia",         ["health_informatics", "analytics", "value_based_care"]),
    CompanyEntry("Veeva Systems",    "lever", "veeva",           ["health_informatics", "life_sciences"]),

    # --- Direct (Workday with CSRF enabled — JS session required; scraping limited) ---
    # These confirmed as Workday but CSRF/session protection prevents JSON API access.
    # Use "workday" type below only for tenants confirmed CSRF-disabled.
    CompanyEntry("Epic Systems",           "direct", "https://epiccareers.wd5.myworkdayjobs.com/External",            ["health_informatics", "ehr"]),
    CompanyEntry("Optum / UnitedHealth",   "direct", "https://uhg.wd5.myworkdayjobs.com/External",                   ["health_informatics", "payer", "analytics"]),
    CompanyEntry("Meditech",               "direct", "https://meditech.wd3.myworkdayjobs.com/meditech",               ["health_informatics", "ehr"]),
    CompanyEntry("Vizient",                "direct", "https://vizientinc.wd1.myworkdayjobs.com/External",             ["health_informatics", "analytics", "supply_chain"]),
    CompanyEntry("Cotiviti",               "direct", "https://cotiviti.wd1.myworkdayjobs.com/Cotiviti_Careers",       ["health_informatics", "analytics", "payer"]),
    CompanyEntry("Oracle Health / Cerner", "direct", "https://careers.oracle.com/jobs/#en/sites/jobsearch/requisitions?keyword=health+informatics", ["health_informatics", "ehr"]),
    CompanyEntry("Waystar",                "direct", "https://www.waystar.com/careers/open-positions/",               ["health_informatics", "rcm"]),
    CompanyEntry("Evolent Health",         "direct", "https://www.evolenthealth.com/careers/open-positions",          ["health_informatics", "payer"]),
    CompanyEntry("Privia Health",          "direct", "https://www.priviahealth.com/careers/",                         ["health_informatics", "clinical"]),
    CompanyEntry("Health Catalyst",        "direct", "https://www.healthcatalyst.com/careers/",                       ["health_informatics", "analytics"]),
    CompanyEntry("Nuance / Microsoft Health", "direct", "https://careers.microsoft.com/v2/global/en/nuance.html",    ["health_informatics", "clinical", "ai"]),
    CompanyEntry("Phreesia",               "direct", "https://www.phreesia.com/careers/",                             ["health_informatics", "patient_engagement"]),
    CompanyEntry("Surescripts",            "direct", "https://surescripts.com/about-surescripts/careers/",            ["health_informatics", "pharmacy"]),
    CompanyEntry("Availity",               "direct", "https://www.availity.com/about-availity/careers/",              ["health_informatics", "rcm"]),
    CompanyEntry("Veradigm / Allscripts",  "direct", "https://veradigm.com/careers/",                                ["health_informatics", "ehr", "analytics"]),
    CompanyEntry("Netsmart",               "direct", "https://www.ntst.com/Careers",                                  ["health_informatics", "ehr", "behavioral_health"]),
    CompanyEntry("Ciox Health",            "direct", "https://www.cioxhealth.com/about-ciox/careers/",                ["health_informatics", "him", "rcm"]),
    CompanyEntry("DrFirst",                "direct", "https://drfirst.com/about/careers/",                            ["health_informatics", "pharmacy", "ehr"]),
    CompanyEntry("Apixio",                 "direct", "https://www.apixio.com/careers/",                               ["health_informatics", "ai", "payer"]),
]


# ---------------------------------------------------------------------------
# Controls & Automation Engineering
# Greenhouse/Lever verified 2026-05-26 — most large industrials use Workday
# ---------------------------------------------------------------------------
_CONTROLS_ENGINEERING: list[CompanyEntry] = [
    # --- Workday CSRF-disabled (JSON API works without a browser session) ---
    # Verified 2026-05-26: cat.wd5 returns 200 with job data, no CSRF required.
    CompanyEntry("Caterpillar",         "workday", "cat:5:CaterpillarCareers",               ["controls_engineering", "embedded", "heavy_equipment"]),

    # --- Direct (Workday with CSRF enabled — JS session required; scraping limited) ---
    # Confirmed as Workday but CSRF protection active: rockwellautomation:1, phstock:1,
    # honeywell:5, siemens:3, danaher:1, trimble:1 all return HTTP 422 on bare POST.
    CompanyEntry("Rockwell Automation", "direct", "https://rockwellautomation.wd1.myworkdayjobs.com/External",     ["controls_engineering", "plc", "scada"]),
    CompanyEntry("Honeywell",           "direct", "https://honeywell.wd5.myworkdayjobs.com/Honeywell_Jobs",        ["controls_engineering", "automation", "aerospace"]),
    CompanyEntry("Parker Hannifin",     "direct", "https://phstock.wd1.myworkdayjobs.com/Parker_Hannifin",         ["controls_engineering", "motion_control", "hydraulics"]),
    CompanyEntry("Siemens",             "direct", "https://siemens.wd3.myworkdayjobs.com/Siemens",                 ["controls_engineering", "automation", "plc"]),
    CompanyEntry("Danaher",             "direct", "https://danaher.wd1.myworkdayjobs.com/Danaher",                 ["controls_engineering", "instrumentation"]),
    CompanyEntry("Trimble",             "direct", "https://trimble.wd1.myworkdayjobs.com/Trimble_Careers",         ["controls_engineering", "gps", "automation"]),

    # --- Direct (non-Workday custom portals) ---
    CompanyEntry("Emerson Electric",    "direct", "https://www.emerson.com/en-us/careers/search-jobs",        ["controls_engineering", "process_control"]),
    CompanyEntry("Eaton",               "direct", "https://eaton.eightfold.ai/careers",                       ["controls_engineering", "power_management"]),
    CompanyEntry("Moog",                "direct", "https://www.moog.com/company/careers.html",                ["controls_engineering", "motion_control", "aerospace"]),
    CompanyEntry("Cognex",              "direct", "https://www.cognex.com/company/careers",                   ["controls_engineering", "machine_vision"]),
    CompanyEntry("Zebra Technologies",  "direct", "https://careers.zebra.com/careers/",                      ["controls_engineering", "automation", "iot"]),
    CompanyEntry("Roper Technologies",  "direct", "https://www.ropertech.com/careers",                       ["controls_engineering", "instrumentation"]),
    CompanyEntry("Keyence",             "direct", "https://www.keyence.com/company/careers/",                 ["controls_engineering", "sensors", "machine_vision"]),
    CompanyEntry("MathWorks",           "direct", "https://www.mathworks.com/company/jobs/opportunities/",   ["controls_engineering", "simulation", "matlab"]),
    CompanyEntry("Beckhoff Automation", "direct", "https://www.beckhoff.com/en-us/company/careers/",         ["controls_engineering", "plc", "automation"]),
    CompanyEntry("FANUC America",       "direct", "https://www.fanucamerica.com/company/careers",            ["controls_engineering", "robotics", "cnc"]),
    CompanyEntry("Yaskawa",             "direct", "https://www.yaskawa.com/us/careers",                      ["controls_engineering", "robotics", "motion_control"]),
    CompanyEntry("ABB",                 "direct", "https://careers.abb/global/en",                           ["controls_engineering", "automation", "robotics"]),
]


# ---------------------------------------------------------------------------
# Registry dict — add a new industry by adding a new key here
# ---------------------------------------------------------------------------
REGISTRIES: dict[str, list[CompanyEntry]] = {
    "health_informatics":   _HEALTH_INFORMATICS,
    "controls_engineering": _CONTROLS_ENGINEERING,
}

# Flat combined list (all industries)
REGISTRY: list[CompanyEntry] = [
    entry for entries in REGISTRIES.values() for entry in entries
]


def _load_user_companies(json_path: Optional[Path] = None) -> list[CompanyEntry]:
    """Load user-defined companies from companies.json. Returns [] if file missing or invalid."""
    from config import COMPANIES_JSON
    path = json_path or COMPANIES_JSON
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        entries = []
        for item in raw.get("companies", []):
            if "_example" in item or not item.get("name"):
                continue
            entries.append(CompanyEntry(
                name=item["name"],
                ats_type=item.get("ats_type", "direct"),
                slug=item.get("slug", ""),
                industries=item.get("industries", []),
            ))
        return entries
    except Exception as e:
        print(f"  [registry] Warning: could not load {path.name} — {e}")
        return []


def get_registry(industry: str | None = None, user_json: Optional[Path] = None) -> list[CompanyEntry]:
    """Return companies filtered by industry key or tag, merged with user companies.json.

    User entries override hardcoded ones by name (case-insensitive match).
    Pass user_json=Path(...) to use a non-default file path.
    """
    user_entries = _load_user_companies(user_json)

    # Build base list: hardcoded registry filtered by industry
    if industry is None:
        base = list(REGISTRY)
    else:
        key = industry.lower().replace(" ", "_")
        if key in REGISTRIES:
            base = list(REGISTRIES[key])
        else:
            base = [e for e in REGISTRY if any(industry.lower() in tag.lower() for tag in e.industries)]

    # Filter user entries by industry too
    if industry is not None:
        key = industry.lower().replace(" ", "_")
        user_entries = [
            e for e in user_entries
            if not e.industries or key in e.industries or any(industry.lower() in t.lower() for t in e.industries)
        ]

    if not user_entries:
        return base

    # Merge: user wins on name collision
    base_by_name = {e.name.lower(): e for e in base}
    for ue in user_entries:
        base_by_name[ue.name.lower()] = ue
    return list(base_by_name.values())
