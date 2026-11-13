# manifest_hash: 862e0dc20133fe81f2ce12812b86d74068db80cce8566a3b71d2d406db72c549
"""ctxfw.rules -- Claude Rules Compiler vendored blueprint and sovereign engine (milestone 4.0-M2).

CTXFW Axiomatic Gateway (milestone M2): status VERIFIED | ACI 1.0000
manifest_hash: 862e0dc20133fe81f2ce12812b86d74068db80cce8566a3b71d2d406db72c549
manifest_hash_wave1a: 4b3c6d65f2aeffd4fcfd8ecf166c4983ef94b046d3c9b7fd5e391811d32a5d82
Sealed blueprint manifest_hash (Claude Rules Compiler SIG-1d0a63f087edb904, VERIFIED, ACI 1.0000):
    b5b8e1cd10ce8beeed6b076f4726d19b361a6ce2f5d480c2bb2aa437986822d3

Vendored, byte-for-byte, from the sealed blueprint (never edited here):
    contracts.py             <- specs/2_pydantic_contracts.py
    schema.sql               <- specs/3_schema_ddl.sql
    blueprint_manifest.json  <- blueprint_manifest.json
``.gitattributes`` pins them as ``-text`` and ``tests/test_rules_vendor.py`` re-checks their SHA-256
against the sealed manifest (gate G9). Any contract change requires a new sealed blueprint.

Implemented engines:
    extractor.py <- extract_normative_clauses
    compiler.py  <- RulesCompiler
    enforcer.py  <- RulesEnforcer, normalize_path, audit_source
    store.py     <- RulesStore

Exported contracts, engines and types:
    NaturalLanguageRuleDTO (aliased as DirectiveRule)
    RuleIntent (aliased as RuleClassifier)
    EnforcementVerdict
    RulesCompiler
    RulesEnforcer
    RulesStore
    extract_normative_clauses
    normalize_path
    audit_source
    RuleSourceFileDTO, CompiledAstGuardDTO, RuleComplianceAuditDTO, CompiledRuleManifestDTO
    FileFormat, PatternType, FailureClass, CompilerState, CompilerEvent, transition, etc.

This package imports nothing heavy at import time (lazy): pydantic models and engines
load only upon attribute access or direct submodule import.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

__all__ = [
    "CONTRACTS_PATH",
    "MANIFEST_PATH",
    "PACKAGE_DIR",
    "SCHEMA_PATH",
    "load_manifest",
    "load_schema_sql",
    # Engines:
    "RulesCompiler",
    "RulesEnforcer",
    "RulesStore",
    "extract_normative_clauses",
    "is_path_confined",
    "normalize_path",
    "audit_source",
    # Architecture directive aliases:
    "DirectiveRule",
    "RuleClassifier",
    "EnforcementVerdict",
    # Canonical vendored contracts and types:
    "RulesBaseDTO",
    "RuleSourceFileDTO",
    "NaturalLanguageRuleDTO",
    "CompiledAstGuardDTO",
    "RuleComplianceAuditDTO",
    "CompiledRuleManifestDTO",
    "FileFormat",
    "RuleIntent",
    "PatternType",
    "FailureClass",
    "CompilerState",
    "CompilerEvent",
    "TERMINAL_STATES",
    "COMPILER_TRANSITIONS",
    "FAILURE_ROUTING",
    "INTENT_TO_PATTERN",
    "PATTERN_TO_INTENT",
    "transition",
    "sha256_hex",
    "detect_file_format",
    "derive_rule_id",
    "derive_guard_id",
    "derive_manifest_id",
    "audit_digest",
]

PACKAGE_DIR = Path(__file__).resolve().parent
CONTRACTS_PATH = PACKAGE_DIR / "contracts.py"
SCHEMA_PATH = PACKAGE_DIR / "schema.sql"
MANIFEST_PATH = PACKAGE_DIR / "blueprint_manifest.json"

_ALIASES: dict[str, str] = {
    "DirectiveRule": "NaturalLanguageRuleDTO",
    "RuleClassifier": "RuleIntent",
}


def load_schema_sql() -> str:
    """Return the sealed DDL text exactly as vendored (UTF-8)."""
    return SCHEMA_PATH.read_text(encoding="utf-8")


def load_manifest() -> dict[str, Any]:
    """Return the sealed blueprint manifest as a dictionary."""
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def __getattr__(name: str) -> Any:
    if name == "RulesCompiler":
        from . import compiler

        return getattr(compiler, name)
    if name in {"RulesEnforcer", "is_path_confined", "normalize_path", "audit_source"}:
        from . import enforcer

        return getattr(enforcer, name)
    if name == "RulesStore":
        from . import store

        return getattr(store, name)
    if name == "extract_normative_clauses":
        from . import extractor

        return getattr(extractor, name)
    if name in _ALIASES:
        from . import contracts

        return getattr(contracts, _ALIASES[name])
    if name in __all__:
        from . import contracts

        return getattr(contracts, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals().keys()) | set(__all__))


if TYPE_CHECKING:
    from .compiler import RulesCompiler
    from .contracts import (
        COMPILER_TRANSITIONS,
        FAILURE_ROUTING,
        INTENT_TO_PATTERN,
        PATTERN_TO_INTENT,
        TERMINAL_STATES,
        CompiledAstGuardDTO,
        CompiledRuleManifestDTO,
        CompilerEvent,
        CompilerState,
        EnforcementVerdict,
        FailureClass,
        FileFormat,
        NaturalLanguageRuleDTO,
        PatternType,
        RuleComplianceAuditDTO,
        RuleIntent,
        RulesBaseDTO,
        RuleSourceFileDTO,
        audit_digest,
        derive_guard_id,
        derive_manifest_id,
        derive_rule_id,
        detect_file_format,
        sha256_hex,
        transition,
    )
    from .enforcer import RulesEnforcer, audit_source, is_path_confined, normalize_path
    from .extractor import extract_normative_clauses
    from .store import RulesStore

    DirectiveRule = NaturalLanguageRuleDTO
    RuleClassifier = RuleIntent
