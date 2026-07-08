"""Build the Zaggregate distributable — the Velopack Setup.exe (and a legacy zip).

  1. pyinstaller app.spec     -> dist/JobProgram/ (onedir, windowed GUI)
  2. assemble  dist/Zaggregate/ -> the app folder + README.txt
  3. zip                      -> dist/Zaggregate.zip

Run:
  py build_package.py              # full build -> the shippable zip
  py build_package.py --no-build   # reassemble from an existing dist/JobProgram
  py build_package.py --velopack   # print the `vpk pack` argv for dist/JobProgram
                                    #   (CI runs it; needs the .NET SDK). --channel
                                    #   selects the update feed: win (stable) | beta.
  py build_package.py --production  # assemble a ready-to-run production/ folder
                                    #   at the repo root (exe + every runtime file
                                    #   + browser_ext/ + .env.example + QUICKSTART),
                                    #   NOT zipped — a reproducible "hand this folder
                                    #   to a user" artifact. Combine with --no-build
                                    #   to skip PyInstaller and reuse dist/JobProgram.

Requires `pip install pyinstaller` (pinned in requirements.txt). NO personal data
is included, and (since 2026-07-08) no `data/` folder is shipped at all: the frozen
app anchors user data at %LOCALAPPDATA%/JobProgram and seeds it at runtime via
userdata.bootstrap(). Velopack replaces the exe's own folder on every update, so
nothing user-owned may live beside the exe.

The `production/` folder (like dist/, build/) is a BUILD ARTIFACT — gitignored.
The deliverable is THIS script + app.spec; run one command to regenerate the folder.
"""
import argparse
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

SRC = Path(__file__).resolve().parent    # src/ — code + bundled assets
ROOT = SRC.parent                        # repo root — build outputs, user-facing docs
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
import config

# Single source of truth for the release version (config.APP_VERSION): names the
# zip, stamps CHANGES.txt, matches the exe's version resource (app.spec).
APP_VERSION = config.APP_VERSION

DIST = ROOT / "dist"
APP_BUILD = DIST / "JobProgram"     # PyInstaller onedir output
PKG = DIST / "Zaggregate"             # assembled package
PROD = ROOT / "production"           # ready-to-run production folder (gitignored)

# ── Velopack packaging (auto-update phase 2) ──────────────────────────────────
# The NuGet-style package id that names the install root (%LOCALAPPDATA%\Zaggregate)
# and every Release asset. NEVER change it after the first release ships — Velopack
# matches an installed app to its update feed by this id.
VELOPACK_PACK_ID = "Zaggregate"
VELOPACK_MAIN_EXE = "JobProgram.exe"
# Update feeds. `win` is Velopack's default channel name for Windows; beta testers
# install a build packed with `--channel beta` and stay on the beta feed forever
# (UpdateOptions.ExplicitChannel can move them back to stable without reinstalling).
VELOPACK_CHANNELS = ("win", "beta")

README = f"""\
Zaggregate v{APP_VERSION}

First time? Read FIRST-RUN.txt - it shows how to open the app past Windows'
"unknown publisher" warning (the app is safe; it just isn't code-signed yet).

Zaggregate - a personal job search that ranks roles to YOUR preferences using
your own AI (Claude, ChatGPT, Gemini, Copilot - a free tier is fine).

QUICK START
  1. Open the JobProgram folder and double-click  Zaggregate-Desktop.bat
     (or JobProgram.exe - same thing): the app opens in its own window.
     Prefer your browser? Double-click  Zaggregate-Web.bat  instead.
  2. The first time, a short Setup wizard asks what jobs you want, where, your
     salary, and your resume - no files to edit. (Changed your mind later? Run it
     again from  Help -> Run Setup Wizard.)
  3. Search, then click "Ask AI to rank these", paste the prompt into your own
     AI chat, and paste the reply back with "Paste AI ranking". The app ranks
     your inbox to your preferences. (Optional: add an API key in
     Tools > "Connect your AI (API key)..." to rank automatically, no pasting.)

To keep your Inbox filling on its own, turn on daily updates from
Tools > "Turn on daily updates".

UPGRADING TO A NEWER VERSION
  Your app and your data are kept separate, so upgrading never loses your saved
  jobs, preferences, or resume.
  1. Download and unzip the new Zaggregate-vX.Y.Z.zip to a NEW folder.
  2. Point the new app at your existing data - EITHER:
       * copy your old  JobProgram\\data  folder into the new
         JobProgram\\ folder (replacing the empty seeded one), OR
       * on a protected install where your data lives under
         %LOCALAPPDATA%\\JobProgram, the new app finds it automatically.
  3. Run the new JobProgram.exe. Your Inbox, tracker, and settings carry over.
  See CHANGES.txt for what's new in this version.

Everything you enter stays on this computer. To find or back up your files, use
Help -> Open my data folder (the app picks the right location automatically; on a
protected install it lives under %LOCALAPPDATA%\\JobProgram). Nothing is sent
anywhere except the prompts you choose to paste into your own AI.
"""

