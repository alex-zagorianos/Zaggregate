"""Dependency-free English-language heuristic.

Cheap guard for the international-source tier (review "language guard"): once a
non-US Adzuna country (or a forced LANGUAGE_GUARD) is in play, a foreign-language
posting would be scored by the keyword matcher with false confidence — a German
title shares zero tokens with an English keyword, so it scores ~0 and gets
dropped for the *wrong* reason, while an occasional cognate can score falsely
high. Rather than trust that, we detect non-English text and let the caller mark
it 'not scored (language)'.

The heuristic is a stopword hit-rate: English prose is dense with a small set of
function words ('the', 'and', 'of', 'to', ...). We tokenize the first ~80 words
of title+description and measure what fraction are English stopwords. Real
English paragraphs sit well above the threshold; German/French/Spanish/etc. prose
sits well below (their function words differ). Deliberately conservative — the
cost of a false 'non-English' is a skipped score, not a crash, and the guard is
OFF unless armed, so Alex's US runs never touch this path.
"""
import re

# A compact, high-frequency English function-word set. Kept small and unambiguous
# — words that are ALSO common in other Latin-script languages (e.g. 'a', 'no',
# 'in', 'me', 'con') are excluded so a Spanish/Italian posting doesn't score as
# English on shared tokens. These are strong English signals.
_EN_STOPWORDS = frozenset({
    "the", "and", "of", "to", "for", "with", "you", "your", "our", "we",
    "will", "are", "is", "be", "this", "that", "as", "have", "has", "or",
    "an", "at", "by", "from", "they", "their", "which", "should", "would",
    "can", "must", "who", "what", "when", "where", "these", "those", "been",
    "were", "was", "about", "into", "through", "during", "including", "such",
    "other", "also", "than", "then", "there", "here", "how", "all", "any",
    "each", "more", "most", "some", "them", "his", "her", "its", "not",
})

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")

# Sampling + decision knobs (conservative on purpose).
_MAX_WORDS = 80          # first N word-tokens sampled from title+description
_MIN_WORDS = 6           # below this, too little signal -> assume English (abstain)
_THRESHOLD = 0.12        # >= this fraction of stopwords -> English


def english_stopword_ratio(text: str) -> float:
    """Fraction of the first ~80 word-tokens that are English stopwords.
    0.0 when there are no alphabetic word tokens at all."""
    if not text:
        return 0.0
    words = _WORD_RE.findall(text)
    if not words:
        return 0.0
    sample = words[:_MAX_WORDS]
    hits = sum(1 for w in sample if w.lower() in _EN_STOPWORDS)
    return hits / len(sample)


def is_probably_english(text: str) -> bool:
    """True when `text` reads as English by stopword density.

    Abstains toward True (returns True) when there is too little text to judge
    (< _MIN_WORDS alphabetic tokens) — a bare English job title like 'Nurse' or a
    non-Latin script that our regex can't tokenize is NOT confidently non-English,
    and the guard's whole point is to avoid confident wrong calls. Only text with
    enough Latin-script words AND a low English-stopword rate is judged non-English.
    """
    if not text:
        return True
    words = _WORD_RE.findall(text)
    if len(words) < _MIN_WORDS:
        return True  # too little signal -> don't claim non-English
    return english_stopword_ratio(text) >= _THRESHOLD
