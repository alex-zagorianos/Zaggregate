"""Deterministic pre-AI gate — drops structural non-fits before any model spend
(spec-2026-06-29 §5 / pipeline §4).

"drop" here means *excluded from the AI ranking batch*, NOT hidden from the user:
the job keeps its local 0-100 score and stays in the inbox. We just don't spend a
model call deciding a posting that fails a hard, mechanical constraint (an
internship, a people-management role, a clearance the candidate lacks, a foreign
work-visa requirement). The fuzzy/semantic calls (is this the kind of build work I
like?) are exactly what the AI batch is for, so those pass through.
"""
from __future__ import annotations

import re

# Restriction strings (from match.facts) that disqualify a US-authorized candidate.
_FOREIGN_RESTRICTION = re.compile(r"japan|europe|\beu\b|uk|united kingdom|canada|australia|"
                                  r"india|germany|mexico|brazil|non-us", re.I)


def evaluate(facts: dict, rubric: dict, *, title: str = "") -> dict:
    """Return {"decision": "keep|downrank|drop", "reasons": [...]}.

    drop      -> exclude from the AI batch (clear structural non-fit)
    downrank  -> keep in the AI batch but flagged (soft mismatch the AI weighs)
    keep      -> in the AI batch, no flags
    """
    drops, downs = [], []
    tl = (title or "").lower()

    # ── hard drops (don't spend AI) ──────────────────────────────────────────
    if facts.get("seniority") == "intern" and not rubric.get("allow_intern"):
        drops.append("internship")

    if facts.get("clearance_required") and not rubric.get("has_clearance"):
        drops.append("security clearance required")

    if (facts.get("seniority") in ("manager", "director") and facts.get("role_type") == "manage"
            and not rubric.get("allow_management")):
        # A management/exec seeker (rubric.allow_management, inferred from roles
        # like "VP"/"Director") WANTS these — dropping them here would empty the
        # whole result set before the AI ever ranked anything.
        drops.append("people-management role")

    restriction = facts.get("restriction") or ""
    if restriction and _FOREIGN_RESTRICTION.search(restriction):
        drops.append(f"location/visa: {restriction}")

    for bad in rubric.get("hard_no_titles", []):
        if bad and re.search(r"(?<!\w)" + re.escape(bad) + r"(?!\w)", tl):
            drops.append(f"excluded title: {bad}")
            break

    years = facts.get("required_years")
    cap = rubric.get("years_cap", 8)
    if years and years >= cap:
        drops.append(f"requires {years}+ years")

    # ── soft downranks (still scored by the AI, just flagged) ─────────────────
    if facts.get("role_type") in rubric.get("penalty_roles", []) and "people-management role" not in drops:
        downs.append(f"role type: {facts['role_type']}")
    if (facts.get("seniority") in ("senior", "lead") and not drops
            and not rubric.get("allow_management")):
        # For an exec/management seeker a senior title isn't a stretch, it's the target.
        downs.append(f"{facts['seniority']}-level (stretch)")

    if drops:
        return {"decision": "drop", "reasons": drops}
    if downs:
        return {"decision": "downrank", "reasons": downs}
    return {"decision": "keep", "reasons": []}


def partition(pairs, rubric: dict):
    """Split [(job, facts), ...] into (kept, dropped).

    kept    = [(job, facts, gate)] with decision keep|downrank  -> goes to the AI
    dropped = [(job, facts, gate)] with decision drop           -> excluded from AI
    """
    kept, dropped = [], []
    for job, facts in pairs:
        gate = evaluate(facts, rubric, title=getattr(job, "title", "") or "")
        (dropped if gate["decision"] == "drop" else kept).append((job, facts, gate))
    return kept, dropped
