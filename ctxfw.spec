# -*- mode: python ; coding: utf-8 -*-
"""
ctxfw.spec — Standalone PyInstaller Specification (v4.2.1)
Embeds Tree-sitter C grammars, lazy ctxfw submodules, SQL schemas, and blueprint manifests
using PyInstaller.utils.hooks.{collect_all, collect_submodules, collect_data_files}.
Guarantees zero-python toolchain execution across Windows, macOS, and Linux.
"""
import importlib.util
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files

_SRC_PATH = str(Path('src').resolve())
if _SRC_PATH not in sys.path:
    sys.path.insert(0, _SRC_PATH)

block_cipher = None

datas = list(collect_data_files('ctxfw'))
binaries = []
hiddenimports = sorted(set([
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'fastapi',
    'fastapi.responses',
    'starlette',
    'httpx',
] + collect_submodules('ctxfw')))

# Tactical Guardrail 2: Collect all dynamic binary extensions (.pyd/.so), grammar tables, and data files
for pkg in ['tree_sitter', 'tree_sitter_python', 'tree_sitter_typescript', 'tree_sitter_go', 'tree_sitter_java']:
    if importlib.util.find_spec(pkg) is None:
        continue
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas.extend(pkg_datas)
        binaries.extend(pkg_binaries)
        hiddenimports.extend(pkg_hidden)
    except Exception:
        pass

a = Analysis(
    ['src/ctxfw/cli/__main__.py'],
    pathex=['src', '.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'scipy', 'pandas', 'IPython', 'notebook'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ctxfw',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
