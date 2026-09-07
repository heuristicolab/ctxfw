"""
finops_auditor.py — Root Compatibility Shim for ctxfw.auditor (v3.4.0)
"""
from __future__ import annotations

import sys
from pathlib import Path

_src = Path(__file__).resolve().parent / "src"
if _src.is_dir() and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from ctxfw.auditor import (
    FinOpsAuditor,
    FinOpsReportDTO,
    main,
)

__all__ = ["FinOpsReportDTO", "FinOpsAuditor", "main"]

if __name__ == "__main__":
    main()
