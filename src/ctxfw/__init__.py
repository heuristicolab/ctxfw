# manifest_hash: 95a55fc5d3734a7591746e268f1a34b487f95a2d2fc15f646305bf738b1bffa3
"""
ctxfw — Sovereign Context Firewall & Token Optimization Engine (v4.2.2)
Axiom Manifest Hash: 95a55fc5d3734a7591746e268f1a34b487f95a2d2fc15f646305bf738b1bffa3
v4.2.2 MCP Burst Guard Manifest Hash: f1329ba99a93db6abeaa6f185ce40327ce2260c53f29ef770477ff1bf22a2546
v4.2.1 SARA-RegDoc-60 Structural Hardening Manifest Hash: f4a77d5537c6c3c60f982ed30b8dd7d6892b3c55a33c338ffb8f2f818de93700
v4.2.0 Wave 2 Security, Packaging & Provenance Release Manifest Hash: c9f28afc9543f48b94ca316d0a6cbedbf1f4baaa979ae9b033f2c36902e8c9ae
v4.1.1 MCP Registry Ownership & OIDC Manifest Hash: bcbfd27bbd8abd674d8b6345c5e0977bbc4897b1b946ed9e5851ba96746f738d
v4.1.0 FinOps, Team Merge & SWE-Gate CLI Manifest Hash: 0dd507acac7dc966a16fa69ccffcb7a51797ce899ca6edab88837448ad38d415
Hermetic Toolchain implementation adhering to Google style and POSIX/XDG standards.
Includes native integration of the TraceKit audit engine and SQLite WAL ledger.
"""
from __future__ import annotations

__version__ = "4.2.2"

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


def __getattr__(name: str):
    if name == "handle_init_command":
        from ctxfw.cli.main import handle_init_command

        globals()["handle_init_command"] = handle_init_command
        return handle_init_command
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

