"""
topological_resolver.py — Root Compatibility Shim for ctxfw.core.topological (v3.4.0)
"""
from __future__ import annotations

import sys
from pathlib import Path

_src = Path(__file__).resolve().parent / "src"
if _src.is_dir() and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from ctxfw.core.topological import (
    ContextFirewallEngine,
    ProjectDependencyGraph,
    StaticImportExtractor,
    TopologicalContextBundleDTO,
    TopologicalResolver,
)

__all__ = [
    "StaticImportExtractor",
    "ProjectDependencyGraph",
    "TopologicalContextBundleDTO",
    "ContextFirewallEngine",
    "TopologicalResolver",
]
