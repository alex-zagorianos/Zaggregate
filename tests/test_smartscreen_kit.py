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


def test_mode_launchers_run_the_exe_with_the_right_flags(tmp_path):
    # One-click launchers for the two modern modes, so nobody types flags.
    created = build_package.write_first_run_kit(tmp_path)
    assert "Zaggregate Desktop.bat" in created
    assert "Zaggregate Web.bat" in created
    desktop = (tmp_path / "Zaggregate Desktop.bat").read_text(encoding="utf-8")
    web = (tmp_path / "Zaggregate Web.bat").read_text(encoding="utf-8")
    assert "JobProgram.exe" in desktop and "--desktop" in desktop
    assert "JobProgram.exe" in web and "--web" in web
    # %~dp0 anchors the exe path to the .bat's own folder (shortcut-safe).
    assert "%~dp0" in desktop and "%~dp0" in web


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


def test_executables_readme_is_versioned_and_actionable():
    # The in-repo Executables/ download README is regenerated per build; it must
    # carry the current version's zip name and point at the mode launchers.
    import config
    md = build_package.EXECUTABLES_README
    assert f"Zaggregate-v{config.APP_VERSION}.zip" in md
    assert "Zaggregate Desktop.bat" in md
    assert "Zaggregate Web.bat" in md
    assert "Run anyway" in md                  # SmartScreen guidance present


def test_quickstart_md_has_desktop_mode_note_and_privacy_line():
    # B3: QUICKSTART must call out the modern app modes (--desktop / --web) and
    # carry a one-line privacy assurance.
    md = build_package.QUICKSTART_MD
    assert "--desktop" in md                   # the native-window mode
    assert "--web" in md                       # the browser mode
    # A privacy one-liner points at PRIVACY.md.
    assert "PRIVACY.md" in md
    assert "stays on this computer" in md.lower()


# ── trust docs in the distributed layout (B3) ─────────────────────────────────

def test_production_contents_includes_trust_docs():
    entries = build_package.production_contents()
    for required in ("PRIVACY.md", "EULA.txt"):
        assert required in entries, required


def test_copy_trust_docs_copies_repo_root_docs(tmp_path):
    # The repo-root PRIVACY.md / EULA.txt are the source of truth; the helper
    # ships them into the distributed folder.
    copied = build_package._copy_trust_docs(tmp_path)
    for name in ("PRIVACY.md", "EULA.txt"):
        assert name in copied
        assert (tmp_path / name).exists()
        # Content is copied verbatim from the repo root.
        assert (tmp_path / name).read_text(encoding="utf-8") == \
            (build_package.ROOT / name).read_text(encoding="utf-8")


# ── SHA256SUMS for produced zips (B3) ─────────────────────────────────────────

def test_write_sha256sums_matches_hashlib(tmp_path):
    import hashlib
    z1 = tmp_path / "Zaggregate-v1.0.0.zip"
    z1.write_bytes(b"fake zip bytes for hashing")
    manifest = build_package.write_sha256sums([z1], tmp_path)
    text = (tmp_path / "SHA256SUMS.txt").read_text(encoding="utf-8")
    expected = hashlib.sha256(z1.read_bytes()).hexdigest()
    # Standard sha256sum layout: "<hex>  <basename>" (two spaces, bare name).
    assert f"{expected}  Zaggregate-v1.0.0.zip" in text
    assert manifest.endswith("SHA256SUMS.txt")


def test_write_sha256sums_lists_every_zip(tmp_path):
    z1 = tmp_path / "a.zip"
    z2 = tmp_path / "b.zip"
    z1.write_bytes(b"aaa")
    z2.write_bytes(b"bbb")
    build_package.write_sha256sums([z1, z2], tmp_path)
    lines = (tmp_path / "SHA256SUMS.txt").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert any(line.endswith("  a.zip") for line in lines)
    assert any(line.endswith("  b.zip") for line in lines)
