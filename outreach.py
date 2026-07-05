"""Warm-path outreach prompts — BYO-AI, prompt-only (B4 beta buildout).

Builds a copy-into-your-AI prompt that turns a target job + the user's network +
their own background into an actionable warm-path plan. Prompt-only (no paste-back
round trip, no AI API call): the user copies the prompt into whatever AI they
already use and reads the answer — the value is the STRUCTURED ASK, not automation.

The ask (baked into the output contract) is:
  * likely warm paths, RANKED (direct network contacts first, then alumni, then
    past-colleague diaspora, then associations/meetups);
  * exact LinkedIn search strings the USER runs in their OWN browser (we never
    scrape LinkedIn — the user drives their own logged-in session);
  * two outreach drafts in the user's voice, <=120 words each (an
    informational-interview ask + a referral ask);
  * the one-follow-up rule (one nudge after ~5 business days, then stop).

Import-safe (no tkinter, no network). B4 creates this module; B5 extends it with
follow-up / interview-prep prompt builders.
"""
from __future__ import annotations

import re

_MAX_DESC_CHARS = 1200
_MAX_CONTACTS = 8
_MAX_EXPERIENCE_CHARS = 6000
_WORD_CAP = 120


# ── experience mining (schools + past employers) ───────────────────────────────

def _experience_sections(experience_text: str) -> dict:
    """Parse the raw experience markdown into the section dict, tolerantly. Reuses
    ``resume.experience_parser.load_experience`` semantics by writing nothing —
    we only need EDUCATION + WORK EXPERIENCE text, so we split headings inline to
    avoid a file round-trip (the caller already has the raw text). Never raises."""
    sections: dict[str, list[str]] = {}
    current = None
    for line in (experience_text or "").splitlines():
        m = re.match(r"^\s*#{1,6}\s*(.+?)\s*:?\s*$", line)
        if m:
            current = m.group(1).strip().lower()
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items()}


def _match_section(sections: dict, *needles: str) -> str:
    for key, body in sections.items():
        if any(n in key for n in needles):
            if body.strip():
                return body
    return ""


def _schools_and_employers(experience_text: str) -> tuple[str, str]:
    """Best-effort (schools_text, employers_text) pulled from the experience
    markdown's EDUCATION and WORK EXPERIENCE sections. Empty strings when a
    section is absent — the prompt simply omits that block, never blocks."""
    sections = _experience_sections(experience_text)
    schools = _match_section(sections, "education", "school", "academic")
    employers = _match_section(sections, "work experience", "employment",
                               "professional experience", "work history",
                               "experience")
    return schools[:1500], employers[:2500]


# ── warm-path prompt ────────────────────────────────────────────────────────────

def _fmt_contacts(contacts) -> str:
    lines = []
    for c in (contacts or [])[:_MAX_CONTACTS]:
        name = (c.get("name") or "").strip()
        if not name:
            continue
        pos = (c.get("position") or "").strip()
        lines.append(f"- {name}" + (f" — {pos}" if pos else ""))
    return "\n".join(lines)


def _job_field(job: dict, *names: str) -> str:
    for n in names:
        v = job.get(n)
        if v and str(v).strip():
            return str(v).strip()
    return ""


def build_warm_path_prompt(job: dict, contacts, experience_text: str = "",
                           cfg: dict | None = None) -> str:
    """The full copy-to-your-AI warm-path prompt for one target job.

    ``job`` — a dict with at least ``title`` + ``company`` (``location`` /
    ``description`` used when present). ``contacts`` — the user's matched network
    contacts at this company (may be empty; the prompt still asks for alumni /
    diaspora / association paths). ``experience_text`` — the raw experience.md
    (schools + past employers are mined from it to seed alumni / past-colleague
    paths). ``cfg`` — the project config (optional; the user's target location
    scopes local meetups).

    Prompt-only: it asks the AI to produce the ranked paths, the LinkedIn search
    strings the user runs themselves, and the two drafts. No paste-back."""
    title = _job_field(job, "title") or "this role"
    company = _job_field(job, "company") or "the company"
    location = _job_field(job, "location")
    desc = _job_field(job, "description", "description_preview")
    if desc:
        desc = " ".join(desc.split())[:_MAX_DESC_CHARS]
    schools, employers = _schools_and_employers(experience_text)
    target_loc = ""
    if cfg:
        target_loc = str(cfg.get("location") or "").strip()

    sections: list[str] = [
        "You are helping me find the warmest path to a referral for a specific "
        "job. Referred candidates reach interviews at roughly ten times the "
        "cold-apply rate, so I want to reach a real person before I apply. Use "
        "ONLY the information below — do not invent names, contacts, or facts.",
        "",
        "## THE TARGET JOB",
        f"- Title: {title}",
        f"- Company: {company}",
    ]
    if location:
        sections.append(f"- Location: {location}")
    if desc:
        sections += ["", "### Job description (excerpt)", desc]

    contacts_block = _fmt_contacts(contacts)
    sections += ["", "## PEOPLE I ALREADY KNOW AT " + company.upper()]
    if contacts_block:
        sections.append(contacts_block)
    else:
        sections.append("(none in my imported network — find me indirect paths)")

    if schools:
        sections += ["", "## MY SCHOOLS (for alumni paths)", schools]
    if employers:
        sections += ["", "## MY PAST EMPLOYERS (for former-colleague paths)",
                     employers]
    if target_loc:
        sections += ["", "## WHERE I'M BASED (for local meetups/associations)",
                     target_loc]

    sections += ["", "## WHAT I NEED FROM YOU", _OUTPUT_CONTRACT.format(
        company=company, word_cap=_WORD_CAP)]
    return "\n".join(sections)


_OUTPUT_CONTRACT = """\
Give me a concrete plan, in this order:

1. **Warm paths, ranked.** List the most promising ways to reach someone at
   {company}, best first: (a) the direct contacts I listed above, (b) alumni from
   my schools who work there, (c) former colleagues from my past employers who may
   have moved there, (d) relevant professional associations / meetups / online
   communities. For each, say WHO to approach and WHY that path is warm.

2. **LinkedIn search strings I can run myself.** Give me exact search queries to
   paste into LinkedIn's search box in my own browser (I'll run them while logged
   in — you don't need account access). Cover: current {company} employees who
   share a school with me, current {company} employees who overlapped at a past
   employer, and recruiters/hiring managers for this role. Show the literal
   search string for each.

3. **Two outreach drafts, in my voice.** Write two short messages I could send
   (natural, specific, not salesy — the way I'd actually write):
   - an INFORMATIONAL-INTERVIEW ask (curious about their work / the team, no
     favor requested yet), and
   - a REFERRAL ask (I'm applying, would they be open to referring me).
   Each must be {word_cap} words or fewer. Reference something concrete from the
   job or company so it doesn't read as a template.

4. **The one-follow-up rule.** Remind me: send exactly ONE polite follow-up if I
   get no reply after about five business days, then stop and move to the next
   path. Always thank anyone who helps within 24 hours."""
