# manifest_hash: ebbcd0d607fa09a71dda690ea76104d762b3f279cde258f64917421d39a249f4
"""Proactive Agent Assurance & PASAC Boundary Gate (Wave 1B :: #18).

CTXFW Axiomatic Gateway (Wave 1B): status VERIFIED | ACI 1.0000
manifest_hash: ebbcd0d607fa09a71dda690ea76104d762b3f279cde258f64917421d39a249f4
Sealed blueprint manifest_hash (BP-SIG-97BA08207ECA7295, VERIFIED, ACI 1.0000):
    da52eae13ef720cd4f56f1f3a3c295b7800aeb9585d8b92e346529e90bf4dc95

Implements the deterministic 8-state PASAC lifecycle FSM, 6-layer non-masking
Boundary Assurance Stack (A_min_t = min(b_t)), parametric risk index R*_t,
leading-indicator hazard bands (NOMINAL_ALLOW, REVIEW_PAUSE, SYNCHRONOUS_STOP),
and the four-predicate conjunctive Policy Enforcement Point Allow(a) gate.
Zero LLM dependencies, zero network egress, zero wall-clock nondeterminism.
"""
from __future__ import annotations

import hashlib
import math
import re
from enum import Enum
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple
import urllib.parse

from pydantic import BaseModel, ConfigDict, Field, model_validator

try:
    from enum import StrEnum
except ImportError:  # Python 3.10 compatibility

    class StrEnum(str, Enum):
        pass


__all__ = [
    "AccountabilityRole",
    "AgentRiskStateVector",
    "AssuranceScopeContract",
    "BoundaryAssuranceVector",
    "CTXFW_MANIFEST_HASH",
    "ContainmentQuarantineAlert",
    "EgressPolicyMode",
    "FailureErrorClass",
    "HazardRegime",
    "MIN_LAYER_FLOOR_DEFAULT",
    "PASAC_FAILURE_DISPOSITION",
    "PASAC_FAILURE_ROUTING",
    "PasacLifecycleEvent",
    "PasacLifecycleState",
    "PolicyEnforcementDecision",
    "PreflightStatus",
    "RuntimePreflightPosture",
    "SEALED_BLUEPRINT_MANIFEST_HASH",
    "STRICT_MODEL_CONFIG",
    "TAU_REVIEW_DEFAULT",
    "TAU_STOP_DEFAULT",
    "TERMINAL_STATES",
    "TRANSITION_TABLE",
    "assess_runtime_isolation_posture",
    "classify_hazard_regime",
    "classify_pasac_failure",
    "compute_boundary_assurances",
    "compute_parametric_risk_r_star",
    "derive_contract_digest",
    "evaluate_pep_gate",
    "format_pasac_session_id",
    "format_pep_action_code",
    "transition",
    "transition_pasac",
]

CTXFW_MANIFEST_HASH: str = "ebbcd0d607fa09a71dda690ea76104d762b3f279cde258f64917421d39a249f4"
SEALED_BLUEPRINT_MANIFEST_HASH: str = (
    "da52eae13ef720cd4f56f1f3a3c295b7800aeb9585d8b92e346529e90bf4dc95"
)

MIN_LAYER_FLOOR_DEFAULT: float = 0.70
TAU_REVIEW_DEFAULT: float = 0.40
TAU_STOP_DEFAULT: float = 0.75

_SESSION_ID_RE = re.compile(r"^PASAC-[A-Z0-9_-]{4,48}$")
_PEP_CODE_BODY_RE = re.compile(r"^[A-Z0-9_-]{4,36}$")
_REMOTE_URL_RE = re.compile(r"^(https?|wss?|ftp)://", re.IGNORECASE)
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "[::1]"})

STRICT_MODEL_CONFIG = ConfigDict(
    frozen=True,
    extra="forbid",
    str_strip_whitespace=True,
    validate_default=True,
)


