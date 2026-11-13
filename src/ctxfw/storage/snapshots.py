"""
src/ctxfw/storage/snapshots.py — Bounded Go-Explore Sandbox Snapshot Rollback & Cache Invalidation
manifest_hash: 00743e30ed7cee52140a1538a8622aeccb12a6c524adc80d875ab067bd39f762
blueprint_manifest_hash: 7fb2c154c3f3e904d0e70445120a150a7d8d59cd7349cf13316421ffc816fc55
"""
from __future__ import annotations

import itertools
import math
import sqlite3
import sys
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional, Sequence, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ctxfw.storage.cache import resolve_project_identity

SNAPSHOT_BLUEPRINT_MANIFEST_HASH = "7fb2c154c3f3e904d0e70445120a150a7d8d59cd7349cf13316421ffc816fc55"
WAVE1C_MANIFEST_HASH = "00743e30ed7cee52140a1538a8622aeccb12a6c524adc80d875ab067bd39f762"

DEFAULT_TOTAL_TOKEN_BUDGET = 1_000_000
MAX_TOTAL_TOKEN_BUDGET = 1_000_000
DEFAULT_MAX_CHILDREN_PER_ROOT = 2
MAX_CHILDREN_PER_ROOT = 4
DEFAULT_ATTRACTOR_FAIL_THRESHOLD = 3

_T = TypeVar("_T")


class FailureErrorClass(str, Enum):
    TRANSIENT = "TRANSIENT"
    DETERMINISTIC = "DETERMINISTIC"
    BUSINESS = "BUSINESS"
    SECURITY = "SECURITY"


class SnapshotLifecycleState(str, Enum):
    CREATED = "CREATED"
    CHECKPOINTED = "CHECKPOINTED"
    BRANCH_EXPANDED = "BRANCH_EXPANDED"
    ATTRACTOR_DETECTED = "ATTRACTOR_DETECTED"
    ROLLBACK_PENDING = "ROLLBACK_PENDING"
    RESTORED_INVALIDATED = "RESTORED_INVALIDATED"
    COMMITTED_TERMINAL = "COMMITTED_TERMINAL"
    QUARANTINED_TERMINAL = "QUARANTINED_TERMINAL"


class SnapshotLifecycleEvent(str, Enum):
    CAPTURE_CHECKPOINT = "CAPTURE_CHECKPOINT"
    SPAWN_CHILD_BRANCH = "SPAWN_CHILD_BRANCH"
    DETECT_ATTRACTOR = "DETECT_ATTRACTOR"
    REQUEST_ROLLBACK = "REQUEST_ROLLBACK"
    EXECUTE_ROLLBACK_AND_INVALIDATE = "EXECUTE_ROLLBACK_AND_INVALIDATE"
    RESUME_FROM_RESTORED = "RESUME_FROM_RESTORED"
    COMMIT_SOLUTION = "COMMIT_SOLUTION"
    ABORT_QUARANTINE = "ABORT_QUARANTINE"
    REMEDIATE_ATTRACTOR = "REMEDIATE_ATTRACTOR"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


class RestorationMode(str, Enum):
    FULL_SANDBOX_SNAPSHOT = "FULL_SANDBOX_SNAPSHOT"
    GIT_DIFF_REPLAY = "GIT_DIFF_REPLAY"
    QUARANTINED_NOOP = "QUARANTINED_NOOP"


class NonGitArtifactKind(str, Enum):
    SQLITE_DB = "SQLITE_DB"
    BACKGROUND_DAEMON = "BACKGROUND_DAEMON"
    MIGRATION_JOURNAL = "MIGRATION_JOURNAL"
    ENV_PACKAGE = "ENV_PACKAGE"


TERMINAL_STATES = frozenset({
    SnapshotLifecycleState.COMMITTED_TERMINAL,
    SnapshotLifecycleState.QUARANTINED_TERMINAL,
})

