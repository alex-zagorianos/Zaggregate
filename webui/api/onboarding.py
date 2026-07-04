"""Onboarding API — first-run Setup wizard + AI express-lane, over HTTP (Phase 5).

Re-hosts the tk ``SetupWizard`` and ``ui.ai_setup`` express lane WITHOUT importing
Tk. The wizard's on-disk CONTRACT lives in the Tk-free ``ui.setup_wizard_core``
(build_preferences / _search_config / structure_resume_text / parse_salary_input /
prefill_from_existing / mark_onboarded / is_onboarded), which the web routes call
directly. Applying the wizard writes the SAME files the tk wizard writes — proven
by ``tests/webui/test_onboarding.py`` asserting the web round-trip against a golden
shape produced by calling ``build_preferences``/``_search_config`` directly.

Routes (mounted under ``/api``)
-------------------------------
Wizard:
* ``GET  /api/onboarding``                 -> ``{ok, onboarded, prefill:{...}}``  (read)
* ``POST /api/onboarding``                 -> apply answers (build_preferences +
                                              scaffold_preferences + _search_config +
                                              save_config + mark_onboarded)        [gate]
* ``POST /api/onboarding/resume-structure`` -> structure a pasted résumé          [gate]
* ``POST /api/onboarding/salary-parse``     -> parse a free-text salary floor      (read)

AI express-lane:
* ``GET  /api/ai-setup/prompt``            -> the copyable BYO-AI setup prompt      (read)
* ``POST /api/ai-setup/apply``             -> parse + apply the pasted config block [gate]

Security: mutating routes are origin-gated (``require_local_origin``). No secret
ever leaves the server (onboarding writes local files only; no key echoing). The
apply routes surface tolerant-parser warnings/errors instead of 500-ing.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

import workspace
from ui import setup_wizard_core as wizard
from ..security import require_local_origin

onboarding_bp = Blueprint("webui_onboarding", __name__)


# ── wizard: read prefill ──────────────────────────────────────────────────────
@onboarding_bp.get("/onboarding")
def onboarding_state():
    """Wizard state for pre-populating the web form: the onboarding-marker flag +
    the SAME prefill dict the tk wizard reads from existing preferences/config
    (``setup_wizard_core.prefill_from_existing``). READ-only, no gate. Returns
    ``{ok, onboarded, prefill:{roles, location, remote_ok, salary_min, about,
    industry, level}}``. A prefill read failure degrades to empty defaults (never
    500) — a fresh install has nothing to prefill."""
    try:
        prefill = wizard.prefill_from_existing()
    except Exception:  # noqa: BLE001 — a missing/partial project prefills empty
        prefill = {"roles": "", "location": "", "remote_ok": True,
                   "salary_min": "", "about": "", "industry": "", "level": ""}
    return jsonify({"ok": True, "onboarded": wizard.is_onboarded(),
                    "prefill": prefill})


def _answers_from_body(data: dict) -> dict:
    """Normalize the posted wizard answers into the ``answers`` dict
    ``build_preferences``/``_search_config`` expect. ``roles`` accepts a list OR a
    comma-joined string (the tk roles box is a single field the user comma-
    separates); everything else is coerced defensively. ``salary_min`` accepts an
    int OR a free-text string (parsed through ``parse_salary_input`` so "18/hr" /
    "90k" work exactly as the tk wizard's salary box does)."""
    raw_roles = data.get("roles")
    if isinstance(raw_roles, list):
        roles = [str(r).strip() for r in raw_roles if str(r).strip()]
    else:
        roles = [r.strip() for r in str(raw_roles or "").split(",") if r.strip()]

    sal = data.get("salary_min")
    if isinstance(sal, (int, float)) and sal:
        salary_min = int(sal)
    elif isinstance(sal, str) and sal.strip():
        salary_min = wizard.parse_salary_input(sal)
    else:
        salary_min = None

    return {
        "roles": roles,
        "location": str(data.get("location") or "").strip(),
        "remote_ok": bool(data.get("remote_ok", True)),
        "salary_min": salary_min,
        "industry": str(data.get("industry") or "").strip(),
        "level": str(data.get("level") or "").strip(),
        "about": str(data.get("about") or "").strip(),
        "resume_text": str(data.get("resume_text") or ""),
    }


@onboarding_bp.post("/onboarding")
@require_local_origin
def onboarding_apply():
    """Apply the wizard answers: write preferences.{json,md} + the search config +
    experience.md (if résumé text was supplied) and mark onboarding complete —
    identical to the tk wizard's ``apply()`` (both funnel through the same Tk-free
    core, so the on-disk contract is byte-identical). Pins the active project
    across the writes (S27-safe) so a background project switch can't misroute
    them. When the industry box is left blank it is auto-derived from the roles
    first (``_derive_industry`` — the exact step the tk wizard runs in _finish),
    so the web and tk paths converge on the same field. Body: ``{roles, location,
    remote_ok, salary_min, industry, level, about, resume_text?}``. Returns
    ``{ok, onboarded:true, resume_restructured:bool, industry_detected:str}``
    (``industry_detected`` is the auto-derived field, or '' when none — lets the
    UI echo the tk "Field detected" notice).
    """
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "expected a JSON object body"}), 400
    answers = _answers_from_body(data)

    # Derive the field from the roles when the optional industry box is blank —
    # the SAME step the tk wizard's _finish() runs before apply() (setup_wizard.py
    # L628), so a non-engineering user who lists roles but leaves industry empty
    # gets the same non-generic O*NET routing on the web path as in Tk instead of
    # being silently routed as an engineer. No-op when a field is already set or no
    # role resolves (keeps the eng path byte-identical).
    detected = wizard._derive_industry(answers.get("industry", ""),
                                       answers.get("roles", []))
    if detected:
        answers["industry"] = detected

    slug = workspace.active_slug()
    workspace.pin_active(slug)  # pin BEFORE the file writes (S27-safe)
    try:
        info = wizard.apply(answers)
    finally:
        workspace.unpin_active()
    return jsonify({"ok": True, "onboarded": True,
                    "resume_restructured": bool(info.get("resume_restructured")),
                    "industry_detected": detected or ""})