# A minimal per-release changelog stub written next to README.txt. The date is a
# placeholder the release author fills in; the body points at the review that
# drove this release rather than duplicating it.
CHANGES = f"""\
Zaggregate - CHANGES

v{APP_VERSION} - {date.today().isoformat()}
  Zaggregate now updates itself. Install once with Setup.exe; from then on
  Settings > "Check for updates" downloads the new version and restarts into
  it. Your data is untouched - it lives outside the app folder now, in
  %LOCALAPPDATA%\\JobProgram.
  Upgrading from a v1.0.2 zip? Open the old app, Settings > "Download a
  backup", install Setup.exe, then Settings > "Restore from backup".
  The legacy Tk window is retired: the app always opens the modern UI.

v1.0.2 - 2026-07-07
  The desktop app is now the default: double-clicking JobProgram.exe (or
  Zaggregate-Desktop.bat) opens the app in its own window. Zaggregate-Web.bat
  opens the same app in your browser.

v1.0.1 - 2026-07-07
  Desktop mode restored in the packaged app: the Desktop launcher opens the
  app in its own native window again. (The v1.0.0 build shipped without the
  native-window runtime, so it quietly fell back to the browser.)

v1.0.0 - 2026-07-07
  First public release.
"""

# Friendly walkthrough for getting past SmartScreen. A non-technical user reads
# "unknown publisher" as "virus" - this spells out the two safe ways to open it.
FIRST_RUN_TXT = """\
HOW TO OPEN ZAGGREGATE THE FIRST TIME
===================================

Zaggregate is safe, but it isn't "code-signed" yet, so Windows shows a warning
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
  4. Zaggregate starts. You won't be asked again.

THE EASY LAUNCHERS
  Zaggregate-Desktop.bat  opens the app in its own window (recommended), and
  Zaggregate-Web.bat  opens the same app in your browser. Both run
  JobProgram.exe for you, so the one-time steps above cover them too.

That's it. Once it has opened the first time, just double-click it like any
other program from then on.
"""

# One-click launchers, named after the product so the folder reads itself
# (S44c: exactly two, no legacy `launch.bat`):
#   Zaggregate-Desktop.bat -> the app in its own native window (the default —
#                             bare JobProgram.exe opens the same thing)
#   Zaggregate-Web.bat     -> the same app in the user's default browser
# A .bat is far less likely to be quarantined than the .exe and lets us print
# a friendly line. `start "" "..."` launches and returns immediately (the
# empty "" is start's required window title); `%~dp0` = this .bat's own
# folder, so a shortcut still finds the exe sitting next to it. The legacy Tk
# window is no longer a shipped surface (retired 2026-07-08); the exe always
# opens the modern UI.
DESKTOP_BAT = """\
@echo off
echo Starting Zaggregate (desktop app)...
start "" "%~dp0JobProgram.exe" --desktop
"""

WEB_BAT = """\
@echo off
echo Starting Zaggregate (web version, opens in your browser)...
start "" "%~dp0JobProgram.exe" --web
"""

