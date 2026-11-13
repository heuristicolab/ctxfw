"""
src/ctxfw/tracelite/contracts.py — Axiomatic Contracts & FSM for TraceLite Optical Trace Reducer
manifest_hash: 00743e30ed7cee52140a1538a8622aeccb12a6c524adc80d875ab067bd39f762
blueprint_manifest_hash: 6a95bb7fd01158ac75d67055df0c328d56433a44625351610307d5ef6b68d0cf
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

TRACELITE_MANIFEST_HASH = "6a95bb7fd01158ac75d67055df0c328d56433a44625351610307d5ef6b68d0cf"
WAVE1C_MANIFEST_HASH = "00743e30ed7cee52140a1538a8622aeccb12a6c524adc80d875ab067bd39f762"

OPTIMAL_RECENT_WINDOW_W = 3
OPTIMAL_OPTICAL_RATIO_K = 4.0
MAX_OPTICAL_RATIO_K = 8.0
MIN_CHAR_SIMILARITY_FLOOR = 0.90
STRICT_CHAR_SIMILARITY = 0.95
BASE_CANVAS_PX = 2240
MIN_CANVAS_PX = 224
DEFAULT_PATCH_SIZE_PX = 14


class FailureErrorClass(str, Enum):
    TRANSIENT = "TRANSIENT"
    DETERMINISTIC = "DETERMINISTIC"
    BUSINESS = "BUSINESS"
    SECURITY = "SECURITY"


class TraceLifecycleState(str, Enum):
    INGESTED = "INGESTED"
    DEDUPLICATED = "DEDUPLICATED"
    PHASE_CLEANED = "PHASE_CLEANED"
    OPTICALLY_RENDERED = "OPTICALLY_RENDERED"
    WINDOW_ASSEMBLED = "WINDOW_ASSEMBLED"
    QUARANTINED = "QUARANTINED"


class TraceLifecycleEvent(str, Enum):
    DEDUPLICATE_OVERLAPS = "DEDUPLICATE_OVERLAPS"
    APPLY_EDIT_CLEANUP = "APPLY_EDIT_CLEANUP"
    SKIP_EDIT_CLEANUP = "SKIP_EDIT_CLEANUP"
    RENDER_OPTICAL = "RENDER_OPTICAL"
    ASSEMBLE_WINDOW = "ASSEMBLE_WINDOW"
    QUARANTINE = "QUARANTINE"
    REMEDIATE = "REMEDIATE"


TERMINAL_TRACE_STATES = frozenset({
    TraceLifecycleState.WINDOW_ASSEMBLED,
    TraceLifecycleState.QUARANTINED,
})

TRANSITION_TABLE: dict[tuple[TraceLifecycleState, TraceLifecycleEvent], TraceLifecycleState] = {
    (TraceLifecycleState.INGESTED, TraceLifecycleEvent.DEDUPLICATE_OVERLAPS): TraceLifecycleState.DEDUPLICATED,
    (TraceLifecycleState.INGESTED, TraceLifecycleEvent.QUARANTINE): TraceLifecycleState.QUARANTINED,
    (TraceLifecycleState.DEDUPLICATED, TraceLifecycleEvent.APPLY_EDIT_CLEANUP): TraceLifecycleState.PHASE_CLEANED,
    (TraceLifecycleState.DEDUPLICATED, TraceLifecycleEvent.SKIP_EDIT_CLEANUP): TraceLifecycleState.PHASE_CLEANED,
    (TraceLifecycleState.DEDUPLICATED, TraceLifecycleEvent.QUARANTINE): TraceLifecycleState.QUARANTINED,
    (TraceLifecycleState.PHASE_CLEANED, TraceLifecycleEvent.RENDER_OPTICAL): TraceLifecycleState.OPTICALLY_RENDERED,
    (TraceLifecycleState.PHASE_CLEANED, TraceLifecycleEvent.QUARANTINE): TraceLifecycleState.QUARANTINED,
    (TraceLifecycleState.OPTICALLY_RENDERED, TraceLifecycleEvent.ASSEMBLE_WINDOW): TraceLifecycleState.WINDOW_ASSEMBLED,
    (TraceLifecycleState.OPTICALLY_RENDERED, TraceLifecycleEvent.QUARANTINE): TraceLifecycleState.QUARANTINED,
    (TraceLifecycleState.QUARANTINED, TraceLifecycleEvent.REMEDIATE): TraceLifecycleState.INGESTED,
}


def transition_trace_state(
    current: TraceLifecycleState,
    event: TraceLifecycleEvent,
) -> TraceLifecycleState:
    """Execute deterministic state transition delta(S, E) for TraceLite."""
    key = (current, event)
    if key not in TRANSITION_TABLE:
        raise ValueError(
            f"Illegal TraceLite FSM transition: current={current.value}, event={event.value}"
        )
    return TRANSITION_TABLE[key]


_STRICT_CONFIG = ConfigDict(
    frozen=True,
    extra="forbid",
    str_strip_whitespace=True,
    validate_default=True,
    allow_inf_nan=False,
)


class TraceReducerPolicy(BaseModel):
    model_config = _STRICT_CONFIG

    policy_id: str = Field(default="tracelite-default-v1", pattern=r"^[A-Za-z0-9_.:-]{1,64}$")
    aux_llm_allowed: bool = Field(default=False)
    training_free_enforced: bool = Field(default=True)
    recent_window_w: int = Field(default=OPTIMAL_RECENT_WINDOW_W, ge=1, le=10)
    optical_ratio_k: float = Field(default=OPTIMAL_OPTICAL_RATIO_K, ge=1.0, le=MAX_OPTICAL_RATIO_K)
    min_char_similarity: float = Field(
        default=MIN_CHAR_SIMILARITY_FLOOR,
        ge=MIN_CHAR_SIMILARITY_FLOOR,
        le=1.0,
    )
    max_canvas_px: int = Field(default=BASE_CANVAS_PX, ge=MIN_CANVAS_PX, le=BASE_CANVAS_PX)
    patch_size_px: int = Field(default=DEFAULT_PATCH_SIZE_PX, ge=8, le=32)
    strip_pre_edit_observations_only: bool = Field(default=True)
    preserve_actions_strictly: bool = Field(default=True)
    preserve_newest_observation_strictly: bool = Field(default=True)
    strict_fidelity_mode: bool = Field(default=False)

    @model_validator(mode="before")
    @classmethod
    def _promote_strict_fidelity(cls, data: object) -> object:
        if isinstance(data, dict) and data.get("strict_fidelity_mode"):
            sim = data.get("min_char_similarity", MIN_CHAR_SIMILARITY_FLOOR)
            if float(sim) < STRICT_CHAR_SIMILARITY:
                copied = dict(data)
                copied["min_char_similarity"] = STRICT_CHAR_SIMILARITY
                return copied
        return data

    @model_validator(mode="after")
    def _enforce_negative_invariants(self) -> "TraceReducerPolicy":
        if self.aux_llm_allowed:
            raise ValueError("SECURITY invariant violation: aux_llm_allowed must never be True.")
        if not self.training_free_enforced:
            raise ValueError("SECURITY invariant violation: training_free_enforced must remain True.")
        if not self.strip_pre_edit_observations_only:
            raise ValueError("DETERMINISTIC invariant violation: edit cleanup only permitted pre-edit.")
        if not self.preserve_actions_strictly:
            raise ValueError("SECURITY invariant violation: action invocations a_i shall never be deleted.")
        if not self.preserve_newest_observation_strictly:
            raise ValueError("SECURITY invariant violation: newest observation O_s shall never be mutated.")
        return self


class AgentObservationStep(BaseModel):
    model_config = _STRICT_CONFIG

    step_index: int = Field(..., ge=0, le=100_000)
    action_invocation: str = Field(..., min_length=1, max_length=16_000)
    observation_text: str = Field(..., min_length=0, max_length=500_000)
    is_edit_action: bool = Field(default=False)
    target_resource: Optional[str] = Field(default=None, max_length=512)
    phase_id: int = Field(default=0, ge=0, le=10_000)
    raw_tokens: Optional[int] = Field(default=None, ge=0, le=2_000_000)
    message_index: Optional[int] = Field(default=None, ge=0, le=100_000)
    tool_call_id: Optional[str] = Field(default=None, max_length=128)


class OpticalRenderArtifact(BaseModel):
    model_config = _STRICT_CONFIG

    artifact_id: str = Field(..., pattern=r"^[a-f0-9]{16,64}$")
    step_index: int = Field(..., ge=0, le=100_000)
    source_sha256: str = Field(..., pattern=r"^[a-f0-9]{64}$")
    policy_hash: str = Field(..., pattern=r"^[a-f0-9]{16,64}$")
    canvas_width_px: int = Field(..., ge=MIN_CANVAS_PX, le=BASE_CANVAS_PX)
    canvas_height_px: int = Field(..., ge=MIN_CANVAS_PX, le=BASE_CANVAS_PX)
    patch_size_px: int = Field(..., ge=8, le=32)
    raw_text_tokens: int = Field(..., ge=1, le=2_000_000)
    optical_patch_tokens: int = Field(..., ge=1, le=2_000_000)
    effective_compression_k: float = Field(..., ge=1.0, le=MAX_OPTICAL_RATIO_K)
    char_similarity: float = Field(..., ge=0.0, le=1.0)
    rendered_digest: str = Field(..., pattern=r"^[a-f0-9]{64}$")
    compacted_payload: str = Field(..., min_length=1, max_length=200_000)
    mime_type: str = Field(
        default="application/vnd.ctxfw.optical-grid+text",
        min_length=1,
        max_length=128,
    )

    @model_validator(mode="after")
    def _validate_optical_bounds(self) -> "OpticalRenderArtifact":
        if self.optical_patch_tokens > self.raw_text_tokens:
            raise ValueError(
                "BUSINESS invariant violation: optical_patch_tokens must not exceed raw_text_tokens."
            )
        return self


class ReducedTrajectoryWindow(BaseModel):
    model_config = _STRICT_CONFIG

    reduction_id: str = Field(..., pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    trajectory_id: str = Field(..., pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    policy_id: str = Field(..., min_length=1, max_length=64)
    lifecycle_state: TraceLifecycleState
    total_steps: int = Field(..., ge=0, le=100_000)
    recent_window_w: int = Field(..., ge=1, le=10)
    steps: tuple[AgentObservationStep, ...] = Field(default=())
    optical_artifacts: tuple[OpticalRenderArtifact, ...] = Field(default=())
    deduplicated_lines_count: int = Field(default=0, ge=0)
    edit_cleaned_steps_count: int = Field(default=0, ge=0)
    raw_tokens_total: int = Field(default=0, ge=0)
    reduced_tokens_total: int = Field(default=0, ge=0)
    tokens_saved: int = Field(default=0, ge=0)
    compression_ratio: float = Field(default=1.0, ge=1.0)
    newest_step_preserved: bool = Field(default=True)
    actions_preserved: bool = Field(default=True)

    @model_validator(mode="after")
    def _validate_window_invariants(self) -> "ReducedTrajectoryWindow":
        if not self.actions_preserved:
            raise ValueError("SECURITY invariant violation: actions_preserved must never be False.")
        if not self.newest_step_preserved:
            raise ValueError("SECURITY invariant violation: newest_step_preserved must never be False.")
        if self.reduced_tokens_total > self.raw_tokens_total:
            raise ValueError(
                "BUSINESS invariant violation: reduced_tokens_total cannot exceed raw_tokens_total."
            )
        return self


class TraceQuarantineIncident(BaseModel):
    model_config = _STRICT_CONFIG

    incident_id: str = Field(..., pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    trajectory_id: str = Field(..., min_length=1, max_length=128)
    error_class: FailureErrorClass
    rule_code: str = Field(..., min_length=1, max_length=64)
    detail: str = Field(..., min_length=1, max_length=2000)
    step_index: Optional[int] = Field(default=None, ge=0, le=100_000)
    created_seq: int = Field(default=1, ge=1)


class TraceAuditTransition(BaseModel):
    model_config = _STRICT_CONFIG

    transition_id: str = Field(..., pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    trajectory_id: str = Field(..., min_length=1, max_length=128)
    from_state: TraceLifecycleState
    event: TraceLifecycleEvent
    to_state: TraceLifecycleState
    policy_id: str = Field(..., min_length=1, max_length=64)
    manifest_hash: str = Field(default=WAVE1C_MANIFEST_HASH, pattern=r"^[a-f0-9]{64}$")
    seq_no: int = Field(default=1, ge=1)