@onboarding_bp.post("/onboarding/resume-structure")
@require_local_origin
def onboarding_resume_structure():
    """Run a pasted plain-text résumé through ``structure_resume_text`` (the P0#1
    auto-structurer) and return the headed markdown WITHOUT saving it — a preview
    the wizard shows before apply. Body ``{text}``. Returns ``{ok, markdown,
    restructured:bool}``. Gated because it's part of the mutating wizard flow (and
    for symmetry), though it writes nothing itself. Blank text -> ``markdown:""``,
    ``restructured:false`` (never an error — an empty résumé is valid)."""
    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "")
    markdown, restructured = wizard.structure_resume_text(text)
    return jsonify({"ok": True, "markdown": markdown,
                    "restructured": bool(restructured)})


@onboarding_bp.post("/onboarding/salary-parse")
def onboarding_salary_parse():
    """Parse a free-text salary floor into ANNUAL dollars via ``parse_salary_input``
    (annual '90k'/'$90,000' or hourly '18/hr', annualized at 2080 h/yr). READ-only
    (pure parse, no side effect, no gate — matches the tk wizard's live-preview
    parse as the user types). Body ``{text}``. Returns ``{ok, annual:int|null,
    kind:'annual'|'hourly'|'none'}`` — ``kind`` reports how the input was read so
    the UI can echo "≈$37,440/yr from $18/hr"."""
    import re as _re
    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "")
    annual = wizard.parse_salary_input(text)
    if annual is None:
        kind = "none"
    elif wizard._HOURLY_INPUT_RE.search(text.strip().lower()):
        kind = "hourly"
    else:
        # A small bare number with no unit is annualized as hourly by the parser
        # (the "18" -> $37,440 case); report that honestly so the UI can explain it.
        m = _re.search(r"(\d[\d,]*\.?\d*)\s*(k)?", text.strip().lower())
        bare_small = bool(m and not m.group(2)
                          and float(m.group(1).replace(",", "") or 0) < 1000)
        kind = "hourly" if bare_small else "annual"
    return jsonify({"ok": True, "annual": annual, "kind": kind})


# ── AI express-lane ───────────────────────────────────────────────────────────
@onboarding_bp.get("/ai-setup/prompt")
def ai_setup_prompt():
    """The copyable BYO-AI setup prompt (``ai_setup.build_setup_prompt``) the user
    pastes into their own AI above their résumé + one sentence of intent. Static,
    no secrets, no I/O — READ-only. Returns ``{ok, prompt}``."""
    from ui.ai_setup import build_setup_prompt
    return jsonify({"ok": True, "prompt": build_setup_prompt()})


@onboarding_bp.post("/ai-setup/apply")
@require_local_origin
def ai_setup_apply():
    """Parse the pasted AI config block and APPLY it (``ai_setup.apply_setup`` ->
    build_preferences + _search_config + scaffold_preferences + save_config +
    mark_onboarded — the SAME on-disk contract as the manual wizard). The parser is
    strict-but-tolerant; a validation problem is a clean 400 carrying its
    human-actionable message (never a 500). Pins the active project across the
    writes (S27-safe). Body ``{text}``. Returns ``{ok, applied:{summary...}}`` on
    success. Empty/unparseable/invalid block -> 400 ``{ok:false, error:<message>}``.
    """
    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "")
    from ui.ai_setup import apply_setup, SetupBlockError

    slug = workspace.active_slug()
    workspace.pin_active(slug)
    try:
        applied = apply_setup(text)
    except SetupBlockError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    finally:
        workspace.unpin_active()
    return jsonify({"ok": True, "applied": applied})
