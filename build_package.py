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
First time? Read FIRST-RUN.txt - it shows how to open the app past Windows'
"unknown publisher" warning (the app is safe; it just isn't code-signed yet).

JobScout - a personal job search that ranks roles to YOUR preferences using your
own Claude.

QUICK START
  1. Run  JobProgram\\JobProgram.exe.
  2. The first time, a short Setup wizard asks what jobs you want, where, your
     salary, and your resume - no files to edit. (Changed your mind later? Run it
     again from  Help -> Run Setup Wizard.)
  3. Search, then click "Ask AI to rank these", paste the prompt into your own
     Claude (claude.ai - any plan), and paste the reply back with "Paste AI
     ranking". The app ranks your inbox to your preferences. (Optional: add an
     Anthropic API key in Tools > "Connect your AI (API key)..." to rank
     automatically, no pasting.)

To keep your Inbox filling on its own, turn on daily updates from
Tools > "Turn on daily updates".

Everything you enter stays on this computer. To find or back up your files, use
Help -> Open my data folder (the app picks the right location automatically; on a
protected install it lives under %LOCALAPPDATA%\\JobProgram). Nothing is sent
anywhere except the prompts you choose to paste into your own Claude.
"""

# Friendly walkthrough for getting past SmartScreen. A non-technical user reads
# "unknown publisher" as "virus" - this spells out the two safe ways to open it.
FIRST_RUN_TXT = """\
HOW TO OPEN JOBSCOUT THE FIRST TIME
===================================

JobScout is safe, but it isn't "code-signed" yet, so Windows shows a warning
the first time you open it. This is normal for small apps. Here is how to get
past it - it only happens once.

EASIEST WAY - unblock the app first
  1. Open the JobProgram folder.
  2. Right-click  JobProgram.exe  and choose  Properties.
  3. At the bottom of the General tab, look for a checkbox or a button that says
     "Unblock". Check it (or click it), then click  OK.
  4. Now double-click  JobProgram.exe  to start the app.

  (No "Unblock" option? It just means Windows already trusts the file - skip to
  the next section and run it normally.)

IF YOU STILL SEE A BLUE BOX - "Windows protected your PC"
  1. Do NOT click "Don't run".
  2. Click the small  "More info"  link in that blue box.
  3. A  "Run anyway"  button appears at the bottom. Click  "Run anyway".
  4. JobScout starts. You won't be asked again.

PREFER A SHORTCUT?
  You can also double-click  launch.bat  - it starts JobScout for you and shows
  a friendly "Starting JobScout..." message.

That's it. Once it has opened the first time, just double-click it like any
other program from then on.
"""

# A .bat is far less likely to be quarantined than the .exe and lets us print a
# friendly line. `start "" "..."` launches the exe and returns immediately; the
# empty "" is the (required) window title for start, not part of the path.
LAUNCH_BAT = """\
@echo off
echo Starting JobScout...
start "" "JobProgram.exe"
"""


def write_first_run_kit(dest_dir):
    """Write the SmartScreen first-run helpers into *dest_dir*.

    Drops two plain-English files next to JobProgram.exe so a non-technical
    Windows user can open the unsigned app:
      - FIRST-RUN.txt : numbered steps to unblock / "Run anyway" past SmartScreen
      - launch.bat    : a friendly one-liner that starts the exe

    Returns the list of filenames created (handy for the build log).
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / "FIRST-RUN.txt").write_text(FIRST_RUN_TXT, encoding="utf-8")
    (dest_dir / "launch.bat").write_text(LAUNCH_BAT, encoding="utf-8")
    return ["FIRST-RUN.txt", "launch.bat"]


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

    # SmartScreen first-run helpers, next to JobProgram.exe so launch.bat's
    # relative `start "" "JobProgram.exe"` and the "Unblock" steps both line up.
    kit = write_first_run_kit(app)

    # Bundle the unpacked browser extension so the in-app "Capture jobs from my
    # browser" walkthrough (Help ▸ Guide) can point at a real browser_ext/ folder
    # next to the exe. The receiver runs in-process (Tools ▸ Capture); the
    # extension is what the user loads via chrome://extensions ▸ Load unpacked.
    ext_src = ROOT / "browser_ext"
    ext_bundled = False
    if ext_src.exists():
        shutil.copytree(ext_src, app / "browser_ext")
        ext_bundled = True

    (PKG / "README.txt").write_text(README, encoding="utf-8")
    print(f"      data/ seeded: {', '.join(created)}")
    print(f"      first-run kit: {', '.join(kit)}")
    print(f"      browser_ext bundled: {ext_bundled}")


def zip_package() -> None:
    print("[3/3] Zipping...")
    out = shutil.make_archive(str(DIST / "JobScout"), "zip",
                              root_dir=str(DIST), base_dir="JobScout")
    print(f"Done -> {out}")


def _sign_exe(exe_path) -> None:
    """Authenticode-sign JobProgram.exe so Windows shows a real publisher and
    SmartScreen stops warning. NOT called - left for the owner to enable.

    The FIRST-RUN.txt workaround above exists *because* the exe is unsigned.
    The real fix is a code-signing certificate. An OV ("Organization Validated")
    cert or Microsoft's Azure Trusted Signing runs ~$100-200/yr and requires a
    one-time identity validation; once the exe is signed, the publisher name
    appears in the UAC/SmartScreen prompt and the "unknown publisher" warning
    goes away (SmartScreen reputation still warms up over the first downloads,
    or instantly with an EV cert).

    To enable: get a cert, then uncomment + point this at signtool.exe and call
    it from main() after run_pyinstaller(), before assemble().

        # subprocess.run([
        #     "signtool", "sign",
        #     "/fd", "SHA256",                       # file digest algorithm
        #     "/tr", "http://timestamp.digicert.com",  # RFC-3161 timestamp server
        #     "/td", "SHA256",                       # timestamp digest algorithm
        #     "/a",                                  # auto-select the best cert
        #     str(exe_path),
        # ], check=True)
    """
    raise NotImplementedError("Signing is disabled; see _sign_exe docstring.")


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
