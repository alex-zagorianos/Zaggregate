"""Boolean keyword queries — Indeed/LinkedIn-style precision for the keyword
strings in user_config.json and CLI --keywords.

Supports: "exact phrase", OR, AND (also implicit between adjacent terms),
NOT / leading '-' for negation, and ( ) grouping. Precedence: NOT > AND > OR.

A plain keyword with no operators behaves exactly like the old matcher: every
significant word must appear (trailing 's' stripped from long words so
"controls engineer" still matches "Control Systems Engineer"), so existing
configs keep working unchanged.

    parse('"controls engineer" OR automation NOT senior').matches(title)
"""
from functools import lru_cache
import re

_TOKEN_RE = re.compile(r'"[^"]*"|[()]|[^\s()]+')
_OPS = {"AND", "OR", "NOT"}


# Word-START-boundary matching. Raw substring matching gave false hits where a
# term appeared in the MIDDLE/END of a longer word ("rn" inside inteRNship, "ros"
# inside "process", "pid" inside "rapid"). Anchoring at a word START (a preceding
# non-word char) kills exactly those, while still allowing a term to be the PREFIX
# of a longer word (keyword "robot" -> "Robotics", "develop" -> "Developer") so
# keyword seeding recall is preserved. This is deliberately LOOSER than the
# scorer's full \\b...\\b skill matcher: a positive title/keyword query wants
# recall; a blocklist wants precision. Cached per (text, fold_s).
_bound_cache: dict[tuple[str, bool], re.Pattern] = {}


def _bound(text: str, fold_s: bool = False) -> re.Pattern:
    """Word-START matcher for `text` (leading boundary, no trailing anchor). When
    `fold_s`, a trailing 's' on the stem is optional so the legacy fold still works
    BOTH ways: query 'controls' matches 'Control Systems' AND the exact 'Controls'.
    Lookbehind on a non-word char (not \\b) so a term starting with a non-word
    char ('.net', 'c++') still anchors."""
    key = (text, fold_s)
    pat = _bound_cache.get(key)
    if pat is None:
        body = re.escape(text) + ("s?" if fold_s else "")
        pat = re.compile(r"(?<!\w)" + body)
        _bound_cache[key] = pat
    return pat


# ── AST nodes ─────────────────────────────────────────────────────────────────
class _Leaf:
    __slots__ = ("text", "phrase")

    def __init__(self, text: str, phrase: bool = False):
        self.text = text.lower()
        self.phrase = phrase

    def matches(self, hay: str) -> bool:
        if self.phrase:
            # Phrases match contiguously, at word boundaries (an anchored phrase
            # can't be a fragment of a larger word run).
            return bool(_bound(self.text).search(hay))
        w = self.text
        # mirror the legacy per-token rule: strip a trailing 's' on longer words,
        # then require a whole-word match with an optional trailing 's' so
        # "controls engineer" still matches BOTH "Control Systems Engineer" and
        # "Controls Engineer", while "rn" no longer matches "internship".
        if len(w) > 3 and w.endswith("s"):
            return bool(_bound(w[:-1], fold_s=True).search(hay))
        return bool(_bound(w).search(hay))

    def positive_terms(self):
        return [self.text]


class _Not:
    __slots__ = ("child",)

    def __init__(self, child):
        self.child = child

    def matches(self, hay):
        return not self.child.matches(hay)

    def positive_terms(self):
        return []


class _And:
    __slots__ = ("kids",)

    def __init__(self, kids):
        self.kids = kids

    def matches(self, hay):
        return all(k.matches(hay) for k in self.kids)

    def positive_terms(self):
        return [t for k in self.kids for t in k.positive_terms()]


class _Or:
    __slots__ = ("kids",)

    def __init__(self, kids):
        self.kids = kids

    def matches(self, hay):
        return any(k.matches(hay) for k in self.kids)

    def positive_terms(self):
        return [t for k in self.kids for t in k.positive_terms()]


