"""Application logging + last-run status — the supportability spine (review P7).

Two jobs, both stdlib-only:

1. ``get_logger(name)`` — a shared logger tree ("jobscout.*") whose records go to
   BOTH a rotating file under ``<user data dir>/logs/app.log`` (1 MB x 5, so a
   friend's install never fills the disk yet always has recent history to send)
   AND the console. The console handler prints the bare message (no level/logger
   prefix) so wiring an existing ``print(...)`` site through ``get_logger`` keeps
   the terminal output byte-for-byte what it was — the file gets the timestamped,
   levelled copy that persists. Source failures (a skipped keyless source, a
   throttled board) that used to print to nowhere now land in a file support can
   read.

2. ``write_last_run`` / ``last_run_info`` — a small machine-readable
   ``last_run.json`` written into the project's data dir at the end of a daily
   run, so the GUI can render "Last updated: <when> - N new jobs" in the Inbox
   header and "Report a problem" can attach an at-a-glance run summary.

No third-party deps; import-safe on a read-only bundle dir (every filesystem op
is best-effort — logging must never crash the app it observes)."""
from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

import config

# Root of the app's logger tree. get_logger("daily_run") -> "jobscout.daily_run".
_ROOT_NAME = "jobscout"
# Guard so handlers are attached exactly once per process (logging is global).
_CONFIGURED = False


# ── secret redaction ──────────────────────────────────────────────────────────
# Several source clients carry their credential in the request URL (Jooble: URL
# path; Adzuna/Careerjet: query params). An HTTP error's message includes the
# full URL, and those strings flow into app.log, last_run.json, and from there
# the "Report a problem" zip — which promises to contain NO keys. Everything
# that persists an error string must pass it through redact() (a logging.Filter
# below covers the log file wholesale). Review-fleet critical finding.

_URL_CRED_RE = re.compile(
    r"(?i)\b(app_key|app_id|api_key|apikey|affid|access_token|token|key)"
    r"=([^&\s\"']+)")
_JOOBLE_PATH_RE = re.compile(r"(?i)(jooble\.org/api/)[A-Za-z0-9._%-]+")
# URL userinfo (https://user:token@host/...) — a BYO base_url can carry a
# credential this way (proxy tokens), and it would ride HTTPError messages.
_URL_USERINFO_RE = re.compile(r"(?i)(://)[^/@\s\"']+@")
_SECRET_VALUES: list[str] | None = None


def _known_secret_values() -> list[str]:
    """Best-effort: the actual configured credential values, so redact() can
    scrub them wherever they appear (not just in URL shapes). Cached per
    process; never raises."""
    global _SECRET_VALUES
    if _SECRET_VALUES is not None:
        return _SECRET_VALUES
    vals: list[str] = []
    try:
        names = list(getattr(config, "SOURCE_SECRET_FILES", {}) or {})
        names += ["ANTHROPIC_API_KEY", "SERPAPI_KEY", "ANTHROPIC_BASE_URL"]
        for n in names:
            try:
                v = config.resolve_secret(n) if hasattr(config, "resolve_secret") \
                    else None
            except Exception:
                v = None
            # Only scrub substantial values; short strings would over-redact.
            # Plain URLs (a bare base_url like https://api.anthropic.com) are
            # skipped, but a CREDENTIAL-BEARING url (userinfo or query token)
            # is scrubbed whole — a BYO base_url may embed a proxy token.
            if not (v and isinstance(v, str) and len(v) >= 8):
                continue
            if "://" in v and not ("@" in v or "?" in v):
                continue
            vals.append(v)
    except Exception:
        pass
    _SECRET_VALUES = vals
    return vals


def redact(text) -> str:
    """Scrub credentials from a string destined for a persisted surface
    (app.log via the filter, last_run.json errors, diagnostic zips)."""
    if not text:
        return text
    s = str(text)
    s = _URL_CRED_RE.sub(lambda m: f"{m.group(1)}=[redacted]", s)
    s = _JOOBLE_PATH_RE.sub(r"\1[redacted]", s)
    s = _URL_USERINFO_RE.sub(r"\1[redacted]@", s)
    for v in _known_secret_values():
        if v in s:
            s = s.replace(v, "[redacted]")
    return s


