"""Warm-path + follow-up + interview-prep outreach prompts — BYO-AI, prompt-only.

Builds copy-into-your-AI prompts that turn a target job + the user's network +
their own background into actionable outreach. Prompt-only (no paste-back round
trip, no AI API call): the user copies the prompt into whatever AI they already
use and reads the answer — the value is the STRUCTURED ASK, not automation.

Three builders live here:
  * ``build_warm_path_prompt`` (B4) — ranked warm paths to a referral, LinkedIn
    search strings the user runs themselves, and two outreach drafts;
  * ``build_followup_prompt`` (B5) — a post-apply FOLLOW-UP or a post-interview
    THANK-YOU note, auto-selected by the application's status + interview rounds,
    with the etiquette rules baked in (exactly one follow-up; thank-you within
    24h; <=120 words; warm/professional; no groveling);
  * ``build_interview_prep_prompt`` (B5) — likely interview areas, ten practice
    questions (behavioral + role-specific), strong-answer sketches grounded in
    the USER'S actual experience, questions to ask the interviewer, and red flags
    to listen for.

Import-safe (no tkinter, no network).
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


# ── follow-up / thank-you prompt (B5) ───────────────────────────────────────────

# An interview has demonstrably happened once the application reaches (or passes)
# one of these statuses — so a THANK-YOU, not a cold follow-up, is what's owed.
_INTERVIEW_STATUSES = frozenset(
    {"phone_screen", "interview", "offer", "accepted"})


def _rounds_from_row(app_row: dict):
    """The interview rounds attached to an application row, tolerant of shape: the
    route folds them in under ``_rounds`` (a list) or ``rounds`` before calling.
    Returns a list (possibly empty) — never raises on a missing/odd value."""
    rounds = app_row.get("_rounds")
    if rounds is None:
        rounds = app_row.get("rounds")
    return list(rounds) if isinstance(rounds, (list, tuple)) else []


def followup_stage(app_row: dict) -> str:
    """Classify which note is owed: ``"thank_you"`` after an interview has
    happened, else ``"followup"`` (a post-apply nudge). An interview counts as
    having happened when the application carries at least one interview round OR
    its status is at/past an interview stage (phone_screen / interview / offer /
    accepted). Everything else — interested, applied, and the terminal
    rejected/withdrawn/ghosted — is a plain follow-up."""
    status = str(app_row.get("status") or "").strip().lower()
    if _rounds_from_row(app_row):
        return "thank_you"
    if status in _INTERVIEW_STATUSES:
        return "thank_you"
    return "followup"


def _round_context(app_row: dict) -> str:
    """A one-line summary of the most recent interview round (kind + when), used to
    ground the thank-you so it references the actual conversation. Empty when there
    are no rounds."""
    rounds = _rounds_from_row(app_row)
    if not rounds:
        return ""
    last = rounds[-1]
    if not isinstance(last, dict):
        return ""
    kind = str(last.get("kind") or "").strip()
    when = str(last.get("scheduled_at") or "").strip()
    interviewer = str(last.get("interviewer") or "").strip()
    bits = []
    if kind:
        bits.append(f"a {kind} round")
    if interviewer:
        bits.append(f"with {interviewer}")
    if when:
        bits.append(f"on {when}")
    return " ".join(bits)


def build_followup_prompt(app_row: dict, stage: str | None = None) -> str:
    """A copy-into-your-AI prompt that drafts the RIGHT outreach note for a tracked
    application. ``stage`` forces the note when given (``"thank_you"`` /
    ``"followup"``); otherwise it is auto-selected from the application's status +
    interview rounds via :func:`followup_stage`.

    ``app_row`` — a tracked-application dict (title/company/status; ``description``
    used when present; interview rounds folded in under ``_rounds``/``rounds`` by
    the route). The etiquette rules are baked into the ask so the AI can't talk the
    user into a bad move: exactly ONE follow-up, a thank-you within 24 hours,
    <=120 words, warm and professional, and no groveling / no apologizing for
    following up. Prompt-only: no paste-back."""
    stage = stage if stage in ("thank_you", "followup") else followup_stage(app_row)
    title = _job_field(app_row, "title") or "the role"
    company = _job_field(app_row, "company") or "the company"
    contact = _job_field(app_row, "contact")
    desc = _job_field(app_row, "description", "description_preview")
    if desc:
        desc = " ".join(desc.split())[:_MAX_DESC_CHARS]

    sections: list[str] = [
        "You are helping me write a short, genuine outreach note about a job I'm "
        "pursuing. Use ONLY the details below — do not invent names, dates, or "
        "facts. Write in a warm, professional voice that sounds like a real "
        "person, not a template.",
        "",
        "## THE APPLICATION",
        f"- Role: {title}",
        f"- Company: {company}",
    ]
    if contact:
        sections.append(f"- My contact there: {contact}")
    if stage == "thank_you":
        rc = _round_context(app_row)
        if rc:
            sections.append(f"- Most recent conversation: {rc}")
    if desc:
        sections += ["", "### Job description (excerpt)", desc]

    body = _THANK_YOU_CONTRACT if stage == "thank_you" else _FOLLOWUP_CONTRACT
    sections += ["", "## WHAT I NEED FROM YOU",
                 body.format(company=company, title=title, word_cap=_WORD_CAP)]
    return "\n".join(sections)


_FOLLOWUP_CONTRACT = """\
Draft ONE post-application follow-up note I can send after applying to {title} at
{company} and hearing nothing back. Follow these rules exactly:

