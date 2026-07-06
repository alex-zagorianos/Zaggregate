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
    """Parse a free-text salary floor into ANNUAL dollars via
    ``parse_salary_input_detailed`` (annual '90k'/'$90,000' or hourly '18/hr',
    annualized at 2080 h/yr). READ-only (pure parse, no side effect, no gate —
    matches the tk wizard's live-preview parse as the user types). Body
    ``{text}``. Returns ``{ok, annual:int|null, kind:'annual'|'hourly'|'none'}``
    — ``kind`` reports how the input was read so the UI can echo "≈$37,440/yr
    from $18/hr". ``kind`` is read directly off the parser's own classification
    (not re-derived) so it can never disagree with ``annual``."""
    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "")
    annual, kind = wizard.parse_salary_input_detailed(text)
    return jsonify({"ok": True, "annual": annual, "kind": kind})


# ── AI express-lane ───────────────────────────────────────────────────────────
@onboarding_bp.get("/ai-setup/prompt")
def ai_setup_prompt():
    """The copyable BYO-AI setup prompt the user pastes into their own AI above
    their résumé + one sentence of intent. Static, no secrets, no I/O — READ-only.

    Two shapes, selected by the ``full`` query flag (S40 AI-first setup):
      * default            -> ``build_setup_prompt()`` — the config-only ```json
                              contract (the standalone express-lane / apply pairing).
      * ``?full=1``        -> ``build_full_setup_prompt()`` — config ```json block
                              PLUS a ```seeds starter-company fence, the ONE prompt
                              whose reply drives apply-full (config + companies +
                              first search). Read-only; it just returns a different
                              static string, so no gate.

    Returns ``{ok, prompt}``."""
    from ui.ai_setup import build_setup_prompt, build_full_setup_prompt
    full = str(request.args.get("full", "")).strip().lower() in ("1", "true", "yes")
    prompt = build_full_setup_prompt() if full else build_setup_prompt()
    return jsonify({"ok": True, "prompt": prompt})


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


@onboarding_bp.post("/ai-setup/apply-full")
@require_local_origin
def ai_setup_apply_full():
    """S40 AI-first setup: ONE paste onboards AND starts searching. The pasted
    reply carries BOTH the search config (```json block) and a starter company
    list (```seeds block) — this splits them (``ai_setup.split_full_reply``),
    applies the config synchronously (the SAME 400-on-missing-config contract as
    ``/ai-setup/apply`` — seeds ALONE never onboard), counts the seed lines, then
    (``autorun`` default true) chains ONE exclusive ``("first_run", slug)`` job:

      phase 1 (only when seeds were present): ``apply_seed_lines(..., probe=True)``
              — detect/probe/save each careers URL, logging start + per-outcome
              counts + done into the job console;
      phase 2: the daily ingest, invoked through the SAME shared helpers the
              ``/runs/daily`` route uses (``resolve_daily_knobs`` / ``run_daily_ingest``
              in ``webui.api.runs``) so the first-run quick pass is identical.

    The config apply is synchronous (fast, and its result must reach the response);
    the probe + ingest are the slow work, so they run on the background job whose
    progress streams over SSE (job_id in the response, attach with /jobs/<id>/events).

    Body ``{text, autorun?: true}``. Returns
    ``{ok, applied:{…same shape as /ai-setup/apply…}, seed_count, job_id, job_error?}``.

    * No config block -> 400 ``{ok:false, error:<human message>}`` (nothing applied,
      no job) — identical to ``/ai-setup/apply``.
    * ``autorun:false`` -> config applied, seeds counted, but NO job (``job_id:null``).
    * Another engine run already in flight (JobConflict) -> still ``ok`` with
      ``job_id:null`` and ``job_error:"another run is in progress"`` (the config IS
      applied; the search just couldn't start right now — the user can retry it).
    """
    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "")
    autorun = bool(data.get("autorun", True))

    from ui.ai_setup import (apply_setup, apply_seed_lines, split_full_reply,
                             SetupBlockError)

    config_text, seed_text = split_full_reply(text)

    # Apply the config synchronously. A missing/invalid config block is a 400 with
    # the SAME human message contract as /ai-setup/apply — seeds alone do NOT
    # onboard (per the plan). We pass the ORIGINAL pasted text to apply_setup (not
    # config_text) so its own tolerant parser + error messages are unchanged; the
    # split's config_text only confirms whether a config object is present at all.
    slug = workspace.active_slug()
    workspace.pin_active(slug)
    try:
        applied = apply_setup(text)
    except SetupBlockError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    finally:
        workspace.unpin_active()

    # Count seed lines WITHOUT probing (probing is phase 1 of the job — doing it
    # here would block the response on live network). One line per careers URL.
    seed_lines = [ln for ln in seed_text.splitlines() if ln.strip()]
    seed_count = len(seed_lines)
    # The applied field routes the seeded companies' industry tag (parity with the
    # standalone seed flow, which tags by the user's field).
    industry = applied.get("field") or ""

    if not autorun:
        return jsonify({"ok": True, "applied": applied,
                        "seed_count": seed_count, "job_id": None})

    from ..jobs import runner, JobConflict
    from . import runs as runs_mod

    knobs, first_run_quick = runs_mod.resolve_daily_knobs(slug)

    def _fn(handle):
        # Phase 1 — seed the starter company registry (probe live, save with the
        # P0-6 verified-by-default gate). Only when the reply carried seeds.
        seed_summary = None
        if seed_text.strip():
            handle.log(f"Seeding {seed_count} starter companies…")
            seed_summary = apply_seed_lines(seed_text, industry=industry,
                                            probe=True)
            handle.log(
                f"Companies: {seed_summary['verified']} verified, "
                f"{seed_summary['unverified']} unverified, "
                f"{seed_summary['skipped']} already known, "
                f"{seed_summary['rejected']} rejected "
                f"({seed_summary['added']} added).")
            handle.log("Company seeding done.")
        # Phase 2 — the first daily search, through the SAME shared helpers the
        # /runs/daily route uses (quick-pass decision + ingest), so behavior is
        # identical whether the run starts here or from the Inbox button.
        rc = runs_mod.run_daily_ingest(handle, slug, knobs=knobs,
                                       first_run_quick=first_run_quick)
        return {"rc": rc, "slug": slug, "seed_count": seed_count,
                "seeds": seed_summary}

    try:
        job_id = runner.start("first_run", str(slug or ""), _fn, exclusive=True)
    except JobConflict as jc:
        # The config is already applied; the search just can't start while another
        # engine run holds the exclusive slot. Report it, don't fail the onboard.
        return jsonify({"ok": True, "applied": applied,
                        "seed_count": seed_count, "job_id": None,
                        "job_error": "another run is in progress"})
    return jsonify({"ok": True, "applied": applied,
                    "seed_count": seed_count, "job_id": job_id})
