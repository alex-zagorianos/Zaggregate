"""Application copy pack (B7): a plaintext block the user pastes into an ATS /
application form so they aren't retyping the same identity fields on every apply.

Assembles, from data already on disk (NO AI, NO network):
  * contact fields — name / email / phone / location / links — parsed from
    experience.md's CONTACT section, with the project config as a fallback (config
    carries a name/location on some profiles);
  * work-history one-liners — the top lines of the WORK EXPERIENCE section;
  * education — the EDUCATION section, condensed to lines;
  * the tailored-resume file path for THIS queue item, when one was generated
    (the Apply Queue saves it onto the application as ``resume_path``).

Graceful throughout: a missing experience file, an empty section, or an absent
resume path simply omits those lines — never a placeholder like "Name: (unknown)".
stdlib + the existing experience parser only; tk-free and import-safe.
"""
from __future__ import annotations

import re


# The CONTACT fields we surface, in display order. Each maps a canonical label to
# the list-line keys it may appear under in experience.md's CONTACT section (the
# seed uses "Name/Email/Phone/Location/Links"; tolerate a couple of common drifts).
_CONTACT_FIELDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Name", ("name", "full name")),
    ("Email", ("email", "e-mail", "email address")),
    ("Phone", ("phone", "phone number", "mobile", "cell", "tel")),
    ("Location", ("location", "address", "city", "based in")),
    ("Links", ("links", "link", "website", "portfolio", "linkedin", "github")),
)


def _parse_contact_lines(contact_text: str) -> dict[str, str]:
    """Parse the CONTACT section body ('- Name: ...' markdown list lines, or plain
    'Name: ...' lines) into ``{canonical_label: value}``. Only non-empty values are
    kept, so an unfilled seed line ('- Email:') contributes nothing. The first
    non-empty match for a field wins."""
    found: dict[str, str] = {}
    for raw_line in (contact_text or "").splitlines():
        # Strip a leading markdown list marker ('- ', '* ') and whitespace.
        line = re.sub(r"^\s*[-*]\s*", "", raw_line).strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key_norm = key.strip().lower()
        value = value.strip()
        if not value:
            continue
        for label, aliases in _CONTACT_FIELDS:
            if label in found:
                continue
            if key_norm in aliases:
                found[label] = value
                break
    return found


def _section_lines(text: str, *, limit: int) -> list[str]:
    """The first ``limit`` non-empty, de-bulleted lines of a section body. Used to
    condense WORK EXPERIENCE / EDUCATION into a few one-liners without dumping the
    whole section into the pack. A blank section yields []."""
    out: list[str] = []
    for raw_line in (text or "").splitlines():
        line = re.sub(r"^\s*[-*]\s*", "", raw_line).strip()
        # Drop leftover markdown heading hashes (a stray '### Role' inside a body).
        line = re.sub(r"^#+\s*", "", line).strip()
        if not line:
            continue
        out.append(line)
        if len(out) >= limit:
            break
    return out


def build_copy_pack(experience: dict, config: dict, *,
                    resume_path: str | None = None) -> str:
    """Build the plaintext application copy pack.

    ``experience`` is the parsed experience.md dict (resume.experience_parser.
    load_experience); ``config`` is the project config (workspace.load_config) used
    only as a fallback for name/location. ``resume_path`` is the saved tailored
    resume path for this queue item, if any. Returns a ready-to-copy block; omits
    any line whose value is missing (never emits placeholder junk)."""
    experience = experience if isinstance(experience, dict) else {}
    config = config if isinstance(config, dict) else {}

    contact = _parse_contact_lines(experience.get("contact", "") or "")
    # Config fallbacks: some profiles carry a name/location in the project config
    # even when the experience CONTACT section is sparse.
    if "Name" not in contact and (config.get("name") or "").strip():
        contact["Name"] = str(config["name"]).strip()
    if "Location" not in contact and (config.get("location") or "").strip():
        contact["Location"] = str(config["location"]).strip()

    lines: list[str] = ["APPLICATION COPY PACK", ""]

    lines.append("-- Contact --")
    contact_written = False
    for label, _aliases in _CONTACT_FIELDS:
        value = contact.get(label)
        if value:
            lines.append(f"{label}: {value}")
            contact_written = True
    if not contact_written:
        lines.append("(add your contact details in experience.md → CONTACT)")

    work_lines = _section_lines(experience.get("work_experience", "") or "", limit=8)
    if work_lines:
        lines.extend(["", "-- Work history --"])
        lines.extend(work_lines)

    edu_lines = _section_lines(experience.get("education", "") or "", limit=6)
    if edu_lines:
        lines.extend(["", "-- Education --"])
        lines.extend(edu_lines)

    if resume_path and str(resume_path).strip():
        lines.extend(["", "-- Tailored resume --", str(resume_path).strip()])

    return "\n".join(lines).strip() + "\n"
