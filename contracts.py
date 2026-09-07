"""
contracts.py — Root Compatibility Shim for ctxfw.core and ctxfw.storage (v3.4.0)
Ensures 100% backward compatibility for existing imports and test matrices.
"""
from __future__ import annotations

import sys
from pathlib import Path

_src = Path(__file__).resolve().parent / "src"
if _src.is_dir() and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from ctxfw.core.contracts import (
    OptimizationRequestDTO,
    OptimizationResultDTO,
    PruningDepth,
    SupportedLanguage,
)
from ctxfw.core.pruner import DeterministicContextPruner, _MethodBodyStripper
from ctxfw.storage.cache import LocalSemanticCache

__all__ = [
    "PruningDepth",
    "SupportedLanguage",
    "OptimizationRequestDTO",
    "OptimizationResultDTO",
    "DeterministicContextPruner",
    "_MethodBodyStripper",
    "LocalSemanticCache",
]