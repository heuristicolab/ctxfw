# manifest_hash: b77d4295c196c37e848903d930d8d1a358fc9178b4dca90ba40fd28db264f37a
"""
SARA Causal Provenance & Monotonic Epoch SQLite WAL Store
=========================================================
Wave 2 Block E.1 (Appendix H):
  - Isolated OCC ledger inside `provenance_occ_ledger` (zero collision with
    `occ_version_ledger`).
  - Persists digest-only graph edges, mutually-exclusive 3-class provenance
    traces, IPI/depth-truncated quarantine entries, and monotonic epoch replays.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import itertools
from pathlib import Path
import sqlite3
import threading
import time
from typing import Callable, FrozenSet, Optional, Sequence, TypeVar

from ctxfw.sara.provenance import (
    DEFAULT_MAX_CHAIN_DEPTH,
    PROVENANCE_MANIFEST_HASH,
    AlignmentStatus,
    IntentExecGraphEdge,
    MonotonicEpochVerdict,
    ProvenanceClassification,
    ProvenanceErrorClass,
    ProvenanceState,
    ProvenanceTraceResult,
    compute_epoch_attestation,
    evaluate_monotonic_epoch,
    trace_ipi_provenance,
)

PROVENANCE_SCHEMA_PATH: Path = Path(__file__).resolve().parent / "provenance_schema.sql"
_MAX_WAL_RETRIES: int = 5
_T = TypeVar("_T")


def load_provenance_schema_sql() -> str:
    """Return the canonical UTF-8 SQLite WAL DDL for Wave 2 E.1 provenance & epoch store."""
    return PROVENANCE_SCHEMA_PATH.read_text(encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProvenanceStore:
    """Thread-safe SQLite WAL store for causal provenance (#31) and monotonic epochs (#28)."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = str(db_path)
        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._seq_counter = itertools.count(1)
        self._conn: Optional[sqlite3.Connection] = sqlite3.connect(
            self._db_path,
            check_same_thread=False,
            isolation_level=None,
            timeout=5.0,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL;")
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._conn.execute("PRAGMA synchronous = NORMAL;")
        self._conn.execute("PRAGMA busy_timeout = 5000;")
        self._conn.executescript(load_provenance_schema_sql())

    def _conn_or_raise(self) -> sqlite3.Connection:
        conn = self._conn
        if conn is None:
            raise RuntimeError("ProvenanceStore connection is closed")
        return conn

    def close(self) -> None:
        """Close the underlying SQLite WAL handle cleanly."""
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

    def _next_occ_version(self, conn: sqlite3.Connection, scope_id: str) -> int:
        row = conn.execute(
            "SELECT COALESCE(MAX(occ_version), 0) FROM provenance_occ_ledger WHERE scope_id = ?",
            (scope_id,),
        ).fetchone()
        return (int(row[0]) if row is not None else 0) + 1

    def record_edge(self, *, session_id: str, edge: IntentExecGraphEdge) -> None:
        """Append a digest-only execution edge to provenance_graph_edges."""
        if not isinstance(edge, IntentExecGraphEdge):
            raise TypeError("edge must be IntentExecGraphEdge")
        now = _utc_now()

        def _op() -> None:
            conn = self._conn_or_raise()
            conn.execute("BEGIN IMMEDIATE;")
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO provenance_graph_edges "
                    "(edge_id, session_id, src_node, dst_node, tool_name, alignment_status, "
                    "tool_succeeded, payload_sha256, recorded_at_utc) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        edge.edge_id,
                        session_id,
                        edge.src_node,
                        edge.dst_node,
                        edge.tool_name,
                        edge.alignment_status.value,
                        int(edge.tool_succeeded),
                        edge.payload_sha256,
                        now,
                    ),
                )
                conn.execute("COMMIT;")
            except Exception:
                conn.execute("ROLLBACK;")
                raise

        self._run_with_retry(_op)

    def list_session_edges(self, session_id: str) -> tuple[IntentExecGraphEdge, ...]:
        """Load persisted session graph edges in insertion order."""
        def _op() -> tuple[IntentExecGraphEdge, ...]:
            conn = self._conn_or_raise()
            rows = conn.execute(
                "SELECT edge_id, src_node, dst_node, tool_name, alignment_status, tool_succeeded, payload_sha256 "
                "FROM provenance_graph_edges WHERE session_id = ? ORDER BY edge_seq ASC",
                (session_id,),
            ).fetchall()
            return tuple(
                IntentExecGraphEdge(
                    edge_id=str(r["edge_id"]),
                    src_node=str(r["src_node"]),
                    dst_node=str(r["dst_node"]),
                    tool_name=str(r["tool_name"]),
                    alignment_status=AlignmentStatus(str(r["alignment_status"])),
                    tool_succeeded=bool(int(r["tool_succeeded"])),
                    payload_sha256=str(r["payload_sha256"]),
                )
                for r in rows
            )

        return self._run_with_retry(_op)

    def evaluate_and_record_trace(
        self,
        *,
        session_id: str,
        sink_node: str,
        external_nodes: FrozenSet[str],
        edges: Optional[Sequence[IntentExecGraphEdge]] = None,
        max_depth: int = DEFAULT_MAX_CHAIN_DEPTH,
        trace_id: Optional[str] = None,
        expected_occ_version: Optional[int] = None,
    ) -> ProvenanceTraceResult:
        """Trace causal provenance, enforce optional OCC version, and persist verdict/quarantine."""
        now = _utc_now()

        def _op() -> ProvenanceTraceResult:
            conn = self._conn_or_raise()
            conn.execute("BEGIN IMMEDIATE;")
            try:
                if edges is None:
                    rows = conn.execute(
                        "SELECT edge_id, src_node, dst_node, tool_name, alignment_status, tool_succeeded, payload_sha256 "
                        "FROM provenance_graph_edges WHERE session_id = ? ORDER BY edge_seq ASC",
                        (session_id,),
                    ).fetchall()
                    graph_edges: Sequence[IntentExecGraphEdge] = tuple(
                        IntentExecGraphEdge(
                            edge_id=str(r["edge_id"]),
                            src_node=str(r["src_node"]),
                            dst_node=str(r["dst_node"]),
                            tool_name=str(r["tool_name"]),
                            alignment_status=AlignmentStatus(str(r["alignment_status"])),
                            tool_succeeded=bool(int(r["tool_succeeded"])),
                            payload_sha256=str(r["payload_sha256"]),
                        )
                        for r in rows
                    )
                else:
                    graph_edges = edges

                occ_row = conn.execute(
                    "SELECT COALESCE(MAX(occ_version), 0) FROM provenance_occ_ledger WHERE scope_id = ?",
                    (session_id,),
                ).fetchone()
                current_occ = int(occ_row[0]) if occ_row is not None else 0
                if expected_occ_version is not None and expected_occ_version != current_occ:
                    raise ValueError(
                        f"PROVENANCE_OCC_CONFLICT: expected={expected_occ_version} actual={current_occ}"
                    )

                seq_n = next(self._seq_counter)
                resolved_tid = trace_id or (
                    f"TRC-{hashlib.sha256(f'{session_id}:{sink_node}:{seq_n}:{now}'.encode('utf-8')).hexdigest()[:16]}"
                )
                result = trace_ipi_provenance(
                    sink_node=sink_node,
                    edges=graph_edges,
                    external_nodes=external_nodes,
                    max_depth=max_depth,
                    trace_id=resolved_tid,
                    session_id=session_id,
                )

                conn.execute(
                    "INSERT INTO provenance_traces "
                    "(trace_id, session_id, sink_node, classification, has_misaligned_sink_edge, "
                    "reaches_external_root, depth_truncated, terminal_state, error_class, "
                    "path_digest_sha256, attestation_sha256, recorded_at_utc) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        result.trace_id,
                        result.session_id,
                        result.sink_node,
                        result.classification.value,
                        int(result.has_misaligned_sink_edge),
                        int(result.reaches_external_root),
                        int(result.depth_truncated),
                        result.terminal_state.value,
                        result.error_class.value if result.error_class is not None else None,
                        result.path_digest_sha256,
                        result.attestation_sha256,
                        now,
                    ),
                )
                new_occ = current_occ + 1
                conn.execute(
                    "INSERT INTO provenance_occ_ledger "
                    "(scope_id, occ_version, attestation_sha256, recorded_at_utc) "
                    "VALUES (?, ?, ?, ?)",
                    (session_id, new_occ, result.attestation_sha256, now),
                )
                if result.classification is ProvenanceClassification.IPI_CONFIRMED:
                    qid = f"QPR-{hashlib.sha256(f'{result.trace_id}:{new_occ}:{now}'.encode('utf-8')).hexdigest()[:16]}"
                    conn.execute(
                        "INSERT INTO provenance_quarantine "
                        "(quarantine_id, trace_id, session_id, classification, depth_truncated, "
                        "error_class, path_digest_sha256, attestation_sha256, recorded_at_utc) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            qid,
                            result.trace_id,
                            result.session_id,
                            result.classification.value,
                            int(result.depth_truncated),
                            ProvenanceErrorClass.SECURITY.value,
                            result.path_digest_sha256,
                            result.attestation_sha256,
                            now,
                        ),
                    )
                conn.execute("COMMIT;")
                return result
            except Exception:
                conn.execute("ROLLBACK;")
                raise

        return self._run_with_retry(_op)

    def check_and_advance_epoch(
        self,
        *,
        scope_id: str,
        epoch_k: int,
        expected_occ_version: Optional[int] = None,
    ) -> MonotonicEpochVerdict:
        """Enforce monotonic epoch freshness k > last_consumed_k; log replay rejections without aborting."""
        now = _utc_now()

        def _op() -> MonotonicEpochVerdict:
            conn = self._conn_or_raise()
            conn.execute("BEGIN IMMEDIATE;")
            try:
                row = conn.execute(
                    "SELECT last_consumed_k, occ_version FROM epoch_freshness_scopes WHERE scope_id = ?",
                    (scope_id,),
                ).fetchone()
                last_k = int(row["last_consumed_k"]) if row is not None else -1
                current_occ = int(row["occ_version"]) if row is not None else 0

                if expected_occ_version is not None and expected_occ_version != current_occ:
                    reason = f"EPOCH_OCC_CONFLICT: expected={expected_occ_version} actual={current_occ}"
                    verdict = MonotonicEpochVerdict(
                        scope_id=scope_id,
                        epoch_k=epoch_k,
                        last_consumed_k=last_k,
                        allowed=False,
                        next_consumed_k=last_k,
                        error_class=ProvenanceErrorClass.SECURITY,
                        terminal_state=ProvenanceState.REJECTED_STALE_EPOCH,
                        reason=reason,
                        attestation_sha256=compute_epoch_attestation(
                            scope_id=scope_id,
                            epoch_k=epoch_k,
                            last_consumed_k=last_k,
                            allowed=False,
                        ),
                    )
                    self._insert_epoch_quarantine(conn, verdict, now)
                    conn.execute("COMMIT;")
                    return verdict

                verdict = evaluate_monotonic_epoch(
                    scope_id=scope_id,
                    epoch_k=epoch_k,
                    last_consumed_k=last_k,
                )
                if verdict.allowed:
                    new_occ = current_occ + 1
                    conn.execute(
                        "INSERT INTO epoch_freshness_scopes "
                        "(scope_id, last_consumed_k, occ_version, updated_at_utc) "
                        "VALUES (?, ?, ?, ?) "
                        "ON CONFLICT(scope_id) DO UPDATE SET "
                        "last_consumed_k = excluded.last_consumed_k, "
                        "occ_version = excluded.occ_version, "
                        "updated_at_utc = excluded.updated_at_utc",
                        (scope_id, epoch_k, new_occ, now),
                    )
                    ledger_occ = self._next_occ_version(conn, f"EPOCH:{scope_id}"[:64])
                    conn.execute(
                        "INSERT INTO provenance_occ_ledger "
                        "(scope_id, occ_version, attestation_sha256, recorded_at_utc) "
                        "VALUES (?, ?, ?, ?)",
                        (f"EPOCH:{scope_id}"[:64], ledger_occ, verdict.attestation_sha256, now),
                    )
                else:
                    self._insert_epoch_quarantine(conn, verdict, now)

                conn.execute("COMMIT;")
                return verdict
            except Exception:
                conn.execute("ROLLBACK;")
                raise

        return self._run_with_retry(_op)

    def _insert_epoch_quarantine(
        self,
        conn: sqlite3.Connection,
        verdict: MonotonicEpochVerdict,
        now: str,
    ) -> None:
        seq_n = next(self._seq_counter)
        rid = (
            f"QEP-{hashlib.sha256(f'{verdict.scope_id}:{verdict.epoch_k}:{verdict.last_consumed_k}:{seq_n}:{now}'.encode('utf-8')).hexdigest()[:16]}"
        )
        conn.execute(
            "INSERT INTO epoch_freshness_quarantine "
            "(rejection_id, scope_id, attempted_epoch_k, last_consumed_k, error_class, "
            "reason, attestation_sha256, recorded_at_utc) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                rid,
                verdict.scope_id,
                verdict.epoch_k,
                verdict.last_consumed_k,
                ProvenanceErrorClass.SECURITY.value,
                verdict.reason,
                verdict.attestation_sha256,
                now,
            ),
        )

    def get_last_consumed_epoch(self, scope_id: str) -> int:
        """Return latest consumed epoch for scope_id, or -1 if uninitialized."""
        def _op() -> int:
            conn = self._conn_or_raise()
            row = conn.execute(
                "SELECT last_consumed_k FROM epoch_freshness_scopes WHERE scope_id = ?",
                (scope_id,),
            ).fetchone()
            return int(row[0]) if row is not None else -1

        return self._run_with_retry(_op)

    def list_epoch_rejections(self, scope_id: str) -> list[dict]:
        """List persisted stale-epoch replay quarantine rows."""
        def _op() -> list[dict]:
            conn = self._conn_or_raise()
            rows = conn.execute(
                "SELECT * FROM epoch_freshness_quarantine WHERE scope_id = ? ORDER BY recorded_at_utc ASC",
                (scope_id,),
            ).fetchall()
            return [dict(r) for r in rows]

        return self._run_with_retry(_op)

    def list_occ_versions(self, scope_id: str) -> list[int]:
        """List monotonically increasing OCC versions recorded in provenance_occ_ledger."""
        def _op() -> list[int]:
            conn = self._conn_or_raise()
            rows = conn.execute(
                "SELECT occ_version FROM provenance_occ_ledger WHERE scope_id = ? ORDER BY occ_version ASC",
                (scope_id,),
            ).fetchall()
            return [int(r[0]) for r in rows]

        return self._run_with_retry(_op)

    def count_provenance_quarantines(self, session_id: str) -> int:
        """Return count of provenance_quarantine incidents for session_id."""
        def _op() -> int:
            conn = self._conn_or_raise()
            row = conn.execute(
                "SELECT COUNT(*) FROM provenance_quarantine WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            return int(row[0]) if row else 0

        return self._run_with_retry(_op)


__all__ = [
    "PROVENANCE_MANIFEST_HASH",
    "PROVENANCE_SCHEMA_PATH",
    "ProvenanceStore",
    "load_provenance_schema_sql",
]
