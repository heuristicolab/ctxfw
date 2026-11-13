# manifest_hash: 4b3c6d65f2aeffd4fcfd8ecf166c4983ef94b046d3c9b7fd5e391811d32a5d82
"""
ctxfw.mcp_guard — MCP Tool Poisoning Firewall & Capability Laundering Guard
===========================================================================
Lazy package interface exposing SHA-256 tool pinning, rug-pull detection,
parameter binding guards, OS component confinement, and SQLite WAL persistence.
"""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Dict, Tuple

MANIFEST_HASH: str = "4b3c6d65f2aeffd4fcfd8ecf166c4983ef94b046d3c9b7fd5e391811d32a5d82"
PACKAGE_DIR: Path = Path(__file__).resolve().parent
SCHEMA_PATH: Path = PACKAGE_DIR / "schema.sql"


def load_schema_sql() -> str:
    """Return the canonical UTF-8 SQLite WAL DDL for ctxfw.mcp_guard."""
    return SCHEMA_PATH.read_text(encoding="utf-8")


_LAZY_SUBMODULES = ("contracts", "store")
_LAZY_SYMBOLS: Dict[str, Tuple[str, str]] = {
    "ChannelSurface": ("ctxfw.mcp_guard.contracts", "ChannelSurface"),
    "ConfinementCheckResult": ("ctxfw.mcp_guard.contracts", "ConfinementCheckResult"),
    "DEFAULT_MAX_DECODE_ROUNDS": ("ctxfw.mcp_guard.contracts", "DEFAULT_MAX_DECODE_ROUNDS"),
    "DetectionLayer": ("ctxfw.mcp_guard.contracts", "DetectionLayer"),
    "ErrorClass": ("ctxfw.mcp_guard.contracts", "ErrorClass"),
    "FirewallDecisionDTO": ("ctxfw.mcp_guard.contracts", "FirewallDecisionDTO"),
    "FirewallEvent": ("ctxfw.mcp_guard.contracts", "FirewallEvent"),
    "FirewallState": ("ctxfw.mcp_guard.contracts", "FirewallState"),
    "InferredSandboxBoundary": ("ctxfw.mcp_guard.contracts", "InferredSandboxBoundary"),
    "MAX_AUTHORIZED_ROOTS": ("ctxfw.mcp_guard.contracts", "MAX_AUTHORIZED_ROOTS"),
    "MAX_DECODE_ROUNDS": ("ctxfw.mcp_guard.contracts", "MAX_DECODE_ROUNDS"),
    "MAX_DESCRIPTION_CHARS": ("ctxfw.mcp_guard.contracts", "MAX_DESCRIPTION_CHARS"),
    "McpGuardStore": ("ctxfw.mcp_guard.store", "McpGuardStore"),
    "McpToolContractSpec": ("ctxfw.mcp_guard.contracts", "McpToolContractSpec"),
    "OracleVerdict": ("ctxfw.mcp_guard.contracts", "OracleVerdict"),
    "ParameterBindingGuard": ("ctxfw.mcp_guard.contracts", "ParameterBindingGuard"),
    "PoisonScanFinding": ("ctxfw.mcp_guard.contracts", "PoisonScanFinding"),
    "QUARANTINE_RISK_THRESHOLD": ("ctxfw.mcp_guard.contracts", "QUARANTINE_RISK_THRESHOLD"),
    "SarifBypassFinding": ("ctxfw.mcp_guard.contracts", "SarifBypassFinding"),
    "SarifRuleId": ("ctxfw.mcp_guard.contracts", "SarifRuleId"),
    "TERMINAL_FAILURE_STATES": ("ctxfw.mcp_guard.contracts", "TERMINAL_FAILURE_STATES"),
    "ToolRegistrationPin": ("ctxfw.mcp_guard.contracts", "ToolRegistrationPin"),
    "ValidationVerdict": ("ctxfw.mcp_guard.contracts", "ValidationVerdict"),
    "canonicalize_mcp_path": ("ctxfw.mcp_guard.contracts", "canonicalize_mcp_path"),
    "compute_tool_pin_hash": ("ctxfw.mcp_guard.contracts", "compute_tool_pin_hash"),
    "has_invisible_or_bidi_unicode": ("ctxfw.mcp_guard.contracts", "has_invisible_or_bidi_unicode"),
    "is_component_confined": ("ctxfw.mcp_guard.contracts", "is_component_confined"),
    "scan_description_risk": ("ctxfw.mcp_guard.contracts", "scan_description_risk"),
    "scan_mcp_config_perimeter": ("ctxfw.mcp_guard.contracts", "scan_mcp_config_perimeter"),
    "transition_firewall_state": ("ctxfw.mcp_guard.contracts", "transition_firewall_state"),
}


def __getattr__(name: str) -> Any:
    if name in _LAZY_SUBMODULES:
        return importlib.import_module(f"ctxfw.mcp_guard.{name}")
    target = _LAZY_SYMBOLS.get(name)
    if target is not None:
        mod_path, attr = target
        return getattr(importlib.import_module(mod_path), attr)
    raise AttributeError(f"module 'ctxfw.mcp_guard' has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(
        list(_LAZY_SUBMODULES)
        + list(_LAZY_SYMBOLS.keys())
        + ["MANIFEST_HASH", "PACKAGE_DIR", "SCHEMA_PATH", "load_schema_sql"]
    )
