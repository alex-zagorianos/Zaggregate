from dataclasses import dataclass, field


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

    # --- Direct (Workday / custom portal) ---
    CompanyEntry("Epic Systems",              "direct", "https://careers.epic.com/",                                   ["health_informatics", "ehr"]),
    CompanyEntry("Oracle Health / Cerner",    "direct", "https://careers.oracle.com/jobs/#en/sites/jobsearch/requisitions?keyword=health+informatics", ["health_informatics", "ehr"]),
    CompanyEntry("Optum / UnitedHealth",      "direct", "https://careers.unitedhealthgroup.com/job-search-results/",  ["health_informatics", "payer", "analytics"]),
    CompanyEntry("Meditech",                  "direct", "https://wd3.myworkdayjobs.com/meditech",                      ["health_informatics", "ehr"]),
    CompanyEntry("Waystar",                   "direct", "https://www.waystar.com/careers/open-positions/",            ["health_informatics", "rcm"]),
    CompanyEntry("Cotiviti",                  "direct", "https://jobs.cotiviti.com/",                                  ["health_informatics", "analytics", "payer"]),
    CompanyEntry("Evolent Health",            "direct", "https://www.evolenthealth.com/careers/open-positions",        ["health_informatics", "payer"]),
    CompanyEntry("Privia Health",             "direct", "https://www.priviahealth.com/careers/",                       ["health_informatics", "clinical"]),
    CompanyEntry("Health Catalyst",           "direct", "https://www.healthcatalyst.com/careers/",                    ["health_informatics", "analytics"]),
    CompanyEntry("Nuance / Microsoft Health", "direct", "https://careers.microsoft.com/v2/global/en/nuance.html",     ["health_informatics", "clinical", "ai"]),
    CompanyEntry("Phreesia",                  "direct", "https://www.phreesia.com/careers/",                           ["health_informatics", "patient_engagement"]),
    CompanyEntry("Surescripts",               "direct", "https://surescripts.com/about-surescripts/careers/",         ["health_informatics", "pharmacy"]),
    CompanyEntry("Availity",                  "direct", "https://www.availity.com/about-availity/careers/",            ["health_informatics", "rcm"]),
    CompanyEntry("Veradigm / Allscripts",     "direct", "https://veradigm.com/careers/",                              ["health_informatics", "ehr", "analytics"]),
    CompanyEntry("Netsmart",                  "direct", "https://www.ntst.com/Careers",                               ["health_informatics", "ehr", "behavioral_health"]),
    CompanyEntry("Vizient",                   "direct", "https://careers.vizientinc.com/",                            ["health_informatics", "analytics", "supply_chain"]),
    CompanyEntry("Ciox Health",               "direct", "https://www.cioxhealth.com/about-ciox/careers/",             ["health_informatics", "him", "rcm"]),
    CompanyEntry("DrFirst",                   "direct", "https://drfirst.com/about/careers/",                         ["health_informatics", "pharmacy", "ehr"]),
    CompanyEntry("Apixio",                    "direct", "https://www.apixio.com/careers/",                            ["health_informatics", "ai", "payer"]),
]


# ---------------------------------------------------------------------------
# Controls & Automation Engineering
# Greenhouse/Lever verified 2026-05-26 — most large industrials use Workday
# ---------------------------------------------------------------------------
_CONTROLS_ENGINEERING: list[CompanyEntry] = [
    # --- Direct (Workday / custom portals) ---
    CompanyEntry("Rockwell Automation", "direct", "https://careers.rockwellautomation.com/jobs",              ["controls_engineering", "plc", "scada"]),
    CompanyEntry("Emerson Electric",    "direct", "https://www.emerson.com/en-us/careers/search-jobs",        ["controls_engineering", "process_control"]),
    CompanyEntry("Honeywell",           "direct", "https://careers.honeywell.com/us/en/search-results",       ["controls_engineering", "automation", "aerospace"]),
    CompanyEntry("Caterpillar",         "direct", "https://careers.caterpillar.com/en/jobs/",                 ["controls_engineering", "embedded", "heavy_equipment"]),
    CompanyEntry("Parker Hannifin",     "direct", "https://phstock.wd1.myworkdayjobs.com/Parker_Hannifin",    ["controls_engineering", "motion_control", "hydraulics"]),
    CompanyEntry("Eaton",               "direct", "https://eaton.eightfold.ai/careers",                       ["controls_engineering", "power_management"]),
    CompanyEntry("Moog",                "direct", "https://www.moog.com/company/careers.html",                ["controls_engineering", "motion_control", "aerospace"]),
    CompanyEntry("Cognex",              "direct", "https://www.cognex.com/company/careers",                   ["controls_engineering", "machine_vision"]),
    CompanyEntry("Danaher",             "direct", "https://jobs.danaher.com/global/en",                       ["controls_engineering", "instrumentation"]),
    CompanyEntry("Trimble",             "direct", "https://jobs.trimble.com/",                                ["controls_engineering", "gps", "automation"]),
    CompanyEntry("Zebra Technologies",  "direct", "https://careers.zebra.com/careers/",                      ["controls_engineering", "automation", "iot"]),
    CompanyEntry("Roper Technologies",  "direct", "https://www.ropertech.com/careers",                       ["controls_engineering", "instrumentation"]),
    CompanyEntry("Keyence",             "direct", "https://www.keyence.com/company/careers/",                 ["controls_engineering", "sensors", "machine_vision"]),
    CompanyEntry("MathWorks",           "direct", "https://www.mathworks.com/company/jobs/opportunities/",   ["controls_engineering", "simulation", "matlab"]),
    CompanyEntry("Beckhoff Automation", "direct", "https://www.beckhoff.com/en-us/company/careers/",         ["controls_engineering", "plc", "automation"]),
    CompanyEntry("FANUC America",       "direct", "https://www.fanucamerica.com/company/careers",            ["controls_engineering", "robotics", "cnc"]),
    CompanyEntry("Yaskawa",             "direct", "https://www.yaskawa.com/us/careers",                      ["controls_engineering", "robotics", "motion_control"]),
    CompanyEntry("ABB",                 "direct", "https://careers.abb/global/en",                           ["controls_engineering", "automation", "robotics"]),
    CompanyEntry("Siemens",             "direct", "https://jobs.siemens.com/careers",                        ["controls_engineering", "automation", "plc"]),
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


def get_registry(industry: str | None = None) -> list[CompanyEntry]:
    """Return companies filtered by industry key or tag. None returns all."""
    if industry is None:
        return list(REGISTRY)
    key = industry.lower().replace(" ", "_")
    if key in REGISTRIES:
        return list(REGISTRIES[key])
    # fuzzy fallback: match against industry tags
    return [e for e in REGISTRY if any(industry.lower() in tag.lower() for tag in e.industries)]