class PasacLifecycleState(StrEnum):
    ANTICIPATE_DRAFT = "ANTICIPATE_DRAFT"
    CONSTRAINED_CONTRACT = "CONSTRAINED_CONTRACT"
    PREFLIGHT_VERIFIED = "PREFLIGHT_VERIFIED"
    ACTIVE_OBSERVED = "ACTIVE_OBSERVED"
    ELEVATED_REVIEW = "ELEVATED_REVIEW"
    CONTAINMENT_HALTED = "CONTAINMENT_HALTED"
    REAUTHORIZED_COMPLETE = "REAUTHORIZED_COMPLETE"
    QUARANTINED_BREACH = "QUARANTINED_BREACH"


class PasacLifecycleEvent(StrEnum):
    E_LOCK_SCOPE_CONTRACT = "E_LOCK_SCOPE_CONTRACT"
    E_PASS_PREFLIGHT = "E_PASS_PREFLIGHT"
    E_FAIL_PREFLIGHT = "E_FAIL_PREFLIGHT"
    E_START_SESSION = "E_START_SESSION"
    E_HAZARD_REVIEW = "E_HAZARD_REVIEW"
    E_HAZARD_STOP = "E_HAZARD_STOP"
    E_PEP_DENY = "E_PEP_DENY"
    E_COMPLETE_SAFE = "E_COMPLETE_SAFE"
    E_RESUME_APPROVED = "E_RESUME_APPROVED"
    E_REAUTHORIZE_PASS = "E_REAUTHORIZE_PASS"
    E_CONFIRM_BREACH = "E_CONFIRM_BREACH"


class AccountabilityRole(StrEnum):
    PROGRAM_OWNER = "PROGRAM_OWNER"
    ENVIRONMENT_OWNER = "ENVIRONMENT_OWNER"
    SECURITY_LEAD = "SECURITY_LEAD"
    INCIDENT_LEAD = "INCIDENT_LEAD"


class EgressPolicyMode(StrEnum):
    OFFLINE_ISOLATED = "OFFLINE_ISOLATED"
    ALLOWLISTED_PROXY = "ALLOWLISTED_PROXY"
    REPLAY_HERMETIC = "REPLAY_HERMETIC"


class PreflightStatus(StrEnum):
    VALID = "VALID"
    FAILED = "FAILED"
    PENDING = "PENDING"


class HazardRegime(StrEnum):
    NOMINAL_ALLOW = "NOMINAL_ALLOW"
    REVIEW_PAUSE = "REVIEW_PAUSE"
    SYNCHRONOUS_STOP = "SYNCHRONOUS_STOP"


class FailureErrorClass(StrEnum):
    TRANSIENT = "TRANSIENT"
    DETERMINISTIC = "DETERMINISTIC"
    BUSINESS = "BUSINESS"
    SECURITY = "SECURITY"


TERMINAL_STATES: Tuple[PasacLifecycleState, ...] = (
    PasacLifecycleState.REAUTHORIZED_COMPLETE,
    PasacLifecycleState.QUARANTINED_BREACH,
)

