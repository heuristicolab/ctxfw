"""
scripts/build_standalone.py — Automated Standalone Packaging Harness (v3.5.0)
Builds the standalone binary using PyInstaller with embedded Tree-sitter binaries,
validating autonomous execution across subcommands without Python installed.
"""
from __future__ import annotations

import os
from pathlib import Path
import platform
import subprocess
import sys
import time


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    os.chdir(project_root)

    print("========================================================================")
    print("  CONTEXT FIREWALL -- ZERO-PYTHON STANDALONE BUILD HARNESS (v3.5.0)    ")
    print("========================================================================")
    print(f"[*] Project Root: {project_root}")
    print(f"[*] Platform:     {platform.system()} ({platform.machine()})")
    print(f"[*] Python:       {sys.version.split()[0]}")

    # Check for PyInstaller
    try:
        import PyInstaller
        print(f"[*] PyInstaller Version: {PyInstaller.__version__}")
    except ImportError:
        print("[!] PyInstaller not found. Installing into current environment...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # Run PyInstaller using ctxfw.spec
    spec_path = project_root / "ctxfw.spec"
    if not spec_path.is_file():
        sys.stderr.write(f"[ERROR] Specification file not found: {spec_path}\n")
        return 1

    t0 = time.perf_counter()
    build_cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(spec_path),
        "--clean",
        "--noconfirm",
    ]
    print(f"[*] Executing: {' '.join(build_cmd)}")
    p = subprocess.run(build_cmd)
    if p.returncode != 0:
        sys.stderr.write(f"[ERROR] Build failed with exit code {p.returncode}\n")
        return p.returncode

    build_time = time.perf_counter() - t0
    exe_name = "ctxfw.exe" if platform.system() == "Windows" else "ctxfw"
    dist_binary = project_root / "dist" / exe_name

    if not dist_binary.is_file():
        sys.stderr.write(f"[ERROR] Expected binary not found at: {dist_binary}\n")
        return 1

    size_mb = dist_binary.stat().st_size / (1024 * 1024)
    print(f"[+] Standalone binary built successfully in {build_time:.2f}s!")
    print(f"    Path: {dist_binary}")
    print(f"    Size: {size_mb:.2f} MB")

    # Verification of subcommands
    print("\n[*] Validating Autonomous Subcommands Execution (Zero-Python Toolchain):")
    subcommands = [
        ["--help"],
        ["proxy", "--help"],
        ["mcp", "--help"],
        ["service", "--help"],
    ]

    for sub in subcommands:
        cmd = [str(dist_binary)] + sub
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5.0)
            status = "PASSED" if proc.returncode == 0 else f"FAILED (code {proc.returncode})"
            print(f"    - ctxfw {' '.join(sub):<18} => {status}")
            if proc.returncode != 0:
                sys.stderr.write(proc.stderr)
                return 1
        except subprocess.TimeoutExpired:
            print(f"    - ctxfw {' '.join(sub):<18} => FAILED (Timeout)")
            return 1

    print("\n[+] All subcommands verified. Zero-Python standalone package ready for fleet deployment!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
