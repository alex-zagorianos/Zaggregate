"""The round-trip file contract (WS-3).

Defines the CSV column order carried between the app and the user's AI, the
versioned prompt template (anchored to preferences.md + the same fit-scoring
guide the bridge/API routes use), and the formula-injection guard. job_key is
the WS-1 cross-source join key and MUST echo back unchanged.
"""
from __future__ import annotations

import re

# Carrier column order. Reordering breaks golden-file tests — change deliberately.
RERANK_CSV_COLUMNS = [
    "job_key", "title", "company", "location", "salary", "url",
    "local_score", "current_fit", "description_excerpt",
    "new_fit", "new_rank", "fit_rationale", "tags",
]
# The AI fills these in; everything else is read-only context the app emits.
IN_COLUMNS = ["new_fit", "new_rank", "fit_rationale", "tags"]
OUT_COLUMNS = [c for c in RERANK_CSV_COLUMNS if c not in IN_COLUMNS]

PROMPT_VERSION = "1"
_DESC_LIMIT = 1200

_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value):
    """Formula-injection guard (parity with search.report_csv._csv_safe): a
    string starting with = + - @ or a control char is prefixed with a single
    quote so spreadsheets don't execute it. Non-strings pass through."""
    if isinstance(value, str) and value and value[0] in _DANGEROUS:
        return "'" + value
    return value


def _job_key_for_row(r: dict) -> str:
    """The WS-1 join key for an inbox row. Build a JobResult and read its
    cached job_key (added by WS-1; itself falls back to identity_key when the
    coverage package is absent), so export/import share one definition with the
    rest of the app. **WS-1 may not have landed yet** — the real models.py today
    has only identity_key/dedup_key, no job_key — so fall back to identity_key
    when JobResult has no job_key attribute. Both are deterministic and used on
    BOTH the export and import sides, so the round-trip join stays consistent
    whichever key is in effect."""
    from models import JobResult
    j = JobResult(
        title=r.get("title", "") or "", company=r.get("company", "") or "",
        location=r.get("location", "") or "", salary_min=None, salary_max=None,
        description=r.get("description", "") or "", url=r.get("url", "") or "",
        source_keyword="", created=r.get("created", "") or "",
        source_api=r.get("source", "") or "",
    )
    # getattr fallback: job_key (WS-1, 16-hex sha1) when present, else the
    # existing identity_key (32-hex md5). Never AttributeError on today's models.
    return getattr(j, "job_key", None) or j.identity_key


def row_from_inbox(r: dict) -> dict:
    """Map an inbox-row dict (tracker.db.inbox_all shape) into a full
    RERANK_CSV_COLUMNS dict. AI-filled columns start blank."""
    desc = re.sub(r"\s+", " ", (r.get("description", "") or "")).strip()[:_DESC_LIMIT]
    return {
        "job_key": _job_key_for_row(r),
        "title": r.get("title", "") or "",
        "company": r.get("company", "") or "",
        "location": r.get("location", "") or "",
        "salary": r.get("salary_text", "") or "",
        "url": r.get("url", "") or "",
        "local_score": r.get("score", -1),
        "current_fit": r.get("fit", -1),
        "description_excerpt": desc,
        "new_fit": "",
        "new_rank": "",
        "fit_rationale": "",
        "tags": "",
    }


def build_prompt(profile_md: str, fit_preference: str = "") -> str:
    """The versioned re-rank prompt: the same scoring guide the bridge/API use,
    plus the user's preferences profile, plus explicit round-trip instructions
    (fill new_fit/new_rank/fit_rationale; leave job_key untouched).

    `fit_preference` is the per-profile bias sentence ('' = neutral). It replaces
    the old baked-in 'prefers smaller companies' text so the file route matches
    the bridge/API de-Alex'd default: an empty preference adds NO bias sentence."""
    # Only the scoring SCALE - NOT the bridge's "respond with a JSON array
    # {i,token,fit}" contract, which contradicts this route's CSV/job_key answer.
    guide = ("Scoring guide: 90+ apply today; 70-89 strong; 50-69 plausible "
             "stretch; <50 skip. Judge against the candidate's real experience "
             "level - do not inflate. A role requiring 10+ years or an active "
             "clearance the candidate lacks caps at 40.")
    pref = (fit_preference or "").strip()
    if pref:
        guide += " " + pref
    cols = ", ".join(RERANK_CSV_COLUMNS)
    return "\n".join([
        f"# Job re-rank request (prompt version {PROMPT_VERSION})",
        "",
        "You are re-ranking the candidate's job inbox. Read the candidate "
        "profile below, then score EVERY row in the attached CSV "
        "(`ranking_export.csv`).",
        "",
        "If the export was split into several files (`ranking_export_01.csv`, "
        "`ranking_export_02.csv`, ...) because it was too large for one chat, "
        "answer EACH file separately and return each file's rows on their own. "
        "The `job_key` column joins every file's answers back together on import, "
        "so you never need all files in one reply.",
        "",
        "## How to return your answer",
        f"Return the SAME CSV with these columns filled in: {', '.join(IN_COLUMNS)}.",
        "- `new_fit`: integer 0-100 (the scoring guide below).",
        "- `new_rank`: rank your recommended shortlist 1..X (1 = best); leave it "
        "BLANK for jobs not on the shortlist. Only ranked rows appear in the "
        "app's Top Picks view, so rank as many as you'd recommend.",
        "- `fit_rationale`: one short line (why / red flags).",
        "- `tags`: optional free dimensions, comma-separated.",
        "**Leave `job_key` EXACTLY as given** — it is how scores are matched "
        "back; do not edit, reorder its characters, or drop the column. "
        "Returning JSON (a list of objects with these keys) is also accepted.",
        "",
        "## Scoring guide",
        guide,
        "",
        "## Candidate profile (from preferences.md)",
        (profile_md or "(no profile provided)").strip(),
        "",
        f"## CSV columns, in order\n{cols}",
    ])


# Module-level convenience: the default prompt rendered against the user's live
# preferences.md. Built lazily so importing schema.py never reads the data dir.
class _LazyPromptTemplate(str):
    pass


def _render_default_prompt() -> str:
    try:
        import preferences
        p = preferences.load() or {}
        profile = p.get("profile_md", "") or ""
        fit_pref = p.get("fit_preference", "") or ""
    except Exception:
        profile, fit_pref = "", ""
    return build_prompt(profile, fit_pref)


PROMPT_TEMPLATE = _render_default_prompt()
