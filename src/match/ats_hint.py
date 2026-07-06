"""Free, local "ATS match hint" (Jobscan-lite) — the own-your-data answer to a
$50/mo resume-match tool. Two honest signals, both computed on-device with ZERO
AI calls and ZERO network:

  (a) which Applicant Tracking System the posting's employer runs, detected from
      the job/company URL alone (``scrape.ats_detect.detect_ats`` — greenhouse,
      lever, workday_cxs, icims, taleo, ...), and

  (b) a keyword-overlap read between the user's own skills (experience.md) and
      the job description — the terms they already match, and the salient terms
      the JD asks for that aren't in their profile yet (``match.skillgap``).

This is deliberately framed as *guidance*, not a fake "ATS score": we don't
claim to know how a given ATS ranks a résumé (that's proprietary and varies),
only what system it is and where the user's own words line up with the posting.
Naming the ATS is useful on its own — it tells the user which parser the posting
runs so they can format for it (the real, defensible half of what Jobscan sells).

Deterministic. Stdlib + ``scrape.ats_detect`` + ``match.skillgap`` only. Every
entry point is defensive: bad/empty input yields an empty-but-valid result, never
an exception, so a détail-pane readout can call it unconditionally.
"""
from __future__ import annotations

# Human-readable name for each ats_detect type key. Unknown keys fall back to a
# title-cased form of the key; "direct" means "no recognizable ATS — a company's
# own careers page or an aggregator link", which we surface plainly.
_ATS_LABELS = {
    "greenhouse": "Greenhouse",
    "lever": "Lever",
    "ashby": "Ashby",
    "smartrecruiters": "SmartRecruiters",
    "workday": "Workday",
    "workday_cxs": "Workday",
    "workable": "Workable",
    "recruitee": "Recruitee",
    "personio": "Personio",
    "bamboohr": "BambooHR",
    "rippling": "Rippling",
    "paylocity": "Paylocity",
    "eightfold": "Eightfold",
    "adp": "ADP Workforce Now",
    "oracle_orc": "Oracle Recruiting Cloud",
    "phenom": "Phenom",
    "breezy": "Breezy HR",
    "pinpoint": "Pinpoint",
    "teamtailor": "Teamtailor",
    "jazzhr": "JazzHR",
    "icims": "iCIMS",
    "taleo": "Oracle Taleo",
    "successfactors": "SAP SuccessFactors",
}


def ats_label(url: str) -> str:
    """The human name of the ATS a posting URL runs on, or "" when the URL is
    empty or resolves to a non-ATS 'direct' link. Never raises."""
    try:
        from scrape.ats_detect import detect_ats
        ats, _slug = detect_ats(url or "")
    except Exception:
        return ""
    if not ats or ats == "direct":
        return ""
    return _ATS_LABELS.get(ats, ats.replace("_", " ").title())


def match_hint(
    description: str,
    url: str = "",
    *,
    skill_terms=None,
    experience_path=None,
    limit: int = 8,
) -> dict:
    """Compose the free local ATS + keyword-overlap hint for one posting.

    Returns a dict — always these keys, always the right types:
      ``ats``     — the detected ATS name ("" if none / non-ATS link).
      ``matched`` — user skill terms the JD actually mentions (sorted, deduped).
      ``missing`` — salient JD terms the user's profile lacks (freq-ranked,
                    capped at ``limit``).
      ``have``    — len(matched); a convenience count for a one-line readout.

    ``skill_terms`` defaults to the user's parsed experience.md skills (via
    ``match.skillgap``/``match.scorer``). No AI, no network. Defensive — a blank
    description or a parse hiccup yields empty lists, never an exception, so a
    detail pane can call this on every row unconditionally.
    """
    out = {"ats": ats_label(url), "matched": [], "missing": [], "have": 0}
    text = description if isinstance(description, str) else ""
    if not text.strip():
        return out
    try:
        from match import skillgap
        gap = skillgap.skill_gap(
            text, skill_terms=skill_terms, experience_path=experience_path,
            limit=limit)
        out["matched"] = list(gap.get("matched", []))
        out["missing"] = list(gap.get("missing", []))
        out["have"] = len(out["matched"])
    except Exception:
        pass
    return out


def hint_lines(hint: dict, *, missing_cap: int = 8, matched_cap: int = 8) -> list[str]:
    """Render a ``match_hint`` result as 0–3 plain-English guidance lines for a
    detail pane — honest wording, never a fabricated "ATS score". Empty pieces are
    omitted, so a posting with no ATS and no description yields ``[]``.

    Kept UI-framework-free (returns strings) so it's unit-testable headlessly and
    reused verbatim by any surface that wants the readout."""
    lines: list[str] = []
    ats = (hint or {}).get("ats") or ""
    if ats:
        lines.append(
            f"Applies through {ats} — format your resume for {ats}'s parser "
            f"(simple layout, standard headings).")
    matched = list((hint or {}).get("matched") or [])
    if matched:
        shown = matched[:matched_cap]
        more = f" +{len(matched) - len(shown)} more" if len(matched) > len(shown) else ""
        lines.append(
            f"Your skills the posting names ({len(matched)}): "
            + ", ".join(shown) + more)
    missing = list((hint or {}).get("missing") or [])
    if missing:
        shown = missing[:missing_cap]
        lines.append(
            "Terms the job asks for that aren't in your profile yet: "
            + ", ".join(shown)
            + " — add any you genuinely have.")
    return lines
