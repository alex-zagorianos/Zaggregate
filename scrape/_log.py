"""One shared entry point for scraper diagnostics (review P7 follow-up).

Every per-company / per-board scraper (greenhouse, lever, bamboohr, eightfold,
workday, the ~20 ATS modules and the direct/registry helpers) used to announce a
skipped-dead board, a throttled host, or a parse error with a bare tagged
``print()`` — e.g. ``print(f"  [greenhouse] {name}: gone — skipping")``. Those
lines went to a console that the embedded GUI / web-server runs discard, so a
failing board left no trace support could read.

``diag(msg)`` routes each of those lines through the ``applog`` framework instead
(exactly the pattern ``careers_client`` already uses for its ``[careers]`` lines):
the shared ``jobscout`` logger mirrors the record to the rotating ``app.log`` AND
echoes the *bare message* to stdout via applog's INFO console handler. Because
that handler resolves ``sys.stdout`` at emit time (applog._DynamicStdoutHandler),
the echo is byte-identical to the old ``print()`` — same text, same trailing
newline, still captured by pytest's capsys — while the diagnostic finally also
lands in the file a friend's "Report a problem" zip can carry.

Kept deliberately tiny (one function, one logger) so all ~24 call sites share a
single channel instead of 24 divergent ``get_logger`` wirings. INFO is the right
level: it keeps the console text prefix-free (WARNING/ERROR would prepend a
``LEVEL:`` tag via applog's bare formatter and change the output), matching the
old unconditional prints exactly.
"""
from __future__ import annotations


def diag(msg: str) -> None:
    """Emit one scraper diagnostic line: bare to the console (byte-identical to
    the old ``print(msg)``) and persisted to app.log. Best-effort — a logging
    hiccup must never abort a scrape, so any failure falls back to a plain
    ``print`` so the line is never lost."""
    try:
        import applog
        applog.get_logger("scrape").info(msg)
    except Exception:
        # Framework logging must never kill a scrape; keep the visible line.
        print(msg)
