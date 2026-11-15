# manifest_hash: b77d4295c196c37e848903d930d8d1a358fc9178b4dca90ba40fd28db264f37a
"""
SARA Causal Multi-Step Provenance & Monotonic Epoch Freshness Engine
====================================================================
Wave 2 Block E.1 (Appendix H):
  - #31 AgentTracer Intention-Alignment Causal Provenance (corrected multi-hop
    ALIGNED + MISALIGNED backward BFS, fail-closed max_chain_depth truncation flag,
    mutually-exclusive 3-class classification law).
  - #28 Generic Monotonic Epoch Freshness micro-kernel (scope_id, epoch_k > last_consumed_k),
    strictly decoupled from domain-specific demo fields.
"""
from __future__ import annotations

from collections import deque
from enum import Enum
import hashlib
import json
from typing import Dict, FrozenSet, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PROVENANCE_MANIFEST_HASH: str = "b77d4295c196c37e848903d930d8d1a358fc9178b4dca90ba40fd28db264f37a"

MIN_CHAIN_DEPTH: int = 1
DEFAULT_MAX_CHAIN_DEPTH: int = 32
MAX_CHAIN_DEPTH: int = 64
MAX_SESSION_GRAPH_EDGES: int = 10000
MAX_EPOCH_K: int = 2147483647
PROVENANCE_HOT_PATH_BUDGET_MS: float = 2.0

PROVENANCE_ID_PATTERN = r"^[A-Za-z0-9_.:-]{4,64}$"
SHA256_HEX_PATTERN = r"^[a-f0-9]{64}$"
EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class ProvenanceState(str, Enum):
    """Deterministic finite-state machine lifecycle states (Appendix H)."""

    IDLE = "IDLE"
    PRECHECK_VALIDATED = "PRECHECK_VALIDATED"
    GRAPH_RECORDING = "GRAPH_RECORDING"
    PROVENANCE_TRACED = "PROVENANCE_TRACED"
    CLEAN_VERIFIED = "CLEAN_VERIFIED"
    DRIFT_LOGGED = "DRIFT_LOGGED"
    QUARANTINED_IPI = "QUARANTINED_IPI"
    QUARANTINED_LAUNDERING = "QUARANTINED_LAUNDERING"
    REJECTED_STALE_EPOCH = "REJECTED_STALE_EPOCH"


TERMINAL_PROVENANCE_STATES: frozenset[ProvenanceState] = frozenset(
    {
        ProvenanceState.CLEAN_VERIFIED,
        ProvenanceState.DRIFT_LOGGED,
        ProvenanceState.QUARANTINED_IPI,
        ProvenanceState.QUARANTINED_LAUNDERING,
        ProvenanceState.REJECTED_STALE_EPOCH,
    }
)


class ProvenanceEvent(str, Enum):
    """Deterministic FSM transition events for causal provenance & epoch freshness."""

    INIT_SCOPE = "INIT_SCOPE"
    EPOCH_STALE_OR_REPLAY = "EPOCH_STALE_OR_REPLAY"
    CANARY_OVERLAP_OR_POC1_INERT = "CANARY_OVERLAP_OR_POC1_INERT"
    READONLY_CAPABILITY_MISMATCH = "READONLY_CAPABILITY_MISMATCH"
    EPOCH_FRESH_AND_CONTAINED = "EPOCH_FRESH_AND_CONTAINED"
    TOOL_CALL_RECORDED = "TOOL_CALL_RECORDED"
    VERIFY_CLEAN_BENIGN = "VERIFY_CLEAN_BENIGN"
    VERIFY_BENIGN_DRIFT = "VERIFY_BENIGN_DRIFT"
    DETECT_IPI_OR_DEPTH_TRUNCATED = "DETECT_IPI_OR_DEPTH_TRUNCATED"


