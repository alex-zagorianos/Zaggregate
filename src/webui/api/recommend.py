"""Discover routes — BYO-AI role recommendations (EXPERIMENTAL, S36c).

Thin HTTP shell over the top-level :mod:`recommend` module (prompt build /
reply parse / card actions). Web-only feature, deliberately isolated for
one-commit removal (see recommend.py's module docstring).

    GET  /api/recommend                 -> {ok, generated_at, interests, recommendations}
    POST /api/recommend/prompt {interests?} -> {ok, prompt}          [gated]
    POST /api/recommend/reply  {text}       -> {ok, ...state}        [gated]
    POST /api/recommend/<id>/apply-keywords -> {ok, added, keywords} [gated]
    POST /api/recommend/<id>/dismiss        -> {ok, dismissed}       [gated]
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

import recommend as core
from ..security import require_local_origin

recommend_bp = Blueprint("webui_recommend", __name__)


@recommend_bp.get("/recommend")
def get_state():
    state = core.load_state()
    return jsonify({"ok": True, **state})


@recommend_bp.post("/recommend/prompt")
@require_local_origin
def build_prompt():
    data = request.get_json(silent=True) or {}
    interests = str(data.get("interests") or "")
    if len(interests) > 4000:
        return jsonify({"ok": False,
                        "error": "interests note is too long (4000 chars max)"}), 400
    return jsonify({"ok": True, "prompt": core.build_recommend_prompt(interests)})


@recommend_bp.post("/recommend/reply")
@require_local_origin
def paste_reply():
    data = request.get_json(silent=True) or {}
    try:
        state = core.save_reply(str(data.get("text") or ""))
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, **state})


@recommend_bp.post("/recommend/<rec_id>/apply-keywords")
@require_local_origin
def apply_keywords(rec_id: str):
    try:
        result = core.apply_keywords(rec_id)
    except KeyError:
        return jsonify({"ok": False, "error": "unknown recommendation"}), 404
    return jsonify({"ok": True, **result})


@recommend_bp.post("/recommend/<rec_id>/dismiss")
@require_local_origin
def dismiss(rec_id: str):
    return jsonify({"ok": True, "dismissed": core.dismiss(rec_id)})
