# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the JobProgram GUI (gui.py), one-folder build.
# Build:  pyinstaller app.spec
#
# DATA_DIR/_MEIPASS holds the read-only bundle (templates + seed assets).
# Writable runtime state (cache/, output/, user_config.json) is resolved at
# runtime by config.WRITABLE_DIR to <exe>/JobProgram, so nothing is written
# into _MEIPASS.
#
# SINGLE exe, FLAG-SWITCHED: gui.main() serves both the windowed app AND the
# headless daily run — `JobProgram.exe --daily [--project <slug>]` runs the same
# search->score->inbox ingest and exits with NO Tk window (used by the Task
# Scheduler job registered from Tools -> "Turn on daily updates"). So there is
# only one entry script (gui.py) and one built exe; no separate daily_run exe.

block_cipher = None

# Single source of truth for the product version (config.APP_VERSION). Read it
# here so the built exe's Windows version resource matches the app + the packaged
# zip name + CHANGES.txt. Best-effort: if the version resource can't be built we
# fall back to an unversioned exe rather than failing the build.
import os as _os
import sys as _sys
_spec_root = _os.path.dirname(_os.path.abspath(SPEC))
if _spec_root not in _sys.path:
    _sys.path.insert(0, _spec_root)
try:
    import config as _cfg
    APP_VERSION = _cfg.APP_VERSION
except Exception:
    APP_VERSION = "0.0.0"

# Build a Windows VERSIONINFO resource from APP_VERSION so right-click ->
# Properties -> Details shows the real version. Written next to the spec; only
# used on Windows (PyInstaller ignores `version=` elsewhere).
_version_file = None
try:
    _parts = (APP_VERSION.split("+")[0].split("-")[0].split("."))
    _nums = tuple(int(x) for x in (_parts + ["0", "0", "0", "0"])[:4])
    _vtext = (
        "VSVersionInfo(\n"
        "  ffi=FixedFileInfo(\n"
        f"    filevers={_nums}, prodvers={_nums},\n"
        "    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,\n"
        "    date=(0, 0)),\n"
        "  kids=[\n"
        "    StringFileInfo([StringTable('040904B0', [\n"
        "      StringStruct('CompanyName', 'Zaggregate'),\n"
        "      StringStruct('FileDescription', 'Zaggregate - personal job search'),\n"
        f"      StringStruct('FileVersion', '{APP_VERSION}'),\n"
        "      StringStruct('InternalName', 'JobProgram'),\n"
        "      StringStruct('OriginalFilename', 'JobProgram.exe'),\n"
        "      StringStruct('ProductName', 'Zaggregate'),\n"
        f"      StringStruct('ProductVersion', '{APP_VERSION}'),\n"
        "    ])]),\n"
        "    VarFileInfo([VarStruct('Translation', [1033, 1200])])\n"
        "  ]\n"
        ")\n"
    )
    # Write into build/ (gitignored) so the generated resource never litters the
    # repo root or shows up as an untracked file.
    _bdir = _os.path.join(_spec_root, "build")
    _os.makedirs(_bdir, exist_ok=True)
    _vpath = _os.path.join(_bdir, "version_info.txt")
    with open(_vpath, "w", encoding="utf-8") as _vf:
        _vf.write(_vtext)
    _version_file = _vpath
except Exception:
    _version_file = None

datas = [
    # NO personal data ships. data_templates/ holds neutral seeds that scaffold
    # the user's data folder (experience.md, preferences.md/json) on first run
    # via userdata.bootstrap(). companies.json is the public starter careers
    # registry (board slugs only — not personal).
    ('companies.json', '.'),
    ('data_static', 'data_static'),
    ('data_templates', 'data_templates'),
    ('search/templates', 'search/templates'),
    ('resume/templates', 'resume/templates'),
    # Built web-UI frontend (Vite output, committed). webui/paths.static_dir()
    # resolves this to <_MEIPASS>/webui/static when frozen, so register_webui()
    # serves /app + assets from inside the exe bundle (no sibling folder).
    ('webui/static', 'webui/static'),
    # The Claude Code channel's find-jobs skill, so agentchannel.ensure_agent_folder()
    # can copy it into Documents\Zaggregate from inside the frozen exe.
    ('claude-code', 'claude-code'),
]

