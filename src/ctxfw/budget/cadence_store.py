# manifest_hash: 34ae93e3f71bcaab59019e9e0139a4b24b69b82c2005b25e5049329f84b1aa2c
"""
TokenCast Cadence SQLite WAL Store (#19)
========================================
Thread-safe SQLite WAL persistence for AIMD cadence runs, two-tier verdicts,
token leverage telemetry, isolated append-only `cadence_occ_ledger`, and
optional `SandboxSnapshotStore` rollback execution on `REPLACEMENT`.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Callable, Optional, TypeVar

from ctxfw.budget.cadence import (
    CADENCE_MANIFEST_HASH,
    CadenceEvent,
    CadenceState,
    ErrorClass,
    InterventionVerdict,
    ScaffoldType,
    SchedulerConfig,
    SchedulerStateSnapshot,
    TokenLeverageTelemetry,
    TrajectoryStepProposal,
    TwoTierVerdict,
    cadence_transition,
    evaluate_deterministic_cadence,
)

CADENCE_SCHEMA_PATH: Path = Path(__file__).resolve().parent / "cadence_schema.sql"
_MAX_WAL_RETRIES: int = 5
_T = TypeVar("_T")


def load_cadence_schema_sql() -> str:
    """Return the Wave 2 D.2 Cadence SQLite WAL DDL text (UTF-8)."""
    return CADENCE_SCHEMA_PATH.read_text(encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CadenceStore:
    """Thread-safe SQLite WAL persistence for deterministic AIMD cadence scheduler."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._seq: int = 0
        self._conn: Optional[sqlite3.Connection] = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
            isolation_level=None,
            timeout=5.0,
        )
        self._conn.execute("PRAGMA journal_mode = WAL;")
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._conn.execute("PRAGMA synchronous = NORMAL;")
        self._conn.execute("PRAGMA busy_timeout = 5000;")
        self._conn.executescript(load_cadence_schema_sql())

    def _conn_or_raise(self) -> sqlite3.Connection:
        conn = self._conn
        if conn is None:
            raise RuntimeError("CadenceStore connection is closed")
        return conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def _run_with_retry(self, fn: Callable[[], _T]) -> _T:
        last_exc: Optional[sqlite3.OperationalError] = None
        for attempt in range(_MAX_WAL_RETRIES):
            try:
                with self._lock:
                    return fn()
            except sqlite3.OperationalError as exc:
                msg = str(exc).lower()
                if "locked" not in msg and "busy" not in msg:
                    raise
                last_exc = exc
                time.sleep(0.005 * (2**attempt))
        if last_exc is not None:
            raise last_exc
        raise sqlite3.OperationalError("SQLITE_BUSY retry exhausted")

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _insert_quarantine_row(
        self,
        conn: sqlite3.Connection,
        *,
        run_id: str,
        session_id: str,
        error_class: ErrorClass,
        reason: str,
        now: str,
    ) -> str:
        seq = self._next_seq()
        qid = f"CDQ-{hashlib.sha256(f'{run_id}:{reason}:{now}:{seq}'.encode('utf-8')).hexdigest()[:16]}"
        conn.execute(
            "INSERT INTO cadence_quarantine "
            "(quarantine_id, run_id, session_id, error_class, reason, recorded_at_utc) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (qid, run_id, session_id, error_class.value, reason[:512], now),
        )
        return qid

    def _execute_snapshot_rollback_hook(
        self,
        conn: sqlite3.Connection,
        *,
        proposal: TrajectoryStepProposal,
        snapshot_store: Any,
        target_snap_run: str,
        snapshot_source_id: Optional[str],
        snapshot_target_root_id: Optional[str],
        projected_branch_tokens: Optional[int],
        handoff_summary_tokens: int,
        cache: Any,
        now: str,
    ) -> tuple[bool, Optional[int]]:
        """Invoke SandboxSnapshotStore.execute_rollback safely inside current cadence lock."""
        try:
            src_id = snapshot_source_id
            root_id = snapshot_target_root_id
            cells_map = getattr(snapshot_store, "_cells", {})
            if (src_id is None or root_id is None) and isinstance(cells_map, dict):
                run_cells = [c for (r_id, _s_id), c in cells_map.items() if r_id == target_snap_run]
                if run_cells:
                    run_cells.sort(key=lambda c: int(getattr(c, "step_index", 0)))
                    if root_id is None:
                        roots = [c for c in run_cells if getattr(c, "parent_snapshot_id", None) is None]
                        root_id = str(getattr(roots[0] if roots else run_cells[0], "snapshot_id"))
                    if src_id is None:
                        src_id = str(getattr(run_cells[-1], "snapshot_id"))

            if not (src_id and root_id):
                self._insert_quarantine_row(
                    conn,
                    run_id=proposal.run_id,
                    session_id=proposal.session_id,
                    error_class=ErrorClass.DETERMINISTIC,
                    reason=f"Snapshot cells not found for run_id={target_snap_run}",
                    now=now,
                )
                return False, None

            branch_tokens = (
                projected_branch_tokens
                if projected_branch_tokens is not None
                else max(256, proposal.signals.estimated_prompt_tokens)
            )
            dispatch = snapshot_store.execute_rollback(
                run_id=target_snap_run,
                source_snapshot_id=src_id,
                target_root_snapshot_id=root_id,
                projected_branch_tokens=int(branch_tokens),
                handoff_summary_tokens=int(handoff_summary_tokens),
                cache=cache,
            )
            allowed_rb = (
                bool(dispatch.get("allowed", False))
                if isinstance(dispatch, dict)
                else bool(getattr(dispatch, "allowed", False))
            )
            if allowed_rb:
                epoch_val = (
                    dispatch.get("rollback_epoch")
                    if isinstance(dispatch, dict)
                    else getattr(dispatch, "rollback_epoch", None)
                )
                return True, (int(epoch_val) if epoch_val is not None else None)

            reason_rb = (
                dispatch.get("block_reason")
                if isinstance(dispatch, dict)
                else getattr(dispatch, "block_reason", "Rollback gate denied")
            )
            self._insert_quarantine_row(
                conn,
                run_id=proposal.run_id,
                session_id=proposal.session_id,
                error_class=ErrorClass.BUSINESS,
                reason=f"Snapshot rollback gate denied: {reason_rb}",
                now=now,
            )
            return False, None
        except Exception as exc:
            self._insert_quarantine_row(
                conn,
                run_id=proposal.run_id,
                session_id=proposal.session_id,
                error_class=ErrorClass.SECURITY,
                reason=f"Snapshot rollback hook rejected or failed: {exc}",
                now=now,
            )
            return False, None

    def ensure_run(
        self,
        *,
        run_id: str,
        session_id: str,
        config: SchedulerConfig,
    ) -> SchedulerStateSnapshot:
        """Create run row if missing and return current SchedulerStateSnapshot."""
        now = _utc_now()

        def _op() -> SchedulerStateSnapshot:
            conn = self._conn_or_raise()
            conn.execute("BEGIN IMMEDIATE;")
            try:
                row = conn.execute(
                    "SELECT session_id, scaffold_type, current_step_index, last_inspection_step, "
                    "current_interval, state, occ_version, updated_at_utc "
                    "FROM cadence_runs WHERE run_id = ?",
                    (run_id,),
                ).fetchone()
                if row is None:
                    conn.execute(
                        "INSERT INTO cadence_runs "
                        "(run_id, session_id, scaffold_type, i_base, delta_step, i_max, "
                        "current_interval, current_step_index, last_inspection_step, state, "
                        "occ_version, created_at_utc, updated_at_utc) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, 0, -1, ?, 0, ?, ?)",
                        (
                            run_id,
                            session_id,
                            str(config.scaffold_type),
                            config.i_base,
                            config.delta_step,
                            config.i_max,
                            config.i_base,
                            CadenceState.EXECUTING_AUTONOMOUS.value,
                            now,
                            now,
                        ),
                    )
                    snap = SchedulerStateSnapshot(
                        run_id=run_id,
                        session_id=session_id,
                        scaffold_type=config.scaffold_type,
                        current_step_index=0,
                        last_inspection_step=-1,
                        current_interval=config.i_base,
                        state=CadenceState.EXECUTING_AUTONOMOUS,
                        occ_version=0,
                        updated_at_utc=now,
                    )
                else:
                    snap = SchedulerStateSnapshot(
                        run_id=run_id,
                        session_id=str(row[0]),
                        scaffold_type=ScaffoldType(str(row[1])),
                        current_step_index=int(row[2]),
                        last_inspection_step=int(row[3]),
                        current_interval=int(row[4]),
                        state=CadenceState(str(row[5])),
                        occ_version=int(row[6]),
                        updated_at_utc=str(row[7]),
                    )
                conn.execute("COMMIT;")
                return snap
            except Exception:
                conn.execute("ROLLBACK;")
                raise

        return self._run_with_retry(_op)

    def evaluate_and_record_step(
        self,
        *,
        proposal: TrajectoryStepProposal,
        config: SchedulerConfig,
        expected_occ_version: Optional[int] = None,
        force_inspect: bool = False,
        snapshot_store: Optional[Any] = None,
        snapshot_run_id: Optional[str] = None,
        snapshot_source_id: Optional[str] = None,
        snapshot_target_root_id: Optional[str] = None,
        projected_branch_tokens: Optional[int] = None,
        handoff_summary_tokens: int = 128,
        cache: Any = None,
    ) -> TwoTierVerdict:
        """Atomically read state, evaluate AIMD cadence, optionally roll back, and seal OCC ledger."""
        now = _utc_now()

        def _op() -> TwoTierVerdict:
            conn = self._conn_or_raise()
            conn.execute("BEGIN IMMEDIATE;")
            try:
                row = conn.execute(
                    "SELECT current_interval, last_inspection_step, occ_version, state "
                    "FROM cadence_runs WHERE run_id = ?",
                    (proposal.run_id,),
                ).fetchone()
                if row is None:
                    conn.execute(
                        "INSERT INTO cadence_runs "
                        "(run_id, session_id, scaffold_type, i_base, delta_step, i_max, "
                        "current_interval, current_step_index, last_inspection_step, state, "
                        "occ_version, created_at_utc, updated_at_utc) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, 0, -1, ?, 0, ?, ?)",
                        (
                            proposal.run_id,
                            proposal.session_id,
                            str(config.scaffold_type),
                            config.i_base,
                            config.delta_step,
                            config.i_max,
                            config.i_base,
                            CadenceState.EXECUTING_AUTONOMOUS.value,
                            now,
                            now,
                        ),
                    )
                    persisted_interval = config.i_base
                    persisted_last = -1
                    actual_occ = 0
                else:
                    persisted_interval = int(row[0])
                    persisted_last = int(row[1])
                    actual_occ = int(row[2])

                if expected_occ_version is not None and expected_occ_version != actual_occ:
                    raise ValueError(
                        f"CADENCE_OCC_CONFLICT: expected={expected_occ_version} actual={actual_occ}"
                    )

                # Reset last_inspection_step when a shorter conversation reuses an existing session/run.
                if proposal.step_index < persisted_last:
                    effective_last = -1
                    effective_interval = persisted_interval
                elif persisted_last > proposal.last_inspection_step or proposal.current_interval == config.i_base:
                    effective_last = max(proposal.last_inspection_step, persisted_last)
                    effective_interval = persisted_interval
                else:
                    effective_last = proposal.last_inspection_step
                    effective_interval = proposal.current_interval

                effective_proposal = proposal.model_copy(
                    update={
                        "current_interval": effective_interval,
                        "last_inspection_step": effective_last,
                    }
                )
                verdict = evaluate_deterministic_cadence(
                    effective_proposal,
                    config,
                    force_inspect=force_inspect,
                )

                new_occ = actual_occ + 1
                disambiguated_verdict_id = (
                    f"CDV-{hashlib.sha256(f'{proposal.proposal_id}:occ={new_occ}:{verdict.cadence_seal_sha256}'.encode('utf-8')).hexdigest()[:16]}"
                )

                rollback_flag = False
                rollback_epoch: Optional[int] = None
                target_snap_run = snapshot_run_id or proposal.signals.snapshot_run_id
                if (
                    verdict.verdict == InterventionVerdict.REPLACEMENT
                    and snapshot_store is not None
                    and target_snap_run
                ):
                    rollback_flag, rollback_epoch = self._execute_snapshot_rollback_hook(
                        conn,
                        proposal=proposal,
                        snapshot_store=snapshot_store,
                        target_snap_run=target_snap_run,
                        snapshot_source_id=snapshot_source_id,
                        snapshot_target_root_id=snapshot_target_root_id,
                        projected_branch_tokens=projected_branch_tokens,
                        handoff_summary_tokens=handoff_summary_tokens,
                        cache=cache,
                        now=now,
                    )

                new_last_insp = proposal.step_index if verdict.inspection_triggered else effective_last
                final_state = verdict.state
                if rollback_flag and final_state == CadenceState.REPLACEMENT_VETOED:
                    final_state = cadence_transition(
                        final_state,
                        CadenceEvent.TRIGGER_SNAPSHOT_ROLLBACK,
                    )
                next_exec_state = (
                    cadence_transition(final_state, CadenceEvent.CONTINUE_RUN)
                    if final_state
                    in {
                        CadenceState.ADVISORY_APPLIED,
                        CadenceState.REPLACEMENT_VETOED,
                        CadenceState.ROLLED_BACK,
                    }
                    else final_state
                )

                sealed_verdict = verdict.model_copy(
                    update={
                        "verdict_id": disambiguated_verdict_id,
                        "state": final_state,
                        "rollback_triggered": rollback_flag,
                        "rollback_target_epoch": rollback_epoch,
                    }
                )

                conn.execute(
                    "UPDATE cadence_runs SET "
                    "current_interval = ?, current_step_index = ?, last_inspection_step = ?, "
                    "state = ?, occ_version = ?, updated_at_utc = ? WHERE run_id = ?",
                    (
                        sealed_verdict.next_interval,
                        proposal.step_index,
                        new_last_insp,
                        next_exec_state.value,
                        new_occ,
                        now,
                        proposal.run_id,
                    ),
                )
                conn.execute(
                    "INSERT INTO cadence_step_verdicts "
                    "(verdict_id, run_id, step_index, inspection_triggered, verdict, category, "
                    "action_executed, next_interval, guidance_note, rollback_triggered, "
                    "rollback_target_epoch, cadence_seal_sha256, created_at_utc) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        sealed_verdict.verdict_id,
                        proposal.run_id,
                        proposal.step_index,
                        int(sealed_verdict.inspection_triggered),
                        sealed_verdict.verdict.value,
                        sealed_verdict.category.value,
                        sealed_verdict.action_executed,
                        sealed_verdict.next_interval,
                        sealed_verdict.guidance_note,
                        int(rollback_flag),
                        rollback_epoch,
                        sealed_verdict.cadence_seal_sha256,
                        now,
                    ),
                )
                conn.execute(
                    "INSERT INTO cadence_occ_ledger "
                    "(run_id, session_id, occ_version, verdict_seal_sha256, manifest_hash, recorded_at_utc) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        proposal.run_id,
                        proposal.session_id,
                        new_occ,
                        sealed_verdict.cadence_seal_sha256,
                        CADENCE_MANIFEST_HASH,
                        now,
                    ),
                )
                conn.execute("COMMIT;")
                return sealed_verdict
            except Exception:
                conn.execute("ROLLBACK;")
                raise

        return self._run_with_retry(_op)

    def record_token_leverage(self, telemetry: TokenLeverageTelemetry) -> None:
        """Persist deterministic token leverage comparison telemetry."""
        now = _utc_now()

        def _op() -> None:
            conn = self._conn_or_raise()
            seq = self._next_seq()
            tid = (
                f"CDL-{hashlib.sha256(f'{telemetry.run_id}:{telemetry.step_index}:{now}:{seq}'.encode('utf-8')).hexdigest()[:16]}"
            )
            conn.execute("BEGIN IMMEDIATE;")
            try:
                conn.execute(
                    "INSERT INTO cadence_token_leverage "
                    "(telemetry_id, run_id, step_index, tokens_without_guidance, "
                    "tokens_with_guidance, token_leverage_ratio, recorded_at_utc) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        tid,
                        telemetry.run_id,
                        telemetry.step_index,
                        telemetry.tokens_without_guidance,
                        telemetry.tokens_with_guidance,
                        telemetry.token_leverage_ratio,
                        now,
                    ),
                )
                conn.execute("COMMIT;")
            except Exception:
                conn.execute("ROLLBACK;")
                raise

        self._run_with_retry(_op)

    def record_quarantine(
        self,
        *,
        run_id: str,
        session_id: str,
        error_class: ErrorClass,
        reason: str,
    ) -> str:
        """Record an invariant or security quarantine event for a cadence run."""
        now = _utc_now()

        def _op() -> str:
            conn = self._conn_or_raise()
            conn.execute("BEGIN IMMEDIATE;")
            try:
                qid = self._insert_quarantine_row(
                    conn,
                    run_id=run_id,
                    session_id=session_id,
                    error_class=error_class,
                    reason=reason,
                    now=now,
                )
                conn.execute("COMMIT;")
                return qid
            except Exception:
                conn.execute("ROLLBACK;")
                raise

        return self._run_with_retry(_op)

    def get_run_snapshot(self, run_id: str) -> Optional[SchedulerStateSnapshot]:
        """Fetch latest persisted AIMD state for a run."""
        def _op() -> Optional[SchedulerStateSnapshot]:
            conn = self._conn_or_raise()
            row = conn.execute(
                "SELECT session_id, scaffold_type, current_step_index, last_inspection_step, "
                "current_interval, state, occ_version, updated_at_utc "
                "FROM cadence_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                return None
            return SchedulerStateSnapshot(
                run_id=run_id,
                session_id=str(row[0]),
                scaffold_type=ScaffoldType(str(row[1])),
                current_step_index=int(row[2]),
                last_inspection_step=int(row[3]),
                current_interval=int(row[4]),
                state=CadenceState(str(row[5])),
                occ_version=int(row[6]),
                updated_at_utc=str(row[7]),
            )

        return self._run_with_retry(_op)

    def list_cadence_occ_versions(self, run_id: str) -> list[int]:
        """Return monotonically ordered OCC versions from isolated cadence_occ_ledger."""
        def _op() -> list[int]:
            conn = self._conn_or_raise()
            rows = conn.execute(
                "SELECT occ_version FROM cadence_occ_ledger WHERE run_id = ? ORDER BY occ_version ASC",
                (run_id,),
            ).fetchall()
            return [int(r[0]) for r in rows]

        return self._run_with_retry(_op)
