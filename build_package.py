"""Build the JobScout distributable — a zip a friend unzips and runs.

  1. pyinstaller app.spec     -> dist/JobProgram/ (onedir, windowed GUI)
  2. assemble  dist/JobScout/ -> the app folder + a seeded data/ (templates only)
                                 + README.txt
  3. zip                      -> dist/JobScout.zip

Run:
  py build_package.py              # full build
  py build_package.py --no-build   # reassemble from an existing dist/JobProgram

Requires `pip install pyinstaller` (pinned in requirements.txt). NO personal data
is included: data/ carries only the neutral templates from data_templates/ and the
public starter companies.json. The .exe resolves its data folder at <exe>/data, so
the seeded data/ is placed next to JobProgram.exe.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
APP_BUILD = DIST / "JobProgram"     # PyInstaller onedir output
PKG = DIST / "JobScout"             # assembled package
TEMPLATES = ROOT / "data_templates"

# data_templates filename -> seeded name in the user's data folder
_SEEDS = {
    "experience.template.md":  "experience.md",
    "preferences.template.md": "preferences.md",
    "preferences.json":        "preferences.json",
}

README = """\
JobScout - a personal job search that ranks roles to YOUR preferences using your
own Claude.

QUICK START
  1. Open  JobProgram\\data\\preferences.md  and describe the jobs you want, in
     plain English. Edit  preferences.json  for hard filters (salary, location,
     deal-breakers).
  2. Open  JobProgram\\data\\experience.md  and paste your resume / experience.
  3. Run   JobProgram\\JobProgram.exe.
  4. Search, then click "Copy fit prompt", paste it into your own Claude
     (claude.ai - any plan), and paste the reply back. The app ranks your inbox
     to your preferences. (Optional: put an Anthropic API key in
     JobProgram\\data\\secrets\\anthropic_key to rank automatically, no pasting.)

Everything you edit lives in  JobProgram\\data\\  - that folder is yours. Nothing
is sent anywhere except the prompts you choose to paste into your own Claude.
"""


def run_pyinstaller() -> None:
    print("[1/3] PyInstaller (app.spec)...")
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "app.spec"],
                   cwd=ROOT, check=True)


def assemble() -> None:
    print("[2/3] Assembling package...")
    if not APP_BUILD.exists():
        sys.exit(f"No build at {APP_BUILD}. Run without --no-build first.")
    if PKG.exists():
        shutil.rmtree(PKG)
    app = PKG / "JobProgram"
    shutil.copytree(APP_BUILD, app)

    data = app / "data"                 # config resolves <exe>/data -> here
    data.mkdir(parents=True, exist_ok=True)
    created = []
    for template_name, target in _SEEDS.items():
        src = TEMPLATES / template_name
        if src.exists():
            shutil.copyfile(src, data / target)
            created.append(target)
    companies = ROOT / "companies.json"
    if companies.exists():
        shutil.copyfile(companies, data / "companies.json")
        created.append("companies.json")

    (PKG / "README.txt").write_text(README, encoding="utf-8")
    print(f"      data/ seeded: {', '.join(created)}")


def zip_package() -> None:
    print("[3/3] Zipping...")
    out = shutil.make_archive(str(DIST / "JobScout"), "zip",
                              root_dir=str(DIST), base_dir="JobScout")
    print(f"Done -> {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the JobScout distributable.")
    ap.add_argument("--no-build", action="store_true",
                    help="Skip PyInstaller; reassemble from an existing dist/JobProgram.")
    args = ap.parse_args()
    if not args.no_build:
        run_pyinstaller()
    assemble()
    zip_package()


if __name__ == "__main__":
    main()
