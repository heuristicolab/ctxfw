"""
ctxfw — Sovereign Context Firewall & Token Optimization Engine (v3.4.0)
Hermetic Toolchain implementation adhering to Google style and POSIX/XDG standards.
"""
from __future__ import annotations

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

__version__ = "3.4.0"

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
