# manifest_hash: 862e0dc20133fe81f2ce12812b86d74068db80cce8566a3b71d2d406db72c549
# manifest_hash_wave2d2: 34ae93e3f71bcaab59019e9e0139a4b24b69b82c2005b25e5049329f84b1aa2c
"""ctxfw.budget -- TokenCast Budgeter vendored blueprint and sovereign engine (milestone 4.0-M2).

CTXFW Axiomatic Gateway (milestone M2): status VERIFIED | ACI 1.0000
manifest_hash: 862e0dc20133fe81f2ce12812b86d74068db80cce8566a3b71d2d406db72c549
manifest_hash_wave2d2: 34ae93e3f71bcaab59019e9e0139a4b24b69b82c2005b25e5049329f84b1aa2c
Sealed blueprint manifest_hash (TokenCast SIG-947678205487bc66, VERIFIED, ACI 1.0000):
    7b7ef06dfc91c02c73bf8117efd362ffecd01cffdb9d0e5a8700be01c874bdae

Vendored, byte-for-byte, from the sealed blueprint (never edited here):
    contracts.py             <- specs/2_pydantic_contracts.py
    schema.sql               <- specs/3_schema_ddl.sql
    blueprint_manifest.json  <- blueprint_manifest.json
``.gitattributes`` pins them as ``-text`` and ``tests/test_tokencast_vendor.py`` re-checks their SHA-256
against the sealed manifest (gate G9). Any contract change requires a new sealed blueprint.

Implemented engines:
    forecaster.py  <- TokenCastForecaster, predict_token_trajectory
    breaker.py     <- CircuitBreaker
    store.py       <- TokenCastStore

Exported contracts, engines and types:
    SessionTokenBudgetDTO (aliased as TokenBudget)
    TokenTrajectoryForecastDTO (aliased as CostProjection)
    BreakerState (aliased as CircuitBreakerState)
    BreakerEvent (aliased as CircuitBreakerEvent)
    TokenCastForecaster, predict_token_trajectory
    CircuitBreaker
    TokenCastStore
    TurnObservationTelemetryDTO
    BudgetEnforcementDecisionDTO
    DecisionKind, FailureClass, transition, estimate_cost_usd, etc.

This package imports nothing heavy at import time (lazy): pydantic models and engines
load only upon attribute access or direct submodule import.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

__all__ = [
    "CONTRACTS_PATH",
    "CADENCE_SCHEMA_PATH",
    "MANIFEST_PATH",
    "PACKAGE_DIR",
    "SCHEMA_PATH",
    "load_cadence_schema_sql",
    "load_manifest",
    "load_schema_sql",
    # Engines:
    "TokenCastForecaster",
    "predict_token_trajectory",
    "CircuitBreaker",
    "TokenCastStore",
    "CadenceStore",
    # Cadence Strategic Agent Guidance (Wave 2 D.2 :: #19):
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
    # Architecture directive aliases:
    "TokenBudget",
    "CostProjection",
    "CircuitBreakerState",
    "CircuitBreakerEvent",
    # Canonical vendored contracts and types:
    "SessionTokenBudgetDTO",
    "TurnObservationTelemetryDTO",
    "TokenTrajectoryForecastDTO",
    "BudgetEnforcementDecisionDTO",
    "DecisionKind",
    "FailureClass",
    "BreakerState",
    "BreakerEvent",
    "TokenCastBaseDTO",
    "TERMINAL_STATES",
    "TRANSITION_TABLE",
    "FAILURE_ROUTING",
    "FAILURE_DISPOSITION",
    "transition",
    "ceil_div",
    "ceil_isqrt",
    "estimate_cost_usd",
    "derive_ledger_id",
]

PACKAGE_DIR = Path(__file__).resolve().parent
CONTRACTS_PATH = PACKAGE_DIR / "contracts.py"
SCHEMA_PATH = PACKAGE_DIR / "schema.sql"
CADENCE_SCHEMA_PATH = PACKAGE_DIR / "cadence_schema.sql"
MANIFEST_PATH = PACKAGE_DIR / "blueprint_manifest.json"

_CADENCE_EXPORTS = frozenset(
    {
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
    }
)

_ALIASES: dict[str, str] = {
    "TokenBudget": "SessionTokenBudgetDTO",
    "CostProjection": "TokenTrajectoryForecastDTO",
    "CircuitBreakerState": "BreakerState",
    "CircuitBreakerEvent": "BreakerEvent",
}


def load_schema_sql() -> str:
    """Return the sealed DDL text exactly as vendored (UTF-8)."""
    return SCHEMA_PATH.read_text(encoding="utf-8")


def load_cadence_schema_sql() -> str:
    """Return the Wave 2 D.2 Cadence SQLite WAL DDL text (UTF-8)."""
    return CADENCE_SCHEMA_PATH.read_text(encoding="utf-8")


def load_manifest() -> dict[str, Any]:
    """Return the sealed blueprint manifest as a dictionary."""
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def __getattr__(name: str) -> Any:
    if name in {"TokenCastForecaster", "predict_token_trajectory"}:
        from . import forecaster

        return getattr(forecaster, name)
    if name == "CircuitBreaker":
        from . import breaker

        return getattr(breaker, name)
    if name == "TokenCastStore":
        from . import store

        return getattr(store, name)
    if name == "CadenceStore":
        from . import cadence_store

        return getattr(cadence_store, name)
    if name in _CADENCE_EXPORTS:
        from . import cadence

        return getattr(cadence, name)
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
    from .breaker import CircuitBreaker
    from .contracts import (
        FAILURE_DISPOSITION,
        FAILURE_ROUTING,
        TERMINAL_STATES,
        TRANSITION_TABLE,
        BreakerEvent,
        BreakerState,
        BudgetEnforcementDecisionDTO,
        DecisionKind,
        FailureClass,
        SessionTokenBudgetDTO,
        TokenCastBaseDTO,
        TokenTrajectoryForecastDTO,
        TurnObservationTelemetryDTO,
        ceil_div,
        ceil_isqrt,
        derive_ledger_id,
        estimate_cost_usd,
        transition,
    )
    from .cadence import (
        CADENCE_MANIFEST_HASH,
        CADENCE_TRANSITIONS,
        MAX_CADENCE_INTERVAL,
        MAX_DELTA_STEP,
        MAX_I_BASE,
        MIN_CADENCE_INTERVAL,
        PROXY_CONTEXT_TOKEN_CAP,
        PROXY_MAX_TOKENS_CAP,
        PROXY_THINKING_BUDGET_CAP,
        TERMINAL_CADENCE_STATES,
        CadenceEvent,
        CadenceRunEnvelope,
        CadenceState,
        CadenceTelemetrySignals,
        ErrorClass,
        InterventionVerdict,
        MisbehaviorCategory,
        ScaffoldType,
        SchedulerConfig,
        SchedulerStateSnapshot,
        TokenLeverageTelemetry,
        TrajectoryStepProposal,
        TwoTierVerdict,
        cadence_transition,
        compute_token_leverage,
        evaluate_deterministic_cadence,
        extract_deterministic_cadence_signals,
        should_trigger_inspection,
        update_inspection_interval,
        validate_scaffold_type,
    )
    from .cadence_store import CadenceStore
    from .forecaster import TokenCastForecaster, predict_token_trajectory
    from .store import TokenCastStore

    TokenBudget = SessionTokenBudgetDTO
    CostProjection = TokenTrajectoryForecastDTO
    CircuitBreakerState = BreakerState
    CircuitBreakerEvent = BreakerEvent
