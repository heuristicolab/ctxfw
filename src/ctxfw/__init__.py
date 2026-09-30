"""
ctxfw — Sovereign Context Firewall & Token Optimization Engine (v3.8.0)
Axiom Manifest Hash: 4a35e336c0621f5b76a6abb20d975bc896c15592b5da2098f2454adc6a4d66a6
Hermetic Toolchain implementation adhering to Google style and POSIX/XDG standards.
"""
from __future__ import annotations

__version__ = "3.8.0"

from ctxfw.core.contracts import (
    OptimizationRequestDTO,
    OptimizationResultDTO,
    PruningDepth,
    SupportedLanguage,
)
from ctxfw.core.polyglot import TreeSitterContextPruner
from ctxfw.core.pruner import DeterministicContextPruner, _MethodBodyStripper
from ctxfw.core.topological import (
    ContextFirewallEngine,
    ProjectDependencyGraph,
    StaticImportExtractor,
    TopologicalContextBundleDTO,
)
from ctxfw.cli import handle_init_command
from ctxfw.storage.cache import LocalSemanticCache, get_canonical_cache_path

__all__ = [
    "__version__",
    "PruningDepth",
    "SupportedLanguage",
    "OptimizationRequestDTO",
    "OptimizationResultDTO",
    "DeterministicContextPruner",
    "_MethodBodyStripper",
    "TreeSitterContextPruner",
    "StaticImportExtractor",
    "ProjectDependencyGraph",
    "TopologicalContextBundleDTO",
    "ContextFirewallEngine",
    "LocalSemanticCache",
    "get_canonical_cache_path",
    "handle_init_command",
]