PROVENANCE_TRANSITIONS: Dict[Tuple[ProvenanceState, ProvenanceEvent], ProvenanceState] = {
    (ProvenanceState.IDLE, ProvenanceEvent.INIT_SCOPE): ProvenanceState.PRECHECK_VALIDATED,
    (ProvenanceState.PRECHECK_VALIDATED, ProvenanceEvent.EPOCH_STALE_OR_REPLAY): ProvenanceState.REJECTED_STALE_EPOCH,
    (ProvenanceState.PRECHECK_VALIDATED, ProvenanceEvent.CANARY_OVERLAP_OR_POC1_INERT): ProvenanceState.QUARANTINED_LAUNDERING,
    (ProvenanceState.PRECHECK_VALIDATED, ProvenanceEvent.READONLY_CAPABILITY_MISMATCH): ProvenanceState.QUARANTINED_LAUNDERING,
    (ProvenanceState.PRECHECK_VALIDATED, ProvenanceEvent.EPOCH_FRESH_AND_CONTAINED): ProvenanceState.GRAPH_RECORDING,
    (ProvenanceState.GRAPH_RECORDING, ProvenanceEvent.TOOL_CALL_RECORDED): ProvenanceState.PROVENANCE_TRACED,
    (ProvenanceState.PROVENANCE_TRACED, ProvenanceEvent.VERIFY_CLEAN_BENIGN): ProvenanceState.CLEAN_VERIFIED,
    (ProvenanceState.PROVENANCE_TRACED, ProvenanceEvent.VERIFY_BENIGN_DRIFT): ProvenanceState.DRIFT_LOGGED,
    (ProvenanceState.PROVENANCE_TRACED, ProvenanceEvent.DETECT_IPI_OR_DEPTH_TRUNCATED): ProvenanceState.QUARANTINED_IPI,
}


def provenance_transition(state: ProvenanceState, event: ProvenanceEvent) -> ProvenanceState:
    """Total deterministic FSM delta(S, E); post-terminal transitions raise ValueError."""
    if not isinstance(state, ProvenanceState) or not isinstance(event, ProvenanceEvent):
        raise ValueError("Invalid ProvenanceState or ProvenanceEvent")
    if state in TERMINAL_PROVENANCE_STATES:
        raise ValueError(f"Terminal state {state.value} is immutable")
    key = (state, event)
    if key not in PROVENANCE_TRANSITIONS:
        raise ValueError(f"Illegal FSM transition: delta({state.value}, {event.value})")
    return PROVENANCE_TRANSITIONS[key]


class AlignmentStatus(str, Enum):
    """Per-edge action-target-checkpoint frame alignment status (#31)."""

    ALIGNED = "ALIGNED"
    MISALIGNED = "MISALIGNED"


class PredicateState(str, Enum):
    """UaScope predicate verification status for (Action, Target, Checkpoint)."""

    SATISFIED = "SATISFIED"
    VIOLATED = "VIOLATED"


class ProvenanceClassification(str, Enum):
    """Mutually exclusive causal IPI provenance classification."""

    CLEAN_BENIGN = "CLEAN_BENIGN"
    BENIGN_AGENT_DRIFT = "BENIGN_AGENT_DRIFT"
    IPI_CONFIRMED = "IPI_CONFIRMED"


class ProvenanceErrorClass(str, Enum):
    """Four-class deterministic error taxonomy."""

    TRANSIENT = "TRANSIENT"
    DETERMINISTIC = "DETERMINISTIC"
    BUSINESS = "BUSINESS"
    SECURITY = "SECURITY"


def digest_payload_sha256(raw_payload: str) -> str:
    """Compute SHA-256 digest of a payload so raw tool outputs are never persisted."""
    if not isinstance(raw_payload, str):
        raise ValueError("raw_payload must be a string")
    return hashlib.sha256(raw_payload.encode("utf-8", errors="replace")).hexdigest()