TRANSITION_TABLE: Mapping[
    Tuple[PasacLifecycleState, PasacLifecycleEvent], PasacLifecycleState
] = MappingProxyType(
    {
        (
            PasacLifecycleState.ANTICIPATE_DRAFT,
            PasacLifecycleEvent.E_LOCK_SCOPE_CONTRACT,
        ): PasacLifecycleState.CONSTRAINED_CONTRACT,
        (
            PasacLifecycleState.CONSTRAINED_CONTRACT,
            PasacLifecycleEvent.E_PASS_PREFLIGHT,
        ): PasacLifecycleState.PREFLIGHT_VERIFIED,
        (
            PasacLifecycleState.CONSTRAINED_CONTRACT,
            PasacLifecycleEvent.E_FAIL_PREFLIGHT,
        ): PasacLifecycleState.QUARANTINED_BREACH,
        (
            PasacLifecycleState.PREFLIGHT_VERIFIED,
            PasacLifecycleEvent.E_START_SESSION,
        ): PasacLifecycleState.ACTIVE_OBSERVED,
        (
            PasacLifecycleState.ACTIVE_OBSERVED,
            PasacLifecycleEvent.E_HAZARD_REVIEW,
        ): PasacLifecycleState.ELEVATED_REVIEW,
        (
            PasacLifecycleState.ACTIVE_OBSERVED,
            PasacLifecycleEvent.E_HAZARD_STOP,
        ): PasacLifecycleState.CONTAINMENT_HALTED,
        (
            PasacLifecycleState.ACTIVE_OBSERVED,
            PasacLifecycleEvent.E_PEP_DENY,
        ): PasacLifecycleState.CONTAINMENT_HALTED,
        (
            PasacLifecycleState.ACTIVE_OBSERVED,
            PasacLifecycleEvent.E_COMPLETE_SAFE,
        ): PasacLifecycleState.REAUTHORIZED_COMPLETE,
        (
            PasacLifecycleState.ELEVATED_REVIEW,
            PasacLifecycleEvent.E_RESUME_APPROVED,
        ): PasacLifecycleState.ACTIVE_OBSERVED,
        (
            PasacLifecycleState.ELEVATED_REVIEW,
            PasacLifecycleEvent.E_HAZARD_STOP,
        ): PasacLifecycleState.CONTAINMENT_HALTED,
        (
            PasacLifecycleState.CONTAINMENT_HALTED,
            PasacLifecycleEvent.E_REAUTHORIZE_PASS,
        ): PasacLifecycleState.PREFLIGHT_VERIFIED,
        (
            PasacLifecycleState.CONTAINMENT_HALTED,
            PasacLifecycleEvent.E_CONFIRM_BREACH,
        ): PasacLifecycleState.QUARANTINED_BREACH,
    }
)

PASAC_FAILURE_ROUTING: Mapping[str, FailureErrorClass] = MappingProxyType(
    {
        "SQLITE_BUSY": FailureErrorClass.TRANSIENT,
        "WAL_RETRY_EXHAUSTED": FailureErrorClass.TRANSIENT,
        "VALIDATION_FAIL": FailureErrorClass.DETERMINISTIC,
        "NON_FINITE_FLOAT": FailureErrorClass.DETERMINISTIC,
        "THRESHOLD_INVERTED": FailureErrorClass.DETERMINISTIC,
        "ILLEGAL_FSM_TRANSITION": FailureErrorClass.DETERMINISTIC,
        "BAS_FLOOR_BELOW_THRESHOLD": FailureErrorClass.BUSINESS,
        "SCOPE_DENIED": FailureErrorClass.BUSINESS,
        "RESOURCE_NOT_WHITELISTED": FailureErrorClass.BUSINESS,
        "RISK_THRESHOLD_EXCEEDED": FailureErrorClass.BUSINESS,
        "CROSS_RUN_WRITABLE": FailureErrorClass.SECURITY,
        "OFFLINE_EGRESS_LEAK": FailureErrorClass.SECURITY,
        "HAZARD_SYNCHRONOUS_STOP": FailureErrorClass.SECURITY,
        "LEDGER_MUTATION_ATTEMPT": FailureErrorClass.SECURITY,
    }
)

PASAC_FAILURE_DISPOSITION: Mapping[FailureErrorClass, str] = MappingProxyType(
    {
        FailureErrorClass.TRANSIENT: "RETRY_BOUNDED_5_THEN_FAIL_CLOSED",
        FailureErrorClass.DETERMINISTIC: "REJECT_INPUT_DENY_ACTION",
        FailureErrorClass.BUSINESS: "DENY_IN_PEP_RECORD_DECISION",
        FailureErrorClass.SECURITY: "HALT_AND_QUARANTINE_REQUIRE_SIGNOFF",
    }
)


