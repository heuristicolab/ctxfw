"""
src/ctxfw/tracelite/store.py — Immutable SQLite WAL Store for TraceLite Reductions
manifest_hash: 00743e30ed7cee52140a1538a8622aeccb12a6c524adc80d875ab067bd39f762
blueprint_manifest_hash: 6a95bb7fd01158ac75d67055df0c328d56433a44625351610307d5ef6b68d0cf
"""
from __future__ import annotations

import itertools
import sqlite3
import threading
import time
from pathlib import Path
from typing import Callable, Iterable, Optional, TypeVar

from ctxfw.tracelite.contracts import (
    WAVE1C_MANIFEST_HASH,
    ReducedTrajectoryWindow,
    TraceAuditTransition,
    TraceQuarantineIncident,
    TraceReducerPolicy,
)

_T = TypeVar("_T")


class TraceLiteStore:
    """Thread-safe SQLite WAL store with monotonic sequence keys and immutable triggers."""

    def __init__(self, db_path: str | Path = ":memory:"):
        self.db_path = str(db_path)
        self._lock = threading.RLock()
        self._seq_counter = itertools.count(1)
        self._conn: Optional[sqlite3.Connection] = None
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
        schema_path = Path(__file__).with_name("schema.sql")
        ddl = schema_path.read_text(encoding="utf-8")
        with self._lock:
            conn = self._get_conn()
            conn.executescript(ddl)
            conn.commit()

    def _next_unique_seq(self) -> int:
        return next(self._seq_counter)

    def _next_unique_id(self, prefix: str) -> str:
        seq = self._next_unique_seq()
        return f"{prefix}_{time.monotonic_ns()}_{seq}"

    def _run_with_retry(self, fn: Callable[[sqlite3.Connection], _T], max_attempts: int = 5) -> _T:
        for attempt in range(max_attempts):
            try:
                with self._lock:
                    conn = self._get_conn()
                    result = fn(conn)
                    conn.commit()
                    return result
            except sqlite3.OperationalError as exc:
                msg = str(exc).lower()
                if ("locked" in msg or "busy" in msg) and attempt < max_attempts - 1:
                    time.sleep(0.01 * (attempt + 1))
                    continue
                raise
        raise sqlite3.OperationalError("SQLite operation failed after retries")

    def record_reduction(
        self,
        window: ReducedTrajectoryWindow,
        policy: Optional[TraceReducerPolicy] = None,
        transitions: Iterable[TraceAuditTransition] = (),
        incidents: Iterable[TraceQuarantineIncident] = (),
    ) -> str:
        eff_policy = policy or TraceReducerPolicy()

        def _op(conn: sqlite3.Connection) -> str:
            created_seq = self._next_unique_seq()
            conn.execute(
                """
                INSERT INTO tracelite_trajectories (
                    reduction_id, trajectory_id, policy_id, lifecycle_state,
                    total_steps, recent_window_w, optical_ratio_k,
                    raw_tokens_total, reduced_tokens_total, tokens_saved,
                    aux_llm_allowed, actions_preserved, newest_preserved,
                    manifest_hash, created_seq
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    window.reduction_id,
                    window.trajectory_id,
                    window.policy_id,
                    window.lifecycle_state.value,
                    window.total_steps,
                    window.recent_window_w,
                    float(eff_policy.optical_ratio_k),
                    window.raw_tokens_total,
                    window.reduced_tokens_total,
                    window.tokens_saved,
                    0,
                    1 if window.actions_preserved else 0,
                    1 if window.newest_step_preserved else 0,
                    WAVE1C_MANIFEST_HASH,
                    created_seq,
                ),
            )
            for art in window.optical_artifacts:
                conn.execute(
                    """
                    INSERT INTO tracelite_optical_artifacts (
                        artifact_id, reduction_id, trajectory_id, step_index,
                        source_sha256, policy_hash, canvas_width_px, canvas_height_px,
                        patch_size_px, raw_text_tokens, optical_patch_tokens,
                        effective_compression_k, char_similarity, rendered_digest, created_seq
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        art.artifact_id,
                        window.reduction_id,
                        window.trajectory_id,
                        art.step_index,
                        art.source_sha256,
                        art.policy_hash,
                        art.canvas_width_px,
                        art.canvas_height_px,
                        art.patch_size_px,
                        art.raw_text_tokens,
                        art.optical_patch_tokens,
                        art.effective_compression_k,
                        art.char_similarity,
                        art.rendered_digest,
                        self._next_unique_seq(),
                    ),
                )
            for tr in transitions:
                tr_id = tr.transition_id or self._next_unique_id("tr")
                conn.execute(
                    """
                    INSERT INTO tracelite_audit_transitions (
                        transition_id, trajectory_id, from_state, event, to_state,
                        policy_id, manifest_hash, seq_no
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tr_id,
                        tr.trajectory_id,
                        tr.from_state.value,
                        tr.event.value,
                        tr.to_state.value,
                        tr.policy_id,
                        tr.manifest_hash,
                        self._next_unique_seq(),
                    ),
                )
            for inc in incidents:
                inc_id = inc.incident_id or self._next_unique_id("qi")
                conn.execute(
                    """
                    INSERT INTO tracelite_quarantine_incidents (
                        incident_id, trajectory_id, error_class, rule_code,
                        detail, step_index, created_seq
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        inc_id,
                        inc.trajectory_id,
                        inc.error_class.value,
                        inc.rule_code,
                        inc.detail,
                        inc.step_index,
                        self._next_unique_seq(),
                    ),
                )
            return window.reduction_id

        return self._run_with_retry(_op)

    def record_quarantine(self, incident: TraceQuarantineIncident) -> str:
        def _op(conn: sqlite3.Connection) -> str:
            inc_id = incident.incident_id or self._next_unique_id("qi")
            conn.execute(
                """
                INSERT INTO tracelite_quarantine_incidents (
                    incident_id, trajectory_id, error_class, rule_code,
                    detail, step_index, created_seq
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    inc_id,
                    incident.trajectory_id,
                    incident.error_class.value,
                    incident.rule_code,
                    incident.detail,
                    incident.step_index,
                    self._next_unique_seq(),
                ),
            )
            return inc_id

        return self._run_with_retry(_op)

    def get_reduction(self, reduction_id: str) -> Optional[dict]:
        with self._lock:
            row = self._get_conn().execute(
                "SELECT * FROM tracelite_trajectories WHERE reduction_id = ?",
                (reduction_id,),
            ).fetchone()
            return dict(row) if row is not None else None

    def list_optical_artifacts(self, trajectory_id: str) -> list[dict]:
        with self._lock:
            rows = self._get_conn().execute(
                """
                SELECT * FROM tracelite_optical_artifacts
                WHERE trajectory_id = ?
                ORDER BY created_seq ASC, step_index ASC
                """,
                (trajectory_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def list_transitions(self, trajectory_id: str) -> list[dict]:
        with self._lock:
            rows = self._get_conn().execute(
                """
                SELECT * FROM tracelite_audit_transitions
                WHERE trajectory_id = ?
                ORDER BY seq_no ASC
                """,
                (trajectory_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def list_quarantines(self, trajectory_id: Optional[str] = None) -> list[dict]:
        with self._lock:
            if trajectory_id is None:
                rows = self._get_conn().execute(
                    "SELECT * FROM tracelite_quarantine_incidents ORDER BY created_seq ASC"
                ).fetchall()
            else:
                rows = self._get_conn().execute(
                    """
                    SELECT * FROM tracelite_quarantine_incidents
                    WHERE trajectory_id = ?
                    ORDER BY created_seq ASC
                    """,
                    (trajectory_id,),
                ).fetchall()
            return [dict(r) for r in rows]

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def __enter__(self) -> "TraceLiteStore":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()
