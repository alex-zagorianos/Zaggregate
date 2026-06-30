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
    assert "Starting JobScout" in bat
    assert "JobProgram.exe" in bat


def test_write_first_run_kit_returns_created_names(tmp_path):
    created = build_package.write_first_run_kit(tmp_path)
    assert "FIRST-RUN.txt" in created
    assert "launch.bat" in created
