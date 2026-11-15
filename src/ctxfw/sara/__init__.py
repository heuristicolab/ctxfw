# manifest_hash: 8f925c1e7c680c7af68e6f3daa48a5ac734923438762ed8836878a97508ce42e
"""ctxfw.sara -- SARA Action Induction Runtime Authorization vendored blueprint and sovereign engines (milestone 4.0-M3).

CTXFW Axiomatic Gateway (milestone M3-P2): status VERIFIED | ACI 1.0000
manifest_hash: 8f925c1e7c680c7af68e6f3daa48a5ac734923438762ed8836878a97508ce42e
manifest_hash_wave1b: ebbcd0d607fa09a71dda690ea76104d762b3f279cde258f64917421d39a249f4
manifest_hash_wave2d1: ece9d70e52f09f3e80d8cadfd432c4b07a094ca40618ff12aa72a6f1cc92052a
manifest_hash_wave2e1: b77d4295c196c37e848903d930d8d1a358fc9178b4dca90ba40fd28db264f37a
manifest_hash_wave2e2: bc6e604a3faf8a75b3d6402b523047e481f35c0d62afca3056114337021196e0
Sealed blueprint manifest_hash (SARA SIG-0d2acf53b92882b0, VERIFIED, ACI 1.0000):
    51d819312f8dd802981a7b7d97b9d6397316738ded76c94161a9f147411c94ea
Sealed blueprint manifest_hash (#18 PASAC SIG-97ba08207eca7295, VERIFIED, ACI 1.0000):
    da52eae13ef720cd4f56f1f3a3c295b7800aeb9585d8b92e346529e90bf4dc95

Vendored, byte-for-byte, from the sealed blueprint (never edited here):
    contracts.py             <- specs/2_pydantic_contracts.py
    schema.sql               <- specs/3_schema_ddl.sql
    blueprint_manifest.json  <- blueprint_manifest.json
``.gitattributes`` pins them as ``-text`` and ``tests/test_sara_vendor.py`` re-checks their SHA-256
against the sealed manifest (gate G9). Any contract change requires a new sealed blueprint.

Implemented engines (M3-P2):
    lexical.py    <- LexicalSanitizer, SanitizationResult
    induction.py  <- InductionParser
    gate.py       <- RuntimeAuthorizationGate
    audit.py      <- AuditSink, derive_quarantine_id
    store.py      <- SaraStore

Exported contracts, engines and types:
    LexicalSanitizer, SanitizationResult
    InductionParser
    RuntimeAuthorizationGate
    AuditSink, SaraStore, derive_quarantine_id
    UntrustedObservationDTO (aliased to RawToolObservationDTO)
    AuthorizedPolicyDTO (aliased to AuthorizationPolicyRuleDTO)
    ToolExecutionSourceDTO
    RawToolObservationDTO
    InductionDirectiveDTO
    AuthorizationPolicyRuleDTO
    AuthorizationVerdictDTO
    SourceType, VerdictKind, DirectiveKind, FailureClass, SaraState, SaraEvent
    TERMINAL_STATES, SARA_TRANSITIONS, FAILURE_ROUTING
    SaraBaseDTO, transition, verdict_for_risk, observation_digest
    load_schema_sql, load_manifest

This package imports nothing heavy at import time (lazy): pydantic models, engines and helper functions
load only upon attribute access or direct submodule import.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

__all__ = [
    "ASSURANCE_SCHEMA_PATH",
    "PROVENANCE_SCHEMA_PATH",
    "TASK_AUTH_SCHEMA_PATH",
    "CONTRACTS_PATH",
    "MANIFEST_PATH",
    "PACKAGE_DIR",
    "SCHEMA_PATH",
    "load_assurance_schema_sql",
    "load_provenance_schema_sql",
    "load_task_auth_schema_sql",
    "load_manifest",
    "load_schema_sql",
    # Sovereign engines:
    "LexicalSanitizer",
    "ReferenceLexicalSanitizer",
    "SanitizationResult",
    "InductionParser",
    "RuntimeAuthorizationGate",
    "AuditSink",
    "SaraStore",
    "PasacAssuranceStore",
    "ProvenanceStore",
    "TaskAuthStore",
    # Wave 2 E.1 provenance & epoch exports:
    "PROVENANCE_MANIFEST_HASH",
    "PROVENANCE_TRANSITIONS",
    "TERMINAL_PROVENANCE_STATES",
    "AlignmentStatus",
    "IntentExecGraphEdge",
    "MonotonicEpochVerdict",
    "PredicateState",
    "ProvenanceClassification",
    "ProvenanceErrorClass",
    "ProvenanceEvent",
    "ProvenanceState",
    "ProvenanceTraceResult",
    "compute_epoch_attestation",
    "compute_provenance_attestation",
    "digest_payload_sha256",
    "evaluate_frame_alignment",
    "evaluate_monotonic_epoch",
    "evaluate_relation_alignment",
    "provenance_transition",
    "prune_graph_edges",
    "trace_ipi_provenance",
    # Wave 2 E.2 lexical multilingual & slot symmetry exports:
    "IntraTokenConfusableFinding",
    "SlotSymmetryResult",
    "detect_intra_token_confusables",
    "fold_confusables",
    "validate_language_tag",
    "verify_symmetric_slot_preservation",
    "derive_quarantine_id",
    # Task-Scoped Paired-Replay Auth, Sandbox PoLP & Spoof Delimiters (Wave 2 D.1 :: #07 + #08 + #10):
    "AUTH_REPLAY_TRANSITIONS",
    "FORBIDDEN_CDP_PORT",
    "MAX_MULTIPLICITY_CEILING",
    "MIN_CONTAINER_UID",
    "SPOOF_DELIMITER_RE",
    "SPOOF_MARKER_SIGNATURES",
    "TASK_AUTH_MANIFEST_HASH",
    "TERMINAL_AUTH_STATES",
    "ArtifactoryMirrorConfig",
    "AttackGoal",
    "AuthReplayEvent",
    "AuthReplayState",
    "DpopProofContext",
    "HttpMethodVerb",
    "OpaRegoVerdictEnvelope",
    "PairedReplayAuthorizationReceipt",
    "PolicyCondition",
    "RefreshTokenExchangeRequest",
    "ReplayErrorClass",
    "SandboxPolpPosture",
    "StructuredToolCallEnvelope",
    "TaskAuthorityPolicySpec",
    "ToolDomain",
    "canonical_dpop_message_bytes",
    "compute_decision_seal",
    "compute_dpop_hmac_signature",
    "compute_harmful_execution",
    "compute_model_compromise",
    "compute_paired_contrast_delta",
    "compute_scope_intersection",
    "compute_state_chain_digest",
    "detect_spoof_delimiters",
    "evaluate_local_rego_policy",
    "evaluate_scoped_tool_call",
    "is_polp_mirror_compliant",
    "task_auth_transition",
    "validate_tool_domain",
    "verify_dpop_proof",
    "verify_jwt_before_parse",
    "verify_opa_fail_closed",
    # Proactive Agent Assurance & PASAC Gate (Wave 1B :: #18):
    "AssuranceScopeContract",
    "BoundaryAssuranceVector",
    "AgentRiskStateVector",
    "PolicyEnforcementDecision",
    "ContainmentQuarantineAlert",
    "RuntimePreflightPosture",
    "PasacLifecycleState",
    "PasacLifecycleEvent",
    "AccountabilityRole",
    "EgressPolicyMode",
    "PreflightStatus",
    "HazardRegime",
    "FailureErrorClass",
    "pasac_transition",
    "compute_boundary_assurances",
    "compute_parametric_risk_r_star",
    "classify_hazard_regime",
    "evaluate_pep_gate",
    "assess_runtime_isolation_posture",
    "format_pep_action_code",
    # Architecture directive aliases:
    "UntrustedObservationDTO",
    "AuthorizedPolicyDTO",
    # Canonical vendored contracts and types:
    "ToolExecutionSourceDTO",
    "RawToolObservationDTO",
    "InductionDirectiveDTO",
    "AuthorizationPolicyRuleDTO",
    "AuthorizationVerdictDTO",
    "SourceType",
    "VerdictKind",
    "DirectiveKind",
    "FailureClass",
    "SaraState",
    "SaraEvent",
    "SaraBaseDTO",
    "TERMINAL_STATES",
    "SARA_TRANSITIONS",
    "FAILURE_ROUTING",
    "transition",
    "verdict_for_risk",
    "observation_digest",
    # Constants:
    "MAX_RAW_OUTPUT_CHARS",
    "MAX_DIRECTIVES_PER_OBSERVATION",
    "MAX_DIRECTIVES_PER_OBS",
    "MAX_DIRECTIVE_TEXT_CHARS",
    "MAX_POLICY_ITEMS",
    "MAX_POLICY_ITEM_CHARS",
    "MAX_POLICY_MASK",
    "RISK_QUARANTINE_THRESHOLD",
    "RISK_STRIP_THRESHOLD",
    "GATE_LATENCY_BUDGET_MS",
    "TOOL_NAME_PATTERN",
    "EXECUTION_ID_PATTERN",
    "POLICY_ID_PATTERN",
    "SHA256_PATTERN",
]

PACKAGE_DIR = Path(__file__).resolve().parent
CONTRACTS_PATH = PACKAGE_DIR / "contracts.py"
SCHEMA_PATH = PACKAGE_DIR / "schema.sql"
ASSURANCE_SCHEMA_PATH = PACKAGE_DIR / "assurance_schema.sql"
PROVENANCE_SCHEMA_PATH = PACKAGE_DIR / "provenance_schema.sql"
TASK_AUTH_SCHEMA_PATH = PACKAGE_DIR / "task_auth_schema.sql"
MANIFEST_PATH = PACKAGE_DIR / "blueprint_manifest.json"

_PROVENANCE_EXPORTS = frozenset(
    {
        "PROVENANCE_MANIFEST_HASH",
        "PROVENANCE_TRANSITIONS",
        "TERMINAL_PROVENANCE_STATES",
        "AlignmentStatus",
        "IntentExecGraphEdge",
        "MonotonicEpochVerdict",
        "PredicateState",
        "ProvenanceClassification",
        "ProvenanceErrorClass",
        "ProvenanceEvent",
        "ProvenanceState",
        "ProvenanceTraceResult",
        "compute_epoch_attestation",
        "compute_provenance_attestation",
        "digest_payload_sha256",
        "evaluate_frame_alignment",
        "evaluate_monotonic_epoch",
        "evaluate_relation_alignment",
        "provenance_transition",
        "prune_graph_edges",
        "trace_ipi_provenance",
    }
)

_LEXICAL_E2_EXPORTS = frozenset(
    {
        "IntraTokenConfusableFinding",
        "SlotSymmetryResult",
        "detect_intra_token_confusables",
        "fold_confusables",
        "validate_language_tag",
        "verify_symmetric_slot_preservation",
    }
)

_SUBMODULES = frozenset(
    {
        "contracts",
        "lexical",
        "induction",
        "gate",
        "audit",
        "store",
        "assurance",
        "assurance_store",
        "provenance",
        "provenance_store",
        "task_auth",
        "task_auth_store",
    }
)

_TASK_AUTH_EXPORTS = frozenset(
    {
        "AUTH_REPLAY_TRANSITIONS",
        "FORBIDDEN_CDP_PORT",
        "MAX_MULTIPLICITY_CEILING",
        "MIN_CONTAINER_UID",
        "SPOOF_DELIMITER_RE",
        "SPOOF_MARKER_SIGNATURES",
        "TASK_AUTH_MANIFEST_HASH",
        "ArtifactoryMirrorConfig",
        "AttackGoal",
        "AuthReplayEvent",
        "AuthReplayState",
        "DpopProofContext",
        "HttpMethodVerb",
        "OpaRegoVerdictEnvelope",
        "PairedReplayAuthorizationReceipt",
        "PolicyCondition",
        "RefreshTokenExchangeRequest",
        "ReplayErrorClass",
        "SandboxPolpPosture",
        "StructuredToolCallEnvelope",
        "TaskAuthorityPolicySpec",
        "ToolDomain",
        "canonical_dpop_message_bytes",
        "compute_decision_seal",
        "compute_dpop_hmac_signature",
        "compute_harmful_execution",
        "compute_model_compromise",
        "compute_paired_contrast_delta",
        "compute_scope_intersection",
        "compute_state_chain_digest",
        "detect_spoof_delimiters",
        "evaluate_local_rego_policy",
        "evaluate_scoped_tool_call",
        "is_polp_mirror_compliant",
        "task_auth_transition",
        "validate_tool_domain",
        "verify_dpop_proof",
        "verify_jwt_before_parse",
        "verify_opa_fail_closed",
    }
)

_ASSURANCE_EXPORTS = frozenset(
    {
        "AccountabilityRole",
        "AgentRiskStateVector",
        "AssuranceScopeContract",
        "BoundaryAssuranceVector",
        "ContainmentQuarantineAlert",
        "EgressPolicyMode",
        "FailureErrorClass",
        "HazardRegime",
        "PasacLifecycleEvent",
        "PasacLifecycleState",
        "PolicyEnforcementDecision",
        "PreflightStatus",
        "RuntimePreflightPosture",
        "assess_runtime_isolation_posture",
        "classify_hazard_regime",
        "compute_boundary_assurances",
        "compute_parametric_risk_r_star",
        "evaluate_pep_gate",
        "format_pep_action_code",
    }
)

_ALIASES: dict[str, str] = {
    "UntrustedObservationDTO": "RawToolObservationDTO",
    "AuthorizedPolicyDTO": "AuthorizationPolicyRuleDTO",
    "MAX_DIRECTIVES_PER_OBS": "MAX_DIRECTIVES_PER_OBSERVATION",
}


def load_schema_sql() -> str:
    """Return the sealed DDL text exactly as vendored (UTF-8)."""
    return SCHEMA_PATH.read_text(encoding="utf-8")


def load_assurance_schema_sql() -> str:
    """Return the PASAC assurance SQLite WAL DDL text (UTF-8)."""
    return ASSURANCE_SCHEMA_PATH.read_text(encoding="utf-8")


def load_provenance_schema_sql() -> str:
    """Return the Wave 2 E.1 causal provenance & monotonic epoch SQLite WAL DDL text (UTF-8)."""
    return PROVENANCE_SCHEMA_PATH.read_text(encoding="utf-8")


def load_task_auth_schema_sql() -> str:
    """Return the Wave 2 D.1 task-auth SQLite WAL DDL text (UTF-8)."""
    return TASK_AUTH_SCHEMA_PATH.read_text(encoding="utf-8")


def load_manifest() -> dict[str, Any]:
    """Return the sealed blueprint manifest as a dictionary."""
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def __getattr__(name: str) -> Any:
    if name in _SUBMODULES:
        import importlib

        mod = importlib.import_module(f"{__name__}.{name}")
        globals()[name] = mod
        return mod
    if name in {"LexicalSanitizer", "ReferenceLexicalSanitizer", "SanitizationResult"}:
        from . import lexical

        return getattr(lexical, name)
    if name == "InductionParser":
        from . import induction

        return getattr(induction, name)
    if name == "RuntimeAuthorizationGate":
        from . import gate

        return getattr(gate, name)
    if name in {"AuditSink", "derive_quarantine_id"}:
        from . import audit

        return getattr(audit, name)
    if name == "SaraStore":
        from . import store

        return getattr(store, name)
    if name == "PasacAssuranceStore":
        from . import assurance_store

        return getattr(assurance_store, name)
    if name == "TaskAuthStore":
        from . import task_auth_store

        return getattr(task_auth_store, name)
    if name in _TASK_AUTH_EXPORTS:
        from . import task_auth

        return getattr(task_auth, name)
    if name == "ProvenanceStore":
        from . import provenance_store

        return getattr(provenance_store, name)
    if name in _PROVENANCE_EXPORTS:
        from . import provenance

        return getattr(provenance, name)
    if name in _LEXICAL_E2_EXPORTS:
        from . import lexical

        return getattr(lexical, name)
    if name == "pasac_transition":
        from . import assurance

        return getattr(assurance, "transition")
    if name in _ASSURANCE_EXPORTS:
        from . import assurance

        return getattr(assurance, name)
    if name == "TERMINAL_STATES":
        from . import contracts

        return getattr(contracts, name)
    if name == "TERMINAL_AUTH_STATES":
        from . import task_auth

        return getattr(task_auth, name)
    if name in _ALIASES:
        from . import contracts

        return getattr(contracts, _ALIASES[name])
    if name in __all__:
        from . import contracts

        return getattr(contracts, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals().keys()) | set(__all__) | set(_SUBMODULES))


if TYPE_CHECKING:
    from .assurance import (
        AccountabilityRole,
        AgentRiskStateVector,
        AssuranceScopeContract,
        BoundaryAssuranceVector,
        ContainmentQuarantineAlert,
        EgressPolicyMode,
        FailureErrorClass,
        HazardRegime,
        PasacLifecycleEvent,
        PasacLifecycleState,
        PolicyEnforcementDecision,
        PreflightStatus,
        RuntimePreflightPosture,
        assess_runtime_isolation_posture,
        classify_hazard_regime,
        compute_boundary_assurances,
        compute_parametric_risk_r_star,
        evaluate_pep_gate,
        format_pep_action_code,
        transition as pasac_transition,
    )
    from .assurance_store import PasacAssuranceStore
    from .audit import AuditSink, derive_quarantine_id
    from .contracts import (
        EXECUTION_ID_PATTERN,
        FAILURE_ROUTING,
        GATE_LATENCY_BUDGET_MS,
        MAX_DIRECTIVE_TEXT_CHARS,
        MAX_DIRECTIVES_PER_OBSERVATION,
        MAX_POLICY_ITEM_CHARS,
        MAX_POLICY_ITEMS,
        MAX_POLICY_MASK,
        MAX_RAW_OUTPUT_CHARS,
        POLICY_ID_PATTERN,
        RISK_QUARANTINE_THRESHOLD,
        RISK_STRIP_THRESHOLD,
        SARA_TRANSITIONS,
        SHA256_PATTERN,
        TERMINAL_STATES,
        TOOL_NAME_PATTERN,
        AuthorizationPolicyRuleDTO,
        AuthorizationVerdictDTO,
        DirectiveKind,
        FailureClass,
        InductionDirectiveDTO,
        RawToolObservationDTO,
        SaraBaseDTO,
        SaraEvent,
        SaraState,
        SourceType,
        ToolExecutionSourceDTO,
        VerdictKind,
        observation_digest,
        transition,
        verdict_for_risk,
    )
    from .gate import RuntimeAuthorizationGate
    from .induction import MAX_DIRECTIVES_PER_OBS, InductionParser
    from .lexical import LexicalSanitizer, SanitizationResult
    from .store import SaraStore
    from .task_auth import (
        AUTH_REPLAY_TRANSITIONS,
        FORBIDDEN_CDP_PORT,
        MAX_MULTIPLICITY_CEILING,
        MIN_CONTAINER_UID,
        SPOOF_DELIMITER_RE,
        SPOOF_MARKER_SIGNATURES,
        TASK_AUTH_MANIFEST_HASH,
        TERMINAL_AUTH_STATES,
        ArtifactoryMirrorConfig,
        AttackGoal,
        AuthReplayEvent,
        AuthReplayState,
        DpopProofContext,
        HttpMethodVerb,
        OpaRegoVerdictEnvelope,
        PairedReplayAuthorizationReceipt,
        PolicyCondition,
        RefreshTokenExchangeRequest,
        ReplayErrorClass,
        SandboxPolpPosture,
        StructuredToolCallEnvelope,
        TaskAuthorityPolicySpec,
        ToolDomain,
        canonical_dpop_message_bytes,
        compute_decision_seal,
        compute_dpop_hmac_signature,
        compute_harmful_execution,
        compute_model_compromise,
        compute_paired_contrast_delta,
        compute_scope_intersection,
        compute_state_chain_digest,
        detect_spoof_delimiters,
        evaluate_local_rego_policy,
        evaluate_scoped_tool_call,
        is_polp_mirror_compliant,
        task_auth_transition,
        validate_tool_domain,
        verify_dpop_proof,
        verify_jwt_before_parse,
        verify_opa_fail_closed,
    )
    from .task_auth_store import TaskAuthStore

    UntrustedObservationDTO = RawToolObservationDTO
    AuthorizedPolicyDTO = AuthorizationPolicyRuleDTO
