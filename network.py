"""Referral network — a local, user-level contact book for warm-path outreach
(B4 beta buildout).

The user exports their LinkedIn Connections (or Google Contacts) as a CSV, the
web UI reads the file client-side and POSTs the raw text, and this module parses
it into a flat list of ``{name, company, position, source}`` contacts stored in a
single JSON file. When a job's company matches a contact's company (conservative
canonicalization — see :func:`company_key`), the inbox/application detail panes
surface "N people in your network work here" so the user can ask for a referral
(referred candidates reach interview at ~10x the cold-apply rate).

DESIGN — deliberately isolated + privacy-first:
  * Import-safe: no tkinter, no network, nothing cached at import. Every path
    resolves through :func:`_store_path` per call.
  * USER-LEVEL storage (``config.USER_DATA_DIR / network.json``), NOT per-project:
    your connections are the same whichever campaign you're running. The file is
    gitignored (dev USER_DATA_DIR = repo root, so ``/network.json`` is excluded by
    an anchored rule alongside ``/preferences.json`` etc.) and never bundled into
    the distributable.
  * The whole feature is one-commit removable: this module + ``webui/api/network``
    + the frontend Sources card + the detail-pane blocks + one registry line.

The company canonicalizer is reused from ``coverage.entity.canonicalize_company``
(cleanco ``basename`` + NFKD casefold + punctuation strip + alias map) — the same
identity the coverage/job_key layer already uses, so a network match and a job
row agree on what "the same company" means.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import config

_STORE_NAME = "network.json"
_SOURCES = ("linkedin", "google")


# ── company canonicalization (reused, with a safe fallback) ────────────────────

def company_key(name: str) -> str:
    """Conservative canonical key for a company name — lowercase, punctuation and
    legal-suffix stripped (Inc/LLC/Ltd/GmbH...), NFKD-folded, alias-mapped. Reuses
    ``coverage.entity.canonicalize_company`` so a network match and a job row use
    the SAME notion of company identity.

    "" for an empty/whitespace name (an unmatchable contact). Falls back to a
    minimal inline normalizer only if the coverage module can't import (it never
    should in-tree) so this module stays independently import-safe."""
    if not name or not str(name).strip():
        return ""
    try:
        from coverage.entity import canonicalize_company
        return canonicalize_company(str(name))
    except Exception:
        # Last-resort fallback: lowercase + collapse whitespace. Never crash the
        # network layer on a canonicalizer import hiccup.
        return " ".join(str(name).lower().split())


# ── CSV parsing ────────────────────────────────────────────────────────────────

def _norm_header(h: str) -> str:
    return (h or "").strip().strip("﻿").lower()


def _strip_linkedin_preamble(text: str) -> str:
    """LinkedIn's Connections.csv prepends a 'Notes:' preamble block (a few lines
    of guidance, then a blank line) BEFORE the real ``First Name,Last Name,...``
    header row. Drop everything up to and including that blank line when a preamble
    is detected; otherwise return the text unchanged.

    Detection is tolerant: we look for a line that starts with 'Notes:' near the
    top, and skip to the first blank line after it. If a real header line appears
    first, there's no preamble and we leave the text as-is."""
    lines = text.splitlines()
    # Find a 'Notes:' line within the first few rows.
    notes_idx = None
    for i, ln in enumerate(lines[:6]):
        if ln.strip().lower().startswith("notes:"):
            notes_idx = i
            break
    if notes_idx is None:
        return text
    # Skip to the first blank line at/after the Notes line; the header follows it.
    for j in range(notes_idx, len(lines)):
        if not lines[j].strip():
            return "\n".join(lines[j + 1:])
    # No blank separator found -> nothing usable after the preamble.
    return ""


# Column-name candidates (case-insensitive), most-specific first. Covers LinkedIn
# and Google Contacts variants plus common drift.
_NAME_COLS = ("name", "full name")
_FIRST_COLS = ("first name", "given name")
_LAST_COLS = ("last name", "family name", "surname")
_COMPANY_COLS = (
    "company", "organization 1 - name", "organization name",
    "organization", "current company", "employer",
)
_POSITION_COLS = (
    "position", "organization 1 - title", "title", "job title",
    "organization title", "role",
)


def _pick(row: dict, candidates) -> str:
    """First non-empty value among the candidate column names (already normalized
    keys), else ''."""
    for c in candidates:
        v = row.get(c)
        if v and str(v).strip():
            return str(v).strip()
    return ""


def _row_name(row: dict) -> str:
    """A contact's display name: an explicit full-name column wins, else First +
    Last joined."""
    full = _pick(row, _NAME_COLS)
    if full:
        return full
    first = _pick(row, _FIRST_COLS)
    last = _pick(row, _LAST_COLS)
    return " ".join(p for p in (first, last) if p).strip()