TRANSITION_TABLE: dict[tuple[SnapshotLifecycleState, SnapshotLifecycleEvent], SnapshotLifecycleState] = {
    (SnapshotLifecycleState.CREATED, SnapshotLifecycleEvent.CAPTURE_CHECKPOINT): SnapshotLifecycleState.CHECKPOINTED,
    (SnapshotLifecycleState.CHECKPOINTED, SnapshotLifecycleEvent.SPAWN_CHILD_BRANCH): SnapshotLifecycleState.BRANCH_EXPANDED,
    (SnapshotLifecycleState.CHECKPOINTED, SnapshotLifecycleEvent.DETECT_ATTRACTOR): SnapshotLifecycleState.ATTRACTOR_DETECTED,
    (SnapshotLifecycleState.CHECKPOINTED, SnapshotLifecycleEvent.REQUEST_ROLLBACK): SnapshotLifecycleState.ROLLBACK_PENDING,
    (SnapshotLifecycleState.CHECKPOINTED, SnapshotLifecycleEvent.COMMIT_SOLUTION): SnapshotLifecycleState.COMMITTED_TERMINAL,
    (SnapshotLifecycleState.CHECKPOINTED, SnapshotLifecycleEvent.ABORT_QUARANTINE): SnapshotLifecycleState.QUARANTINED_TERMINAL,
    (SnapshotLifecycleState.CHECKPOINTED, SnapshotLifecycleEvent.BUDGET_EXHAUSTED): SnapshotLifecycleState.QUARANTINED_TERMINAL,
    (SnapshotLifecycleState.BRANCH_EXPANDED, SnapshotLifecycleEvent.CAPTURE_CHECKPOINT): SnapshotLifecycleState.CHECKPOINTED,
    (SnapshotLifecycleState.BRANCH_EXPANDED, SnapshotLifecycleEvent.SPAWN_CHILD_BRANCH): SnapshotLifecycleState.BRANCH_EXPANDED,
    (SnapshotLifecycleState.BRANCH_EXPANDED, SnapshotLifecycleEvent.DETECT_ATTRACTOR): SnapshotLifecycleState.ATTRACTOR_DETECTED,
    (SnapshotLifecycleState.BRANCH_EXPANDED, SnapshotLifecycleEvent.REQUEST_ROLLBACK): SnapshotLifecycleState.ROLLBACK_PENDING,
    (SnapshotLifecycleState.BRANCH_EXPANDED, SnapshotLifecycleEvent.COMMIT_SOLUTION): SnapshotLifecycleState.COMMITTED_TERMINAL,
    (SnapshotLifecycleState.BRANCH_EXPANDED, SnapshotLifecycleEvent.ABORT_QUARANTINE): SnapshotLifecycleState.QUARANTINED_TERMINAL,
    (SnapshotLifecycleState.BRANCH_EXPANDED, SnapshotLifecycleEvent.BUDGET_EXHAUSTED): SnapshotLifecycleState.QUARANTINED_TERMINAL,
    (SnapshotLifecycleState.ATTRACTOR_DETECTED, SnapshotLifecycleEvent.REQUEST_ROLLBACK): SnapshotLifecycleState.ROLLBACK_PENDING,
    (SnapshotLifecycleState.ATTRACTOR_DETECTED, SnapshotLifecycleEvent.REMEDIATE_ATTRACTOR): SnapshotLifecycleState.CHECKPOINTED,
    (SnapshotLifecycleState.ATTRACTOR_DETECTED, SnapshotLifecycleEvent.ABORT_QUARANTINE): SnapshotLifecycleState.QUARANTINED_TERMINAL,
    (SnapshotLifecycleState.ATTRACTOR_DETECTED, SnapshotLifecycleEvent.BUDGET_EXHAUSTED): SnapshotLifecycleState.QUARANTINED_TERMINAL,
    (SnapshotLifecycleState.ROLLBACK_PENDING, SnapshotLifecycleEvent.EXECUTE_ROLLBACK_AND_INVALIDATE): SnapshotLifecycleState.RESTORED_INVALIDATED,
    (SnapshotLifecycleState.ROLLBACK_PENDING, SnapshotLifecycleEvent.ABORT_QUARANTINE): SnapshotLifecycleState.QUARANTINED_TERMINAL,
    (SnapshotLifecycleState.RESTORED_INVALIDATED, SnapshotLifecycleEvent.RESUME_FROM_RESTORED): SnapshotLifecycleState.CHECKPOINTED,
    (SnapshotLifecycleState.RESTORED_INVALIDATED, SnapshotLifecycleEvent.SPAWN_CHILD_BRANCH): SnapshotLifecycleState.BRANCH_EXPANDED,
    (SnapshotLifecycleState.RESTORED_INVALIDATED, SnapshotLifecycleEvent.REQUEST_ROLLBACK): SnapshotLifecycleState.ROLLBACK_PENDING,
    (SnapshotLifecycleState.RESTORED_INVALIDATED, SnapshotLifecycleEvent.COMMIT_SOLUTION): SnapshotLifecycleState.COMMITTED_TERMINAL,
    (SnapshotLifecycleState.RESTORED_INVALIDATED, SnapshotLifecycleEvent.ABORT_QUARANTINE): SnapshotLifecycleState.QUARANTINED_TERMINAL,
}


def transition(
    current: SnapshotLifecycleState,
    event: SnapshotLifecycleEvent,
) -> SnapshotLifecycleState:
    """Execute deterministic state transition delta(S, E) for SandboxSnapshotRollback."""
    if current in TERMINAL_STATES:
        raise ValueError(
            f"SECURITY invariant violation: terminal state {current.value} cannot transition on {event.value}"
        )
    key = (current, event)
    if key not in TRANSITION_TABLE:
        raise ValueError(
            f"DETERMINISTIC invariant violation: invalid transition {current.value} + {event.value}"
        )
    return TRANSITION_TABLE[key]


_STRICT_CONFIG = ConfigDict(
    frozen=True,
    extra="forbid",
    str_strip_whitespace=True,
    validate_default=True,
    allow_inf_nan=False,
)