# Top-level "start here" for the production/ folder. Deliberately SHORT: the app's
# own in-app Guide (Help ▸ Guide) carries the full walkthrough — this just gets a
# user from "unzipped folder" to "the wizard is open" and points at the extension.
QUICKSTART_MD = f"""\
# Zaggregate v{APP_VERSION} — Quick Start

Zaggregate is a personal job search that ranks roles to YOUR preferences using
your own AI (Claude, ChatGPT, Gemini, Copilot — a free tier is fine). Everything
stays on this computer — no account, no cloud, no telemetry (see `PRIVACY.md`).

## 1. Run the app

Open the `JobProgram` folder and double-click **`Zaggregate-Desktop.bat`**
(or `JobProgram.exe` — same thing): the app opens in its own window.

First time only, Windows may warn about an "unknown publisher" (the app is safe,
it just isn't code-signed yet). See `JobProgram/FIRST-RUN.txt` for the two safe
ways past it.

A short **Setup wizard** opens the first time and asks what jobs you want, where,
your salary, and your resume. No files to edit. (Change your mind later from
**Help ▸ Run Setup Wizard**.)

### Prefer your browser? (optional)

The same exe runs every mode — the `JobProgram` folder has a double-clickable
launcher for each, no typing needed:

- **`Zaggregate-Desktop.bat`** (= `JobProgram.exe --desktop`, also what plain
  `JobProgram.exe` opens) — the app in its own window (no browser needed).
- **`Zaggregate-Web.bat`** (= `JobProgram.exe --web`) — the same app in
  your default browser (loopback only — nothing is exposed off your machine).

## 2. Get a ranked inbox

Search, then click **"Ask AI to rank these"**, paste the prompt into your own AI
chat, and paste the reply back with **"Paste AI ranking"**. Optional: add an API
key under **Tools ▸ "Connect your AI (API key)…"** to rank automatically.

Turn on **Tools ▸ "Turn on daily updates"** to keep the Inbox filling on its own.

## 3. (Optional) Capture jobs from your browser

The **`browser_ext`** folder in here is a Chrome/Edge extension that clips a job
straight from an employer's careers page into Zaggregate.

1. In the app, open **Tools ▸ Capture** (starts the in-app receiver).
2. In Chrome/Edge, go to `chrome://extensions`, turn on **Developer mode**, click
   **Load unpacked**, and pick this `browser_ext` folder.
3. On any job page, click the Zaggregate toolbar button to send it to your Inbox.

The in-app **Help ▸ Guide** has the full, illustrated walkthrough.

## Your data & upgrades

Your saved jobs, preferences, and resume live in `JobProgram/data` (or, on a
protected install, under `%LOCALAPPDATA%\\JobProgram`). App and data are kept
separate, so upgrading to a newer version never loses your data — see
`README.txt` in this folder for the upgrade steps.

`PRIVACY.md` (how your data is handled — short version: it never leaves this
computer) and `EULA.txt` (the beta terms of use) are in this folder too.

## Advanced: API keys and BYO-AI

`.env.example` lists every optional API key (job sources, your AI backend). You do
NOT need any of them to start — the app works keyless and via copy/paste. Power
users can copy it to `.env` next to the exe, or paste keys into the in-app
**"Connect job sources"** / **"Connect your AI"** dialogs.
"""


