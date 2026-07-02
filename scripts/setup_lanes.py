"""One-off: create the 2026 job-search lane projects (controls / software /
applied-ai) per the agreed strategy — $90k floor, inverted exclude_titles
(no longer hiding ai/ml/software/data), seeded from the updated root
experience.md. Non-destructive: leaves mechdesign / controls-cincinnati intact.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import workspace

ROOT_EXP = Path(__file__).resolve().parent.parent / "experience.md"

# Sources: protect the jsearch 200/month free tier — use it only for manual
# targeted pulls, not these broad lane sweeps.
SOURCES = {
    "adzuna": True, "jsearch": False, "usajobs": True, "careers": True,
    "themuse": True, "remoteok": True, "remotive": True, "jobicy": True,
    "himalayas": True, "hn": True,
}
EXCLUDE_KW = ["active clearance required", "ts/sci", "sales engineer"]

LANES = {
    "controls": {
        "name": "Controls / Motion / Embedded",
        "config": {
            "keywords": [
                "controls engineer", "controls software engineer",
                "motion control engineer", "embedded systems engineer",
                "embedded software engineer", "firmware engineer",
                "robotics engineer", "mechatronics engineer",
                "automation engineer",
            ],
            "location": "Cincinnati",
            "salary_min": 90000,
            "min_score": 0,
            "max_per_company": 15,
            "exclude_keywords": EXCLUDE_KW,
            # inverted vs mechdesign: software/ai/ml NO LONGER excluded
            "exclude_titles": ["sales", "field service technician", "intern", "co-op"],
            "seniority_exclude": ["principal", "staff", "director", "vp", "head of"],
            "title_miss_penalty": 30,
            "sources": SOURCES,
        },
    },
    "software": {
        "name": "Software / Full-Stack",
        "config": {
            "keywords": [
                "software engineer", "full stack engineer", "full stack developer",
                "backend engineer", "backend developer", "python developer",
                "typescript developer", "software engineer manufacturing",
                "platform engineer", "applications engineer software",
            ],
            "location": "Cincinnati",
            "salary_min": 90000,
            "min_score": 0,
            "max_per_company": 15,
            "exclude_keywords": EXCLUDE_KW,
            "exclude_titles": ["sales", "intern", "co-op", "manager", "director"],
            "seniority_exclude": ["principal", "staff", "director", "vp", "head of"],
            "title_miss_penalty": 30,
            "sources": SOURCES,
        },
    },
    "applied-ai": {
        "name": "Applied AI / AI Engineer",
        "config": {
            "keywords": [
                "AI engineer", "applied AI engineer", "AI software engineer",
                "machine learning engineer", "ML engineer", "LLM engineer",
                "forward deployed engineer", "MLOps engineer",
                "AI for engineering", "AI applications engineer",
            ],
            "location": "Cincinnati",
            "salary_min": 90000,
            "min_score": 0,
            "max_per_company": 15,
            "exclude_keywords": EXCLUDE_KW,
            "exclude_titles": ["sales", "intern", "co-op", "recruiter"],
            "seniority_exclude": ["principal", "staff", "director", "vp", "head of"],
            "title_miss_penalty": 25,
            "sources": SOURCES,
        },
    },
}

for slug, spec in LANES.items():
    created = workspace.create_project(
        spec["name"], slug=slug, config=spec["config"],
        copy_resume_from=ROOT_EXP, make_active=False,
    )
    print(f"  ok: {created}  ({spec['name']})")

print("\nProjects now:")
for p in workspace.list_projects():
    print(f"  {p['slug']:22} {p['name']}")
