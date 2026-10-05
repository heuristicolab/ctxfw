"""
ctxfw — Sovereign Context Firewall & Token Optimization Engine (v3.9.1)
Axiom Manifest Hash: 97b5ec2bb5f02761382a2523a5daa304851eb863641d2aa6a1059a2bd1c26414
Hermetic Toolchain implementation adhering to Google style and POSIX/XDG standards.
"""
from __future__ import annotations

__version__ = "3.9.1"

from ctxfw.core.contracts import (
    OptimizationRequestDTO,
    OptimizationResultDTO,
    PruningDepth,
    SupportedLanguage,
)
from ctxfw.config import (
    ContextDepthLevel,
    CtxfwConfigDTO,
    load_depth_config,
)
from ctxfw.core.polyglot import TreeSitterContextPruner
from ctxfw.core.pruner import DeterministicContextPruner, _MethodBodyStripper
from ctxfw.core.topological import (
    ContextFirewallEngine,
    D3SymbolExtractor,
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
    "D3SymbolExtractor",
    "ContextDepthLevel",
    "CtxfwConfigDTO",
    "load_depth_config",
    "LocalSemanticCache",
    "get_canonical_cache_path",
    "handle_init_command",
]