def parse_connections_csv(text: str, source: str = "linkedin") -> list[dict]:
    """Parse a LinkedIn Connections.csv or Google Contacts CSV into a list of
    ``{name, company, position, source, company_key}`` dicts.

    Tolerant by design (inclusion over precision):
      * strips LinkedIn's 'Notes:' preamble before the header row;
      * matches columns case-insensitively and in any order (First/Last vs Name,
        Company vs 'Organization 1 - Name', Position vs 'Organization 1 - Title');
      * a row with a name but NO company is KEPT (stored, just unmatchable) — never
        silently dropped;
      * a row with neither a name nor a company is skipped (nothing to store).

    ``source`` tags each contact ('linkedin'|'google'); an unknown value is coerced
    to 'linkedin'. Never raises on malformed rows — a bad row is skipped, not fatal."""
    src = source if source in _SOURCES else "linkedin"
    raw = (text or "")
    if not raw.strip():
        return []
    if src == "linkedin":
        raw = _strip_linkedin_preamble(raw)
    if not raw.strip():
        return []

    reader = csv.reader(io.StringIO(raw))
    try:
        header = next(reader)
    except StopIteration:
        return []
    keys = [_norm_header(h) for h in header]

    out: list[dict] = []
    for cells in reader:
        if not any((c or "").strip() for c in cells):
            continue
        row = {keys[i]: cells[i] for i in range(min(len(keys), len(cells)))}
        name = _row_name(row)
        company = _pick(row, _COMPANY_COLS)
        if not name and not company:
            continue
        position = _pick(row, _POSITION_COLS)
        out.append({
            "name": name,
            "company": company,
            "position": position,
            "source": src,
            "company_key": company_key(company),
        })
    return out


# ── storage ────────────────────────────────────────────────────────────────────

def _store_path() -> Path:
    """The user-level network store (``USER_DATA_DIR/network.json``). Read config
    lazily (not frozen at import) so a test that repoints ``config.USER_DATA_DIR``
    lands the file under its tmp dir."""
    return Path(config.USER_DATA_DIR) / _STORE_NAME


def load() -> dict:
    """The saved network: ``{contacts:[...], last_import, total}``. Tolerant — a
    missing/corrupt file is an empty store, never an error."""
    try:
        raw = json.loads(_store_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"contacts": [], "last_import": None}
    if not isinstance(raw, dict):
        return {"contacts": [], "last_import": None}
    contacts = [c for c in (raw.get("contacts") or [])
                if isinstance(c, dict) and (c.get("name") or c.get("company"))]
    return {"contacts": contacts, "last_import": raw.get("last_import")}


def _save(store: dict) -> None:
    p = _store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(store, indent=2, ensure_ascii=False) + "\n",
                 encoding="utf-8")


def clear() -> int:
    """Forget the whole network (delete the store). Returns the count removed.
    Idempotent — clearing an empty/absent store returns 0, never errors."""
    store = load()
    n = len(store["contacts"])
    _save({"contacts": [], "last_import": None})
    return n


def _dedup_key(contact: dict) -> tuple[str, str, str]:
    """Merge identity for a contact: (lowercased name, canonical company). Two
    imports of the same person at the same company collapse to one row.

    NO-COMPANY contacts fold the position into the key instead (S37 Phase-2
    review): with company_key == '' the old key collapsed two distinct people
    who merely share a name (two blank-company "Sarah Chen" rows) — silent
    data loss. Same person re-imported (same name + position, no company)
    still merges; distinct positions stay distinct."""
    name = (contact.get("name") or "").strip().lower()
    ckey = contact.get("company_key") or company_key(contact.get("company") or "")
    if ckey:
        return (name, ckey, "")
    return (name, "", (contact.get("position") or "").strip().lower())


def import_text(text: str, source: str = "linkedin") -> dict:
    """Parse ``text`` as a connections CSV and MERGE the contacts into the store
    (never destructive — call :func:`clear` to reset). De-duplicates by
    (name, canonical-company) across the existing store AND within the incoming
    batch. Returns ``{added, total}``.

    ``source`` picks the parser variant + tags the new rows ('linkedin'|'google')."""
    incoming = parse_connections_csv(text, source)
    store = load()
    existing = store["contacts"]
    seen = {_dedup_key(c) for c in existing}
    added = 0
    for c in incoming:
        k = _dedup_key(c)
        if k in seen:
            continue
        seen.add(k)
        existing.append(c)
        added += 1
    store["last_import"] = {
        "source": source if source in _SOURCES else "linkedin",
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "added": added,
    }
    _save({"contacts": existing, "last_import": store["last_import"]})
    return {"added": added, "total": len(existing)}


# ── matching ───────────────────────────────────────────────────────────────────

def matches_for(company: str) -> list[dict]:
    """Contacts whose company canonicalizes to the same key as ``company``.
    Empty list for a blank company or a company with a blank key (an unmatchable
    contact never matches an unmatchable job — no false positives). Cheap: one
    canonicalize + a linear scan."""
    key = company_key(company)
    if not key:
        return []
    return [c for c in load()["contacts"]
            if (c.get("company_key") or company_key(c.get("company") or "")) == key]


def match_counts(companies) -> dict:
    """Bulk match count per company name (for annotating a list of rows without a
    per-row full scan). Returns ``{company_name: count}`` for every input name that
    has >=1 match; names with 0 matches are omitted. Builds one key->count index
    over the store, then looks each input up."""
    index: dict[str, int] = {}
    for c in load()["contacts"]:
        k = c.get("company_key") or company_key(c.get("company") or "")
        if k:
            index[k] = index.get(k, 0) + 1
    out: dict = {}
    for name in companies or []:
        k = company_key(name)
        if k and index.get(k):
            out[name] = index[k]
    return out


def summary() -> dict:
    """A compact overview for the Sources card: ``{total, companies, last_import}``
    where ``companies`` is the count of DISTINCT matchable companies known."""
    store = load()
    contacts = store["contacts"]
    keys = {c.get("company_key") or company_key(c.get("company") or "")
            for c in contacts}
    keys.discard("")
    return {"total": len(contacts),
            "companies": len(keys),
            "last_import": store["last_import"]}