class _Always:
    def matches(self, hay):
        return True

    def positive_terms(self):
        return []


class Query:
    """A parsed keyword query. matches() is case-insensitive."""
    __slots__ = ("root", "source")

    def __init__(self, root, source=""):
        self.root = root
        self.source = source

    def matches(self, haystack: str) -> bool:
        return self.root.matches((haystack or "").lower())

    def positive_terms(self):
        """Non-negated leaf terms/phrases (for title scoring & display)."""
        return self.root.positive_terms()


# ── Tokenizer + recursive-descent parser ──────────────────────────────────────
def _tokenize(q: str):
    """-> list of (kind, value): kind in WORD/PHRASE/AND/OR/NOT/MINUS/LP/RP."""
    out = []
    for raw in _TOKEN_RE.findall(q):
        if raw == "(":
            out.append(("LP", raw))
        elif raw == ")":
            out.append(("RP", raw))
        elif raw.startswith('"'):
            phrase = raw.strip('"')
            if phrase:                          # drop empty "" (would match every job)
                out.append(("PHRASE", phrase))
        elif raw.upper() in _OPS:
            out.append((raw.upper(), raw))
        elif raw.startswith("-") and len(raw) > 1:
            out.append(("MINUS", raw))
            out.append(("WORD", raw[1:]))
        else:
            out.append(("WORD", raw))
    return out


def _starts_atom(tok) -> bool:
    return tok[0] in ("WORD", "PHRASE", "NOT", "MINUS", "LP")


def _parse_or(toks, i):
    node, i = _parse_and(toks, i)
    kids = [node]
    while i < len(toks) and toks[i][0] == "OR":
        rhs, i = _parse_and(toks, i + 1)
        kids.append(rhs)
    return (kids[0] if len(kids) == 1 else _Or(kids)), i


def _parse_and(toks, i):
    node, i = _parse_not(toks, i)
    kids = [node]
    while i < len(toks):
        if toks[i][0] == "AND":
            i += 1
        elif _starts_atom(toks[i]):
            pass  # implicit AND
        else:
            break
        if i >= len(toks) or not _starts_atom(toks[i]):
            break
        rhs, i = _parse_not(toks, i)
        kids.append(rhs)
    return (kids[0] if len(kids) == 1 else _And(kids)), i


def _parse_not(toks, i):
    if i < len(toks) and toks[i][0] in ("NOT", "MINUS"):
        child, i = _parse_not(toks, i + 1)
        return _Not(child), i
    return _parse_atom(toks, i)


def _parse_atom(toks, i):
    if i >= len(toks):
        raise ValueError("unexpected end of query")
    kind, val = toks[i]
    if kind == "LP":
        # Empty group "()" -> inert (matches-all) so it neither crashes nor
        # leaks a ')' literal into positive_terms.
        if i + 1 < len(toks) and toks[i + 1][0] == "RP":
            return _Always(), i + 2
        node, i = _parse_or(toks, i + 1)
        if i < len(toks) and toks[i][0] == "RP":
            i += 1
        return node, i
    if kind == "RP":
        raise ValueError("unexpected ')'")
    if kind == "PHRASE":
        return _Leaf(val, phrase=True), i + 1
    return _Leaf(val), i + 1  # WORD


@lru_cache(maxsize=1024)
def parse(query: str) -> Query:
    toks = _tokenize(query or "")
    if not toks:
        return Query(_Always(), query or "")
    try:
        root, idx = _parse_or(toks, 0)
        if idx < len(toks):
            raise ValueError("unconsumed tokens")
    except (IndexError, ValueError):
        # Malformed query (bad operators / stray parens): fall back to an
        # implicit-AND of the bare words so a scrape/score never crashes on a
        # user typo AND no tokens are silently dropped.
        words = [_Leaf(v) for k, v in toks if k == "WORD"]
        root = words[0] if len(words) == 1 else _And(words) if words else _Always()
    return Query(root, query or "")