- **{word_cap} words or fewer.** Short and easy to reply to.
- **Warm and professional**, not stiff and not overly familiar.
- **No groveling.** Do not apologize for reaching out, do not sound desperate,
  do not say sorry to bother them. I'm a strong candidate touching base, not a
  supplicant.
- **Reaffirm my fit in one line** — reference something concrete about the role
  or company so it doesn't read as a form letter.
- **One clear, low-pressure ask** (e.g. whether they can share timing or next
  steps).

Then remind me of the etiquette: send exactly ONE follow-up. If I still hear
nothing after this, I stop and move on — a second and third chase hurts more than
it helps. Give me the note, then that one-line reminder."""

_THANK_YOU_CONTRACT = """\
Draft a post-interview THANK-YOU note for my interview for {title} at {company}.
Follow these rules exactly:

- **Send within 24 hours** of the interview — remind me of that up top.
- **{word_cap} words or fewer.** Sincere and specific beats long.
- **Warm and professional**, in my own natural voice.
- **No groveling** and no over-apologizing — this is gratitude plus a light
  reinforcement of my fit, not begging for the job.
- **Reference something specific from the conversation** (a topic we discussed or
  something I learned) so it's clearly not a template.
- **Reaffirm my interest and one relevant strength** in a single line, and offer
  to answer anything follow-up.

Then remind me of the etiquette: one thank-you per interviewer within 24 hours;
if I don't hear back afterward, exactly ONE polite follow-up later, then stop.
Give me the note, then that one-line reminder."""


# ── interview prep prompt (B5) ──────────────────────────────────────────────────

def build_interview_prep_prompt(app_row: dict, experience_text: str = "") -> str:
    """A copy-into-your-AI prompt that turns a role + company + stored job
    description into a focused interview-prep brief grounded in the USER'S actual
    background.

    ``app_row`` — a tracked-application dict (title/company; ``description`` /
    ``description_preview`` used when present). ``experience_text`` — the raw
    experience.md; the user's schools + past employers + work history are mined
    from it so the AI's strong-answer sketches draw on REAL experience rather than
    inventing a candidate. The output contract asks for: likely interview areas,
    ten practice questions (behavioral + role-specific), strong-answer sketches
    tied to my experience, questions I should ask the interviewer, and red flags
    to listen for. Prompt-only: no paste-back."""
    title = _job_field(app_row, "title") or "this role"
    company = _job_field(app_row, "company") or "the company"
    location = _job_field(app_row, "location")
    desc = _job_field(app_row, "description", "description_preview")
    if desc:
        desc = " ".join(desc.split())[:_MAX_DESC_CHARS]
    schools, employers = _schools_and_employers(experience_text)

    sections: list[str] = [
        "You are my interview coach. Help me prepare for an interview using ONLY "
        "the details below — do not invent facts about me or the company. Ground "
        "every suggested answer in MY actual experience as given; where my "
        "background doesn't cover something, say so and suggest how I'd honestly "
        "bridge it rather than fabricating.",
        "",
        "## THE INTERVIEW",
        f"- Role: {title}",
        f"- Company: {company}",
    ]
    if location:
        sections.append(f"- Location: {location}")
    if desc:
        sections += ["", "### Job description (excerpt)", desc]
    if employers:
        sections += ["", "## MY WORK EXPERIENCE", employers]
    if schools:
        sections += ["", "## MY EDUCATION", schools]

    sections += ["", "## WHAT I NEED FROM YOU",
                 _PREP_CONTRACT.format(company=company, title=title)]
    return "\n".join(sections)


_PREP_CONTRACT = """\
Give me a focused prep brief, in this order:

1. **Likely interview areas.** From the role, the company, and the job
   description, list the 4-6 topics this interview will most likely probe (mix of
   technical/role-specific and behavioral). Say WHY each is likely.

2. **Ten practice questions.** Write exactly ten questions I should be ready for:
   a mix of BEHAVIORAL questions (e.g. tell-me-about-a-time) and ROLE-SPECIFIC
   questions drawn from the job description for {title}. Number them.

3. **Strong-answer sketches from MY experience.** For each of the ten, sketch a
   strong answer that draws on MY actual work history and education above — name
   the specific role/project/school it should come from. Use the STAR shape
   (situation, task, action, result) for the behavioral ones. If my background
   genuinely doesn't cover a question, say so and suggest an honest way to bridge
   it — never invent an accomplishment.

4. **Questions I should ask them.** Give me 5-6 sharp questions to ask the
   interviewer about {company}, the team, and the role that show I've done my
   homework and help me judge if it's a fit.

5. **Red flags to listen for.** List the warning signs I should watch for in
   their answers (about the team, workload, turnover, the role's realism) so I
   can evaluate {company} as much as they're evaluating me."""
