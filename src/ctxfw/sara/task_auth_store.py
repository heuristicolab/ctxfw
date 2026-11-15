# manifest_hash: ece9d70e52f09f3e80d8cadfd432c4b07a094ca40618ff12aa72a6f1cc92052a
"""
SARA Task-Scoped Paired-Replay SQLite WAL Store (#07 + #28)
===========================================================
manifest_hash_wave2e1: b77d4295c196c37e848903d930d8d1a358fc9178b4dca90ba40fd28db264f37a
Atomic persistence for task policies, durable DPoP anti-replay JTI nonces,
continuous `pre_state_sha256` state tracking, append-only `auth_occ_ledger`
(isolated from `occ_version_ledger`), optional monotonic epoch freshness (#28),
and quarantine forensics.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Callable, Optional, TypeVar

from ctxfw.sara.task_auth import (
    MAX_MULTIPLICITY_CEILING,
    TASK_AUTH_MANIFEST_HASH,
    AttackGoal,
    AuthReplayState,
    DpopProofContext,
    OpaRegoVerdictEnvelope,
    PairedReplayAuthorizationReceipt,
    ReplayErrorClass,
    StructuredToolCallEnvelope,
    TaskAuthorityPolicySpec,
    evaluate_scoped_tool_call,
)

TASK_AUTH_SCHEMA_PATH: Path = Path(__file__).resolve().parent / "task_auth_schema.sql"
_MAX_WAL_RETRIES: int = 5
_T = TypeVar("_T")


def load_task_auth_schema_sql() -> str:
    """Return the Wave 2 D.1 task-auth SQLite WAL DDL text (UTF-8)."""
    return TASK_AUTH_SCHEMA_PATH.read_text(encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskAuthStore:
    """Thread-safe SQLite WAL store for #07 task-scoped authorization & anti-replay."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
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
        self._conn.executescript(load_task_auth_schema_sql())

    def _conn_or_raise(self) -> sqlite3.Connection:
        conn = self._conn
        if conn is None:
            raise RuntimeError("TaskAuthStore connection is closed")
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

    def register_policy(
        self,
        policy: TaskAuthorityPolicySpec,
        *,
        initial_state_sha256: Optional[str] = None,
    ) -> str:
        """Persist task authority policy and initialize continuous state chain if absent."""
        if not isinstance(policy, TaskAuthorityPolicySpec):
            raise TypeError("policy must be TaskAuthorityPolicySpec")
        init_sha = (initial_state_sha256 or policy.expected_pre_state_sha256 or ("0" * 64)).lower()
        now = _utc_now()

        def _op() -> str:
            conn = self._conn_or_raise()
            conn.execute("BEGIN IMMEDIATE;")
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO task_auth_policies "
                    "(policy_id, task_id, session_id, allowed_domains_json, allowed_verbs_json, "
                    "allowed_scopes_json, max_multiplicity_k, policy_condition, require_dpop, "
                    "require_local_opa, created_at_utc) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        policy.policy_id,
                        policy.task_id,
                        policy.session_id,
                        json.dumps([str(d) for d in policy.allowed_domains]),
                        json.dumps([v.value for v in policy.allowed_verbs]),
                        json.dumps(list(policy.allowed_scopes)),
                        int(policy.max_multiplicity_k),
                        policy.policy_condition.value,
                        int(policy.require_dpop),
                        int(policy.require_local_opa),
                        now,
                    ),
                )
                existing_state = conn.execute(
                    "SELECT latest_state_sha256 FROM task_auth_session_state WHERE session_id = ?",
                    (policy.session_id,),
                ).fetchone()
                if existing_state is None:
                    conn.execute(
                        "INSERT INTO task_auth_session_state "
                        "(session_id, latest_state_sha256, occ_version, updated_at_utc) "
                        "VALUES (?, ?, 0, ?)",
                        (policy.session_id, init_sha, now),
                    )
                conn.execute("COMMIT;")
                return init_sha
            except Exception:
                conn.execute("ROLLBACK;")
                raise

        return self._run_with_retry(_op)

    def get_session_state(self, session_id: str) -> tuple[Optional[str], int]:
        """Return (latest_state_sha256, occ_version) for session_id."""
        def _op() -> tuple[Optional[str], int]:
            conn = self._conn_or_raise()
            row = conn.execute(
                "SELECT latest_state_sha256, occ_version FROM task_auth_session_state WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return None, 0
            return str(row[0]), int(row[1])

        return self._run_with_retry(_op)

    def is_dpop_jti_consumed(self, dpop_jti: str) -> bool:
        """Check whether dpop_jti has already been burned in SQLite WAL."""
        def _op() -> bool:
            conn = self._conn_or_raise()
            row = conn.execute(
                "SELECT 1 FROM task_auth_dpop_nonces WHERE dpop_jti = ?",
                (dpop_jti,),
            ).fetchone()
            return row is not None

        return self._run_with_retry(_op)

    def authorize_and_record(
        self,
        *,
        call: StructuredToolCallEnvelope,
        policy: Optional[TaskAuthorityPolicySpec],
        dpop_proof: Optional[DpopProofContext] = None,
        opa_verdict: Optional[OpaRegoVerdictEnvelope] = None,
        hmac_secret: Optional[bytes] = None,
        eddsa_verifier: Optional[Callable[[bytes, bytes], bool]] = None,
        now_epoch_sec: Optional[int] = None,
        expected_occ_version: Optional[int] = None,
        attack_goal: AttackGoal = AttackGoal.BENIGN_BASELINE,
        proposed_unsafe_action: bool = False,
        monotonic_epoch_k: Optional[int] = None,
        epoch_scope_id: Optional[str] = None,
    ) -> PairedReplayAuthorizationReceipt:
        """Atomically verify DPoP anti-replay, TTL, state continuity, multiplicity, local OPA, OCC, and optional epoch freshness."""
        now = _utc_now()
        effective_now = int(time.time()) if now_epoch_sec is None else int(now_epoch_sec)

        def _op() -> PairedReplayAuthorizationReceipt:
            conn = self._conn_or_raise()
            conn.execute("BEGIN IMMEDIATE;")
            try:
                state_row = conn.execute(
                    "SELECT latest_state_sha256, occ_version FROM task_auth_session_state WHERE session_id = ?",
                    (call.session_id,),
                ).fetchone()

                current_occ = int(state_row[1]) if state_row is not None else 0
                led_sha: Optional[str] = (
                    str(state_row[0])
                    if state_row is not None
                    else (policy.expected_pre_state_sha256 if policy is not None else None)
                )

                effective_policy = policy
                if policy is not None and led_sha is not None and policy.expected_pre_state_sha256 != led_sha:
                    effective_policy = policy.model_copy(update={"expected_pre_state_sha256": led_sha})

                # Cumulative multiplicity counted durably from allowed=1 rows inside BEGIN IMMEDIATE
                mult_row = conn.execute(
                    "SELECT COUNT(*) FROM task_auth_tool_decisions "
                    "WHERE task_id = ? AND session_id = ? AND allowed = 1",
                    (call.task_id, call.session_id),
                ).fetchone()
                persisted_allowed_count = int(mult_row[0]) if mult_row is not None else 0
                effective_multiplicity = min(
                    MAX_MULTIPLICITY_CEILING,
                    max(call.current_multiplicity, persisted_allowed_count),
                )
                effective_call = (
                    call
                    if effective_multiplicity == call.current_multiplicity
                    else call.model_copy(update={"current_multiplicity": effective_multiplicity})
                )

                seen_jtis: set[str] = set()
                if dpop_proof is not None:
                    seen_row = conn.execute(
                        "SELECT 1 FROM task_auth_dpop_nonces WHERE dpop_jti = ?",
                        (dpop_proof.dpop_jti,),
                    ).fetchone()
                    if seen_row is not None:
                        seen_jtis.add(dpop_proof.dpop_jti)

                epoch_scope_key: Optional[str] = None
                if monotonic_epoch_k is not None:
                    from ctxfw.sara.provenance import evaluate_monotonic_epoch

                    epoch_scope_key = epoch_scope_id or call.session_id
                    if len(epoch_scope_key) < 4:
                        epoch_scope_key = f"scope:{epoch_scope_key}"
                    ep_row = conn.execute(
                        "SELECT last_consumed_k FROM task_auth_epoch_scopes WHERE scope_id = ?",
                        (epoch_scope_key,),
                    ).fetchone()
                    last_k = int(ep_row[0]) if ep_row is not None else -1
                    epoch_verdict = evaluate_monotonic_epoch(
                        scope_id=epoch_scope_key,
                        epoch_k=monotonic_epoch_k,
                        last_consumed_k=last_k,
                    )
                    if not epoch_verdict.allowed:
                        from ctxfw.sara.task_auth import _build_receipt

                        receipt = _build_receipt(
                            call=effective_call,
                            policy=effective_policy,
                            state=AuthReplayState.QUARANTINED,
                            error_class=ReplayErrorClass.SECURITY,
                            allowed=False,
                            pre_sha=led_sha or ("0" * 64),
                            dpop_jti=(dpop_proof.dpop_jti if dpop_proof is not None else "stale_epoch"),
                            attack_goal=attack_goal,
                            proposed_unsafe_action=proposed_unsafe_action,
                            reasons=(epoch_verdict.reason,),
                        )
                        q_seed = f"epq:{epoch_scope_key}:{call.call_id}:{monotonic_epoch_k}:{now}"
                        eq_id = f"EPQ-{hashlib.sha256(q_seed.encode('utf-8')).hexdigest()[:16]}"
                        conn.execute(
                            "INSERT INTO task_auth_epoch_quarantine "
                            "(quarantine_id, scope_id, session_id, call_id, attempted_epoch_k, "
                            "last_consumed_k, error_class, reason, attestation_sha256, recorded_at_utc) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                eq_id,
                                epoch_scope_key,
                                call.session_id,
                                call.call_id,
                                int(monotonic_epoch_k),
                                int(last_k),
                                "SECURITY",
                                epoch_verdict.reason,
                                epoch_verdict.attestation_sha256,
                                now,
                            ),
                        )
                        self._persist_decision_rows(
                            conn=conn,
                            receipt=receipt,
                            call=effective_call,
                            dpop_proof=dpop_proof,
                            current_occ=current_occ,
                            now=now,
                        )
                        conn.execute("COMMIT;")
                        return receipt

                if expected_occ_version is not None and expected_occ_version != current_occ:
                    receipt = self._occ_mismatch_receipt(
                        call=effective_call,
                        policy=effective_policy,
                        pre_sha=led_sha or ("0" * 64),
                        expected_occ=expected_occ_version,
                        actual_occ=current_occ,
                        attack_goal=attack_goal,
                        proposed_unsafe_action=proposed_unsafe_action,
                    )
                else:
                    receipt = evaluate_scoped_tool_call(
                        call=effective_call,
                        policy=effective_policy,
                        dpop_proof=dpop_proof,
                        opa_verdict=opa_verdict,
                        seen_jtis=seen_jtis,
                        hmac_secret=hmac_secret,
                        eddsa_verifier=eddsa_verifier,
                        now_epoch_sec=effective_now,
                        attack_goal=attack_goal,
                        proposed_unsafe_action=proposed_unsafe_action,
                    )

                self._persist_decision_rows(
                    conn=conn,
                    receipt=receipt,
                    call=effective_call,
                    dpop_proof=dpop_proof,
                    current_occ=current_occ,
                    now=now,
                )
                if receipt.allowed and monotonic_epoch_k is not None and epoch_scope_key is not None:
                    conn.execute(
                        "INSERT INTO task_auth_epoch_scopes (scope_id, session_id, last_consumed_k, updated_at_utc) "
                        "VALUES (?, ?, ?, ?) "
                        "ON CONFLICT(scope_id) DO UPDATE SET "
                        "session_id = excluded.session_id, "
                        "last_consumed_k = excluded.last_consumed_k, "
                        "updated_at_utc = excluded.updated_at_utc",
                        (epoch_scope_key, call.session_id, int(monotonic_epoch_k), now),
                    )
                conn.execute("COMMIT;")
                return receipt
            except Exception:
                conn.execute("ROLLBACK;")
                raise

        return self._run_with_retry(_op)

    def _occ_mismatch_receipt(
        self,
        *,
        call: StructuredToolCallEnvelope,
        policy: Optional[TaskAuthorityPolicySpec],
        pre_sha: str,
        expected_occ: int,
        actual_occ: int,
        attack_goal: AttackGoal,
        proposed_unsafe_action: bool,
    ) -> PairedReplayAuthorizationReceipt:
        from ctxfw.sara.task_auth import _build_receipt

        return _build_receipt(
            call=call,
            policy=policy,
            state=AuthReplayState.DENIED,
            error_class=ReplayErrorClass.BUSINESS,
            allowed=False,
            pre_sha=pre_sha,
            dpop_jti="occ_conflict",
            attack_goal=attack_goal,
            proposed_unsafe_action=proposed_unsafe_action,
            reasons=(f"AUTH_OCC_VERSION_CONFLICT: expected={expected_occ} actual={actual_occ}",),
        )

    def _persist_decision_rows(
        self,
        *,
        conn: sqlite3.Connection,
        receipt: PairedReplayAuthorizationReceipt,
        call: StructuredToolCallEnvelope,
        dpop_proof: Optional[DpopProofContext],
        current_occ: int,
        now: str,
    ) -> None:
        conn.execute(
            "INSERT OR REPLACE INTO task_auth_tool_decisions "
            "(decision_id, call_id, task_id, session_id, domain_name, verb, tool_name, "
            "state, error_class, allowed, decision_seal_sha256, created_at_utc) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                receipt.receipt_id,
                call.call_id,
                call.task_id,
                call.session_id,
                str(call.domain),
                call.verb.value,
                call.tool_name,
                receipt.state.value,
                receipt.error_class.value if receipt.error_class else None,
                int(receipt.allowed),
                receipt.decision_seal_sha256,
                now,
            ),
        )
        conn.execute(
            "INSERT OR REPLACE INTO task_auth_paired_replays "
            "(receipt_id, task_id, session_id, domain_name, attack_goal, policy_condition, "
            "compromise_c, executed_y, harmful_execution_h, decision_seal_sha256, created_at_utc) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                receipt.receipt_id,
                receipt.task_id,
                receipt.session_id,
                str(receipt.domain),
                receipt.attack_goal.value,
                receipt.policy_condition.value,
                int(receipt.compromise_c),
                int(receipt.executed_y),
                int(receipt.harmful_execution_h),
                receipt.decision_seal_sha256,
                now,
            ),
        )
        if receipt.allowed:
            new_occ = current_occ + 1
            if dpop_proof is not None:
                expected_htm = call.verb.value
                expected_htu = f"mcp://{call.domain}/{call.tool_name}"
                conn.execute(
                    "INSERT INTO task_auth_dpop_nonces "
                    "(dpop_jti, session_id, pre_state_sha256, post_state_sha256, htm, htu, consumed_at_utc) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        dpop_proof.dpop_jti,
                        call.session_id,
                        dpop_proof.pre_state_sha256,
                        receipt.post_state_sha256,
                        expected_htm,
                        expected_htu,
                        now,
                    ),
                )
            conn.execute(
                "INSERT INTO task_auth_session_state "
                "(session_id, latest_state_sha256, occ_version, updated_at_utc) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(session_id) DO UPDATE SET "
                "latest_state_sha256 = excluded.latest_state_sha256, "
                "occ_version = excluded.occ_version, "
                "updated_at_utc = excluded.updated_at_utc",
                (call.session_id, receipt.post_state_sha256, new_occ, now),
            )
            conn.execute(
                "INSERT INTO auth_occ_ledger "
                "(session_id, occ_version, decision_seal_sha256, manifest_hash, recorded_at_utc) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    call.session_id,
                    new_occ,
                    receipt.decision_seal_sha256,
                    TASK_AUTH_MANIFEST_HASH,
                    now,
                ),
            )
        elif receipt.state == AuthReplayState.QUARANTINED or receipt.error_class == ReplayErrorClass.SECURITY:
            qid = f"QTA-{hashlib.sha256((call.call_id + receipt.decision_seal_sha256).encode('utf-8')).hexdigest()[:16]}"
            p_digest = hashlib.sha256((call.raw_context_text or call.tool_name).encode("utf-8")).hexdigest()
            conn.execute(
                "INSERT OR IGNORE INTO task_auth_quarantine "
                "(quarantine_id, session_id, call_id, error_class, reason, dpop_jti, payload_digest_sha256, recorded_at_utc) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    qid,
                    call.session_id,
                    call.call_id,
                    (receipt.error_class or ReplayErrorClass.SECURITY).value,
                    "; ".join(receipt.reasons)[:512],
                    dpop_proof.dpop_jti if dpop_proof is not None else None,
                    p_digest,
                    now,
                ),
            )

    def list_auth_occ_versions(self, session_id: str) -> list[int]:
        """Return monotonically ordered OCC versions recorded in isolated auth_occ_ledger."""
        def _op() -> list[int]:
            conn = self._conn_or_raise()
            rows = conn.execute(
                "SELECT occ_version FROM auth_occ_ledger WHERE session_id = ? ORDER BY occ_version ASC",
                (session_id,),
            ).fetchall()
            return [int(r[0]) for r in rows]

        return self._run_with_retry(_op)

    def count_quarantines(self, session_id: str) -> int:
        """Count quarantine incidents logged for a session."""
        def _op() -> int:
            conn = self._conn_or_raise()
            row = conn.execute(
                "SELECT COUNT(*) FROM task_auth_quarantine WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            return int(row[0]) if row else 0

        return self._run_with_retry(_op)

    def get_last_consumed_epoch(self, scope_id: str) -> int:
        """Return latest consumed monotonic epoch k for scope_id, or -1 if uninitialized (#28)."""
        def _op() -> int:
            conn = self._conn_or_raise()
            row = conn.execute(
                "SELECT last_consumed_k FROM task_auth_epoch_scopes WHERE scope_id = ?",
                (scope_id,),
            ).fetchone()
            return int(row[0]) if row is not None else -1

        return self._run_with_retry(_op)

    def list_epoch_quarantines(self, scope_id: Optional[str] = None) -> list[dict]:
        """List persisted stale-epoch replay quarantine rows (#28)."""
        def _op() -> list[dict]:
            conn = self._conn_or_raise()
            if scope_id is None:
                cur = conn.execute(
                    "SELECT * FROM task_auth_epoch_quarantine ORDER BY recorded_at_utc ASC"
                )
            else:
                cur = conn.execute(
                    "SELECT * FROM task_auth_epoch_quarantine WHERE scope_id = ? ORDER BY recorded_at_utc ASC",
                    (scope_id,),
                )
            cols = [str(d[0]) for d in (cur.description or ())]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

        return self._run_with_retry(_op)