def write_first_run_kit(dest_dir):
    """Write the SmartScreen first-run helpers into *dest_dir*.

    Drops plain-English files next to JobProgram.exe so a non-technical
    Windows user can open the unsigned app without typing flags:
      - FIRST-RUN.txt          : numbered steps to unblock / "Run anyway" past SmartScreen
      - Zaggregate-Desktop.bat : the app in its own native window (the default)
      - Zaggregate-Web.bat     : the same app in the default browser

    Returns the list of filenames created (handy for the build log).
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / "FIRST-RUN.txt").write_text(FIRST_RUN_TXT, encoding="utf-8")
    (dest_dir / "Zaggregate-Desktop.bat").write_text(DESKTOP_BAT, encoding="utf-8")
    (dest_dir / "Zaggregate-Web.bat").write_text(WEB_BAT, encoding="utf-8")
    return ["FIRST-RUN.txt", "Zaggregate-Desktop.bat", "Zaggregate-Web.bat"]


def _normalize_pack_version(pack_version: str | None) -> str:
    """The SemVer string Velopack packs under. Defaults to config.APP_VERSION.

    A beta pre-release must pack under the FULL prerelease version (e.g. the tag
    `v1.0.3-beta1` -> `1.0.3-beta1`), NOT the bare `1.0.3`: SemVer sorts a prerelease
    BELOW its release, which is exactly what keeps a beta tester ahead of the stable
    feed and lets the eventual stable `1.0.3` carry them forward. A leading `v` is
    tolerated so the tag can be passed straight through."""
    v = (pack_version or APP_VERSION).strip()
    return v[1:] if v[:1] in ("v", "V") else v


def vpk_pack_argv(channel: str = "win", *, pack_version=None,
                  pack_dir=None, out_dir=None) -> list[str]:
    """The exact `vpk pack` command line for the current build, as an argv list.

    Single source of truth so CI can never drift from the pack id an already-installed
    app is bound to. `vpk` is a .NET tool absent from most dev boxes, so this module
    only BUILDS (and unit-tests) the argv; pass ``--run`` on the CLI to actually shell
    it out (CI does that after installing vpk).

    `channel` selects the update feed the produced Setup.exe is bound to:
      * "win"  — the stable feed (Velopack's Windows default)
      * "beta" — the closed-cohort feed, fed by `vX.Y.Z-betaN` pre-release tags

    Raises ValueError on an unknown channel rather than silently packing a feed no
    installed client will ever poll."""
    if channel not in VELOPACK_CHANNELS:
        raise ValueError(
            f"unknown Velopack channel {channel!r}; expected one of {VELOPACK_CHANNELS}")
    # Default to the ASSEMBLED app (PKG/JobProgram), not the raw PyInstaller output
    # (APP_BUILD): the assembled copy carries browser_ext/ + claude-code/ that the
    # in-app Guide points at. `python build_package.py` (no args) produces it via
    # assemble() before this runs.
    pack_dir = Path(pack_dir) if pack_dir else (PKG / "JobProgram")
    out_dir = Path(out_dir) if out_dir else (DIST / "Releases")
    return [
        "vpk", "pack",
        "--packId", VELOPACK_PACK_ID,
        "--packVersion", _normalize_pack_version(pack_version),
        "--packDir", str(pack_dir),
        "--mainExe", VELOPACK_MAIN_EXE,
        "--packTitle", VELOPACK_PACK_ID,
        "--channel", channel,
        "--outputDir", str(out_dir),
    ]


def run_pyinstaller() -> None:
    print("[1/3] PyInstaller (app.spec)...")
    # cwd=ROOT keeps PyInstaller's dist/ + build/ outputs at the repo root;
    # the spec lives in src/ so its own relative paths resolve beside the code.
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "src/app.spec"],
                   cwd=ROOT, check=True)


def _populate_app(app) -> dict:
    """Turn a fresh copy of the PyInstaller onedir build (`app` = the JobProgram/
    folder holding JobProgram.exe) into a runnable app: seed data/, drop the
    SmartScreen first-run kit, and bundle browser_ext/ + the claude-code MCP
    channel next to the exe. Shared by the zip package (assemble) and the
    production folder (assemble_production) so both stay byte-identical.

    Returns a manifest dict (kit files, what bundled) for the log.

    NOTE (2026-07-08, Velopack phase 2): this function no longer seeds a `data/`
    folder beside the exe. The frozen app now anchors user data at
    %LOCALAPPDATA%/JobProgram (config._get_user_data_dir) because Velopack
    replaces the exe's own folder wholesale on every update — a `data/` next to
    the exe would look like the user's data and be destroyed on first update.
    Seeding happens at runtime instead: every entry point calls
    `userdata.bootstrap()` (gui.py, webui/__main__.py, daily_run.py,
    mcp_server.py), which scaffolds from the bundled data_templates/."""
    # SmartScreen first-run helpers, next to JobProgram.exe so launch.bat's
    # relative `start "" "JobProgram.exe"` and the "Unblock" steps both line up.
    kit = write_first_run_kit(app)

    # Bundle the unpacked browser extension so the in-app "Capture jobs from my
    # browser" walkthrough (Help ▸ Guide) can point at a real browser_ext/ folder
    # next to the exe. The receiver runs in-process (Tools ▸ Capture); the
    # extension is what the user loads via chrome://extensions ▸ Load unpacked.
    ext_src = SRC / "browser_ext"
    ext_bundled = False
    if ext_src.exists():
        shutil.copytree(ext_src, app / "browser_ext")
        ext_bundled = True

    # Bundle the Claude Code / MCP channel so a friend who wants to drive the
    # search (or any application-cycle help) from Claude Code or another MCP
    # client has the server config, skill, README, and its pip requirements next
    # to the exe. This is the bring-your-own-AI path; it needs a Python + `mcp`
    # SDK the exe user may not have, so it ships as source alongside, not baked in.
    cc_src = SRC / "claude-code"
    cc_bundled = False
    if cc_src.exists():
        shutil.copytree(cc_src, app / "claude-code")
        cc_bundled = True
    req_mcp = ROOT / "requirements-mcp.txt"
    req_bundled = False
    if req_mcp.exists():
        shutil.copyfile(req_mcp, app / "requirements-mcp.txt")
        req_bundled = True

    return {
        "kit": kit,
        "ext_bundled": ext_bundled,
        "cc_bundled": cc_bundled,
        "req_bundled": req_bundled,
    }


def _print_app_manifest(m: dict) -> None:
    print(f"      version: v{APP_VERSION}")
    print(f"      data/ seeded: (none — runtime userdata.bootstrap() seeds "
          f"%LOCALAPPDATA%/JobProgram)")
    print(f"      first-run kit: {', '.join(m['kit'])}")
    print(f"      browser_ext bundled: {m['ext_bundled']}")
    print(f"      claude-code bundled: {m['cc_bundled']}; "
          f"requirements-mcp: {m['req_bundled']}")


# The trust docs live at the repo root and ship at the top of every distributed
# folder (next to README.txt), so a user sees the privacy policy and beta terms
# without digging into the app folder. Copied verbatim from the source tree — the
# repo copies (PRIVACY.md / EULA.txt) are the single source of truth.
TRUST_DOCS = ("PRIVACY.md", "EULA.txt")


def _copy_trust_docs(dest_dir) -> list[str]:
    """Copy the repo-root trust docs (PRIVACY.md, EULA.txt) into *dest_dir*.

    Ships the privacy policy + beta EULA at the top of the distributed folder so
    they're visible next to README.txt. Returns the names actually copied (a
    missing source is skipped, not fatal — the build still produces a folder)."""
    dest_dir = Path(dest_dir)
    copied = []
    for name in TRUST_DOCS:
        src = ROOT / name
        if src.exists():
            shutil.copyfile(src, dest_dir / name)
            copied.append(name)
    return copied


def assemble() -> None:
    print("[2/3] Assembling package...")
    if not APP_BUILD.exists():
        sys.exit(f"No build at {APP_BUILD}. Run without --no-build first.")
    if PKG.exists():
        shutil.rmtree(PKG)
    app = PKG / "JobProgram"
    shutil.copytree(APP_BUILD, app)

    manifest = _populate_app(app)

    (PKG / "README.txt").write_text(README, encoding="utf-8")
    (PKG / "CHANGES.txt").write_text(CHANGES, encoding="utf-8")
    trust = _copy_trust_docs(PKG)
    _print_app_manifest(manifest)
    print(f"      trust docs: {', '.join(trust) or '(none found)'}")


def production_contents() -> list[str]:
    """The top-level entries the production/ folder is expected to contain, in a
    stable order. A single source of truth so the build and its unit test agree on
    exactly what a user receives. (JobProgram/ is the app; browser_ext/ is lifted
    to the top level so the 'Load unpacked' target is obvious.)"""
    return [
        "JobProgram",       # the app folder: JobProgram.exe + runtime files + data/
        "browser_ext",      # unpacked Chrome/Edge extension (Load unpacked here)
        "QUICKSTART.md",    # start-here walkthrough
        "README.txt",       # full readme (upgrade path, data location)
        "CHANGES.txt",      # per-release changelog
        "PRIVACY.md",       # privacy policy (data stays local)
        "EULA.txt",         # beta terms of use
        ".env.example",     # optional API keys (BYO-AI / job sources)
    ]


def assemble_production() -> None:
    """Assemble a ready-to-run `production/` folder at the repo root: the runnable
    exe + every runtime file + a top-level browser_ext/ + .env.example + QUICKSTART.
    NOT zipped — this is the 'here is the folder' artifact. Rebuildable, gitignored.

    Layout:
      production/
        JobProgram/            JobProgram.exe + PyInstaller runtime + data/ +
                               FIRST-RUN.txt + launch.bat + browser_ext/ + claude-code/
        browser_ext/           the extension, lifted to the top level so the user's
                               'Load unpacked' target is obvious (mirror of the copy
                               inside JobProgram/, which the in-app Guide points at)
        QUICKSTART.md          run the exe -> wizard -> load the extension
        README.txt / CHANGES.txt
        .env.example           optional keys; the app needs none to start
    """
    print("[2/3] Assembling production folder...")
    if not APP_BUILD.exists():
        sys.exit(f"No build at {APP_BUILD}. Run without --no-build first.")
    if PROD.exists():
        shutil.rmtree(PROD)
    PROD.mkdir(parents=True)
    app = PROD / "JobProgram"
    shutil.copytree(APP_BUILD, app)

    manifest = _populate_app(app)

    # Lift browser_ext/ to the production root so the "Load unpacked" target is
    # obvious without digging into JobProgram/. (JobProgram/browser_ext also exists
    # for the in-app Guide's relative pointer — this is the friendly duplicate.)
    ext_src = SRC / "browser_ext"
    if ext_src.exists():
        shutil.copytree(ext_src, PROD / "browser_ext")

    (PROD / "QUICKSTART.md").write_text(QUICKSTART_MD, encoding="utf-8")
    (PROD / "README.txt").write_text(README, encoding="utf-8")
    (PROD / "CHANGES.txt").write_text(CHANGES, encoding="utf-8")
    trust = _copy_trust_docs(PROD)

    # Optional keys, for power users. The app starts with none (keyless + copy/paste),
    # so this is reference material, not a required step.
    env_example = ROOT / ".env.example"
    env_bundled = False
    if env_example.exists():
        shutil.copyfile(env_example, PROD / ".env.example")
        env_bundled = True

    _print_app_manifest(manifest)
    print(f"      trust docs: {', '.join(trust) or '(none found)'}")
    print(f"      .env.example bundled: {env_bundled}")
    print(f"      production/ -> {PROD}")


def zip_name() -> str:
    """The versioned archive base name (no extension), e.g. 'Zaggregate-v1.0.0'.
    Kept as a helper so the build and its unit test agree on the naming."""
    return f"Zaggregate-v{APP_VERSION}"


SHA256SUMS_NAME = "SHA256SUMS.txt"


def _sha256_of(path) -> str:
    """The SHA-256 hex digest of a file, streamed so a large zip isn't slurped
    into memory."""
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_sha256sums(zip_paths, dest_dir) -> str:
    """Write a ``SHA256SUMS.txt`` next to the produced zip(s) so a downloader can
    verify the archive is intact and unmodified (the beta ships unsigned, so a
    checksum is the trust anchor). Standard ``sha256sum`` format — ``<hex>  <name>``
    (two spaces, bare basename) — so ``sha256sum -c SHA256SUMS.txt`` and Windows
    ``certutil -hashfile <zip> SHA256`` both line up. Returns the manifest path."""
    dest_dir = Path(dest_dir)
    lines = []
    for zp in zip_paths:
        zp = Path(zp)
        lines.append(f"{_sha256_of(zp)}  {zp.name}")
    manifest = dest_dir / SHA256SUMS_NAME
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(manifest)


def zip_package() -> None:
    print("[3/3] Zipping...")
    out = shutil.make_archive(str(DIST / zip_name()), "zip",
                              root_dir=str(DIST), base_dir="Zaggregate")
    print(f"Done -> {out}")
    sums = write_sha256sums([out], DIST)
    print(f"Checksums -> {sums}")
    refresh_executables()


# The tracked repo-root Executables/ folder: a lightweight POINTER for
# non-technical visitors. The app itself ships as a zip attached to each
# GitHub Release, built by CI (.github/workflows/release.yml) when a version
# tag is pushed — committing the ~50 MB onedir per version was bloating git
# history (S43c layout, retired S44). Only the version-stamped README lives
# here now, regenerated on every zip build so it never goes stale.
EXECUTABLES = ROOT / "Executables"

EXECUTABLES_README = f"""\
# Just want to run the app? Download it here.

