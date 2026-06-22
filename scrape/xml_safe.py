"""XXE / billion-laughs-safe XML parsing for untrusted feeds (Personio, sitemaps).

Prefers defusedxml (rejects DTDs + entity expansion). When defusedxml is not
installed, falls back to stdlib ElementTree AFTER stripping any DOCTYPE/DTD —
both XXE and entity-expansion attacks require a DTD, so a DTD-free document is
safe to parse with the stdlib. Returns a normal ElementTree.Element either way.
"""
from __future__ import annotations
import re
import xml.etree.ElementTree as _ET

try:
    from defusedxml.ElementTree import fromstring as _defused_fromstring
    _HAVE_DEFUSED = True
except ImportError:
    _HAVE_DEFUSED = False

# Matches a leading <!DOCTYPE ...> declaration (incl. an internal [...] subset).
_DOCTYPE_RE = re.compile(rb"<!DOCTYPE[^>\[]*(\[[^\]]*\])?[^>]*>", re.IGNORECASE | re.DOTALL)


def _to_bytes(data) -> bytes:
    return data.encode("utf-8") if isinstance(data, str) else data


def _safe_fromstring(data):
    """Parse untrusted XML safely. Accepts str or bytes; returns an Element."""
    raw = _to_bytes(data)
    if _HAVE_DEFUSED:
        return _defused_fromstring(raw)
    # No defusedxml: strip the DTD so entity/XXE payloads cannot execute.
    stripped = _DOCTYPE_RE.sub(b"", raw)
    parser = _ET.XMLParser()
    try:  # belt-and-suspenders: disable entity handling on the expat parser
        parser.parser.DefaultHandler = lambda data: None
        parser.parser.EntityDeclHandler = None
    except (AttributeError, TypeError):
        pass
    return _ET.fromstring(stripped, parser=parser)