def classify_pasac_failure(code: object) -> FailureErrorClass:
    """Map an error code onto the 4-class PASAC failure taxonomy."""
    if not isinstance(code, str):
        return FailureErrorClass.DETERMINISTIC
    return PASAC_FAILURE_ROUTING.get(code, FailureErrorClass.DETERMINISTIC)


def transition(
    state: PasacLifecycleState, event: PasacLifecycleEvent
) -> PasacLifecycleState:
    """Execute deterministic total PASAC FSM transition delta(S, E)."""
    if not isinstance(state, PasacLifecycleState) or not isinstance(
        event, PasacLifecycleEvent
    ):
        raise ValueError("Invalid PASAC state or event type")
    if state in TERMINAL_STATES:
        raise ValueError(f"Terminal state {state.value} rejects event {event.value}")
    key = (state, event)
    if key not in TRANSITION_TABLE:
        raise ValueError(f"Illegal FSM transition: delta({state.value}, {event.value})")
    return TRANSITION_TABLE[key]


transition_pasac = transition


def _require_finite(value: float, name: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{name} must be finite numeric")
    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"{name} must never be NaN or Inf")


def derive_contract_digest(*parts: object) -> str:
    """Compute canonical SHA-256 hex digest over deterministic contract attributes."""
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def format_pasac_session_id(raw_session: str) -> str:
    """Deterministically normalize a session identifier into ^PASAC-[A-Z0-9_-]{4,48}$."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", str(raw_session or "").strip()).upper()
    if cleaned.startswith("PASAC-"):
        body = cleaned[6:]
    else:
        body = cleaned
    body = body.strip("-")
    if len(body) >= 4 and len(body) <= 48 and _SESSION_ID_RE.fullmatch(f"PASAC-{body}"):
        return f"PASAC-{body}"
    digest = hashlib.sha256(str(raw_session or "default").encode("utf-8")).hexdigest()[:12].upper()
    return f"PASAC-{digest}"


def format_pep_action_code(raw_action: str) -> str:
    """Deterministically normalize an action/tool name for PolicyEnforcementDecision (^PEP-[A-Z0-9_-]{4,40}$)."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", str(raw_action or "").strip()).upper().strip("_-")
    if _PEP_CODE_BODY_RE.fullmatch(cleaned):
        return cleaned
    digest = hashlib.sha256(str(raw_action or "act").encode("utf-8")).hexdigest()[:12].upper()
    prefix = cleaned[:20] if cleaned else "ACT"
    candidate = f"{prefix}_{digest}"[:36]
    if _PEP_CODE_BODY_RE.fullmatch(candidate):
        return candidate
    return f"ACT_{digest}"


