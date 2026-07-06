"""Semantic icon glyphs. Prefers Windows' built-in 'Segoe MDL2 Assets' line-icon
font — present on Windows 8.1/10/11, so it ships with every target machine and
needs NO bundled assets — rendered in that font and tinted via fg. Falls back to a
plain emoji when the font is unavailable. Codepoints verified against the live font
(scratchpad probe), not guessed."""
import tkinter.font as tkfont

MDL2 = "Segoe MDL2 Assets"

# semantic name -> (MDL2 codepoint, emoji fallback)
_ICONS = {
    "info":    (0xE946, "\N{INFORMATION SOURCE}"),
    "search":  (0xE721, "\N{LEFT-POINTING MAGNIFYING GLASS}"),
    "warning": (0xE7BA, "\N{WARNING SIGN}"),
    "accept":  (0xE73E, "\N{CHECK MARK}"),
    "help":    (0xE897, "\N{BLACK QUESTION MARK ORNAMENT}"),
    "list":    (0xE8FD, "\N{CLIPBOARD}"),
    "empty":   (0xE8FD, "\N{INBOX TRAY}"),
    "contact": (0xE77B, "\N{BUST IN SILHOUETTE}"),
    "chart":   (0xE9D9, "\N{BAR CHART}"),
    "star":    (0xE735, "\N{WHITE MEDIUM STAR}"),
}

_have = None


def native():
    """Whether the MDL2 icon font is available. Cached once a Tk root exists (before
    that, tkfont.families() raises → return False WITHOUT caching so it retries)."""
    global _have
    if _have is None:
        try:
            _have = MDL2 in tkfont.families()
        except Exception:
            return False
    return _have


def glyph(name):
    """The icon character for `name`: the MDL2 glyph if the font is available, else
    an emoji fallback. Render it in font() so the MDL2 glyph resolves."""
    cp, emoji = _ICONS.get(name, (None, ""))
    if cp is not None and native():
        return chr(cp)
    return emoji


def font(size=11):
    """Font tuple to render an icon glyph in (the MDL2 font when available)."""
    return (MDL2 if native() else "Segoe UI", size)
