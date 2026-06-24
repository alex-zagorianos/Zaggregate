# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the JobProgram GUI (gui.py), one-folder build.
# Build:  pyinstaller app.spec
#
# DATA_DIR/_MEIPASS holds the read-only bundle (templates + seed assets).
# Writable runtime state (cache/, output/, user_config.json) is resolved at
# runtime by config.WRITABLE_DIR to <exe>/JobProgram, so nothing is written
# into _MEIPASS.

block_cipher = None

datas = [
    # NO personal data ships. data_templates/ holds neutral seeds that scaffold
    # the user's data folder (experience.md, preferences.md/json) on first run
    # via userdata.bootstrap(). companies.json is the public starter careers
    # registry (board slugs only — not personal).
    ('companies.json', '.'),
    ('data_templates', 'data_templates'),
    ('search/templates', 'search/templates'),
    ('resume/templates', 'resume/templates'),
]

# Lazy-imported optional clients; PyInstaller's static analysis misses them
# because they're imported inside functions. Best-effort list.
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = [
    'anthropic',
    'docx',
    'bs4',
    # coverage/ deps with C-extensions that PyInstaller's static analysis misses.
    'rapidfuzz',
]
# The GUI lazily imports first-party app modules (scrapers, feed clients,
# coverage, rerank, etc.) inside functions, so PyInstaller's static pass can
# miss them. Pull in every submodule so the frozen exe never hits an
# ImportError on first use.
for _pkg in ('search', 'scrape', 'coverage', 'discover', 'rerank',
             'resume', 'tracker', 'match', 'geo', 'ui'):
    hiddenimports += collect_submodules(_pkg)

a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='JobProgram',
)
