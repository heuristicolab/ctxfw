# -*- mode: python ; coding: utf-8 -*-
"""
ctxfw.spec — Standalone PyInstaller Specification (v3.5.0)
Embeds Tree-sitter C grammars and binary runtime (.pyd / .so) using PyInstaller.utils.hooks.collect_all
Guarantees zero-python toolchain execution across Windows, macOS, and Linux.
"""
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files

block_cipher = None

datas = [
    ('schema.sql', '.'),
    ('src/ctxfw/storage/schema.sql', 'ctxfw/storage'),
]
binaries = []
hiddenimports = [
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
    'ctxfw.cli',
    'ctxfw.cli.main',
    'ctxfw.cli.commands',
    'ctxfw.cli.commands.benchmark',
    'ctxfw.proxy',
    'ctxfw.mcp',
    'ctxfw.service',
    'ctxfw.auditor',
    'ctxfw.gatekeeper',
    'ctxfw.storage.telemetry',
    'ctxfw.storage.dashboard_template',
]

# Tactical Guardrail 2: Collect all dynamic binary extensions (.pyd/.so), grammar tables, and data files
for pkg in ['tree_sitter', 'tree_sitter_typescript', 'tree_sitter_go', 'tree_sitter_java']:
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
