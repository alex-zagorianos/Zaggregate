"""Tolerant import of an AI-returned re-rank file (CSV or JSON).

Validates the WS-1 job_key join (unmatched rows are REPORTED, never silently
dropped), clamps new_fit to 0-100, tolerates Excel artifacts (UTF-8 BOM, locale
decimal commas, trailing commas in JSON, reordered/extra columns), applies the
chosen merge policy, then hands the survivors to a writer (default:
tracker.service.apply_rerank_scores) that snapshots to score_history.
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field

_POLICIES = ("overwrite", "keep_existing", "add_only")


@dataclass
class ImportResult:
    matched: int = 0
    unmatched: list = field(default_factory=list)
    updated: int = 0
    skipped: int = 0
    errors: list = field(default_factory=list)


def _default_apply(updates, *, source="file_import"):
    from tracker import service
    return service.apply_rerank_scores(updates, source=source)


def _read_text(path) -> str:
    raw = open(path, "r", encoding="utf-8-sig").read()  # utf-8-sig strips a BOM
    return raw


def _coerce_int(value):
    """Tolerant int: locale decimal comma ('88,0'), stray spaces, floats."""
    if value is None:
        raise ValueError("missing")
    s = str(value).strip().strip('"').replace(" ", "")
    if not s:
        raise ValueError("blank")
    s = s.replace(",", ".")          # locale decimal comma -> dot
    return int(round(float(s)))


def _clamp_fit(value) -> int:
    return max(0, min(100, _coerce_int(value)))


def _parse_records(text: str) -> tuple[list[dict], list[str]]:
    """Return (records, errors). Each record is a dict with at least job_key."""
    errors: list[str] = []
    stripped = text.lstrip()
    if stripped[:1] in ("[", "{"):
        from claude_bridge import _extract_json
        try:
            data = json.loads(_extract_json(text, prefer="array"))
        except json.JSONDecodeError as e:
            return [], [f"JSON parse failed: {e}"]
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return [], ["Expected a JSON array of score objects."]
        return [d for d in data if isinstance(d, dict)], errors
    # CSV path
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "job_key" not in [
            (h or "").strip().lstrip("﻿") for h in reader.fieldnames]:
        return [], ["CSV is missing the required job_key column."]
    records = []
    for raw in reader:
        records.append({(k or "").strip().lstrip("﻿"): v for k, v in raw.items()})
    return records, errors


def _extras_for(rec, batch, service) -> str | None:
    """The extras JSON for one imported row: rank (mapped from new_rank) +
    rec_batch via service.rank_patch, plus tags. Tolerant of a bad rank cell —
    falls back to tags-only, then None."""
    rank_raw = rec.get("new_rank")
    tags = rec.get("tags")
    has_tags = bool(str(tags or "").strip())
    if str(rank_raw or "").strip():
        try:
            return json.dumps(service.rank_patch(
                _coerce_int(rank_raw), batch, tags if has_tags else None))
        except (ValueError, TypeError):
            pass
    if has_tags:
        return json.dumps({"tags": str(tags)})
    return None


def import_scores(path, rows_by_key: dict, *, policy: str = "overwrite",
                  _apply=None) -> ImportResult:
    if policy not in _POLICIES:
        raise ValueError(f"policy must be one of {_POLICIES}, got {policy!r}")
    from tracker import service
    apply = _apply or _default_apply
    batch = service.new_rec_batch()
    res = ImportResult()
    records, parse_errors = _parse_records(_read_text(path))
    res.errors.extend(parse_errors)

    updates: list[dict] = []
    for rec in records:
        key = (rec.get("job_key") or "").strip()
        if not key:
            res.errors.append("row with missing/blank job_key")
            continue
        row = rows_by_key.get(key)
        if row is None:
            res.unmatched.append({"job_key": key, **{k: rec.get(k) for k in
                                  ("new_fit", "fit_rationale")}})
            continue
        res.matched += 1
        current_fit = int(row.get("fit", -1) or -1)
        already_scored = current_fit >= 0
        if policy in ("keep_existing", "add_only") and already_scored:
            res.skipped += 1
            continue
        try:
            new_fit = _clamp_fit(rec.get("new_fit"))
        except (ValueError, TypeError):
            res.errors.append(f"{key}: bad new_fit {rec.get('new_fit')!r}")
            continue
        update = {"id": row["id"], "new_fit": new_fit,
                  "fit_rationale": str(rec.get("fit_rationale", "") or "").strip()}
        extras = _extras_for(rec, batch, service)
        if extras:
            update["extras"] = extras
        updates.append(update)

    res.updated = apply(updates, source="file_import") if updates else 0
    return res