class NonGitRuntimeArtifact(BaseModel):
    model_config = _STRICT_CONFIG

    artifact_id: str = Field(..., pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    kind: NonGitArtifactKind
    resource_path_or_pid: str = Field(..., min_length=1, max_length=512)
    pre_state_digest: str = Field(..., pattern=r"^[a-f0-9]{64}$")
    dirty_after_step: bool = Field(default=True)
    reversible_via_snapshot: bool = Field(default=True)


class SnapshotArchiveCell(BaseModel):
    model_config = _STRICT_CONFIG

    snapshot_id: str = Field(..., pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    run_id: str = Field(..., pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    project_root: str = Field(..., min_length=1, max_length=1024)
    parent_snapshot_id: Optional[str] = Field(default=None, pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    step_index: int = Field(..., ge=0, le=100_000)
    depth: int = Field(default=0, ge=0, le=128)
    git_commit_sha: Optional[str] = Field(default=None, pattern=r"^[a-f0-9]{7,64}$")
    working_tree_digest: str = Field(..., pattern=r"^[a-f0-9]{64}$")
    pass_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    failing_tests: int = Field(default=0, ge=0, le=100_000)
    visit_count: int = Field(default=1, ge=1, le=1_000_000)
    children_spawned: int = Field(default=0, ge=0, le=MAX_CHILDREN_PER_ROOT)
    max_children_per_root: int = Field(default=DEFAULT_MAX_CHILDREN_PER_ROOT, ge=1, le=MAX_CHILDREN_PER_ROOT)
    tokens_used_to_reach: int = Field(default=0, ge=0, le=MAX_TOTAL_TOKEN_BUDGET)
    handoff_tokens: int = Field(default=0, ge=0, le=MAX_TOTAL_TOKEN_BUDGET)
    non_git_artifacts: tuple[NonGitRuntimeArtifact, ...] = Field(default=())
    lifecycle_state: SnapshotLifecycleState = Field(default=SnapshotLifecycleState.CHECKPOINTED)
    rollback_epoch: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _enforce_fanout_bound(self) -> "SnapshotArchiveCell":
        if self.children_spawned > self.max_children_per_root:
            raise ValueError(
                f"BUSINESS invariant violation: children_spawned={self.children_spawned} "
                f"exceeds max_children_per_root={self.max_children_per_root}."
            )
        return self


class BranchBudgetLedger(BaseModel):
    model_config = _STRICT_CONFIG

    run_id: str = Field(..., pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    total_token_budget: int = Field(
        default=DEFAULT_TOTAL_TOKEN_BUDGET,
        ge=1,
        le=MAX_TOTAL_TOKEN_BUDGET,
    )
    tokens_spent: int = Field(default=0, ge=0, le=MAX_TOTAL_TOKEN_BUDGET)
    handoff_tokens_spent: int = Field(default=0, ge=0, le=MAX_TOTAL_TOKEN_BUDGET)
    active_branches: int = Field(default=1, ge=0, le=256)
    max_children_per_root: int = Field(default=DEFAULT_MAX_CHILDREN_PER_ROOT, ge=1, le=MAX_CHILDREN_PER_ROOT)

    @model_validator(mode="after")
    def _validate_total_spend(self) -> "BranchBudgetLedger":
        if self.tokens_spent + self.handoff_tokens_spent > self.total_token_budget:
            raise ValueError(
                "BUSINESS invariant violation: combined token spend exceeds total_token_budget."
            )
        return self

    @property
    def remaining_tokens(self) -> int:
        return max(0, self.total_token_budget - self.tokens_spent - self.handoff_tokens_spent)


class AttractorAssessment(BaseModel):
    model_config = _STRICT_CONFIG

    snapshot_id: str = Field(..., pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    is_wrong_state_attractor: bool
    attractor_code: str = Field(..., min_length=1, max_length=64)
    consecutive_same_error_count: int = Field(..., ge=0, le=100_000)
    score_stagnation_steps: int = Field(..., ge=0, le=100_000)
    has_dirty_non_git_state: bool = Field(default=False)
    recommended_restoration: RestorationMode
    reason: str = Field(..., min_length=1, max_length=1000)


class RecoveryBranchDispatch(BaseModel):
    model_config = _STRICT_CONFIG

    dispatch_id: str = Field(..., pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    run_id: str = Field(..., pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    source_snapshot_id: str = Field(..., pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    target_root_snapshot_id: str = Field(..., pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    restoration_mode: RestorationMode
    selection_score: float = Field(..., ge=0.0)
    projected_handoff_tokens: int = Field(..., ge=0, le=MAX_TOTAL_TOKEN_BUDGET)
    projected_branch_tokens: int = Field(..., ge=0, le=MAX_TOTAL_TOKEN_BUDGET)
    recovery_efficiency: float = Field(..., ge=0.0)
    cache_invalidated_entries: int = Field(default=0, ge=0)
    rollback_epoch: int = Field(..., ge=1)
    stale_reads_blocked: bool = Field(default=True)
    allowed: bool = Field(default=True)
    block_reason: Optional[str] = Field(default=None, max_length=500)


class RollbackQuarantineEntry(BaseModel):
    model_config = _STRICT_CONFIG

    quarantine_id: str = Field(..., pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    run_id: str = Field(..., pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    snapshot_id: Optional[str] = Field(default=None, pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    error_class: FailureErrorClass
    rule_code: str = Field(..., min_length=1, max_length=64)
    detail: str = Field(..., min_length=1, max_length=2000)
    created_seq: int = Field(default=1, ge=1)


def compute_handoff_overhead(summary_tokens: int, trace_tokens: int = 0) -> int:
    """Compute bounded handoff accounting tokens required to resume after rollback."""
    if summary_tokens < 0 or trace_tokens < 0:
        raise ValueError("DETERMINISTIC invariant violation: token counts must be non-negative.")
    return summary_tokens + trace_tokens


def compute_selection_score(
    pass_rate: float,
    visit_count: int,
    failing_tests: int,
    handoff_tokens: int,
) -> float:
    """Compute deterministic Go-Explore archive root selection priority score."""
    rate = max(0.0, min(1.0, float(pass_rate)))
    visits = max(1, int(visit_count))
    fails = max(0, int(failing_tests))
    handoff = max(0, int(handoff_tokens))
    raw = (rate * 100.0) + (25.0 / math.sqrt(visits)) - (fails * 2.0) - (handoff / 10_000.0)
    return round(max(0.0, raw), 6)


def compute_recovery_efficiency(baseline_tokens: int, recovery_tokens: int) -> float:
    """Compute token efficiency ratio between wasted retry loop vs archive rollback branch."""
    if baseline_tokens < 0 or recovery_tokens < 0:
        raise ValueError("DETERMINISTIC invariant violation: token metrics must be non-negative.")
    if recovery_tokens == 0:
        return 1.0 if baseline_tokens == 0 else float(baseline_tokens)
    return round(max(0.0, baseline_tokens / float(recovery_tokens)), 6)


def select_restoration_mode(
    non_git_artifacts: Sequence[NonGitRuntimeArtifact],
    git_diff_available: bool = True,
    sandbox_snapshot_available: bool = True,
) -> RestorationMode:
    """
    Never replay bare git-diff when dirty non-Git artifacts (SQLite WAL, background daemons,
    migration journals, env packages) are present; escalate to FULL_SANDBOX_SNAPSHOT or QUARANTINED_NOOP.
    """
    dirty_non_git = any(art.dirty_after_step for art in non_git_artifacts)
    unreversible = any(not art.reversible_via_snapshot for art in non_git_artifacts)
    if unreversible:
        return RestorationMode.QUARANTINED_NOOP
    if dirty_non_git:
        if sandbox_snapshot_available:
            return RestorationMode.FULL_SANDBOX_SNAPSHOT
        return RestorationMode.QUARANTINED_NOOP
    if git_diff_available:
        return RestorationMode.GIT_DIFF_REPLAY
    if sandbox_snapshot_available:
        return RestorationMode.FULL_SANDBOX_SNAPSHOT
    return RestorationMode.QUARANTINED_NOOP


def assess_wrong_state_attractor(
    snapshot: SnapshotArchiveCell,
    error_signatures: Sequence[str],
    score_stagnation_steps: int,
    fail_threshold: int = DEFAULT_ATTRACTOR_FAIL_THRESHOLD,
    git_diff_available: bool = True,
    sandbox_snapshot_available: bool = True,
) -> AttractorAssessment:
    """Detect repetitive wrong-state attractor loops and recommend deterministic restoration mode."""
    consecutive = 0
    if error_signatures:
        last_sig = error_signatures[-1]
        for sig in reversed(error_signatures):
            if sig == last_sig:
                consecutive += 1
            else:
                break

    dirty_non_git = any(art.dirty_after_step for art in snapshot.non_git_artifacts)
    recommended = select_restoration_mode(
        snapshot.non_git_artifacts,
        git_diff_available=git_diff_available,
        sandbox_snapshot_available=sandbox_snapshot_available,
    )

    stagnant = score_stagnation_steps >= fail_threshold and snapshot.failing_tests > 0
    is_attractor = consecutive >= fail_threshold or stagnant

    if is_attractor:
        reason = (
            f"WRONG_STATE_ATTRACTOR detected: consecutive_same_error={consecutive}, "
            f"score_stagnation_steps={score_stagnation_steps}, failing_tests={snapshot.failing_tests}"
        )
        code = "WRONG_STATE_ATTRACTOR"
    else:
        reason = "No attractor stall threshold reached."
        code = "NONE"

    return AttractorAssessment(
        snapshot_id=snapshot.snapshot_id,
        is_wrong_state_attractor=is_attractor,
        attractor_code=code,
        consecutive_same_error_count=consecutive,
        score_stagnation_steps=max(0, score_stagnation_steps),
        has_dirty_non_git_state=dirty_non_git,
        recommended_restoration=recommended,
        reason=reason,
    )


def evaluate_branch_gate(
    root: SnapshotArchiveCell,
    ledger: BranchBudgetLedger,
    projected_branch_tokens: int,
    projected_handoff_tokens: int,
    dispatch_id: str,
    source_snapshot_id: str,
    rollback_epoch: int,
    cache_invalidated_entries: int = 0,
    baseline_retry_tokens: int = 0,
    git_diff_available: bool = True,
    sandbox_snapshot_available: bool = True,
    source: Optional[SnapshotArchiveCell] = None,
) -> RecoveryBranchDispatch:
    """Validate bounded Go-Explore rollback branch fanout, token budget, and artifact safety."""
    combined_artifacts = list(root.non_git_artifacts)
    if source is not None:
        combined_artifacts.extend(source.non_git_artifacts)
    mode = select_restoration_mode(
        combined_artifacts,
        git_diff_available=git_diff_available,
        sandbox_snapshot_available=sandbox_snapshot_available,
    )
    score = compute_selection_score(
        pass_rate=root.pass_rate,
        visit_count=root.visit_count,
        failing_tests=root.failing_tests,
        handoff_tokens=projected_handoff_tokens,
    )
    eff_baseline = baseline_retry_tokens or max(1, projected_branch_tokens)
    efficiency = compute_recovery_efficiency(
        baseline_tokens=eff_baseline,
        recovery_tokens=projected_branch_tokens + projected_handoff_tokens,
    )

    block_reason: Optional[str] = None
    allowed = True
    if root.lifecycle_state in TERMINAL_STATES:
        allowed = False
        mode = RestorationMode.QUARANTINED_NOOP
        block_reason = f"TERMINAL_STATE_LOCKED: root snapshot {root.snapshot_id} is {root.lifecycle_state.value}"
    elif (
        root.children_spawned >= root.max_children_per_root
        or root.children_spawned >= ledger.max_children_per_root
    ):
        allowed = False
        mode = RestorationMode.QUARANTINED_NOOP
        block_reason = (
            f"FANOUT_EXCEEDED: children_spawned={root.children_spawned} "
            f">= max_children_per_root={min(root.max_children_per_root, ledger.max_children_per_root)}"
        )
    elif (projected_branch_tokens + projected_handoff_tokens) > ledger.remaining_tokens:
        allowed = False
        mode = RestorationMode.QUARANTINED_NOOP
        block_reason = (
            f"BUDGET_EXHAUSTED: projected={projected_branch_tokens + projected_handoff_tokens} "
            f"> remaining_tokens={ledger.remaining_tokens}"
        )
    elif mode == RestorationMode.QUARANTINED_NOOP:
        allowed = False
        block_reason = "UNREVERSIBLE_NON_GIT_ARTIFACT: safe rollback snapshot unavailable"

    return RecoveryBranchDispatch(
        dispatch_id=dispatch_id,
        run_id=ledger.run_id,
        source_snapshot_id=source_snapshot_id,
        target_root_snapshot_id=root.snapshot_id,
        restoration_mode=mode,
        selection_score=score,
        projected_handoff_tokens=projected_handoff_tokens,
        projected_branch_tokens=projected_branch_tokens,
        recovery_efficiency=efficiency,
        cache_invalidated_entries=cache_invalidated_entries,
        rollback_epoch=rollback_epoch,
        stale_reads_blocked=True,
        allowed=allowed,
        block_reason=block_reason,
    )


def _invalidate_loaded_pruners(reason: str) -> None:
    """Trigger cache/epoch invalidation on loaded core pruners without violating lazy imports."""
    pruner_mod = sys.modules.get("ctxfw.core.pruner")
    if pruner_mod is not None and hasattr(pruner_mod, "DeterministicContextPruner"):
        cls = getattr(pruner_mod, "DeterministicContextPruner")
        if hasattr(cls, "invalidate_cache"):
            cls.invalidate_cache(reason=reason)
    poly_mod = sys.modules.get("ctxfw.core.polyglot")
    if poly_mod is not None and hasattr(poly_mod, "TreeSitterContextPruner"):
        cls = getattr(poly_mod, "TreeSitterContextPruner")
        if hasattr(cls, "invalidate_cache"):
            cls.invalidate_cache(reason=reason)


class SandboxSnapshotStore:
    """
    Thread-safe SQLite WAL Go-Explore Archive & Rollback Invalidation Store.
    All ledger tables are strictly append-only (BEFORE UPDATE ABORT triggers).
    """

    def __init__(self, db_path: str | Path = ":memory:"):
        self.db_path = str(db_path)
        self._lock = threading.RLock()
        self._seq_counter = itertools.count(1)
        self._conn: Optional[sqlite3.Connection] = None
        self._runs: dict[str, str] = {}
        self._ledgers: dict[str, BranchBudgetLedger] = {}
        self._cells: dict[tuple[str, str], SnapshotArchiveCell] = {}
        self._error_history: dict[tuple[str, str], list[str]] = {}
        self._stagnation_steps: dict[tuple[str, str], int] = {}
        self._last_pass_rate: dict[tuple[str, str], float] = {}
        self._run_epochs: dict[str, int] = {}
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            if self.db_path != ":memory:":
                Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.db_path, timeout=5.0, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA busy_timeout = 5000;")
            self._conn = conn
        return self._conn

    def _init_db(self) -> None:
        schema_path = Path(__file__).with_name("snapshot_schema.sql")
        ddl = schema_path.read_text(encoding="utf-8")
        with self._lock:
            conn = self._get_conn()
            conn.executescript(ddl)
            conn.commit()

    def _next_seq(self) -> int:
        return next(self._seq_counter)

    def _next_id(self, prefix: str) -> str:
        return f"{prefix}_{time.monotonic_ns()}_{self._next_seq()}"

    def _run_with_retry(self, fn: Callable[[sqlite3.Connection], _T], max_attempts: int = 5) -> _T:
        for attempt in range(max_attempts):
            try:
                with self._lock:
                    conn = self._get_conn()
                    out = fn(conn)
                    conn.commit()
                    return out
            except sqlite3.OperationalError as exc:
                msg = str(exc).lower()
                if ("locked" in msg or "busy" in msg) and attempt < max_attempts - 1:
                    time.sleep(0.01 * (attempt + 1))
                    continue
                raise
        raise sqlite3.OperationalError("SQLite operation failed after retries")

    def register_run(
        self,
        run_id: str,
        project_root: str | Path,
        total_token_budget: int = DEFAULT_TOTAL_TOKEN_BUDGET,
        max_children_per_root: int = DEFAULT_MAX_CHILDREN_PER_ROOT,
    ) -> BranchBudgetLedger:
        resolved_root = str(Path(project_root).resolve())
        project_id, _project_name = resolve_project_identity(resolved_root)
        ledger = BranchBudgetLedger(
            run_id=run_id,
            total_token_budget=total_token_budget,
            tokens_spent=0,
            handoff_tokens_spent=0,
            active_branches=1,
            max_children_per_root=max_children_per_root,
        )

        def _op(conn: sqlite3.Connection) -> BranchBudgetLedger:
            seq = self._next_seq()
            conn.execute(
                """
                INSERT INTO snapshot_runs (
                    run_id, project_root, project_id, total_token_budget,
                    max_children_per_root, manifest_hash, created_seq
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    resolved_root,
                    project_id,
                    ledger.total_token_budget,
                    ledger.max_children_per_root,
                    WAVE1C_MANIFEST_HASH,
                    seq,
                ),
            )
            self._runs[run_id] = resolved_root
            self._ledgers[run_id] = ledger
            self._run_epochs.setdefault(run_id, 0)
            return ledger

        return self._run_with_retry(_op)

    def _insert_cell_record(
        self,
        conn: sqlite3.Connection,
        cell: SnapshotArchiveCell,
        transitions_to_append: Sequence[tuple[SnapshotLifecycleState, SnapshotLifecycleEvent, SnapshotLifecycleState]] = (),
    ) -> None:
        conn.execute(
            """
            INSERT INTO snapshot_archive_cells (
                cell_record_id, snapshot_id, run_id, project_root, parent_snapshot_id,
                step_index, depth, git_commit_sha, working_tree_digest,
                pass_rate, failing_tests, tokens_used_to_reach, handoff_tokens,
                max_children_per_root, lifecycle_state, rollback_epoch, manifest_hash, created_seq
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self._next_id("cell"),
                cell.snapshot_id,
                cell.run_id,
                cell.project_root,
                cell.parent_snapshot_id,
                cell.step_index,
                cell.depth,
                cell.git_commit_sha,
                cell.working_tree_digest,
                cell.pass_rate,
                cell.failing_tests,
                cell.tokens_used_to_reach,
                cell.handoff_tokens,
                cell.max_children_per_root,
                cell.lifecycle_state.value,
                cell.rollback_epoch,
                WAVE1C_MANIFEST_HASH,
                self._next_seq(),
            ),
        )
        for art in cell.non_git_artifacts:
            conn.execute(
                """
                INSERT INTO snapshot_non_git_artifacts (
                    record_id, snapshot_id, run_id, artifact_id, kind,
                    resource_path_or_pid, pre_state_digest, dirty_after_step,
                    reversible_via_snapshot, created_seq
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._next_id("nga"),
                    cell.snapshot_id,
                    cell.run_id,
                    art.artifact_id,
                    art.kind.value,
                    art.resource_path_or_pid,
                    art.pre_state_digest,
                    1 if art.dirty_after_step else 0,
                    1 if art.reversible_via_snapshot else 0,
                    self._next_seq(),
                ),
            )
        for from_s, ev, to_s in transitions_to_append:
            conn.execute(
                """
                INSERT INTO snapshot_fsm_transitions (
                    transition_id, run_id, snapshot_id, from_state, event,
                    to_state, rollback_epoch, manifest_hash, seq_no
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._next_id("tr"),
                    cell.run_id,
                    cell.snapshot_id,
                    from_s.value,
                    ev.value,
                    to_s.value,
                    cell.rollback_epoch,
                    WAVE1C_MANIFEST_HASH,
                    self._next_seq(),
                ),
            )
        self._cells[(cell.run_id, cell.snapshot_id)] = cell

    def _record_budget_delta(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        tokens_delta: int,
        handoff_delta: int,
        active_branches_delta: int = 0,
    ) -> BranchBudgetLedger:
        ledger = self._ledgers[run_id]
        updated = ledger.model_copy(
            update={
                "tokens_spent": ledger.tokens_spent + tokens_delta,
                "handoff_tokens_spent": ledger.handoff_tokens_spent + handoff_delta,
                "active_branches": max(0, ledger.active_branches + active_branches_delta),
            }
        )
        # Re-validate cumulative spend against hard budget limit <= 1_000_000.
        updated = BranchBudgetLedger.model_validate(updated.model_dump())
        conn.execute(
            """
            INSERT INTO snapshot_budget_ledger_events (
                ledger_event_id, run_id, tokens_delta, handoff_delta,
                cumulative_tokens_spent, cumulative_handoff_spent,
                total_token_budget, created_seq
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self._next_id("bud"),
                run_id,
                tokens_delta,
                handoff_delta,
                updated.tokens_spent,
                updated.handoff_tokens_spent,
                updated.total_token_budget,
                self._next_seq(),
            ),
        )
        self._ledgers[run_id] = updated
        return updated

    def checkpoint_snapshot(self, cell: SnapshotArchiveCell, tokens_delta: int = 0) -> SnapshotArchiveCell:
        def _op(conn: sqlite3.Connection) -> SnapshotArchiveCell:
            if cell.run_id not in self._ledgers:
                raise KeyError(f"Unknown snapshot run_id={cell.run_id}")
            if tokens_delta > 0:
                self._record_budget_delta(conn, cell.run_id, tokens_delta=tokens_delta, handoff_delta=0)
            target_cell = cell
            if target_cell.lifecycle_state == SnapshotLifecycleState.CREATED:
                next_state = transition(
                    SnapshotLifecycleState.CREATED,
                    SnapshotLifecycleEvent.CAPTURE_CHECKPOINT,
                )
                target_cell = target_cell.model_copy(update={"lifecycle_state": next_state})
                tr_list = [(
                    SnapshotLifecycleState.CREATED,
                    SnapshotLifecycleEvent.CAPTURE_CHECKPOINT,
                    next_state,
                )]
            else:
                tr_list = []
            self._insert_cell_record(conn, target_cell, transitions_to_append=tr_list)
            self._last_pass_rate[(cell.run_id, cell.snapshot_id)] = target_cell.pass_rate
            return target_cell

        return self._run_with_retry(_op)

    def record_step_outcome(
        self,
        run_id: str,
        snapshot_id: str,
        error_signature: Optional[str] = None,
        pass_rate: Optional[float] = None,
        failing_tests: Optional[int] = None,
        tokens_delta: int = 0,
        non_git_artifacts: Optional[Sequence[NonGitRuntimeArtifact]] = None,
        fail_threshold: int = DEFAULT_ATTRACTOR_FAIL_THRESHOLD,
        git_diff_available: bool = True,
        sandbox_snapshot_available: bool = True,
    ) -> AttractorAssessment:
        def _op(conn: sqlite3.Connection) -> AttractorAssessment:
            key = (run_id, snapshot_id)
            cell = self._cells[key]
            ledger = self._ledgers[run_id]
            if tokens_delta > ledger.remaining_tokens:
                self._insert_quarantine(
                    conn,
                    run_id=run_id,
                    snapshot_id=snapshot_id,
                    error_class=FailureErrorClass.BUSINESS,
                    rule_code="BUDGET_EXHAUSTED",
                    detail=f"tokens_delta={tokens_delta} exceeds remaining_tokens={ledger.remaining_tokens}",
                )
                raise ValueError("BUSINESS invariant violation: token budget exhausted.")
            if tokens_delta > 0:
                self._record_budget_delta(conn, run_id, tokens_delta=tokens_delta, handoff_delta=0)

            new_rate = cell.pass_rate if pass_rate is None else pass_rate
            new_fail = cell.failing_tests if failing_tests is None else failing_tests
            prev_rate = self._last_pass_rate.get(key, cell.pass_rate)
            if new_rate <= prev_rate and new_fail > 0:
                stagnation = self._stagnation_steps.get(key, 0) + 1
            else:
                stagnation = 0
            self._stagnation_steps[key] = stagnation
            self._last_pass_rate[key] = new_rate

            sigs = self._error_history.setdefault(key, [])
            if error_signature:
                sigs.append(error_signature)

            merged_artifacts = (
                tuple(non_git_artifacts) if non_git_artifacts is not None else cell.non_git_artifacts
            )
            updated_cell = cell.model_copy(
                update={
                    "pass_rate": new_rate,
                    "failing_tests": new_fail,
                    "tokens_used_to_reach": cell.tokens_used_to_reach + tokens_delta,
                    "non_git_artifacts": merged_artifacts,
                }
            )
            assessment = assess_wrong_state_attractor(
                snapshot=updated_cell,
                error_signatures=sigs,
                score_stagnation_steps=stagnation,
                fail_threshold=fail_threshold,
                git_diff_available=git_diff_available,
                sandbox_snapshot_available=sandbox_snapshot_available,
            )
            transitions: list[tuple[SnapshotLifecycleState, SnapshotLifecycleEvent, SnapshotLifecycleState]] = []
            if (
                assessment.is_wrong_state_attractor
                and updated_cell.lifecycle_state
                in (SnapshotLifecycleState.CHECKPOINTED, SnapshotLifecycleState.BRANCH_EXPANDED)
            ):
                next_state = transition(
                    updated_cell.lifecycle_state,
                    SnapshotLifecycleEvent.DETECT_ATTRACTOR,
                )
                transitions.append((
                    updated_cell.lifecycle_state,
                    SnapshotLifecycleEvent.DETECT_ATTRACTOR,
                    next_state,
                ))
                updated_cell = updated_cell.model_copy(update={"lifecycle_state": next_state})
            self._insert_cell_record(conn, updated_cell, transitions_to_append=transitions)
            return assessment

        return self._run_with_retry(_op)

    def _insert_quarantine(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        snapshot_id: Optional[str],
        error_class: FailureErrorClass,
        rule_code: str,
        detail: str,
    ) -> RollbackQuarantineEntry:
        entry = RollbackQuarantineEntry(
            quarantine_id=self._next_id("rq"),
            run_id=run_id,
            snapshot_id=snapshot_id,
            error_class=error_class,
            rule_code=rule_code,
            detail=detail,
            created_seq=self._next_seq(),
        )
        conn.execute(
            """
            INSERT INTO snapshot_quarantine_entries (
                quarantine_id, run_id, snapshot_id, error_class, rule_code, detail, created_seq
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.quarantine_id,
                entry.run_id,
                entry.snapshot_id,
                entry.error_class.value,
                entry.rule_code,
                entry.detail,
                entry.created_seq,
            ),
        )
        return entry

    def execute_rollback(
        self,
        run_id: str,
        source_snapshot_id: str,
        target_root_snapshot_id: str,
        projected_branch_tokens: int,
        handoff_summary_tokens: int,
        trace_tokens: int = 0,
        baseline_retry_tokens: int = 0,
        cache: Any = None,
        engine: Any = None,
        git_diff_available: bool = True,
        sandbox_snapshot_available: bool = True,
    ) -> RecoveryBranchDispatch:
        handoff_tokens = compute_handoff_overhead(handoff_summary_tokens, trace_tokens)

        def _op(conn: sqlite3.Connection) -> RecoveryBranchDispatch:
            root = self._cells[(run_id, target_root_snapshot_id)]
            source = self._cells[(run_id, source_snapshot_id)]
            ledger = self._ledgers[run_id]
            new_epoch = self._run_epochs.get(run_id, 0) + 1
            dispatch_id = self._next_id("rbd")

            candidate = evaluate_branch_gate(
                root=root,
                ledger=ledger,
                projected_branch_tokens=projected_branch_tokens,
                projected_handoff_tokens=handoff_tokens,
                dispatch_id=dispatch_id,
                source_snapshot_id=source_snapshot_id,
                rollback_epoch=new_epoch,
                cache_invalidated_entries=0,
                baseline_retry_tokens=baseline_retry_tokens,
                git_diff_available=git_diff_available,
                sandbox_snapshot_available=sandbox_snapshot_available,
                source=source,
            )

            if not candidate.allowed:
                self._insert_quarantine(
                    conn,
                    run_id=run_id,
                    snapshot_id=target_root_snapshot_id,
                    error_class=FailureErrorClass.BUSINESS,
                    rule_code="ROLLBACK_GATE_REJECTED",
                    detail=candidate.block_reason or "Rollback gate rejected",
                )
                self._record_dispatch(conn, candidate)
                return candidate

            # Mandatory deterministic cache/graph/pruner invalidation on restore.
            invalidated_count = 0
            project_root = self._runs[run_id]
            if engine is not None and hasattr(engine, "invalidate_after_rollback"):
                invalidated_count += int(engine.invalidate_after_rollback(snapshot_id=target_root_snapshot_id))
            elif cache is not None and hasattr(cache, "invalidate_for_rollback"):
                invalidated_count += int(
                    cache.invalidate_for_rollback(
                        project_root=project_root,
                        snapshot_id=target_root_snapshot_id,
                    )
                )
            _invalidate_loaded_pruners(reason=f"rollback:{target_root_snapshot_id}:epoch:{new_epoch}")

            # Record FSM transitions on root & update epoch/visit count immutably via new archive records.
            self._run_epochs[run_id] = new_epoch
            self._record_budget_delta(
                conn,
                run_id,
                tokens_delta=projected_branch_tokens,
                handoff_delta=handoff_tokens,
                active_branches_delta=1,
            )

            s0 = root.lifecycle_state
            s1 = transition(s0, SnapshotLifecycleEvent.REQUEST_ROLLBACK)
            s2 = transition(s1, SnapshotLifecycleEvent.EXECUTE_ROLLBACK_AND_INVALIDATE)
            restored_root = root.model_copy(
                update={
                    "visit_count": root.visit_count + 1,
                    "children_spawned": root.children_spawned + 1,
                    "handoff_tokens": root.handoff_tokens + handoff_tokens,
                    "lifecycle_state": s2,
                    "rollback_epoch": new_epoch,
                }
            )
            self._insert_cell_record(
                conn,
                restored_root,
                transitions_to_append=[
                    (s0, SnapshotLifecycleEvent.REQUEST_ROLLBACK, s1),
                    (s1, SnapshotLifecycleEvent.EXECUTE_ROLLBACK_AND_INVALIDATE, s2),
                ],
            )
            # Clear error streak on restored branch root cleanly.
            self._error_history[(run_id, target_root_snapshot_id)] = []
            self._stagnation_steps[(run_id, target_root_snapshot_id)] = 0

            # Quarantine stalled source branch if still non-terminal so old path isn't silently reused.
            if source_snapshot_id != target_root_snapshot_id and source.lifecycle_state not in TERMINAL_STATES:
                q_state = transition(source.lifecycle_state, SnapshotLifecycleEvent.ABORT_QUARANTINE)
                quarantined_source = source.model_copy(
                    update={"lifecycle_state": q_state, "rollback_epoch": new_epoch}
                )
                self._insert_cell_record(
                    conn,
                    quarantined_source,
                    transitions_to_append=[
                        (source.lifecycle_state, SnapshotLifecycleEvent.ABORT_QUARANTINE, q_state)
                    ],
                )

            final_dispatch = candidate.model_copy(
                update={
                    "cache_invalidated_entries": invalidated_count,
                    "stale_reads_blocked": True,
                }
            )
            self._record_dispatch(conn, final_dispatch)
            return final_dispatch

        return self._run_with_retry(_op)

    def spawn_child_branch(
        self,
        run_id: str,
        parent_snapshot_id: str,
        child_snapshot_id: str,
        working_tree_digest: str,
        step_index: int,
        tokens_delta: int = 0,
        git_commit_sha: Optional[str] = None,
    ) -> SnapshotArchiveCell:
        def _op(conn: sqlite3.Connection) -> SnapshotArchiveCell:
            parent = self._cells[(run_id, parent_snapshot_id)]
            ledger = self._ledgers[run_id]
            if (
                parent.children_spawned >= parent.max_children_per_root
                or parent.children_spawned >= ledger.max_children_per_root
            ):
                self._insert_quarantine(
                    conn,
                    run_id=run_id,
                    snapshot_id=parent_snapshot_id,
                    error_class=FailureErrorClass.BUSINESS,
                    rule_code="FANOUT_EXCEEDED",
                    detail="Maximum Go-Explore children per root exceeded.",
                )
                raise ValueError("BUSINESS invariant violation: max_children_per_root exceeded.")
            if tokens_delta > ledger.remaining_tokens:
                self._insert_quarantine(
                    conn,
                    run_id=run_id,
                    snapshot_id=parent_snapshot_id,
                    error_class=FailureErrorClass.BUSINESS,
                    rule_code="BUDGET_EXHAUSTED",
                    detail="Branch token budget exhausted.",
                )
                raise ValueError("BUSINESS invariant violation: token budget exhausted.")

            if tokens_delta > 0:
                self._record_budget_delta(conn, run_id, tokens_delta=tokens_delta, handoff_delta=0)

            p_state = transition(parent.lifecycle_state, SnapshotLifecycleEvent.SPAWN_CHILD_BRANCH)
            updated_parent = parent.model_copy(
                update={
                    "children_spawned": parent.children_spawned + 1,
                    "lifecycle_state": p_state,
                }
            )
            self._insert_cell_record(
                conn,
                updated_parent,
                transitions_to_append=[
                    (parent.lifecycle_state, SnapshotLifecycleEvent.SPAWN_CHILD_BRANCH, p_state)
                ],
            )
            child = SnapshotArchiveCell(
                snapshot_id=child_snapshot_id,
                run_id=run_id,
                project_root=parent.project_root,
                parent_snapshot_id=parent_snapshot_id,
                step_index=step_index,
                depth=parent.depth + 1,
                git_commit_sha=git_commit_sha,
                working_tree_digest=working_tree_digest,
                pass_rate=parent.pass_rate,
                failing_tests=parent.failing_tests,
                visit_count=1,
                children_spawned=0,
                max_children_per_root=parent.max_children_per_root,
                tokens_used_to_reach=parent.tokens_used_to_reach + tokens_delta,
                handoff_tokens=0,
                non_git_artifacts=(),
                lifecycle_state=SnapshotLifecycleState.CHECKPOINTED,
                rollback_epoch=self._run_epochs.get(run_id, 0),
            )
            self._insert_cell_record(conn, child)
            self._last_pass_rate[(run_id, child_snapshot_id)] = child.pass_rate
            return child

        return self._run_with_retry(_op)

    def _record_dispatch(self, conn: sqlite3.Connection, dispatch: RecoveryBranchDispatch) -> None:
        conn.execute(
            """
            INSERT INTO snapshot_rollback_dispatches (
                dispatch_id, run_id, source_snapshot_id, target_root_snapshot_id,
                restoration_mode, selection_score, projected_handoff_tokens,
                projected_branch_tokens, recovery_efficiency, cache_invalidated_entries,
                rollback_epoch, stale_reads_blocked, allowed, block_reason, created_seq
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dispatch.dispatch_id,
                dispatch.run_id,
                dispatch.source_snapshot_id,
                dispatch.target_root_snapshot_id,
                dispatch.restoration_mode.value,
                dispatch.selection_score,
                dispatch.projected_handoff_tokens,
                dispatch.projected_branch_tokens,
                dispatch.recovery_efficiency,
                dispatch.cache_invalidated_entries,
                dispatch.rollback_epoch,
                1 if dispatch.stale_reads_blocked else 0,
                1 if dispatch.allowed else 0,
                dispatch.block_reason,
                self._next_seq(),
            ),
        )

    def get_ledger(self, run_id: str) -> BranchBudgetLedger:
        with self._lock:
            return self._ledgers[run_id]

    def get_cell(self, run_id: str, snapshot_id: str) -> SnapshotArchiveCell:
        with self._lock:
            return self._cells[(run_id, snapshot_id)]

    def list_dispatches(self, run_id: str) -> list[dict]:
        with self._lock:
            rows = self._get_conn().execute(
                """
                SELECT * FROM snapshot_rollback_dispatches
                WHERE run_id = ?
                ORDER BY created_seq ASC
                """,
                (run_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def list_transitions(self, run_id: str) -> list[dict]:
        with self._lock:
            rows = self._get_conn().execute(
                """
                SELECT * FROM snapshot_fsm_transitions
                WHERE run_id = ?
                ORDER BY seq_no ASC
                """,
                (run_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def list_quarantines(self, run_id: str) -> list[dict]:
        with self._lock:
            rows = self._get_conn().execute(
                """
                SELECT * FROM snapshot_quarantine_entries
                WHERE run_id = ?
                ORDER BY created_seq ASC
                """,
                (run_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def __enter__(self) -> "SandboxSnapshotStore":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()
