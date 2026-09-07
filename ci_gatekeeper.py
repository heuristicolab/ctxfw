"""
ci_gatekeeper.py — Root Compatibility Shim for ctxfw.gatekeeper (v3.4.0)
"""
from __future__ import annotations

import sys
from pathlib import Path

_src = Path(__file__).resolve().parent / "src"
if _src.is_dir() and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from ctxfw.gatekeeper import (
    CIGatekeeper,
    PRE_COMMIT_CONFIG_TEMPLATE,
    main,
)

__all__ = ["CIGatekeeper", "PRE_COMMIT_CONFIG_TEMPLATE", "main"]

if __name__ == "__main__":
    main()
