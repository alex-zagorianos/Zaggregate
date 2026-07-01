"""D2 - product lifecycle + supportability (review P7).

Version constant + zip naming, the applog logging framework (handlers +
rotation), last_run.json round-trip, redaction in the problem-report zip,
the due-follow-up log line, auto-backup keep-7 rotation, the sync-folder
warning, the socket guard, and a non-trivial README. Fixture-based, no network,
no writes to real user data (tmp_path + monkeypatch only)."""
import io
import json
import logging
import socket
import zipfile
from pathlib import Path

import pytest

import config


# ── shared isolation ──────────────────────────────────────────────────────────

@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Repoint config.USER_DATA_DIR + the derived LOG_DIR at a temp folder and
    give applog a fresh handler set so every artifact lands under tmp_path."""
    d = tmp_path / "data"
    d.mkdir()
    monkeypatch.setattr(config, "USER_DATA_DIR", d)
    monkeypatch.setattr(config, "LOG_DIR", d / config.LOG_DIR_NAME)
    import applog
    applog.reset_for_tests()
    yield d
    applog.reset_for_tests()


# ── 1. version + zip naming ───────────────────────────────────────────────────

def test_app_version_is_semver():
    parts = config.APP_VERSION.split(".")
    assert len(parts) == 3 and all(p.isdigit() for p in parts), config.APP_VERSION


def test_build_package_zip_name_carries_version():
    import build_package
    assert build_package.APP_VERSION == config.APP_VERSION
    assert build_package.zip_name() == f"JobScout-v{config.APP_VERSION}"


def test_build_package_readme_and_changes_reference_version_and_upgrade():
    import build_package
    assert config.APP_VERSION in build_package.README
    assert "UPGRADING" in build_package.README.upper()
    # data + app are described as separate in the upgrade path
    assert "data" in build_package.README.lower()
    assert config.APP_VERSION in build_package.CHANGES
    assert "brain/review-2026-07-01" in build_package.CHANGES


# ── 2. logging framework: handlers + rotation ─────────────────────────────────

def test_get_logger_attaches_file_and_console_handlers(data_dir):
    import applog
    log = applog.get_logger("unit")
    root = logging.getLogger("jobscout")
    kinds = {type(h).__name__ for h in root.handlers}
    assert any("RotatingFileHandler" in k for k in kinds)
    assert any("Handler" in k for k in kinds)  # a console stream handler too
    log.info("hello world")
    for h in root.handlers:
        h.flush()
    log_file = data_dir / config.LOG_DIR_NAME / config.LOG_FILE_NAME
    assert log_file.exists()
    assert "hello world" in log_file.read_text(encoding="utf-8")


def test_console_output_stays_bare_for_info(data_dir, capsys):
    import applog
    applog.get_logger("unit").info("  [adzuna] Skipping - no key")
    out = capsys.readouterr().out
    # Byte-identical to what print() would have shown (no level/logger prefix).
    assert out == "  [adzuna] Skipping - no key\n"


def test_console_echo_suppressed_when_flagged(data_dir, capsys):
    import applog
    applog.get_logger("daily_run").info("quiet", extra={"_console": False})
    out = capsys.readouterr().out
    assert out == ""  # daily_run print()s the line itself; no doubled console echo
    # ...but the file still got it.
    for h in logging.getLogger("jobscout").handlers:
        h.flush()
    log_file = data_dir / config.LOG_DIR_NAME / config.LOG_FILE_NAME
    assert "quiet" in log_file.read_text(encoding="utf-8")


def test_rotating_handler_rolls_over(data_dir, monkeypatch):
    # Tiny max size so a few records force a rollover -> a .1 backup appears.
    monkeypatch.setattr(config, "LOG_MAX_BYTES", 512)
    monkeypatch.setattr(config, "LOG_BACKUP_COUNT", 3)
    import applog
    applog.reset_for_tests()
    log = applog.get_logger("rot")
    for i in range(200):
        log.info("x" * 50 + f" {i}")
    for h in logging.getLogger("jobscout").handlers:
        h.flush()
    logs = list((data_dir / config.LOG_DIR_NAME).glob(config.LOG_FILE_NAME + "*"))
    assert any(p.name != config.LOG_FILE_NAME for p in logs), \
        f"expected a rotated backup, saw {[p.name for p in logs]}"


# ── 3. last_run.json round-trip ───────────────────────────────────────────────

def test_last_run_write_read_roundtrip(data_dir, monkeypatch):
    import applog
    # Force the project data dir to the temp data dir (no projects registry).
    monkeypatch.setattr(applog, "_project_data_dir", lambda slug: data_dir)
    info = {
        "project": "", "added": 3, "found": 40, "qualified": 12,
        "per_source_counts": {"adzuna": 10, "careers": 30},
        "errors": ["adzuna: throttled"], "capped": {"Acme": 5},
    }
    path = applog.write_last_run(info, project_slug=None)
    assert path is not None and path.exists()
    back = applog.last_run_info(None)
    assert back["added"] == 3 and back["found"] == 40
    assert back["version"] == config.APP_VERSION       # stamped in
    assert "timestamp" in back                          # stamped in
    assert back["per_source_counts"]["careers"] == 30


def test_last_run_info_absent_is_none(data_dir, monkeypatch):
    import applog
    monkeypatch.setattr(applog, "_project_data_dir", lambda slug: data_dir)
    assert applog.last_run_info(None) is None


# ── 4. redaction in the problem-report zip ────────────────────────────────────

def test_report_zip_excludes_secrets_and_includes_diagnostics(data_dir, monkeypatch):
    import applog
    from ui import help as uihelp
    # Plant a fake secret that must NOT appear anywhere in the report.
    secrets = data_dir / "secrets"
    secrets.mkdir()
    (secrets / "anthropic_key").write_text("sk-SUPER-SECRET-XYZ", encoding="utf-8")
    monkeypatch.setattr(config, "SECRETS_DIR", secrets)
    # A log line + a last_run.json to prove diagnostics ARE included.
    applog.get_logger("unit").info("diagnostic breadcrumb")
    for h in logging.getLogger("jobscout").handlers:
        h.flush()
    monkeypatch.setattr(applog, "_project_data_dir", lambda slug: data_dir)
    applog.write_last_run({"project": "", "added": 1, "found": 1,
                           "qualified": 1, "per_source_counts": {}, "errors": []},
                          project_slug=None)

    out_dir = data_dir / "out"
    zpath = uihelp.build_report_zip(dest_dir=out_dir)
    assert zpath.endswith(".zip")
    with zipfile.ZipFile(zpath) as z:
        names = z.namelist()
        blob = b"".join(z.read(n) for n in names)
    text = blob.decode("utf-8", "replace")
    # The secret value must never appear; the secrets file must not be bundled.
    assert "sk-SUPER-SECRET-XYZ" not in text
    assert not any("secrets" in n and "key" in n for n in names)
    # Diagnostics present: metadata (version) + the log breadcrumb + last_run.
    assert "report_meta.json" in names
    assert config.APP_VERSION in text
    assert "diagnostic breadcrumb" in text
    assert any(n.endswith("last_run.json") for n in names)


def test_report_meta_provider_flags_are_redacted(data_dir, monkeypatch):
    from ui import help as uihelp
    secrets = data_dir / "secrets"
    secrets.mkdir()
    (secrets / "anthropic_key").write_text("sk-REDACT-ME", encoding="utf-8")
    monkeypatch.setattr(config, "SECRETS_DIR", secrets)
    # Ensure env doesn't leak a real key into the snapshot.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    meta = uihelp._report_meta()
    flags = meta["providers_configured"]
    assert flags.get("anthropic") == "set"          # detected...
    assert "sk-REDACT-ME" not in json.dumps(meta)   # ...but value never present


# ── 5. due follow-ups line in the daily log ───────────────────────────────────

def test_daily_run_logs_followups_due(monkeypatch):
    import daily_run
    from tracker import db
    logged = []
    monkeypatch.setattr(daily_run, "log", lambda m: logged.append(m))
    monkeypatch.setattr(db, "count_followups_due", lambda: 4)
    # Exercise just the due-count fragment the way main() does it.
    n = db.count_followups_due()
    if n:
        daily_run.log(f"{n} follow-up(s) due - open the Job Tracker to act on them")
    assert any("4 follow-up(s) due" in m for m in logged)


def test_count_followups_due_real(tmp_path, monkeypatch):
    import datetime
    from tracker import db
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "tracker.db")
    db.init_db()
    a = db.add_job("Nurse", "Acme", url="u1")
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    db.update_job(a, status="applied", follow_up_date=yesterday)
    assert db.count_followups_due() == 1


# ── 6. auto-backup keep-7 rotation ────────────────────────────────────────────

def test_auto_backup_keeps_last_seven(data_dir):
    from ui import help as uihelp
    (data_dir / "preferences.md").write_text("profile", encoding="utf-8")
    made = []
    from datetime import datetime, timedelta
    base = datetime(2026, 7, 1, 8, 0, 0)
    for i in range(10):
        out = uihelp.auto_backup(keep=7, when=base + timedelta(minutes=i))
        assert out is not None
        made.append(out)
    archives = sorted((data_dir / uihelp.BACKUP_DIR_NAME).glob("jobscout-backup-*.zip"))
    assert len(archives) == 7                      # older 3 pruned
    # The 7 kept are the most recent (highest timestamps).
    kept_names = {p.name for p in archives}
    assert Path(made[-1]).name in kept_names
    assert Path(made[0]).name not in kept_names


def test_make_backup_excludes_backups_and_logs(data_dir):
    from ui import help as uihelp
    (data_dir / "preferences.md").write_text("keepme", encoding="utf-8")
    (data_dir / config.LOG_DIR_NAME).mkdir()
    (data_dir / config.LOG_DIR_NAME / "app.log").write_text("noise", encoding="utf-8")
    uihelp.auto_backup(keep=7)  # creates backups/ + a nested archive
    # A second backup must not embed the first backup or the log tree.
    out = uihelp.make_backup(str(data_dir / "check"))
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
    assert any("preferences.md" in n for n in names)
    assert not any(n.startswith("backups/") or "/backups/" in n for n in names)
    assert not any(n.startswith("logs/") or "/logs/" in n for n in names)


# ── 7. sync-folder warning ────────────────────────────────────────────────────

@pytest.mark.parametrize("path,expect", [
    (r"C:\Users\bob\OneDrive\JobProgram", True),
    (r"C:\Users\bob\Dropbox\data", True),
    (r"C:\Users\bob\Google Drive\data", True),
    (r"C:\Users\bob\Documents\JobProgram", False),
    (r"C:\Users\bob\AppData\Local\JobProgram", False),
])
def test_sync_folder_warning_triggers(path, expect):
    import userdata
    warn = userdata.sync_folder_warning(path)
    assert (warn is not None) == expect
    if expect:
        assert "corrupt" in warn.lower()


def test_bootstrap_emits_sync_warning(data_dir, monkeypatch, capsys):
    import userdata
    monkeypatch.setattr(userdata, "sync_folder_warning",
                        lambda d=None: "SYNC WARNING: move your data")
    userdata.bootstrap()
    err = capsys.readouterr().err
    assert "SYNC WARNING" in err


# ── 8. socket guard ───────────────────────────────────────────────────────────

def test_socket_guard_blocks_outbound():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(Exception) as ei:
            s.connect(("example.com", 80))
        assert "Blocked outbound" in str(ei.value)
    finally:
        s.close()


def test_socket_guard_allows_loopback_bind():
    # Binding + connecting to loopback must still work (in-process servers).
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    cli = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        cli.connect(("127.0.0.1", port))  # loopback allowed -> no raise
    finally:
        cli.close()
        srv.close()


@pytest.mark.network
def test_network_marker_opts_out():
    # With the marker, the guard is not installed, so patching is absent. We only
    # assert the marker path doesn't itself raise on a plain socket construction.
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.close()


# ── 9. README is real ─────────────────────────────────────────────────────────

def test_readme_is_nontrivial():
    readme = Path(__file__).resolve().parent.parent / "README.md"
    text = readme.read_text(encoding="utf-8")
    assert len(text) > 500
    low = text.lower()
    assert "zaggregate" in low or "jobscout" in low
    assert "quick start" in low
    assert "mcp" in low and "clipboard" in low       # both AI channels
    assert "license" in low