class AssuranceScopeContract(BaseModel):
    """Executable scope contract binding egress policy, cross-run isolation & sign-off."""

    model_config = STRICT_MODEL_CONFIG

    session_id: str = Field(..., pattern=r"^PASAC-[A-Z0-9_-]{4,48}$")
    proposal_id: str = Field(
        default="PROP-97ba08207eca7295-H2",
        pattern=r"^PROP-[a-f0-9]{16}-H[123]$",
    )
    egress_mode: EgressPolicyMode
    live_egress_detected: bool = Field(default=False)
    cross_run_writable: bool = Field(default=False)
    signoff_role: AccountabilityRole = Field(default=AccountabilityRole.ENVIRONMENT_OWNER)
    preflight_status: PreflightStatus = Field(default=PreflightStatus.VALID)
    contract_digest: str = Field(..., pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def verify_isolation_invariants(self) -> "AssuranceScopeContract":
        if self.cross_run_writable:
            raise ValueError("Cross-run writable channels are strictly prohibited (INV-B3)")
        if (
            self.egress_mode == EgressPolicyMode.OFFLINE_ISOLATED
            and self.live_egress_detected
            and self.preflight_status == PreflightStatus.VALID
        ):
            raise ValueError(
                "Offline isolated session cannot report VALID preflight when egress leaks (INV-B2)"
            )
        return self


class BoundaryAssuranceVector(BaseModel):
    """Six-layer Boundary Assurance Stack vector b_t in [0, 1]^6."""

    model_config = STRICT_MODEL_CONFIG

    probe_id: str = Field(..., pattern=r"^BAS-[A-Z0-9_-]{4,40}$")
    session_id: str = Field(..., pattern=r"^PASAC-[A-Z0-9_-]{4,48}$")
    b_scope: float = Field(..., allow_inf_nan=False, ge=0.0, le=1.0)
    b_identity: float = Field(..., allow_inf_nan=False, ge=0.0, le=1.0)
    b_network: float = Field(..., allow_inf_nan=False, ge=0.0, le=1.0)
    b_storage: float = Field(..., allow_inf_nan=False, ge=0.0, le=1.0)
    b_monitor: float = Field(..., allow_inf_nan=False, ge=0.0, le=1.0)
    b_response: float = Field(..., allow_inf_nan=False, ge=0.0, le=1.0)
    min_layer_floor: float = Field(default=MIN_LAYER_FLOOR_DEFAULT, allow_inf_nan=False, ge=0.10, le=0.99)

    def as_tuple(self) -> Tuple[float, float, float, float, float, float]:
        return (
            self.b_scope,
            self.b_identity,
            self.b_network,
            self.b_storage,
            self.b_monitor,
            self.b_response,
        )


class AgentRiskStateVector(BaseModel):
    """Quantitative cyber-evaluation risk state X_t = (G_t, C_t, E_t, S_t, M_t, R_t)."""

    model_config = STRICT_MODEL_CONFIG

    telemetry_id: str = Field(..., pattern=r"^RISK-[A-Z0-9_-]{4,40}$")
    session_id: str = Field(..., pattern=r"^PASAC-[A-Z0-9_-]{4,48}$")
    task_generality_g: float = Field(..., allow_inf_nan=False, ge=0.0, le=1.0)
    agent_capability_c: float = Field(..., allow_inf_nan=False, ge=0.0, le=1.0)
    external_exposure_e: float = Field(..., allow_inf_nan=False, ge=0.0, le=1.0)
    scope_weakness_s: float = Field(..., allow_inf_nan=False, ge=0.0, le=1.0)
    monitoring_strength_m: float = Field(..., allow_inf_nan=False, ge=0.0, le=1.0)
    response_speed_r: float = Field(..., allow_inf_nan=False, ge=0.0, le=1.0)
    impact_severity_i: float = Field(..., allow_inf_nan=False, ge=0.0, le=100.0)
    exposure_duration_d: float = Field(..., allow_inf_nan=False, ge=0.0, le=10000.0)
    hazard_l_t: float = Field(..., allow_inf_nan=False, ge=0.0, le=1.0)
    tau_review: float = Field(default=TAU_REVIEW_DEFAULT, allow_inf_nan=False, ge=0.01, le=0.90)
    tau_stop: float = Field(default=TAU_STOP_DEFAULT, allow_inf_nan=False, ge=0.02, le=1.0)

    @model_validator(mode="after")
    def verify_threshold_ordering(self) -> "AgentRiskStateVector":
        if self.tau_review >= self.tau_stop:
            raise ValueError("tau_review must be strictly less than tau_stop")
        return self


class PolicyEnforcementDecision(BaseModel):
    """Deterministic Policy Enforcement Point output binding Allow(a) and hazard regime."""

    model_config = STRICT_MODEL_CONFIG

    decision_code: str = Field(..., pattern=r"^PEP-[A-Z0-9_-]{4,40}$")
    session_id: str = Field(..., pattern=r"^PASAC-[A-Z0-9_-]{4,48}$")
    in_authorized_scope: bool
    resource_whitelisted: bool
    action_risk: float = Field(..., allow_inf_nan=False, ge=0.0, le=1.0)
    risk_threshold: float = Field(..., allow_inf_nan=False, ge=0.01, le=1.0)
    preflight_status: PreflightStatus
    allow_action: bool
    hazard_regime: HazardRegime
    conservative_assurance: float = Field(..., allow_inf_nan=False, ge=0.0, le=1.0)
    risk_index_r_star: float = Field(..., allow_inf_nan=False, ge=0.0, le=1000000.0)
    manifest_hash: str = Field(default=CTXFW_MANIFEST_HASH, pattern=r"^[a-f0-9]{64}$")


class ContainmentQuarantineAlert(BaseModel):
    """Immutable containment halt / quarantine escalation record requiring sign-off."""

    model_config = STRICT_MODEL_CONFIG

    alert_id: str = Field(..., pattern=r"^QALT-[A-Z0-9_-]{4,40}$")
    session_id: str = Field(..., pattern=r"^PASAC-[A-Z0-9_-]{4,48}$")
    error_class: FailureErrorClass
    assigned_role: AccountabilityRole
    incident_summary: str = Field(..., min_length=8, max_length=240)
    occ_version: int = Field(..., ge=1, le=1000000)


class RuntimePreflightPosture(BaseModel):
    """Deterministic offline runtime assurance posture result for doctor & preflight gates."""

    model_config = STRICT_MODEL_CONFIG

    contract: AssuranceScopeContract
    bas: BoundaryAssuranceVector
    conservative_assurance: float = Field(..., allow_inf_nan=False, ge=0.0, le=1.0)
    product_assurance: float = Field(..., allow_inf_nan=False, ge=0.0, le=1.0)
    findings: Tuple[str, ...] = Field(default=())
    passed: bool


def compute_boundary_assurances(vec: BoundaryAssuranceVector) -> Tuple[float, float]:
    """Return (A_min_t, A_prod_t): conservative min-floor and independent product."""
    vals = vec.as_tuple()
    a_min = min(vals)
    a_prod = 1.0
    for v in vals:
        a_prod *= v
    return (round(a_min, 6), round(a_prod, 6))


def compute_parametric_risk_r_star(
    state: AgentRiskStateVector,
    beta_0: float = -1.5,
) -> float:
    """Compute R*_t = sigma(logit(X_t)) * I*_t * D*_t deterministically."""
    _require_finite(beta_0, "beta_0")
    logit = (
        beta_0
        + 1.2 * state.task_generality_g
        + 1.5 * state.agent_capability_c
        + 1.4 * state.external_exposure_e
        + 1.6 * state.scope_weakness_s
        + 0.9 * state.task_generality_g * state.agent_capability_c
        + 1.1 * state.agent_capability_c * state.scope_weakness_s
        - 1.3 * state.monitoring_strength_m
        - 1.2 * state.response_speed_r
    )
    _require_finite(logit, "logit")
    prob = 1.0 / (1.0 + math.exp(-logit))
    result = round(prob * state.impact_severity_i * state.exposure_duration_d, 4)
    _require_finite(result, "risk_index_r_star")
    return result


def classify_hazard_regime(
    hazard_l_t: float, tau_review: float, tau_stop: float
) -> HazardRegime:
    """Classify leading-indicator hazard band relative to tau_review < tau_stop."""
    _require_finite(hazard_l_t, "hazard_l_t")
    _require_finite(tau_review, "tau_review")
    _require_finite(tau_stop, "tau_stop")
    if tau_review >= tau_stop:
        raise ValueError("tau_review must be strictly less than tau_stop")
    if hazard_l_t >= tau_stop:
        return HazardRegime.SYNCHRONOUS_STOP
    if hazard_l_t >= tau_review:
        return HazardRegime.REVIEW_PAUSE
    return HazardRegime.NOMINAL_ALLOW


def evaluate_pep_gate(
    contract: AssuranceScopeContract,
    bas: BoundaryAssuranceVector,
    risk_state: AgentRiskStateVector,
    action_code: str,
    in_authorized_scope: bool,
    resource_whitelisted: bool,
    action_risk: float,
    risk_threshold: float,
) -> PolicyEnforcementDecision:
    """Enforce Allow(a) conjunction, BAS non-masking floor, and hazard escalation."""
    _require_finite(action_risk, "action_risk")
    _require_finite(risk_threshold, "risk_threshold")
    a_min, _ = compute_boundary_assurances(bas)
    r_star = compute_parametric_risk_r_star(risk_state)
    regime = classify_hazard_regime(
        risk_state.hazard_l_t, risk_state.tau_review, risk_state.tau_stop
    )
    boundary_ok = (a_min >= bas.min_layer_floor) and not contract.live_egress_detected
    pep_conjunction = bool(
        in_authorized_scope
        and resource_whitelisted
        and (action_risk < risk_threshold)
        and (contract.preflight_status == PreflightStatus.VALID)
        and (not contract.cross_run_writable)
        and boundary_ok
        and (regime != HazardRegime.SYNCHRONOUS_STOP)
    )
    norm_code = format_pep_action_code(action_code)
    return PolicyEnforcementDecision(
        decision_code=f"PEP-{norm_code[:36]}",
        session_id=contract.session_id,
        in_authorized_scope=in_authorized_scope,
        resource_whitelisted=resource_whitelisted,
        action_risk=action_risk,
        risk_threshold=risk_threshold,
        preflight_status=contract.preflight_status,
        allow_action=pep_conjunction,
        hazard_regime=regime,
        conservative_assurance=a_min,
        risk_index_r_star=r_star,
    )


def _is_non_loopback_remote_url(raw_url: str) -> bool:
    """True when URL specifies a remote non-loopback network endpoint."""
    candidate = raw_url.strip()
    if not _REMOTE_URL_RE.match(candidate):
        return False
    parsed = urllib.parse.urlparse(candidate)
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return True
    return host not in _LOOPBACK_HOSTS


def _scan_config_object_for_pasac(
    config_obj: Mapping[str, Any],
    egress_mode: EgressPolicyMode,
) -> Tuple[Tuple[str, ...], bool, bool, bool]:
    """Deterministically inspect a single MCP/workspace config dict for egress/cross-run risks."""
    findings: list[str] = []
    live_egress = False
    cross_run_flag = False
    unsandboxed_flag = False

    if bool(config_obj.get("cross_run_writable")) or bool(config_obj.get("shared_board_writable")):
        cross_run_flag = True
        findings.append("cross_run_writable=True violates INV-B3 isolation boundary")

    if bool(config_obj.get("allow_unsandboxed_fallback")):
        unsandboxed_flag = True
        findings.append("allow_unsandboxed_fallback=True weakens b_scope confinement")

    if bool(config_obj.get("live_egress_detected")) and egress_mode == EgressPolicyMode.OFFLINE_ISOLATED:
        live_egress = True
        findings.append("Explicit live_egress_detected flag in OFFLINE_ISOLATED config")

    servers = config_obj.get("mcpServers")
    if isinstance(servers, Mapping):
        for srv_name, srv_cfg in sorted(servers.items(), key=lambda kv: str(kv[0])):
            if not isinstance(srv_cfg, Mapping):
                continue
            if bool(srv_cfg.get("cross_run_writable")) or bool(srv_cfg.get("shared_board_writable")):
                cross_run_flag = True
                findings.append(f"{srv_name}: cross_run_writable channel prohibited (INV-B3)")
            if bool(srv_cfg.get("allow_unsandboxed_fallback")):
                unsandboxed_flag = True
                findings.append(f"{srv_name}: allow_unsandboxed_fallback=True prohibited")
            for url_key in ("url", "endpoint", "serverUrl", "sseUrl", "baseUrl"):
                raw_url = srv_cfg.get(url_key)
                if isinstance(raw_url, str) and _is_non_loopback_remote_url(raw_url):
                    if egress_mode == EgressPolicyMode.OFFLINE_ISOLATED:
                        live_egress = True
                        findings.append(
                            f"{srv_name}: non-loopback remote MCP endpoint '{url_key}' under OFFLINE_ISOLATED"
                        )

    return tuple(findings), live_egress, cross_run_flag, unsandboxed_flag


def assess_runtime_isolation_posture(
    *,
    session_id: str = "PASAC-DOCTOR-LOCAL-01",
    egress_mode: EgressPolicyMode = EgressPolicyMode.OFFLINE_ISOLATED,
    mcp_configs: Sequence[Mapping[str, Any]] = (),
    wal_healthy: bool = True,
    tracekit_intact: bool = True,
    sieve_verified: bool = True,
    confinement_enabled: bool = True,
    strict_param_binding: bool = True,
    mcp_guard_quarantined_count: int = 0,
    min_layer_floor: float = MIN_LAYER_FLOOR_DEFAULT,
) -> RuntimePreflightPosture:
    """Evaluate offline local PASAC isolation posture without making any network calls."""
    findings: list[str] = []
    live_egress = False
    cross_run_flag = False
    unsandboxed_flag = False

    for cfg in mcp_configs:
        if isinstance(cfg, Mapping):
            sub_findings, sub_egress, sub_cross, sub_unsandboxed = _scan_config_object_for_pasac(
                cfg, egress_mode
            )
            findings.extend(sub_findings)
            live_egress = live_egress or sub_egress
            cross_run_flag = cross_run_flag or sub_cross
            unsandboxed_flag = unsandboxed_flag or sub_unsandboxed

    if mcp_guard_quarantined_count > 0:
        findings.append(
            f"mcp_guard reports {mcp_guard_quarantined_count} active tool poisoning quarantine(s)"
        )
    if not wal_healthy:
        findings.append("SQLite WAL concurrency PRAGMA check degraded")
    if not tracekit_intact:
        findings.append("TraceKit ledger integrity check failed")

    b_scope = 0.25 if (unsandboxed_flag or not confinement_enabled) else 0.96
    b_identity = (
        0.55
        if mcp_guard_quarantined_count > 0
        else (0.65 if not strict_param_binding else 0.95)
    )
    b_network = 0.0 if live_egress else (0.95 if egress_mode == EgressPolicyMode.OFFLINE_ISOLATED else 0.85)
    b_storage = 0.0 if cross_run_flag else (0.60 if not wal_healthy else 0.95)
    b_monitor = 0.30 if not tracekit_intact else (0.88 if not sieve_verified else 0.94)
    b_response = 0.95 if (confinement_enabled and strict_param_binding) else 0.60

    norm_sid = format_pasac_session_id(session_id)
    bas = BoundaryAssuranceVector(
        probe_id=f"BAS-{format_pep_action_code(norm_sid)[:32]}",
        session_id=norm_sid,
        b_scope=b_scope,
        b_identity=b_identity,
        b_network=b_network,
        b_storage=b_storage,
        b_monitor=b_monitor,
        b_response=b_response,
        min_layer_floor=min_layer_floor,
    )
    a_min, a_prod = compute_boundary_assurances(bas)

    preflight_ok = (
        (not live_egress)
        and (not cross_run_flag)
        and (not unsandboxed_flag)
        and wal_healthy
        and tracekit_intact
        and (mcp_guard_quarantined_count == 0)
        and (a_min >= min_layer_floor)
    )
    preflight_status = PreflightStatus.VALID if preflight_ok else PreflightStatus.FAILED

    contract = AssuranceScopeContract(
        session_id=norm_sid,
        egress_mode=egress_mode,
        live_egress_detected=live_egress,
        cross_run_writable=False,
        preflight_status=preflight_status,
        contract_digest=derive_contract_digest(
            norm_sid,
            egress_mode.value,
            int(live_egress),
            int(cross_run_flag),
            preflight_status.value,
            a_min,
        ),
    )

    return RuntimePreflightPosture(
        contract=contract,
        bas=bas,
        conservative_assurance=a_min,
        product_assurance=a_prod,
        findings=tuple(findings),
        passed=preflight_ok and (not cross_run_flag),
    )
