"""
src/ctxfw/tracelite/__init__.py — TraceLite Optical Trace Reducer Package (Wave 1 Block C #12)
manifest_hash: 00743e30ed7cee52140a1538a8622aeccb12a6c524adc80d875ab067bd39f762
blueprint_manifest_hash: 6a95bb7fd01158ac75d67055df0c328d56433a44625351610307d5ef6b68d0cf
"""
from __future__ import annotations

from typing import Any

__all__ = [
    "TRACELITE_MANIFEST_HASH",
    "WAVE1C_MANIFEST_HASH",
    "OPTIMAL_RECENT_WINDOW_W",
    "OPTIMAL_OPTICAL_RATIO_K",
    "MAX_OPTICAL_RATIO_K",
    "MIN_CHAR_SIMILARITY_FLOOR",
    "STRICT_CHAR_SIMILARITY",
    "BASE_CANVAS_PX",
    "MIN_CANVAS_PX",
    "DEFAULT_PATCH_SIZE_PX",
    "FailureErrorClass",
    "TraceLifecycleState",
    "TraceLifecycleEvent",
    "TERMINAL_TRACE_STATES",
    "TRANSITION_TABLE",
    "transition_trace_state",
    "TraceReducerPolicy",
    "AgentObservationStep",
    "OpticalRenderArtifact",
    "ReducedTrajectoryWindow",
    "TraceQuarantineIncident",
    "TraceAuditTransition",
    "OpticalObservationRenderer",
    "CrossStepOverlapDeduplicator",
    "EditPhaseCleanupEngine",
    "TraceLiteReducer",
    "TraceLiteStore",
]

_CONTRACT_EXPORTS = frozenset({
    "TRACELITE_MANIFEST_HASH",
    "WAVE1C_MANIFEST_HASH",
    "OPTIMAL_RECENT_WINDOW_W",
    "OPTIMAL_OPTICAL_RATIO_K",
    "MAX_OPTICAL_RATIO_K",
    "MIN_CHAR_SIMILARITY_FLOOR",
    "STRICT_CHAR_SIMILARITY",
    "BASE_CANVAS_PX",
    "MIN_CANVAS_PX",
    "DEFAULT_PATCH_SIZE_PX",
    "FailureErrorClass",
    "TraceLifecycleState",
    "TraceLifecycleEvent",
    "TERMINAL_TRACE_STATES",
    "TRANSITION_TABLE",
    "transition_trace_state",
    "TraceReducerPolicy",
    "AgentObservationStep",
    "OpticalRenderArtifact",
    "ReducedTrajectoryWindow",
    "TraceQuarantineIncident",
    "TraceAuditTransition",
})

_REDUCER_EXPORTS = frozenset({
    "OpticalObservationRenderer",
    "CrossStepOverlapDeduplicator",
    "EditPhaseCleanupEngine",
    "TraceLiteReducer",
})

_STORE_EXPORTS = frozenset({
    "TraceLiteStore",
})


def __getattr__(name: str) -> Any:
    if name in _CONTRACT_EXPORTS:
        from . import contracts

        return getattr(contracts, name)
    if name in _REDUCER_EXPORTS:
        from . import reducer

        return getattr(reducer, name)
    if name in _STORE_EXPORTS:
        from . import store

        return getattr(store, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
