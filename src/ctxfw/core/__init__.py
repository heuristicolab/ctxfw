"""
src/ctxfw/core/__init__.py — Core algorithmic components
"""
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

__all__ = [
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
]