def compute_provenance_attestation(
    *,
    trace_id: str,
    classification: ProvenanceClassification,
    provenance_path: Sequence[str],
    depth_truncated: bool,
    manifest_hash: str = PROVENANCE_MANIFEST_HASH,
) -> str:
    """Compute canonical SHA-256 seal binding provenance trace outcome and path."""
    payload = {
        "trace_id": trace_id,
        "classification": classification.value,
        "provenance_path": list(provenance_path),
        "depth_truncated": bool(depth_truncated),
        "manifest_hash": manifest_hash,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def compute_epoch_attestation(
    *,
    scope_id: str,
    epoch_k: int,
    last_consumed_k: int,
    allowed: bool,
    manifest_hash: str = PROVENANCE_MANIFEST_HASH,
) -> str:
    """Compute canonical SHA-256 digest over monotonic epoch verification verdict."""
    payload = {
        "scope_id": scope_id,
        "epoch_k": epoch_k,
        "last_consumed_k": last_consumed_k,
        "allowed": bool(allowed),
        "manifest_hash": manifest_hash,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class IntentExecGraphEdge(BaseModel):
    """Immutable directed execution/data-flow edge storing only SHA-256 payload digest."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    edge_id: str = Field(pattern=PROVENANCE_ID_PATTERN)
    src_node: str = Field(pattern=PROVENANCE_ID_PATTERN)
    dst_node: str = Field(pattern=PROVENANCE_ID_PATTERN)
    tool_name: str = Field(min_length=1, max_length=128)
    alignment_status: AlignmentStatus
    tool_succeeded: bool = True
    payload_sha256: str = Field(default=EMPTY_SHA256, pattern=SHA256_HEX_PATTERN)


class ProvenanceTraceResult(BaseModel):
    """Verified causal provenance receipt enforcing strict mutual-exclusion invariants."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    trace_id: str = Field(pattern=PROVENANCE_ID_PATTERN)
    session_id: str = Field(pattern=PROVENANCE_ID_PATTERN)
    sink_node: str = Field(pattern=PROVENANCE_ID_PATTERN)
    classification: ProvenanceClassification
    has_misaligned_sink_edge: bool
    reaches_external_root: bool
    depth_truncated: bool = False
    provenance_path: Tuple[str, ...] = Field(min_length=1)
    path_digest_sha256: str = Field(pattern=SHA256_HEX_PATTERN)
    terminal_state: ProvenanceState
    error_class: Optional[ProvenanceErrorClass] = None
    attestation_sha256: str = Field(pattern=SHA256_HEX_PATTERN)
    manifest_hash: str = Field(default=PROVENANCE_MANIFEST_HASH, pattern=SHA256_HEX_PATTERN)

    @model_validator(mode="after")
    def _enforce_mutual_exclusion(self) -> "ProvenanceTraceResult":
        if self.terminal_state not in TERMINAL_PROVENANCE_STATES:
            raise ValueError("ProvenanceTraceResult must record a terminal ProvenanceState")

        if self.classification is ProvenanceClassification.CLEAN_BENIGN:
            if (
                self.has_misaligned_sink_edge
                or self.reaches_external_root
                or self.depth_truncated
                or self.terminal_state is not ProvenanceState.CLEAN_VERIFIED
                or self.error_class is not None
            ):
                raise ValueError(
                    "CLEAN_BENIGN requires has_misaligned_sink_edge=False, reaches_external_root=False, "
                    "depth_truncated=False, terminal_state=CLEAN_VERIFIED, and error_class=None"
                )
        elif self.classification is ProvenanceClassification.BENIGN_AGENT_DRIFT:
            if (
                not self.has_misaligned_sink_edge
                or self.reaches_external_root
                or self.depth_truncated
                or self.terminal_state is not ProvenanceState.DRIFT_LOGGED
            ):
                raise ValueError(
                    "BENIGN_AGENT_DRIFT requires has_misaligned_sink_edge=True, reaches_external_root=False, "
                    "depth_truncated=False, and terminal_state=DRIFT_LOGGED"
                )
        elif self.classification is ProvenanceClassification.IPI_CONFIRMED:
            if not (self.depth_truncated or (self.has_misaligned_sink_edge and self.reaches_external_root)):
                raise ValueError(
                    "IPI_CONFIRMED requires depth_truncated=True or "
                    "(has_misaligned_sink_edge=True and reaches_external_root=True)"
                )
            if (
                self.terminal_state is not ProvenanceState.QUARANTINED_IPI
                or self.error_class is not ProvenanceErrorClass.SECURITY
            ):
                raise ValueError(
                    "IPI_CONFIRMED must route fail-closed to QUARANTINED_IPI with SECURITY error_class"
                )
        return self


class MonotonicEpochVerdict(BaseModel):
    """Generic monotonic epoch freshness verdict (#28 micro-kernel, zero domain lock-in)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scope_id: str = Field(pattern=PROVENANCE_ID_PATTERN)
    epoch_k: int = Field(ge=0, le=MAX_EPOCH_K)
    last_consumed_k: int = Field(ge=-1, le=MAX_EPOCH_K)
    allowed: bool
    next_consumed_k: int = Field(ge=-1, le=MAX_EPOCH_K)
    error_class: Optional[ProvenanceErrorClass] = None
    terminal_state: Optional[ProvenanceState] = None
    reason: str = Field(min_length=1, max_length=512)
    attestation_sha256: str = Field(pattern=SHA256_HEX_PATTERN)
    manifest_hash: str = Field(default=PROVENANCE_MANIFEST_HASH, pattern=SHA256_HEX_PATTERN)

    @model_validator(mode="after")
    def _validate_monotonic_law(self) -> "MonotonicEpochVerdict":
        if self.allowed:
            if self.epoch_k <= self.last_consumed_k or self.next_consumed_k != self.epoch_k:
                raise ValueError("Allowed epoch verdict requires epoch_k > last_consumed_k and next_consumed_k == epoch_k")
            if self.error_class is not None or self.terminal_state is ProvenanceState.REJECTED_STALE_EPOCH:
                raise ValueError("Allowed epoch verdict cannot carry failure state")
        else:
            if self.next_consumed_k != self.last_consumed_k:
                raise ValueError("Rejected epoch verdict shall never advance next_consumed_k")
            if self.terminal_state is not ProvenanceState.REJECTED_STALE_EPOCH or self.error_class is not ProvenanceErrorClass.SECURITY:
                raise ValueError("Rejected epoch verdict must route to REJECTED_STALE_EPOCH with SECURITY error_class")
        return self


def evaluate_frame_alignment(
    p_action: PredicateState,
    p_target: PredicateState,
    p_checkpoint: PredicateState,
) -> AlignmentStatus:
    """Evaluate UaScope task-frame alignment across Action, Target, and Checkpoint."""
    if PredicateState.VIOLATED in (p_action, p_target, p_checkpoint):
        return AlignmentStatus.MISALIGNED
    return AlignmentStatus.ALIGNED


def evaluate_relation_alignment(frame_verdicts: Sequence[AlignmentStatus]) -> AlignmentStatus:
    """A tool relation is ALIGNED iff at least one candidate frame verdict is ALIGNED."""
    if not frame_verdicts:
        raise ValueError("At least one candidate frame verdict is required")
    return AlignmentStatus.ALIGNED if AlignmentStatus.ALIGNED in frame_verdicts else AlignmentStatus.MISALIGNED


def prune_graph_edges(edges: Sequence[IntentExecGraphEdge]) -> Tuple[IntentExecGraphEdge, ...]:
    """Level-2 Graph-Scope Pruning: discard failed calls and enforce bounded edge count."""
    if len(edges) > MAX_SESSION_GRAPH_EDGES:
        raise ValueError(
            f"Session edge count {len(edges)} exceeds bounded maximum {MAX_SESSION_GRAPH_EDGES}"
        )
    return tuple(edge for edge in edges if edge.tool_succeeded)


def trace_ipi_provenance(
    *,
    sink_node: str,
    edges: Sequence[IntentExecGraphEdge],
    external_nodes: FrozenSet[str],
    max_depth: int = DEFAULT_MAX_CHAIN_DEPTH,
    trace_id: Optional[str] = None,
    session_id: str = "SES-provenance",
) -> ProvenanceTraceResult:
    """
    Level-3 multi-hop causal provenance backward BFS (#31 corrected):
      - Traverses ALL active data-flow edges (both ALIGNED and MISALIGNED).
      - Confirms IPI_CONFIRMED only when an external untrusted source reaches sink_node
        via a path containing >= 1 MISALIGNED transition.
      - Enforces fail-closed depth_truncated=True whenever active ancestry continues past max_depth.
    """
    if isinstance(max_depth, bool) or not isinstance(max_depth, int) or not (MIN_CHAIN_DEPTH <= max_depth <= MAX_CHAIN_DEPTH):
        raise ValueError(f"max_depth must be an integer in [{MIN_CHAIN_DEPTH}, {MAX_CHAIN_DEPTH}]")

    pruned = prune_graph_edges(edges)

    rev_adj: Dict[str, list[IntentExecGraphEdge]] = {}
    for edge in pruned:
        rev_adj.setdefault(edge.dst_node, []).append(edge)

    resolved_trace_id = trace_id or f"TRC-{digest_payload_sha256(f'{session_id}:{sink_node}:{len(pruned)}')[:16]}"
    path_hash = lambda p: digest_payload_sha256("->".join(p))

    # BFS state tracks (current_node, has_seen_misaligned_edge, path_from_cur_to_sink)
    visited: set[Tuple[str, bool]] = {(sink_node, False)}
    q: deque[Tuple[str, bool, Tuple[str, ...]]] = deque([(sink_node, False, (sink_node,))])

    saw_any_misaligned_in_subgraph = False
    depth_truncated = False

    while q:
        curr, seen_misaligned, path = q.popleft()
        hop_count = len(path) - 1
        incoming = rev_adj.get(curr, ())
        if hop_count >= max_depth:
            if incoming:
                depth_truncated = True
            continue

        for edge in incoming:
            prev_node = edge.src_node
            next_seen_mis = seen_misaligned or (edge.alignment_status is AlignmentStatus.MISALIGNED)
            if edge.alignment_status is AlignmentStatus.MISALIGNED:
                saw_any_misaligned_in_subgraph = True
            new_path = (prev_node,) + path

            if prev_node in external_nodes and next_seen_mis:
                return ProvenanceTraceResult(
                    trace_id=resolved_trace_id,
                    session_id=session_id,
                    sink_node=sink_node,
                    classification=ProvenanceClassification.IPI_CONFIRMED,
                    has_misaligned_sink_edge=True,
                    reaches_external_root=True,
                    depth_truncated=False,
                    provenance_path=new_path,
                    path_digest_sha256=path_hash(new_path),
                    terminal_state=ProvenanceState.QUARANTINED_IPI,
                    error_class=ProvenanceErrorClass.SECURITY,
                    attestation_sha256=compute_provenance_attestation(
                        trace_id=resolved_trace_id,
                        classification=ProvenanceClassification.IPI_CONFIRMED,
                        provenance_path=new_path,
                        depth_truncated=False,
                    ),
                )

            state_key = (prev_node, next_seen_mis)
            if state_key not in visited:
                visited.add(state_key)
                q.append((prev_node, next_seen_mis, new_path))

    if depth_truncated:
        return ProvenanceTraceResult(
            trace_id=resolved_trace_id,
            session_id=session_id,
            sink_node=sink_node,
            classification=ProvenanceClassification.IPI_CONFIRMED,
            has_misaligned_sink_edge=saw_any_misaligned_in_subgraph,
            reaches_external_root=False,
            depth_truncated=True,
            provenance_path=(sink_node,),
            path_digest_sha256=path_hash((sink_node,)),
            terminal_state=ProvenanceState.QUARANTINED_IPI,
            error_class=ProvenanceErrorClass.SECURITY,
            attestation_sha256=compute_provenance_attestation(
                trace_id=resolved_trace_id,
                classification=ProvenanceClassification.IPI_CONFIRMED,
                provenance_path=(sink_node,),
                depth_truncated=True,
            ),
        )

    if saw_any_misaligned_in_subgraph:
        return ProvenanceTraceResult(
            trace_id=resolved_trace_id,
            session_id=session_id,
            sink_node=sink_node,
            classification=ProvenanceClassification.BENIGN_AGENT_DRIFT,
            has_misaligned_sink_edge=True,
            reaches_external_root=False,
            depth_truncated=False,
            provenance_path=(sink_node,),
            path_digest_sha256=path_hash((sink_node,)),
            terminal_state=ProvenanceState.DRIFT_LOGGED,
            error_class=ProvenanceErrorClass.BUSINESS,
            attestation_sha256=compute_provenance_attestation(
                trace_id=resolved_trace_id,
                classification=ProvenanceClassification.BENIGN_AGENT_DRIFT,
                provenance_path=(sink_node,),
                depth_truncated=False,
            ),
        )

    return ProvenanceTraceResult(
        trace_id=resolved_trace_id,
        session_id=session_id,
        sink_node=sink_node,
        classification=ProvenanceClassification.CLEAN_BENIGN,
        has_misaligned_sink_edge=False,
        reaches_external_root=False,
        depth_truncated=False,
        provenance_path=(sink_node,),
        path_digest_sha256=path_hash((sink_node,)),
        terminal_state=ProvenanceState.CLEAN_VERIFIED,
        error_class=None,
        attestation_sha256=compute_provenance_attestation(
            trace_id=resolved_trace_id,
            classification=ProvenanceClassification.CLEAN_BENIGN,
            provenance_path=(sink_node,),
            depth_truncated=False,
        ),
    )


def evaluate_monotonic_epoch(
    *,
    scope_id: str,
    epoch_k: int,
    last_consumed_k: int = -1,
) -> MonotonicEpochVerdict:
    """Validate strictly increasing epoch progression k > last_consumed_k (#28 micro-kernel)."""
    if isinstance(epoch_k, bool) or not isinstance(epoch_k, int) or not (0 <= epoch_k <= MAX_EPOCH_K):
        raise ValueError(f"epoch_k must be integer in [0, {MAX_EPOCH_K}]")
    if isinstance(last_consumed_k, bool) or not isinstance(last_consumed_k, int) or not (-1 <= last_consumed_k <= MAX_EPOCH_K):
        raise ValueError(f"last_consumed_k must be integer in [-1, {MAX_EPOCH_K}]")

    allowed = epoch_k > last_consumed_k
    attestation = compute_epoch_attestation(
        scope_id=scope_id,
        epoch_k=epoch_k,
        last_consumed_k=last_consumed_k,
        allowed=allowed,
    )
    if allowed:
        return MonotonicEpochVerdict(
            scope_id=scope_id,
            epoch_k=epoch_k,
            last_consumed_k=last_consumed_k,
            allowed=True,
            next_consumed_k=epoch_k,
            error_class=None,
            terminal_state=ProvenanceState.PRECHECK_VALIDATED,
            reason=f"Monotonic epoch {epoch_k} > {last_consumed_k} accepted for scope '{scope_id}'",
            attestation_sha256=attestation,
        )
    return MonotonicEpochVerdict(
        scope_id=scope_id,
        epoch_k=epoch_k,
        last_consumed_k=last_consumed_k,
        allowed=False,
        next_consumed_k=last_consumed_k,
        error_class=ProvenanceErrorClass.SECURITY,
        terminal_state=ProvenanceState.REJECTED_STALE_EPOCH,
        reason=f"STALE_EPOCH_REPLAY: epoch_k={epoch_k} <= last_consumed_k={last_consumed_k} for scope '{scope_node_safe(scope_id)}'",
        attestation_sha256=attestation,
    )


def scope_node_safe(scope_id: str) -> str:
    """Bounded display helper for audit reason formatting."""
    return str(scope_id)[:64]


__all__ = [
    "DEFAULT_MAX_CHAIN_DEPTH",
    "EMPTY_SHA256",
    "MAX_CHAIN_DEPTH",
    "MAX_EPOCH_K",
    "MAX_SESSION_GRAPH_EDGES",
    "MIN_CHAIN_DEPTH",
    "PROVENANCE_HOT_PATH_BUDGET_MS",
    "PROVENANCE_ID_PATTERN",
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
]