The ready-to-run Windows app — Zaggregate v{APP_VERSION} — is a free download
on the **[latest release](https://github.com/alex-zagorianos/Zaggregate/releases/latest)**
page. No Python, no build tools, no source code needed.

## Get the app (about 2 minutes)

1. Open the [latest release](https://github.com/alex-zagorianos/Zaggregate/releases/latest)
   and, under **Assets**, download **`Zaggregate-v{APP_VERSION}.zip`**.
2. Extract it anywhere (right-click → *Extract All…*).
3. Open the extracted `Zaggregate/JobProgram` folder and **double-click
   `Zaggregate-Desktop.bat`** — the app opens in its own window.
   (`Zaggregate-Web.bat` opens the same app in your browser instead; plain
   `JobProgram.exe` also opens the desktop app.)

Want to check the download? `SHA256SUMS.txt` on the same release page carries
the zip's checksum (`certutil -hashfile <zip> SHA256` on Windows).

## First launch

Windows may show an "unknown publisher" warning once (the app is safe — it
just isn't code-signed yet). Click **More info → Run anyway**, or see
`JobProgram/FIRST-RUN.txt` inside the download for the two safe ways past it.

That's it — a short setup wizard opens, or use **Set up with AI** to configure
everything with one paste. Everything stays on your computer: no account, no
cloud, no telemetry.

## Why isn't the app in this folder anymore?

It used to be — but shipping the built app inside the repository added ~50 MB
to its history with every version. Each release zip is now built from this
exact source by GitHub Actions and attached to the Release instead. Curious
how it works, or want to run from source? Start at the
[main README](../README.md).
"""


def refresh_executables() -> None:
    """Keep Executables/ a lightweight pointer: regenerate the version-stamped
    README that sends users to the GitHub Release download, and clear any app
    payload left by the retired layouts (S43b nested zip, S43c unzipped
    onedir) so ~50 MB per version stays out of git."""
    EXECUTABLES.mkdir(exist_ok=True)
    stale_app = EXECUTABLES / "JobProgram"
    if stale_app.exists():
        shutil.rmtree(stale_app)
    for old in list(EXECUTABLES.glob("Zaggregate-v*.zip")) + [EXECUTABLES / SHA256SUMS_NAME]:
        if old.exists():
            old.unlink()
    (EXECUTABLES / "README.md").write_text(EXECUTABLES_README, encoding="utf-8")
    print("Executables/ README refreshed (the app ships via GitHub Releases)")


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
    ap = argparse.ArgumentParser(description="Build the Zaggregate distributable.")
    ap.add_argument("--no-build", action="store_true",
                    help="Skip PyInstaller; reassemble from an existing dist/JobProgram.")
    ap.add_argument("--production", action="store_true",
                    help="Assemble a ready-to-run production/ folder at the repo "
                         "root (exe + runtime files + browser_ext + .env.example + "
                         "QUICKSTART) instead of the shippable zip. Gitignored artifact.")
    ap.add_argument("--velopack", action="store_true",
                    help="Print the `vpk pack` argv for dist/JobProgram (does not run "
                         "vpk unless --run is given — vpk is a .NET tool).")
    ap.add_argument("--run", action="store_true",
                    help="With --velopack, actually execute vpk (CI, after installing "
                         "the tool). Without it, the argv is only printed.")
    ap.add_argument("--channel", default="win", choices=list(VELOPACK_CHANNELS),
                    help="Velopack update feed for --velopack (default: win).")
    ap.add_argument("--pack-version", default=None,
                    help="Override the Velopack pack version (defaults to "
                         "config.APP_VERSION; pass the full tag for a beta prerelease, "
                         "e.g. 1.0.3-beta1).")
    args = ap.parse_args()
    if args.velopack:
        argv = vpk_pack_argv(args.channel, pack_version=args.pack_version)
        if args.run:
            print("[vpk]", " ".join(argv))
            subprocess.run(argv, check=True)
        else:
            # Emit the argv, one token per line, so a CI shell can read it back
            # verbatim without re-deriving the version or quoting a path with spaces.
            for token in argv:
                print(token)
        return
    if not args.no_build:
        run_pyinstaller()
    if args.production:
        assemble_production()
    else:
        assemble()
        zip_package()


if __name__ == "__main__":
    main()
