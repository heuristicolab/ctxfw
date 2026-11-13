# manifest_hash: 8f925c1e7c680c7af68e6f3daa48a5ac734923438762ed8836878a97508ce42e
"""
SARA Runtime Authorization Gate :: Deterministic Policy & FSM Enforcement
=========================================================================
manifest_hash (M3-P2): 8f925c1e7c680c7af68e6f3daa48a5ac734923438762ed8836878a97508ce42e
manifest_hash (M3-P3): 8d94151e921e2f8eaacb440cb3c1b0d4e0ff6ac80fa217e5830de1c1edec1b13
manifest_hash_wave1b: ebbcd0d607fa09a71dda690ea76104d762b3f279cde258f64917421d39a249f4
Evaluates untrusted tool observations against immutable allowlist policies
(AuthorizedPolicyDTO), emits AuthorizationVerdictDTO (ALLOW, STRIP_COMMANDS,
QUARANTINE_TOOL), tracks the total FSM transition trace delta(S, E), and
enforces fail-closed degradation on any malformed or adversarial input.
"""
from __future__ import annotations

import functools
import math
import re
from typing import Any, Callable, Optional, Tuple, TypeVar

from ctxfw.sara.contracts import (
    EXECUTION_ID_PATTERN,
    GATE_LATENCY_BUDGET_MS,
    RISK_QUARANTINE_THRESHOLD,
    TOOL_NAME_PATTERN,
    AuthorizationPolicyRuleDTO,
    AuthorizationVerdictDTO,
    DirectiveKind,
    InductionDirectiveDTO,
    RawToolObservationDTO,
    SaraEvent,
    SaraState,
    VerdictKind,
    observation_digest,
    transition,
    verdict_for_risk,
)
from ctxfw.sara.induction import InductionParser
from ctxfw.sara.lexical import LexicalSanitizer

# Architectural aliases
UntrustedObservationDTO = RawToolObservationDTO
AuthorizedPolicyDTO = AuthorizationPolicyRuleDTO

__all__ = [
    "AuthorizedPolicyDTO",
    "GATE_LATENCY_BUDGET_MS",
    "RuntimeAuthorizationGate",
    "UntrustedObservationDTO",
]

_F = TypeVar("_F", bound=Callable[..., Any])

_FALLBACK_EXECUTION_ID = "EXE-0000failclosed"
_FALLBACK_TOOL_NAME = "unknown_tool"
_EXECUTION_ID_RE = re.compile(EXECUTION_ID_PATTERN)
_TOOL_NAME_RE = re.compile(TOOL_NAME_PATTERN)


class _DualMethod:
    """Descriptor allowing a method to be called on either the class or an instance."""

    def __init__(self, func: _F) -> None:
        self._func = func
        functools.update_wrapper(self, func)

    def __get__(self, instance: Any, owner: Any = None) -> Any:
        target = owner if instance is None else instance
        return functools.partial(self._func, target)


def _extract_safe_execution_id(observation: Any) -> str:
    """Extract a valid execution_id or return the canonical fail-closed fallback."""
    try:
        source = getattr(observation, "source", None)
        exe_id = getattr(source, "execution_id", None) or getattr(observation, "execution_id", None)
        if isinstance(exe_id, str) and 12 <= len(exe_id) <= 68 and _EXECUTION_ID_RE.match(exe_id):
            return exe_id
    except Exception:
        pass
    return _FALLBACK_EXECUTION_ID


def _extract_safe_tool_name(observation: Any, policy: Any) -> str:
    """Extract a valid tool_name or return the canonical fail-closed fallback."""
    for candidate_obj in (getattr(observation, "source", None), observation, policy):
        try:
            t_name = getattr(candidate_obj, "tool_name", None)
            if isinstance(t_name, str) and 2 <= len(t_name) <= 64 and _TOOL_NAME_RE.match(t_name):
                return t_name
        except Exception:
            continue
    return _FALLBACK_TOOL_NAME


def _build_violation_reason(
    verdict: VerdictKind,
    risk_score: float,
    directives: Tuple[InductionDirectiveDTO, ...],
    tool_mismatch: bool,
) -> Optional[str]:
    """Construct a deterministic, non-empty violation reason for non-ALLOW verdicts."""
    if verdict is VerdictKind.ALLOW:
        return None

    kinds = sorted({d.directive_kind.value for d in directives})
    kinds_str = ", ".join(kinds) if kinds else "POLICY_VIOLATION"
    prefix = (
        "Tool quarantined due to critical induction risk"
        if verdict is VerdictKind.QUARANTINE_TOOL
        else "Imperative directives stripped from untrusted observation"
    )
    mismatch_note = " [tool_name mismatch against policy]" if tool_mismatch else ""
    reason = f"{prefix}: {kinds_str} (risk_score={risk_score:.4f}){mismatch_note}"
    return reason[:512]