# Lazy-imported optional clients; PyInstaller's static analysis misses them
# because they're imported inside functions. Best-effort list.
from PyInstaller.utils.hooks import (collect_submodules, collect_data_files,
                                     collect_dynamic_libs)

# Extra native libs to bundle (velopack.pyd's dependencies). Analysis(binaries=...)
# below consumes this; it was an inline [] before auto-update needed a PyO3 module.
binaries = []

hiddenimports = [
    'anthropic',
    'docx',
    'bs4',
    # coverage/ deps with C-extensions that PyInstaller's static analysis misses.
    'rapidfuzz',
    # ui.theme's GUI engine. Pull the whole package so its theme builders +
    # localization helpers come along; PIL is its only runtime dep (auto-hooked).
    'ttkbootstrap',
    'PIL',
]
hiddenimports += collect_submodules('ttkbootstrap')
# ttkbootstrap ships non-py data (localization .msg catalogs) the loader reads.
datas += collect_data_files('ttkbootstrap')
# The GUI lazily imports first-party app modules (scrapers, feed clients,
# coverage, rerank, etc.) inside functions, so PyInstaller's static pass can
# miss them. Pull in every submodule so the frozen exe never hits an
# ImportError on first use.
for _pkg in ('search', 'scrape', 'coverage', 'discover', 'rerank',
             'resume', 'tracker', 'match', 'geo', 'ui', 'webui'):
    hiddenimports += collect_submodules(_pkg)

# Optional Scrapling stealth/JS fetch fallback (scrape/stealth_fetch.py). Bundle
# the PYTHON packages + the Playwright node driver only — NOT the ~1.4GB browser
# binaries. The seam is a graceful no-op until the user picks "Enable stealth
# fetching", which downloads Chromium on demand via the bundled driver.
hiddenimports += ['scrapling', 'playwright', 'patchright', 'curl_cffi',
                  'browserforge', 'msgspec', 'orjson']
for _opt in ('scrapling', 'playwright', 'patchright', 'browserforge'):
    try:
        hiddenimports += collect_submodules(_opt)
        datas += collect_data_files(_opt)
    except Exception:
        # Not installed on this build box -> the stealth-fetch seam ships as
        # its graceful no-op. Say so instead of silently shrinking the build
        # (S38 debt sweep #24: the old bare pass hid which flavor you built).
        print(f"app.spec: optional package '{_opt}' not present - "
              f"stealth fetch will be unavailable in this build")

# Desktop mode (--desktop): pywebview native window over Edge WebView2. The
# Windows backend rides pythonnet + clr_loader (Python.Runtime.dll ships as
# clr_loader package data, so collect its data files too). Lazy-imported in
# webui.__main__._run_desktop — static analysis misses all of it. Best-effort:
# a build box without pywebview still builds fine, and the exe's --desktop
# degrades to browser mode by design.
for _dt in ('webview', 'clr_loader', 'pythonnet'):
    try:
        hiddenimports += [_dt] + collect_submodules(_dt)
        datas += collect_data_files(_dt)
    except Exception:
        pass
hiddenimports += ['clr']

# In-app auto-update (src/updater.py). `velopack` is a PyO3 native extension: the
# importable name is the package `velopack`, whose payload is velopack/velopack.pyd.
# Both names are declared because updater.py and gui.py import it lazily inside
# functions, where PyInstaller's static pass would otherwise miss it entirely.
#
# Unlike the stealth/pywebview seams above, a missing velopack is NOT a benign
# degradation for a RELEASE build: the shipped exe would silently lose the ability to
# self-update, which is precisely how v1.0.0 shipped without a native window. CI sets
# ZAGGREGATE_REQUIRE_VELOPACK=1 so that build fails loudly instead; a local
# `py src\build_package.py` without the wheel still builds (and says so).
import os as _os
try:
    hiddenimports += ['velopack', 'velopack.velopack']
    hiddenimports += collect_submodules('velopack')
    binaries += collect_dynamic_libs('velopack')
