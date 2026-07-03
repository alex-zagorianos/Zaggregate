"""SmartScreen first-run kit — the friendly files that let a non-technical
Windows user get past the unsigned-exe "unknown publisher" warning."""
import build_package


def test_write_first_run_kit_creates_both_files(tmp_path):
    build_package.write_first_run_kit(tmp_path)
    assert (tmp_path / "FIRST-RUN.txt").exists()
    assert (tmp_path / "launch.bat").exists()


def test_first_run_txt_has_smartscreen_steps(tmp_path):
    build_package.write_first_run_kit(tmp_path)
    txt = (tmp_path / "FIRST-RUN.txt").read_text(encoding="utf-8")
    # The two ways past SmartScreen, in plain English.
    assert "Unblock" in txt
    assert "Run anyway" in txt
    assert "More info" in txt
    assert "JobProgram.exe" in txt


def test_launch_bat_runs_the_exe(tmp_path):
    build_package.write_first_run_kit(tmp_path)
    bat = (tmp_path / "launch.bat").read_text(encoding="utf-8")
    assert "Starting Zaggregate" in bat
    assert "JobProgram.exe" in bat


def test_write_first_run_kit_returns_created_names(tmp_path):
    created = build_package.write_first_run_kit(tmp_path)
    assert "FIRST-RUN.txt" in created
    assert "launch.bat" in created


# ── production/ folder manifest (build_package --production) ───────────────────

def test_production_contents_lists_the_required_entries():
    entries = build_package.production_contents()
    # The app, the extension the user loads unpacked, the start-here doc, and the
    # optional-keys reference must all be part of the promised folder.
    for required in ("JobProgram", "browser_ext", "QUICKSTART.md", ".env.example"):
        assert required in entries, required
    # Stable, de-duplicated manifest (each entry named once).
    assert len(entries) == len(set(entries))


def test_quickstart_md_is_actionable_and_versioned():
    import config
    md = build_package.QUICKSTART_MD
    assert config.APP_VERSION in md            # stamped with the release version
    assert "JobProgram.exe" in md              # run the exe
    assert "wizard" in md.lower()              # the first-run wizard opens
    assert "Load unpacked" in md               # how to load the extension
    assert "browser_ext" in md