class RuntimeAuthorizationGate:
    """Deterministic runtime authorization gate enforcing SARA policies and total FSM transitions."""

    GATE_LATENCY_BUDGET_MS: float = GATE_LATENCY_BUDGET_MS

    def __init__(self, audit_sink: Optional[Any] = None, pasac_store: Optional[Any] = None) -> None:
        self._audit_sink = audit_sink
        self._pasac_store = pasac_store

    @_DualMethod
    def authorize_traced(
        self_or_cls: Any,
        observation: UntrustedObservationDTO,
        policy: AuthorizedPolicyDTO,
    ) -> Tuple[AuthorizationVerdictDTO, list[SaraState]]:
        """Evaluate an untrusted observation against an authorized policy, returning (verdict, fsm_trace).

        Raises:
            TypeError, ValueError: If observation or policy fails validation.
        """
        state = SaraState.INGRESSED
        trace: list[SaraState] = [state]

        if not isinstance(observation, RawToolObservationDTO):
            raise TypeError(
                f"observation must be RawToolObservationDTO, got {type(observation).__name__}"
            )
        if not isinstance(policy, AuthorizationPolicyRuleDTO):
            raise TypeError(
                f"policy must be AuthorizationPolicyRuleDTO, got {type(policy).__name__}"
            )

        # 1. Lexical validation & digest integrity gate
        LexicalSanitizer.validate_raw(observation.raw_output)
        if observation_digest(observation.raw_output) != observation.observation_sha256:
            raise ValueError("observation_sha256 does not match SHA-256(raw_output)")
        state = transition(state, SaraEvent.SANITIZE_OK)
        trace.append(state)

        # 2. Action induction parsing & risk scoring
        directives, risk_score = InductionParser.parse(observation, policy)
        if math.isnan(risk_score) or math.isinf(risk_score):
            raise ValueError("risk_score shall never be NaN or Inf")

        has_hidden_escape = any(
            d.directive_kind is DirectiveKind.HIDDEN_ESCAPE for d in directives
        )

        # 3. FSM transition according to escape detection and risk thresholds
        if has_hidden_escape and risk_score >= RISK_QUARANTINE_THRESHOLD:
            state = transition(state, SaraEvent.ESCAPE_PATTERN_DETECTED)
            trace.append(state)
        else:
            state = transition(state, SaraEvent.PARSE_OK)
            trace.append(state)

            verdict_kind = verdict_for_risk(risk_score)
            if verdict_kind is VerdictKind.ALLOW:
                state = transition(state, SaraEvent.RISK_LOW)
            elif verdict_kind is VerdictKind.STRIP_COMMANDS:
                state = transition(state, SaraEvent.RISK_MEDIUM)
            else:
                state = transition(state, SaraEvent.RISK_HIGH)
            trace.append(state)

        final_verdict_kind = verdict_for_risk(risk_score)
        tool_mismatch = policy.tool_name != observation.source.tool_name
        violation_reason = _build_violation_reason(
            final_verdict_kind,
            risk_score,
            directives,
            tool_mismatch,
        )

        verdict_dto = AuthorizationVerdictDTO(
            execution_id=observation.source.execution_id,
            tool_name=observation.source.tool_name,
            verdict=final_verdict_kind,
            risk_score=risk_score,
            directives=directives,
            violation_reason=violation_reason,
        )

        # 4. Optional synchronous WAL commit if an AuditSink / SaraStore is attached to this gate instance
        audit_sink = getattr(self_or_cls, "_audit_sink", None)
        if audit_sink is not None:
            audit_sink.audit_commit(observation, verdict_dto)
            state = transition(state, SaraEvent.WAL_COMMIT)
            trace.append(state)

        return verdict_dto, trace

    @_DualMethod
    def authorize(
        self_or_cls: Any,
        observation: UntrustedObservationDTO,
        policy: AuthorizedPolicyDTO,
    ) -> AuthorizationVerdictDTO:
        """Evaluate an untrusted observation against an authorized policy and return the verdict DTO."""
        verdict_dto, _ = self_or_cls.authorize_traced(observation, policy)
        return verdict_dto

    @_DualMethod
    def authorize_fail_closed(
        self_or_cls: Any,
        observation: Any,
        policy: Any,
    ) -> Tuple[AuthorizationVerdictDTO, list[SaraState]]:
        """Fail-closed evaluation wrapper: never raises; collapses any error or invalid input to QUARANTINE_TOOL."""
        try:
            return self_or_cls.authorize_traced(observation, policy)
        except Exception as exc:
            exe_id = _extract_safe_execution_id(observation)
            t_name = _extract_safe_tool_name(observation, policy)
            reason = f"Fail-closed quarantine ({type(exc).__name__}): {exc}".strip()[:512]
            if not reason:
                reason = "Fail-closed quarantine: invalid input or runtime fault"

            fallback_verdict = AuthorizationVerdictDTO(
                execution_id=exe_id,
                tool_name=t_name,
                verdict=VerdictKind.QUARANTINE_TOOL,
                risk_score=1.0,
                directives=(),
                violation_reason=reason,
            )
            rejected_state = transition(SaraState.INGRESSED, SaraEvent.VALIDATION_FAIL)
            return fallback_verdict, [SaraState.INGRESSED, rejected_state]

    @_DualMethod
    def evaluate_pasac_pep(
        self_or_cls: Any,
        contract: Any,
        bas: Any,
        risk_state: Any,
        action_code: str,
        *,
        in_authorized_scope: bool = True,
        resource_whitelisted: bool = True,
        action_risk: float = 0.0,
        risk_threshold: float = 0.50,
        pasac_store: Optional[Any] = None,
    ) -> Any:
        """Evaluate PASAC 6-layer Boundary Assurance Stack & four-predicate PEP Allow(a) gate."""
        from ctxfw.sara.assurance import evaluate_pep_gate

        target_store = pasac_store or getattr(self_or_cls, "_pasac_store", None)
        if target_store is not None:
            return target_store.evaluate_and_record_pep(
                contract=contract,
                bas=bas,
                risk_state=risk_state,
                action_code=action_code,
                in_authorized_scope=in_authorized_scope,
                resource_whitelisted=resource_whitelisted,
                action_risk=action_risk,
                risk_threshold=risk_threshold,
            )
        return evaluate_pep_gate(
            contract=contract,
            bas=bas,
            risk_state=risk_state,
            action_code=action_code,
            in_authorized_scope=in_authorized_scope,
            resource_whitelisted=resource_whitelisted,
            action_risk=action_risk,
            risk_threshold=risk_threshold,
        )
