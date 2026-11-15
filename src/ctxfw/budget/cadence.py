# manifest_hash: 34ae93e3f71bcaab59019e9e0139a4b24b69b82c2005b25e5049329f84b1aa2c
"""
TokenCast Cadence :: Deterministic AIMD Strategic Agent Guidance Engine (#19)
================================================================================
Pure stdlib + Pydantic v2 scheduler and trajectory guidance engine:
  - Purely deterministic AIMD cadence (`I' = min(i_max, I + delta_step)` on ADVISORY,
    `I' = i_base` on REPLACEMENT) driven by TokenCast budget/breaker signals, TraceLite
    edit/overlap signals, and consecutive tool failure streaks (ZERO auxiliary LLMs).
  - Open extensible `ScaffoldType` (`^[A-Za-z0-9_.:-]{2,64}$`), decoupling benchmark types.
  - Zero FastAPI / httpx / network / tree-sitter imports for lightweight RSS footprint.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
import re
from typing import Any, Mapping, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import core_schema

CADENCE_MANIFEST_HASH: str = "34ae93e3f71bcaab59019e9e0139a4b24b69b82c2005b25e5049329f84b1aa2c"

SCAFFOLD_TYPE_PATTERN = r"^[A-Za-z0-9_.:-]{2,64}$"
SHA256_HEX_PATTERN = r"^[a-f0-9]{64}$"

MIN_CADENCE_INTERVAL: int = 1
MAX_CADENCE_INTERVAL: int = 50
MAX_I_BASE: int = 20
MAX_DELTA_STEP: int = 10

PROXY_CONTEXT_TOKEN_CAP: int = 40000
PROXY_MAX_TOKENS_CAP: int = 4096
PROXY_THINKING_BUDGET_CAP: int = 1024

_SCAFFOLD_TYPE_RE = re.compile(SCAFFOLD_TYPE_PATTERN)


def validate_scaffold_type(value: str) -> str:
    """Validate and normalize an open extensible agent scaffold identifier."""
    if not isinstance(value, str):
        raise ValueError("scaffold_type must be a string")
    normalized = value.strip()
    if not _SCAFFOLD_TYPE_RE.match(normalized):
        raise ValueError(
            f"Invalid scaffold_type {value!r}: must match {SCAFFOLD_TYPE_PATTERN}"
        )
    return normalized


class ScaffoldType(str):
    """Open, extensible agent scaffold identifier supporting arbitrary IDE & CLI agents."""

    MINI_SWE_AGENT: str = "MINI_SWE_AGENT"
    MOATLESS_LINEAR: str = "MOATLESS_LINEAR"
    CTXFW_PRUNER_AGENT: str = "CTXFW_PRUNER_AGENT"
    GENERIC_MCP_PROXY: str = "GENERIC_MCP_PROXY"
    CLAUDE_CODE: str = "claude_code"
    CURSOR: str = "cursor"

    def __new__(cls, value: str) -> "ScaffoldType":
        return super().__new__(cls, validate_scaffold_type(value))

    @classmethod
    def __get_pydantic_core_schema__(cls, _source_type: Any, _handler: Any) -> Any:
        return core_schema.no_info_after_validator_function(
            cls,
            core_schema.str_schema(min_length=2, max_length=64),
        )


class InterventionVerdict(str, Enum):
    ADVISORY = "ADVISORY"
    REPLACEMENT = "REPLACEMENT"


class MisbehaviorCategory(str, Enum):
    NONE = "NONE"
    GOAL_DRIFT = "GOAL_DRIFT"
    REPEATED_EDIT_STALL = "REPEATED_EDIT_STALL"
    CONTEXT_BLOAT_SPIKE = "CONTEXT_BLOAT_SPIKE"
    CONSECUTIVE_TOOL_FAILURE = "CONSECUTIVE_TOOL_FAILURE"
    BREAKER_TRIP = "BREAKER_TRIP"


class CadenceState(str, Enum):
    EXECUTING_AUTONOMOUS = "EXECUTING_AUTONOMOUS"
    CADENCE_DUE = "CADENCE_DUE"
    EVALUATING_DETERMINISTIC = "EVALUATING_DETERMINISTIC"
    ADVISORY_APPLIED = "ADVISORY_APPLIED"
    REPLACEMENT_VETOED = "REPLACEMENT_VETOED"
    ROLLED_BACK = "ROLLED_BACK"
    COMPLETED = "COMPLETED"
    QUARANTINED = "QUARANTINED"


class CadenceEvent(str, Enum):
    STEP_DUE = "STEP_DUE"
    INSPECT_SIGNAL_CLEAN = "INSPECT_SIGNAL_CLEAN"
    VERDICT_ADVISORY = "VERDICT_ADVISORY"
    VERDICT_REPLACEMENT = "VERDICT_REPLACEMENT"
    CONTINUE_RUN = "CONTINUE_RUN"
    TRIGGER_SNAPSHOT_ROLLBACK = "TRIGGER_SNAPSHOT_ROLLBACK"
    FINISH_TASK = "FINISH_TASK"
    INVARIANT_BREACH = "INVARIANT_BREACH"


class ErrorClass(str, Enum):
    TRANSIENT = "TRANSIENT"
    DETERMINISTIC = "DETERMINISTIC"
    BUSINESS = "BUSINESS"
    SECURITY = "SECURITY"


TERMINAL_CADENCE_STATES: frozenset[CadenceState] = frozenset(
    {CadenceState.COMPLETED, CadenceState.QUARANTINED}
)

CADENCE_TRANSITIONS: dict[tuple[CadenceState, CadenceEvent], CadenceState] = {
    (CadenceState.EXECUTING_AUTONOMOUS, CadenceEvent.STEP_DUE): CadenceState.CADENCE_DUE,
    (CadenceState.EXECUTING_AUTONOMOUS, CadenceEvent.FINISH_TASK): CadenceState.COMPLETED,
    (CadenceState.CADENCE_DUE, CadenceEvent.INSPECT_SIGNAL_CLEAN): CadenceState.EVALUATING_DETERMINISTIC,
    (CadenceState.EVALUATING_DETERMINISTIC, CadenceEvent.VERDICT_ADVISORY): CadenceState.ADVISORY_APPLIED,
    (CadenceState.EVALUATING_DETERMINISTIC, CadenceEvent.VERDICT_REPLACEMENT): CadenceState.REPLACEMENT_VETOED,
    (CadenceState.ADVISORY_APPLIED, CadenceEvent.CONTINUE_RUN): CadenceState.EXECUTING_AUTONOMOUS,
    (CadenceState.REPLACEMENT_VETOED, CadenceEvent.TRIGGER_SNAPSHOT_ROLLBACK): CadenceState.ROLLED_BACK,
    (CadenceState.REPLACEMENT_VETOED, CadenceEvent.CONTINUE_RUN): CadenceState.EXECUTING_AUTONOMOUS,
    (CadenceState.ROLLED_BACK, CadenceEvent.CONTINUE_RUN): CadenceState.EXECUTING_AUTONOMOUS,
}


def cadence_transition(state: CadenceState, event: CadenceEvent) -> CadenceState:
    """Deterministic FSM transition δ(S, E); invariant breach or post-terminal quarantines."""
    if not isinstance(state, CadenceState) or not isinstance(event, CadenceEvent):
        raise TypeError("state must be CadenceState and event must be CadenceEvent")
    if event == CadenceEvent.INVARIANT_BREACH:
        return CadenceState.QUARANTINED
    if state in TERMINAL_CADENCE_STATES:
        return CadenceState.QUARANTINED
    nxt = CADENCE_TRANSITIONS.get((state, event))
    if nxt is None:
        raise ValueError(f"Illegal Cadence FSM transition: {state.value} + {event.value}")
    return nxt


def _check_finite(val: float, name: str) -> float:
    if not isinstance(val, (int, float)) or isinstance(val, bool) or math.isnan(val) or math.isinf(val):
        raise ValueError(f"{name} must be a finite numeric value")
    return float(val)


class _CadenceBaseDTO(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SchedulerConfig(_CadenceBaseDTO):
    """Deterministic AIMD scheduler parameters bounded within [1, 50]."""

    config_id: str = Field(default="cadence-default", min_length=1, max_length=128)
    scaffold_type: ScaffoldType = Field(default=ScaffoldType("GENERIC_MCP_PROXY"))
    i_base: int = Field(default=2, ge=MIN_CADENCE_INTERVAL, le=MAX_I_BASE)
    delta_step: int = Field(default=1, ge=1, le=MAX_DELTA_STEP)
    i_max: int = Field(default=16, ge=2, le=MAX_CADENCE_INTERVAL)
    max_consecutive_errors: int = Field(default=3, ge=1, le=100)
    max_repeated_edits: int = Field(default=4, ge=2, le=100)
    budget_utilization_threshold: float = Field(default=0.85, ge=0.1, le=1.0)
    redundancy_ratio_threshold: float = Field(default=0.75, ge=0.1, le=1.0)

    @field_validator("budget_utilization_threshold", "redundancy_ratio_threshold")
    @classmethod
    def _finite_thresholds(cls, v: float, info: Any) -> float:
        return _check_finite(v, info.field_name)

    @model_validator(mode="after")
    def _validate_interval_order(self) -> "SchedulerConfig":
        if self.i_base > self.i_max:
            raise ValueError(f"i_base ({self.i_base}) cannot exceed i_max ({self.i_max})")
        return self


class CadenceTelemetrySignals(_CadenceBaseDTO):
    """Deterministic telemetry inputs from TokenCast, TraceLite, and repeated tool failures."""

    budget_utilization: float = Field(default=0.0, ge=0.0, le=10.0)
    breaker_state: str = Field(default="CLOSED", min_length=1, max_length=32)
    estimated_prompt_tokens: int = Field(default=0, ge=0, le=PROXY_CONTEXT_TOKEN_CAP * 10)
    tokens_saved_step: int = Field(default=0, ge=0)
    cumulative_tokens_saved: int = Field(default=0, ge=0)
    edit_phase_cleanups: int = Field(default=0, ge=0)
    redundant_overlap_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    consecutive_tool_errors: int = Field(default=0, ge=0, le=1000)
    repeated_file_edits: int = Field(default=0, ge=0, le=1000)
    snapshot_run_id: Optional[str] = Field(default=None, max_length=128)

    @field_validator("budget_utilization", "redundant_overlap_ratio")
    @classmethod
    def _finite_signal(cls, v: float, info: Any) -> float:
        return _check_finite(v, info.field_name)


class TrajectoryStepProposal(_CadenceBaseDTO):
    """Step context inspected deterministically by the AIMD cadence engine."""

    proposal_id: str = Field(..., min_length=1, max_length=128)
    run_id: str = Field(..., min_length=1, max_length=128)
    session_id: str = Field(..., min_length=1, max_length=128)
    scaffold_type: ScaffoldType = Field(default=ScaffoldType("GENERIC_MCP_PROXY"))
    step_index: int = Field(..., ge=0)
    last_inspection_step: int = Field(default=-1, ge=-1)
    current_interval: int = Field(default=2, ge=MIN_CADENCE_INTERVAL, le=MAX_CADENCE_INTERVAL)
    action_summary: str = Field(default="", max_length=1024)
    signals: CadenceTelemetrySignals = Field(default_factory=CadenceTelemetrySignals)


class TwoTierVerdict(_CadenceBaseDTO):
    """Deterministic cadence outcome enforcing ADVISORY => 1 and REPLACEMENT => 0."""

    verdict_id: str = Field(..., min_length=1, max_length=128)
    run_id: str = Field(..., min_length=1, max_length=128)
    step_index: int = Field(..., ge=0)
    inspection_triggered: bool = Field(default=True)
    verdict: InterventionVerdict
    category: MisbehaviorCategory
    action_executed: int = Field(..., ge=0, le=1)
    guidance_note: str = Field(..., min_length=1, max_length=1024)
    next_interval: int = Field(..., ge=MIN_CADENCE_INTERVAL, le=MAX_CADENCE_INTERVAL)
    state: CadenceState
    rollback_triggered: bool = Field(default=False)
    rollback_target_epoch: Optional[int] = Field(default=None, ge=0)
    cadence_seal_sha256: str = Field(..., min_length=64, max_length=64)

    @model_validator(mode="after")
    def _enforce_verdict_execution_invariant(self) -> "TwoTierVerdict":
        if self.verdict == InterventionVerdict.REPLACEMENT and self.action_executed != 0:
            raise ValueError("REPLACEMENT verdict shall never set action_executed = 1")
        if self.verdict == InterventionVerdict.ADVISORY and self.action_executed != 1:
            raise ValueError("ADVISORY verdict requires action_executed = 1")
        return self


class SchedulerStateSnapshot(_CadenceBaseDTO):
    """Persisted AIMD cadence state for a run."""

    run_id: str = Field(..., min_length=1, max_length=128)
    session_id: str = Field(..., min_length=1, max_length=128)
    scaffold_type: ScaffoldType
    current_step_index: int = Field(..., ge=0)
    last_inspection_step: int = Field(..., ge=-1)
    current_interval: int = Field(..., ge=MIN_CADENCE_INTERVAL, le=MAX_CADENCE_INTERVAL)
    state: CadenceState
    occ_version: int = Field(..., ge=0)
    updated_at_utc: str = Field(..., min_length=1)


class TokenLeverageTelemetry(_CadenceBaseDTO):
    """Token efficiency comparison metric under deterministic guidance."""

    run_id: str = Field(..., min_length=1, max_length=128)
    step_index: int = Field(..., ge=0)
    tokens_without_guidance: int = Field(..., ge=0)
    tokens_with_guidance: int = Field(..., ge=0)
    token_leverage_ratio: float = Field(..., ge=0.0)

    @field_validator("token_leverage_ratio")
    @classmethod
    def _finite_ratio(cls, v: float) -> float:
        return _check_finite(v, "token_leverage_ratio")


class CadenceRunEnvelope(_CadenceBaseDTO):
    """Run registration envelope."""

    run_id: str = Field(..., min_length=1, max_length=128)
    session_id: str = Field(..., min_length=1, max_length=128)
    config: SchedulerConfig
    initial_state: CadenceState = Field(default=CadenceState.EXECUTING_AUTONOMOUS)


# ---------------------------------------------------------------------------
# Pure deterministic AIMD & signal evaluation functions (0 LLMs)
# ---------------------------------------------------------------------------


def should_trigger_inspection(
    step_index: int,
    last_inspection_step: int,
    interval: int,
) -> bool:
    """Return True iff `(step_index - last_inspection_step) >= interval` within valid bounds."""
    if step_index < 0:
        raise ValueError("step_index must be >= 0")
    if last_inspection_step < -1:
        raise ValueError("last_inspection_step must be >= -1")
    if interval < MIN_CADENCE_INTERVAL or interval > MAX_CADENCE_INTERVAL:
        raise ValueError(
            f"interval must lie in [{MIN_CADENCE_INTERVAL}, {MAX_CADENCE_INTERVAL}]"
        )
    return (step_index - last_inspection_step) >= interval


def update_inspection_interval(
    current_interval: int,
    verdict: InterventionVerdict,
    *,
    i_base: int = 2,
    delta_step: int = 1,
    i_max: int = 16,
) -> int:
    """Pure AIMD cadence recurrence: additive increase on ADVISORY, reset to i_base on REPLACEMENT."""
    if i_base < MIN_CADENCE_INTERVAL or i_base > MAX_I_BASE:
        raise ValueError(f"i_base must lie in [{MIN_CADENCE_INTERVAL}, {MAX_I_BASE}]")
    if i_max < 2 or i_max > MAX_CADENCE_INTERVAL or i_base > i_max:
        raise ValueError(f"i_max must lie in [{i_base}, {MAX_CADENCE_INTERVAL}]")
    if delta_step < 1 or delta_step > MAX_DELTA_STEP:
        raise ValueError(f"delta_step must lie in [1, {MAX_DELTA_STEP}]")

    bounded_current = max(i_base, min(i_max, int(current_interval)))
    if verdict == InterventionVerdict.REPLACEMENT:
        return i_base
    return min(i_max, bounded_current + delta_step)


def compute_token_leverage(tokens_without_guidance: int, tokens_with_guidance: int) -> float:
    """Compute finite token leverage ratio = tokens_without_guidance / max(1, tokens_with_guidance)."""
    if tokens_without_guidance < 0 or tokens_with_guidance < 0:
        raise ValueError("Token counts must be >= 0")
    denom = max(1, int(tokens_with_guidance))
    ratio = round(float(tokens_without_guidance) / float(denom), 6)
    return _check_finite(ratio, "token_leverage_ratio")


def _compute_cadence_seal(payload: Mapping[str, Any]) -> str:
    data = {"manifest_hash": CADENCE_MANIFEST_HASH, "payload": dict(payload)}
    raw = json.dumps(data, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def extract_deterministic_cadence_signals(
    raw_body: Mapping[str, Any],
    *,
    tokens_saved: int = 0,
    estimated_tokens: int = 0,
    trace_signals: Optional[Mapping[str, Any]] = None,
    tokencast_signals: Optional[Mapping[str, Any]] = None,
    consecutive_tool_errors_override: Optional[int] = None,
    scaffold_override: Optional[str] = None,
) -> Tuple[ScaffoldType, int, CadenceTelemetrySignals]:
    """Deterministically extract Cadence signals from request trajectory, TokenCast, and TraceLite."""
    messages = raw_body.get("messages") if isinstance(raw_body.get("messages"), list) else []
    step_index = len(messages)

    scaffold_raw = (
        scaffold_override
        or raw_body.get("scaffold_type")
        or raw_body.get("client")
        or "GENERIC_MCP_PROXY"
    )
    try:
        scaffold = ScaffoldType(str(scaffold_raw))
    except ValueError:
        scaffold = ScaffoldType("GENERIC_MCP_PROXY")

    # Deterministic consecutive trailing tool error streak counter
    err_streak = 0
    repeated_edits = 0
    for msg in reversed(messages):
        if not isinstance(msg, dict):
            break
        role = str(msg.get("role") or "").lower()
        content = msg.get("content")
        text_repr = content if isinstance(content, str) else json.dumps(content, default=str) if content is not None else ""
        lower_repr = text_repr.lower()
        is_err = bool(
            msg.get("is_error")
            or msg.get("isError")
            or (
                role in {"tool", "user"}
                and ("is_error" in lower_repr or "traceback (most recent call last)" in lower_repr or "policy_blocked" in lower_repr)
            )
        )
        if is_err:
            err_streak += 1
        elif role in {"tool", "assistant"}:
            break

    if isinstance(consecutive_tool_errors_override, int) and consecutive_tool_errors_override >= 0:
        err_streak = consecutive_tool_errors_override

    trace_map = dict(trace_signals or {})
    tokencast_map = dict(tokencast_signals or {})

    if isinstance(trace_map.get("repeated_file_edits"), int):
        repeated_edits = max(0, int(trace_map["repeated_file_edits"]))

    prompt_tokens = max(0, int(estimated_tokens))
    default_util = min(10.0, round(float(prompt_tokens) / float(PROXY_CONTEXT_TOKEN_CAP), 4))
    budget_util = float(tokencast_map.get("budget_utilization", default_util))
    breaker_state = str(tokencast_map.get("breaker_state", "CLOSED")).upper()
    overlap_ratio = float(trace_map.get("redundant_overlap_ratio", 0.0))
    edit_cleanups = int(trace_map.get("edit_phase_cleanups", 0))
    cumulative_saved = int(trace_map.get("cumulative_tokens_saved", max(0, tokens_saved)))
    snapshot_run_id = raw_body.get("snapshot_run_id")
    if isinstance(snapshot_run_id, str):
        snapshot_run_id = snapshot_run_id.strip()[:128] or None
    else:
        snapshot_run_id = None

    signals = CadenceTelemetrySignals(
        budget_utilization=max(0.0, min(10.0, budget_util)),
        breaker_state=breaker_state,
        estimated_prompt_tokens=prompt_tokens,
        tokens_saved_step=max(0, int(tokens_saved)),
        cumulative_tokens_saved=max(0, cumulative_saved),
        edit_phase_cleanups=max(0, edit_cleanups),
        redundant_overlap_ratio=max(0.0, min(1.0, overlap_ratio)),
        consecutive_tool_errors=max(0, min(1000, err_streak)),
        repeated_file_edits=max(0, min(1000, repeated_edits)),
        snapshot_run_id=snapshot_run_id,
    )
    return scaffold, step_index, signals


def evaluate_deterministic_cadence(
    proposal: TrajectoryStepProposal,
    config: SchedulerConfig,
    *,
    force_inspect: bool = False,
) -> TwoTierVerdict:
    """Evaluate a trajectory step purely deterministically (zero external LLMs)."""
    due = should_trigger_inspection(
        proposal.step_index,
        proposal.last_inspection_step,
        proposal.current_interval,
    )
    sig = proposal.signals
    state = CadenceState.EXECUTING_AUTONOMOUS

    # Severe deterministic misbehavior signals always inspect immediately even mid-interval
    category = MisbehaviorCategory.NONE
    guidance = "Nominal trajectory telemetry; continue autonomous execution."
    verdict = InterventionVerdict.ADVISORY

    if sig.breaker_state.upper() in {"HARD_HALT", "HALTED", "TRIPPED"}:
        category = MisbehaviorCategory.BREAKER_TRIP
        verdict = InterventionVerdict.REPLACEMENT
        guidance = "TokenCast breaker halted run; veto autonomous action and reset AIMD cadence."
    elif sig.consecutive_tool_errors >= config.max_consecutive_errors:
        category = MisbehaviorCategory.CONSECUTIVE_TOOL_FAILURE
        verdict = InterventionVerdict.REPLACEMENT
        guidance = (
            f"Detected {sig.consecutive_tool_errors} consecutive tool failures "
            f"(>= {config.max_consecutive_errors}); replace failing trajectory branch."
        )
    elif sig.repeated_file_edits >= config.max_repeated_edits:
        category = MisbehaviorCategory.REPEATED_EDIT_STALL
        verdict = InterventionVerdict.REPLACEMENT
        guidance = (
            f"Detected {sig.repeated_file_edits} repeated file edits without progress; "
            "veto edit loop and reset cadence."
        )
    elif (
        sig.budget_utilization >= config.budget_utilization_threshold
        and sig.redundant_overlap_ratio >= config.redundancy_ratio_threshold
    ):
        category = MisbehaviorCategory.CONTEXT_BLOAT_SPIKE
        verdict = InterventionVerdict.REPLACEMENT
        guidance = (
            f"High budget utilization ({sig.budget_utilization:.2f}) paired with redundant overlap "
            f"({sig.redundant_overlap_ratio:.2f}); veto step for compaction/rollback."
        )

    should_inspect = due or force_inspect or verdict == InterventionVerdict.REPLACEMENT
    if should_inspect:
        state = cadence_transition(state, CadenceEvent.STEP_DUE)
        state = cadence_transition(state, CadenceEvent.INSPECT_SIGNAL_CLEAN)
        evt = (
            CadenceEvent.VERDICT_REPLACEMENT
            if verdict == InterventionVerdict.REPLACEMENT
            else CadenceEvent.VERDICT_ADVISORY
        )
        state = cadence_transition(state, evt)
        next_interval = update_inspection_interval(
            proposal.current_interval,
            verdict,
            i_base=config.i_base,
            delta_step=config.delta_step,
            i_max=config.i_max,
        )
    else:
        next_interval = max(config.i_base, min(config.i_max, proposal.current_interval))

    action_executed = 0 if verdict == InterventionVerdict.REPLACEMENT else 1
    seal = _compute_cadence_seal(
        {
            "run_id": proposal.run_id,
            "step_index": proposal.step_index,
            "verdict": verdict.value,
            "category": category.value,
            "next_interval": next_interval,
            "action_executed": action_executed,
        }
    )
    verdict_id = f"CDV-{hashlib.sha256((proposal.proposal_id + seal).encode('utf-8')).hexdigest()[:16]}"
    return TwoTierVerdict(
        verdict_id=verdict_id,
        run_id=proposal.run_id,
        step_index=proposal.step_index,
        inspection_triggered=should_inspect,
        verdict=verdict,
        category=category,
        action_executed=action_executed,
        guidance_note=guidance,
        next_interval=next_interval,
        state=state,
        rollback_triggered=False,
        rollback_target_epoch=None,
        cadence_seal_sha256=seal,
    )


__all__ = [
    "CADENCE_MANIFEST_HASH",
    "CADENCE_TRANSITIONS",
    "MAX_CADENCE_INTERVAL",
    "MAX_DELTA_STEP",
    "MAX_I_BASE",
    "MIN_CADENCE_INTERVAL",
    "PROXY_CONTEXT_TOKEN_CAP",
    "PROXY_MAX_TOKENS_CAP",
    "PROXY_THINKING_BUDGET_CAP",
    "TERMINAL_CADENCE_STATES",
    "CadenceEvent",
    "CadenceRunEnvelope",
    "CadenceState",
    "CadenceTelemetrySignals",
    "ErrorClass",
    "InterventionVerdict",
    "MisbehaviorCategory",
    "ScaffoldType",
    "SchedulerConfig",
    "SchedulerStateSnapshot",
    "TokenLeverageTelemetry",
    "TrajectoryStepProposal",
    "TwoTierVerdict",
    "cadence_transition",
    "compute_token_leverage",
    "evaluate_deterministic_cadence",
    "extract_deterministic_cadence_signals",
    "should_trigger_inspection",
    "update_inspection_interval",
    "validate_scaffold_type",
]
