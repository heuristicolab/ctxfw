"""
firewall_cli.py — Root Compatibility Shim for ctxfw.cli (v3.4.0)
"""
from __future__ import annotations

import sys
from pathlib import Path

_src = Path(__file__).resolve().parent / "src"
if _src.is_dir() and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from ctxfw.cli import (
    copy_to_clipboard,
    handle_init_command,
    init_entrypoint,
    main,
    run_firewall_cli,
)

__all__ = ["copy_to_clipboard", "run_firewall_cli", "handle_init_command", "init_entrypoint", "main"]

if __name__ == "__main__":
    main()