class _RedactFilter(logging.Filter):
    """Applies redact() to every record before any handler formats it, so a
    credential embedded in an exception message can never reach app.log or the
    console scrollback a user screenshots."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            scrubbed = redact(msg)
            if scrubbed != msg:
                record.msg = scrubbed
                record.args = ()
        except Exception:
            pass  # redaction must never block logging
        return True


class _BareMessageFormatter(logging.Formatter):
    """Console formatter that emits just the message for INFO (so a print()
    routed through the logger looks identical on the terminal), but prefixes
    WARNING/ERROR so a friend notices a problem line in the scrollback."""

    def format(self, record: logging.LogRecord) -> str:
        msg = record.getMessage()
        if record.levelno >= logging.WARNING:
            return f"{record.levelname}: {msg}"
        return msg


def _file_handler() -> logging.Handler | None:
    """A RotatingFileHandler at <user data dir>/logs/app.log, or None if the log
    directory can't be created (read-only bundle) — the console handler still
    works, so the app is never blocked by an unwritable log path."""
    try:
        log_path = config.log_dir() / config.LOG_FILE_NAME
        h = RotatingFileHandler(
            str(log_path),
            maxBytes=config.LOG_MAX_BYTES,
            backupCount=config.LOG_BACKUP_COUNT,
            encoding="utf-8",
            delay=True,  # don't open the file until the first record
        )
        h.setLevel(logging.DEBUG)
        h.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"))
        return h
    except OSError:
        return None


class _ConsoleEchoFilter(logging.Filter):
    """Let a caller suppress the console echo for a specific record by passing
    ``extra={"_console": False}`` — used where the caller already print()s the
    line itself (daily_run.log) and only wants the persisted file copy, so the
    terminal output stays byte-identical."""

    def filter(self, record: logging.LogRecord) -> bool:
        return getattr(record, "_console", True) is not False


class _DynamicStdoutHandler(logging.StreamHandler):
    """A StreamHandler that resolves ``sys.stdout`` at EMIT time, not at
    construction. The stdlib StreamHandler captures the stream once, which breaks
    under pytest's capsys (it swaps sys.stdout after our handler is built) and any
    other stdout redirection — this mirrors print()'s late binding so routing a
    print() through the logger stays observable exactly where print() was."""

    def __init__(self):
        super().__init__(stream=sys.stdout)

    @property
    def stream(self):
        return sys.stdout

    @stream.setter
    def stream(self, value):
        # StreamHandler.__init__ assigns self.stream; ignore so the property wins.
        pass


def _console_handler() -> logging.Handler:
    """A stdout StreamHandler mirroring the old print() behavior (bare message)."""
    h = _DynamicStdoutHandler()
    h.setLevel(logging.INFO)
    h.setFormatter(_BareMessageFormatter())
    h.addFilter(_ConsoleEchoFilter())
    return h


def _configure_root() -> logging.Logger:
    """Attach the file + console handlers to the 'jobscout' root logger once."""
    global _CONFIGURED
    root = logging.getLogger(_ROOT_NAME)
    if _CONFIGURED:
        return root
    root.setLevel(logging.DEBUG)
    root.propagate = False  # don't double-log through the stdlib root
    root.addFilter(_RedactFilter())  # no credential ever reaches a handler
    fh = _file_handler()
    if fh is not None:
        root.addHandler(fh)
    root.addHandler(_console_handler())
    _CONFIGURED = True
    return root


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a logger under the shared 'jobscout' tree with the file+console
    handlers attached. ``get_logger("daily_run")`` -> logger 'jobscout.daily_run'.
    Idempotent: handlers are configured on the root exactly once per process, so
    repeated calls (and every module-level ``log = get_logger(__name__)``) are
    cheap and never duplicate output."""
    _configure_root()
    if not name:
        return logging.getLogger(_ROOT_NAME)
    # Strip a leading package path so get_logger(__name__) reads cleanly, and
    # avoid a doubled 'jobscout.jobscout' if a caller passes the full name.
    short = name.rsplit(".", 1)[-1]
    if short == _ROOT_NAME:
        return logging.getLogger(_ROOT_NAME)
    return logging.getLogger(f"{_ROOT_NAME}.{short}")


def reset_for_tests() -> None:
    """Drop the configured handlers so a test that repoints config.USER_DATA_DIR
    gets a fresh file handler under the new path. Test-only."""
    global _CONFIGURED
    root = logging.getLogger(_ROOT_NAME)
    for h in list(root.handlers):
        try:
            h.close()
        except Exception:
            pass
        root.removeHandler(h)
    _CONFIGURED = False


# ── last-run status ───────────────────────────────────────────────────────────

_LAST_RUN_NAME = "last_run.json"


def _project_data_dir(project_slug: str | None) -> Path:
    """The data directory for a project's last_run.json. Uses workspace.project_dir
    so it tracks the same per-project layout the DB/config use; falls back to the
    user data dir if workspace can't be imported (defensive)."""
    try:
        import workspace
        return Path(workspace.project_dir(project_slug))
    except Exception:
        return Path(config.USER_DATA_DIR)


def last_run_path(project_slug: str | None = None) -> Path:
    return _project_data_dir(project_slug) / _LAST_RUN_NAME


def write_last_run(info: dict, project_slug: str | None = None) -> Path | None:
    """Write the machine-readable ``last_run.json`` for a project. A ``timestamp``
    (UTC ISO-8601) and ``version`` are stamped in if the caller didn't supply
    them. Best-effort — returns the path on success, None if the write failed
    (status reporting must never crash a run)."""
    payload = dict(info)
    # Error strings may embed request URLs (and thus URL-borne credentials);
    # last_run.json ships in the report-a-problem zip, so scrub here too.
    if payload.get("errors"):
        try:
            payload["errors"] = [redact(e) for e in payload["errors"]]
        except Exception:
            pass
    payload.setdefault(
        "timestamp",
        datetime.now(timezone.utc).replace(microsecond=0).isoformat())
    payload.setdefault("version", config.APP_VERSION)
    if project_slug is not None and "project" not in payload:
        payload["project"] = project_slug
    try:
        path = last_run_path(project_slug)
        path.parent.mkdir(parents=True, exist_ok=True)
        # atomic-ish: write a temp sibling then replace, so a reader never sees a
        # half-written file.
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(path)
        return path
    except OSError:
        return None


def last_run_info(project_slug: str | None = None) -> dict | None:
    """Read a project's ``last_run.json`` back for the GUI ("Last updated: ... -
    N new jobs"). Returns the parsed dict, or None if absent/unreadable."""
    try:
        raw = last_run_path(project_slug).read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None