except Exception as _ve:
    if _os.environ.get('ZAGGREGATE_REQUIRE_VELOPACK') == '1':
        raise SystemExit(
            f"app.spec: velopack is REQUIRED for a release build but is not "
            f"importable ({_ve}). `pip install -r requirements.txt`.")
    print("app.spec: velopack not present - the exe will NOT be able to "
          "self-update (it will fall back to opening the releases page)")

# AI agent channel: bundle the `mcp` SDK so the packaged app can serve MCP over stdio
# (via the Zaggregate-MCP.exe companion below) with no separate Python or repo clone.
# Like velopack, a missing `mcp` is a silent capability loss for a release, so CI sets
# ZAGGREGATE_REQUIRE_MCP=1 to fail loudly; a local build without it just skips the
# companion exe (the second EXE is guarded on _have_mcp).
_have_mcp = False
try:
    hiddenimports += ['mcp'] + collect_submodules('mcp')
    datas += collect_data_files('mcp')
    _have_mcp = True
except Exception as _me:
    if _os.environ.get('ZAGGREGATE_REQUIRE_MCP') == '1':
        raise SystemExit(
            f"app.spec: mcp is REQUIRED for a release build but is not importable "
            f"({_me}). `pip install -r requirements.txt`.")
    print("app.spec: mcp not present - the Zaggregate-MCP.exe agent companion will "
          "NOT be built (the Claude Code channel is unavailable in this build)")

a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # S38 debt sweep #23: ~30MB of numpy/tokenizers/hf_xet/safetensors was
    # riding in on match/semantic.py's literal `import numpy` even though
    # model2vec itself never bundles - so the semantic-ranking feature could
    # never work in the exe anyway. Excluding the chain makes semantic.py's
    # gated import degrade to available()==False, byte-identical to the
    # shipped behavior. coverage/estimators.py's numpy path is unreachable
    # too (gated behind statsmodels, also excluded/never bundled). If
    # semantic ranking should ever WORK frozen, remove these and add
    # model2vec + a bundled model dir instead.
    excludes=['numpy', 'tokenizers', 'hf_xet', 'safetensors',
              'huggingface_hub', 'model2vec', 'statsmodels'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='JobProgram',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=_version_file,   # Windows version resource from config.APP_VERSION
    icon='data_static/zaggregate.ico',   # Z mark (scripts/make_icon.py)
)

# The console MCP companion (Zaggregate-MCP.exe), built from the same module graph so
# it shares the collected _internal (one runtime copy, one small extra exe). console=True
# guarantees real stdio for the MCP protocol; when an MCP client spawns it as a
# subprocess no console window appears. Only built when `mcp` bundled (see _have_mcp).
_collect_extra = []
if _have_mcp:
    b = Analysis(
        ['mcp_entry.py'],
        pathex=[],
        binaries=binaries,
        datas=datas,
        hiddenimports=hiddenimports,
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[],
        excludes=['numpy', 'tokenizers', 'hf_xet', 'safetensors',
                  'huggingface_hub', 'model2vec', 'statsmodels'],
        win_no_prefer_redirects=False,
        win_private_assemblies=False,
        cipher=block_cipher,
        noarchive=False,
    )
    pyz_b = PYZ(b.pure, b.zipped_data, cipher=block_cipher)
    exe_mcp = EXE(
        pyz_b,
        b.scripts,
        [],
        exclude_binaries=True,
        name='Zaggregate-MCP',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=True,   # stdio MUST be real for MCP; a windowed exe has null stdio
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        version=_version_file,
        icon='data_static/zaggregate.ico',
    )
    _collect_extra = [exe_mcp, b.binaries, b.zipfiles, b.datas]

coll = COLLECT(
    exe,
    *_collect_extra,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='JobProgram',
)
