# manifest_hash: ebbcd0d607fa09a71dda690ea76104d762b3f279cde258f64917421d39a249f4
"""PASAC Assurance SQLite WAL Store (Wave 1B :: #18).

CTXFW Axiomatic Gateway (Wave 1B): status VERIFIED | ACI 1.0000
manifest_hash: ebbcd0d607fa09a71dda690ea76104d762b3f279cde258f64917421d39a249f4

Thread-safe SQLite WAL persistence over assurance_schema.sql with bounded retries
on SQLITE_BUSY, monotonic append-only OCC version ledger, PEP decision logging,
containment quarantine records, and accountability role reauthorization signoffs.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple, TypeVar, Union

from ctxfw.sara.assurance import (
    AccountabilityRole,
    AgentRiskStateVector,
    AssuranceScopeContract,
    BoundaryAssuranceVector,
    CTXFW_MANIFEST_HASH,
    ContainmentQuarantineAlert,
    FailureErrorClass,
    HazardRegime,
    PasacLifecycleEvent,
    PasacLifecycleState,
    PolicyEnforcementDecision,
    PreflightStatus,
    TERMINAL_STATES,
    evaluate_pep_gate,
    format_pep_action_code,
    transition,
)

__all__ = [
    "ASSURANCE_SCHEMA_PATH",
    "PasacAssuranceStore",
    "load_assurance_schema_sql",
]

ASSURANCE_SCHEMA_PATH = Path(__file__).resolve().parent / "assurance_schema.sql"
_MAX_WAL_RETRIES: int = 5
_T = TypeVar("_T")


def load_assurance_schema_sql() -> str:
    """Return the sealed PASAC assurance SQLite WAL DDL (UTF-8)."""
    return ASSURANCE_SCHEMA_PATH.read_text(encoding="utf-8")


class PasacAssuranceStore:
    """Thread-safe SQLite WAL persistence for PASAC scope contracts, BAS probes, and PEP logs."""

    def __init__(self, db_path: Union[str, Path]) -> None:
        self._raw_path = str(db_path)
        self._is_memory = self._raw_path == ":memory:"
        if not self._is_memory:
            Path(self._raw_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            self._raw_path,
            timeout=5.0,
            isolation_level=None,
            check_same_thread=False,
        )
        self._conn.execute("PRAGMA journal_mode = WAL;")
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._conn.execute("PRAGMA busy_timeout = 5000;")
        self._conn.executescript(load_assurance_schema_sql())
        self._closed = False

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

    def register_scope_contract(
        self,
        contract: AssuranceScopeContract,
        *,
        lifecycle_state: PasacLifecycleState = PasacLifecycleState.PREFLIGHT_VERIFIED,
    ) -> int:
        """Persist or refresh a validated scope contract and append an immutable OCC ledger entry."""
        if not isinstance(contract, AssuranceScopeContract):
            raise TypeError("contract must be AssuranceScopeContract")
        if not isinstance(lifecycle_state, PasacLifecycleState):
            raise TypeError("lifecycle_state must be PasacLifecycleState")

        def _op() -> int:
            self._conn.execute("BEGIN IMMEDIATE;")
            try:
                existing = self._conn.execute(
                    "SELECT contract_digest FROM assurance_scope_contracts WHERE session_id = ?",
                    (contract.session_id,),
                ).fetchone()
                if existing is None:
                    self._conn.execute(
                        "INSERT INTO assurance_scope_contracts "
                        "(session_id, proposal_ref, egress_mode, live_egress_detected, "
                        "cross_run_writable, signoff_role, preflight_status, lifecycle_state, contract_digest) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            contract.session_id,
                            contract.proposal_id,
                            contract.egress_mode.value,
                            int(contract.live_egress_detected),
                            int(contract.cross_run_writable),
                            contract.signoff_role.value,
                            contract.preflight_status.value,
                            lifecycle_state.value,
                            contract.contract_digest,
                        ),
                    )
                    occ_ver = 1
                else:
                    self._conn.execute(
                        "UPDATE assurance_scope_contracts SET "
                        "proposal_ref = ?, egress_mode = ?, live_egress_detected = ?, "
                        "signoff_role = ?, preflight_status = ?, lifecycle_state = ?, contract_digest = ? "
                        "WHERE session_id = ?",
                        (
                            contract.proposal_id,
                            contract.egress_mode.value,
                            int(contract.live_egress_detected),
                            contract.signoff_role.value,
                            contract.preflight_status.value,
                            lifecycle_state.value,
                            contract.contract_digest,
                            contract.session_id,
                        ),
                    )
                    row = self._conn.execute(
                        "SELECT COALESCE(MAX(occ_version), 0) FROM occ_version_ledger WHERE session_id = ?",
                        (contract.session_id,),
                    ).fetchone()
                    occ_ver = int(row[0] or 0) + 1

                self._conn.execute(
                    "INSERT INTO occ_version_ledger "
                    "(session_id, occ_version, contract_digest, manifest_hash) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        contract.session_id,
                        occ_ver,
                        contract.contract_digest,
                        CTXFW_MANIFEST_HASH,
                    ),
                )
                self._conn.execute("COMMIT;")
                return occ_ver
            except Exception:
                self._conn.execute("ROLLBACK;")
                raise

        return self._run_with_retry(_op)

    def record_bas_probe(self, bas: BoundaryAssuranceVector) -> None:
        """Persist a 6-layer Boundary Assurance Stack probe."""
        if not isinstance(bas, BoundaryAssuranceVector):
            raise TypeError("bas must be BoundaryAssuranceVector")

        def _op() -> None:
            self._conn.execute("BEGIN IMMEDIATE;")
            try:
                self._conn.execute(
                    "INSERT OR REPLACE INTO boundary_assurance_probes "
                    "(probe_id, session_id, b_scope, b_identity, b_network, b_storage, "
                    "b_monitor, b_response, min_layer_floor) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        bas.probe_id,
                        bas.session_id,
                        bas.b_scope,
                        bas.b_identity,
                        bas.b_network,
                        bas.b_storage,
                        bas.b_monitor,
                        bas.b_response,
                        bas.min_layer_floor,
                    ),
                )
                self._conn.execute("COMMIT;")
            except Exception:
                self._conn.execute("ROLLBACK;")
                raise

        self._run_with_retry(_op)

    def record_risk_telemetry(self, risk_state: AgentRiskStateVector) -> None:
        """Persist quantitative risk state telemetry X_t."""
        if not isinstance(risk_state, AgentRiskStateVector):
            raise TypeError("risk_state must be AgentRiskStateVector")

        def _op() -> None:
            self._conn.execute("BEGIN IMMEDIATE;")
            try:
                self._conn.execute(
                    "INSERT OR REPLACE INTO agent_risk_telemetry "
                    "(telemetry_id, session_id, task_generality_g, agent_capability_c, "
                    "external_exposure_e, scope_weakness_s, monitoring_strength_m, "
                    "response_speed_r, hazard_l_t, tau_review, tau_stop) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        risk_state.telemetry_id,
                        risk_state.session_id,
                        risk_state.task_generality_g,
                        risk_state.agent_capability_c,
                        risk_state.external_exposure_e,
                        risk_state.scope_weakness_s,
                        risk_state.monitoring_strength_m,
                        risk_state.response_speed_r,
                        risk_state.hazard_l_t,
                        risk_state.tau_review,
                        risk_state.tau_stop,
                    ),
                )
                self._conn.execute("COMMIT;")
            except Exception:
                self._conn.execute("ROLLBACK;")
                raise

        self._run_with_retry(_op)

    def _next_unique_id(self, table: str, column: str, base_id: str, max_len: int) -> str:
        row = self._conn.execute(
            f"SELECT 1 FROM {table} WHERE {column} = ?",
            (base_id,),
        ).fetchone()
        if row is None:
            return base_id
        cnt_row = self._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        seq = int(cnt_row[0] or 0) + 1
        while True:
            suffix = f"_{seq}"
            candidate = f"{base_id[: max_len - len(suffix)]}{suffix}"
            exists = self._conn.execute(
                f"SELECT 1 FROM {table} WHERE {column} = ?",
                (candidate,),
            ).fetchone()
            if exists is None:
                return candidate
            seq += 1

    def evaluate_and_record_pep(
        self,
        contract: AssuranceScopeContract,
        bas: BoundaryAssuranceVector,
        risk_state: AgentRiskStateVector,
        *,
        action_code: str,
        in_authorized_scope: bool,
        resource_whitelisted: bool,
        action_risk: float,
        risk_threshold: float,
    ) -> PolicyEnforcementDecision:
        """Evaluate Allow(a), persist decision in WAL, and escalate/halt on SYNCHRONOUS_STOP or breach."""
        decision = evaluate_pep_gate(
            contract=contract,
            bas=bas,
            risk_state=risk_state,
            action_code=action_code,
            in_authorized_scope=in_authorized_scope,
            resource_whitelisted=resource_whitelisted,
            action_risk=action_risk,
            risk_threshold=risk_threshold,
        )

        def _op() -> PolicyEnforcementDecision:
            self._conn.execute("BEGIN IMMEDIATE;")
            try:
                cur_row = self._conn.execute(
                    "SELECT lifecycle_state FROM assurance_scope_contracts WHERE session_id = ?",
                    (contract.session_id,),
                ).fetchone()
                if cur_row is None:
                    init_state = (
                        PasacLifecycleState.ACTIVE_OBSERVED
                        if contract.preflight_status == PreflightStatus.VALID
                        else PasacLifecycleState.CONSTRAINED_CONTRACT
                    )
                    self._conn.execute(
                        "INSERT INTO assurance_scope_contracts "
                        "(session_id, proposal_ref, egress_mode, live_egress_detected, "
                        "cross_run_writable, signoff_role, preflight_status, lifecycle_state, contract_digest) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            contract.session_id,
                            contract.proposal_id,
                            contract.egress_mode.value,
                            int(contract.live_egress_detected),
                            int(contract.cross_run_writable),
                            contract.signoff_role.value,
                            contract.preflight_status.value,
                            init_state.value,
                            contract.contract_digest,
                        ),
                    )
                    occ_ver = 1
                    self._conn.execute(
                        "INSERT INTO occ_version_ledger "
                        "(session_id, occ_version, contract_digest, manifest_hash) "
                        "VALUES (?, ?, ?, ?)",
                        (contract.session_id, occ_ver, contract.contract_digest, CTXFW_MANIFEST_HASH),
                    )
                    cur_state = init_state
                else:
                    cur_state = PasacLifecycleState(cur_row[0])
                    if cur_state == PasacLifecycleState.PREFLIGHT_VERIFIED:
                        cur_state = transition(cur_state, PasacLifecycleEvent.E_START_SESSION)
                        self._conn.execute(
                            "UPDATE assurance_scope_contracts SET lifecycle_state = ? WHERE session_id = ?",
                            (cur_state.value, contract.session_id),
                        )

                self._conn.execute(
                    "INSERT OR REPLACE INTO boundary_assurance_probes "
                    "(probe_id, session_id, b_scope, b_identity, b_network, b_storage, "
                    "b_monitor, b_response, min_layer_floor) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        bas.probe_id,
                        bas.session_id,
                        bas.b_scope,
                        bas.b_identity,
                        bas.b_network,
                        bas.b_storage,
                        bas.b_monitor,
                        bas.b_response,
                        bas.min_layer_floor,
                    ),
                )
                self._conn.execute(
                    "INSERT OR REPLACE INTO agent_risk_telemetry "
                    "(telemetry_id, session_id, task_generality_g, agent_capability_c, "
                    "external_exposure_e, scope_weakness_s, monitoring_strength_m, "
                    "response_speed_r, hazard_l_t, tau_review, tau_stop) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        risk_state.telemetry_id,
                        risk_state.session_id,
                        risk_state.task_generality_g,
                        risk_state.agent_capability_c,
                        risk_state.external_exposure_e,
                        risk_state.scope_weakness_s,
                        risk_state.monitoring_strength_m,
                        risk_state.response_speed_r,
                        risk_state.hazard_l_t,
                        risk_state.tau_review,
                        risk_state.tau_stop,
                    ),
                )

                effective_code = self._next_unique_id(
                    "pep_enforcement_decisions", "decision_code", decision.decision_code, 44
                )
                effective_decision = (
                    decision
                    if effective_code == decision.decision_code
                    else decision.model_copy(update={"decision_code": effective_code})
                )

                self._conn.execute(
                    "INSERT INTO pep_enforcement_decisions "
                    "(decision_code, session_id, in_authorized_scope, resource_whitelisted, "
                    "action_risk, risk_threshold, allow_action, hazard_regime, "
                    "conservative_assurance, manifest_hash) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        effective_decision.decision_code,
                        effective_decision.session_id,
                        int(effective_decision.in_authorized_scope),
                        int(effective_decision.resource_whitelisted),
                        effective_decision.action_risk,
                        effective_decision.risk_threshold,
                        int(effective_decision.allow_action),
                        effective_decision.hazard_regime.value,
                        effective_decision.conservative_assurance,
                        effective_decision.manifest_hash,
                    ),
                )

                requires_containment = (
                    effective_decision.hazard_regime == HazardRegime.SYNCHRONOUS_STOP
                    or (
                        not effective_decision.allow_action
                        and (
                            effective_decision.conservative_assurance < bas.min_layer_floor
                            or contract.live_egress_detected
                        )
                    )
                )
                if requires_containment:
                    target_state = cur_state
                    if cur_state not in TERMINAL_STATES:
                        if cur_state == PasacLifecycleState.CONSTRAINED_CONTRACT:
                            target_state = transition(cur_state, PasacLifecycleEvent.E_FAIL_PREFLIGHT)
                        elif cur_state in (
                            PasacLifecycleState.ACTIVE_OBSERVED,
                            PasacLifecycleState.ELEVATED_REVIEW,
                        ):
                            ev = (
                                PasacLifecycleEvent.E_HAZARD_STOP
                                if effective_decision.hazard_regime == HazardRegime.SYNCHRONOUS_STOP
                                else PasacLifecycleEvent.E_PEP_DENY
                            )
                            if cur_state == PasacLifecycleState.ELEVATED_REVIEW:
                                ev = PasacLifecycleEvent.E_HAZARD_STOP
                            target_state = transition(cur_state, ev)
                        if target_state != cur_state:
                            self._conn.execute(
                                "UPDATE assurance_scope_contracts SET lifecycle_state = ? WHERE session_id = ?",
                                (target_state.value, contract.session_id),
                            )
                    occ_row = self._conn.execute(
                        "SELECT COALESCE(MAX(occ_version), 0) FROM occ_version_ledger WHERE session_id = ?",
                        (contract.session_id,),
                    ).fetchone()
                    next_occ = int(occ_row[0] or 0) + 1
                    self._conn.execute(
                        "INSERT INTO occ_version_ledger "
                        "(session_id, occ_version, contract_digest, manifest_hash) "
                        "VALUES (?, ?, ?, ?)",
                        (
                            contract.session_id,
                            next_occ,
                            contract.contract_digest,
                            CTXFW_MANIFEST_HASH,
                        ),
                    )
                    raw_alert_id = f"QALT-{format_pep_action_code(action_code)[:32]}"
                    alert_id = self._next_unique_id(
                        "assurance_breach_quarantine", "alert_id", raw_alert_id, 45
                    )
                    err_cls = (
                        FailureErrorClass.SECURITY
                        if (
                            effective_decision.hazard_regime == HazardRegime.SYNCHRONOUS_STOP
                            or contract.live_egress_detected
                        )
                        else FailureErrorClass.BUSINESS
                    )
                    role = (
                        AccountabilityRole.INCIDENT_LEAD
                        if err_cls == FailureErrorClass.SECURITY
                        else AccountabilityRole.SECURITY_LEAD
                    )
                    summary = (
                        f"PEP containment ({effective_decision.hazard_regime.value}): "
                        f"A_min={effective_decision.conservative_assurance:.2f}, "
                        f"R*={effective_decision.risk_index_r_star:.2f}"
                    )[:240]
                    self._conn.execute(
                        "INSERT INTO assurance_breach_quarantine "
                        "(alert_id, session_id, error_class, assigned_role, incident_summary, occ_version) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            alert_id,
                            contract.session_id,
                            err_cls.value,
                            role.value,
                            summary,
                            next_occ,
                        ),
                    )
                elif (
                    effective_decision.hazard_regime == HazardRegime.REVIEW_PAUSE
                    and cur_state == PasacLifecycleState.ACTIVE_OBSERVED
                ):
                    rev_state = transition(cur_state, PasacLifecycleEvent.E_HAZARD_REVIEW)
                    self._conn.execute(
                        "UPDATE assurance_scope_contracts SET lifecycle_state = ? WHERE session_id = ?",
                        (rev_state.value, contract.session_id),
                    )

                self._conn.execute("COMMIT;")
                return effective_decision
            except Exception:
                self._conn.execute("ROLLBACK;")
                raise

        return self._run_with_retry(_op)

    def record_breach_quarantine(self, alert: ContainmentQuarantineAlert) -> None:
        """Persist an immutable containment quarantine alert."""
        if not isinstance(alert, ContainmentQuarantineAlert):
            raise TypeError("alert must be ContainmentQuarantineAlert")

        def _op() -> None:
            self._conn.execute("BEGIN IMMEDIATE;")
            try:
                self._conn.execute(
                    "INSERT INTO assurance_breach_quarantine "
                    "(alert_id, session_id, error_class, assigned_role, incident_summary, occ_version) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        alert.alert_id,
                        alert.session_id,
                        alert.error_class.value,
                        alert.assigned_role.value,
                        alert.incident_summary,
                        alert.occ_version,
                    ),
                )
                self._conn.execute("COMMIT;")
            except Exception:
                self._conn.execute("ROLLBACK;")
                raise

        self._run_with_retry(_op)

    def record_reauthorization(
        self,
        *,
        signoff_code: str,
        session_id: str,
        accountability_role: AccountabilityRole,
        approval_rationale: str,
    ) -> PasacLifecycleState:
        """Record formal reauthorization sign-off and restore CONTAINMENT_HALTED -> PREFLIGHT_VERIFIED."""
        if not isinstance(accountability_role, AccountabilityRole):
            raise TypeError("accountability_role must be AccountabilityRole")
        rationale = str(approval_rationale or "").strip()
        if not (8 <= len(rationale) <= 240):
            raise ValueError("approval_rationale must be 8..240 chars")
        if not (8 <= len(signoff_code) <= 44):
            raise ValueError("signoff_code must be 8..44 chars")

        def _op() -> PasacLifecycleState:
            self._conn.execute("BEGIN IMMEDIATE;")
            try:
                row = self._conn.execute(
                    "SELECT lifecycle_state, contract_digest FROM assurance_scope_contracts "
                    "WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                if row is None:
                    raise ValueError(f"Unknown PASAC session_id: {session_id}")
                cur_state = PasacLifecycleState(row[0])
                digest = str(row[1])
                if cur_state == PasacLifecycleState.CONTAINMENT_HALTED:
                    next_state = transition(cur_state, PasacLifecycleEvent.E_REAUTHORIZE_PASS)
                elif cur_state == PasacLifecycleState.ELEVATED_REVIEW:
                    next_state = transition(cur_state, PasacLifecycleEvent.E_RESUME_APPROVED)
                else:
                    raise ValueError(
                        f"Session {session_id} in state {cur_state.value} cannot reauthorize"
                    )

                self._conn.execute(
                    "INSERT INTO reauthorization_signoffs "
                    "(signoff_code, session_id, accountability_role, approval_rationale) "
                    "VALUES (?, ?, ?, ?)",
                    (signoff_code, session_id, accountability_role.value, rationale),
                )
                self._conn.execute(
                    "UPDATE assurance_scope_contracts SET lifecycle_state = ?, preflight_status = ? "
                    "WHERE session_id = ?",
                    (next_state.value, PreflightStatus.VALID.value, session_id),
                )
                occ_row = self._conn.execute(
                    "SELECT COALESCE(MAX(occ_version), 0) FROM occ_version_ledger WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                next_occ = int(occ_row[0] or 0) + 1
                self._conn.execute(
                    "INSERT INTO occ_version_ledger "
                    "(session_id, occ_version, contract_digest, manifest_hash) "
                    "VALUES (?, ?, ?, ?)",
                    (session_id, next_occ, digest, CTXFW_MANIFEST_HASH),
                )
                self._conn.execute("COMMIT;")
                return next_state
            except Exception:
                self._conn.execute("ROLLBACK;")
                raise

        return self._run_with_retry(_op)

    def get_lifecycle_state(self, session_id: str) -> Optional[PasacLifecycleState]:
        """Return persisted lifecycle state for session_id, or None."""

        def _op() -> Optional[PasacLifecycleState]:
            row = self._conn.execute(
                "SELECT lifecycle_state FROM assurance_scope_contracts WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            return PasacLifecycleState(row[0]) if row else None

        return self._run_with_retry(_op)

    def get_latest_occ_version(self, session_id: str) -> int:
        """Return latest OCC version counter for session_id (0 if none)."""

        def _op() -> int:
            row = self._conn.execute(
                "SELECT COALESCE(MAX(occ_version), 0) FROM occ_version_ledger WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            return int(row[0] or 0) if row else 0

        return self._run_with_retry(_op)

    def get_metrics(self) -> Dict[str, int]:
        """Return deterministic row counts across PASAC assurance tables."""

        def _op() -> Dict[str, int]:
            tables = (
                ("contracts", "assurance_scope_contracts"),
                ("bas_probes", "boundary_assurance_probes"),
                ("risk_telemetry", "agent_risk_telemetry"),
                ("pep_decisions", "pep_enforcement_decisions"),
                ("reauthorizations", "reauthorization_signoffs"),
                ("occ_entries", "occ_version_ledger"),
                ("quarantine_alerts", "assurance_breach_quarantine"),
            )
            counts: Dict[str, int] = {}
            for key, tbl in tables:
                row = self._conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()
                counts[key] = int(row[0] or 0) if row else 0
            return counts

        return self._run_with_retry(_op)

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._conn.close()
                self._closed = True

    def __enter__(self) -> "PasacAssuranceStore":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()
