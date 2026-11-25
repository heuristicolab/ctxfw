# manifest_hash: 4b3c6d65f2aeffd4fcfd8ecf166c4983ef94b046d3c9b7fd5e391811d32a5d82
# manifest_hash_wave2e1: b77d4295c196c37e848903d930d8d1a358fc9178b4dca90ba40fd28db264f37a
# manifest_hash_v422_burst_guard: f1329ba99a93db6abeaa6f185ce40327ce2260c53f29ef770477ff1bf22a2546
"""
ctxfw.mcp_guard.store — SQLite WAL Security Persistence & Immutable Ledgers
============================================================================
Provides thread-safe SQLite WAL persistence with bounded exponential retry for
cryptographic MCP tool pins, rug-pull drift detection, poisoning quarantine,
parameter binding audits, sandbox contracts, and OS confinement logs.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

from ctxfw.mcp_guard.contracts import (
    CLIENT_KEY_HASH_PATTERN,
    ERR_RATE_LIMIT_EXCEEDED,
    MAX_DESCRIPTION_CHARS,
    CapabilityLaunderingCheckResult,
    ChannelSurface,
    ConfinementCheckResult,
    ErrorClass,
    FirewallDecisionDTO,
    FirewallEvent,
    FirewallState,
    InferredSandboxBoundary,
    McpToolContractSpec,
    OracleVerdict,
    PairedDynamicValidation,
    ParameterBindingGuard,
    PoisonScanFinding,
    RateLimitDecisionDTO,
    RateLimitState,
    ToolCapabilityProfile,
    ToolRegistrationPin,
    ValidationVerdict,
    compute_tool_pin_hash,
    evaluate_capability_laundering,
    scan_description_risk,
    transition_firewall_state,
    utc_now_iso,
)

_CLIENT_KEY_HASH_RE = re.compile(CLIENT_KEY_HASH_PATTERN)

_T = TypeVar("_T")
_SCHEMA_PATH = Path(__file__).resolve().with_name("schema.sql")


def _new_id(prefix: str, seed: str) -> str:
    """Derive a deterministic or collision-resistant 16-hex identifier."""
    digest = hashlib.sha256(seed.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"{prefix}-{digest}"


class McpGuardStore:
    """Thread-safe SQLite WAL store for MCP Guard pins, quarantines, and confinement audits."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._seq_counter = itertools.count(1)
        self._conn = sqlite3.connect(
            str(self.db_path),
            timeout=30.0,
            isolation_level=None,
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        self._initialize_schema()

    def _next_unique_seed(self) -> str:
        """Return a collision-free per-call seed even when system timers lack sub-ms resolution."""
        with self._lock:
            seq = next(self._seq_counter)
        return f"{os.getpid()}:{time.perf_counter_ns()}:{seq}"

    def _initialize_schema(self) -> None:
        """Apply SQLite WAL PRAGMAs and load idempotent DDL schema."""
        ddl = _SCHEMA_PATH.read_text(encoding="utf-8")
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA synchronous=NORMAL;")
            self._conn.execute("PRAGMA foreign_keys=ON;")
            self._conn.execute("PRAGMA busy_timeout=5000;")
            self._conn.executescript(ddl)

    def _run_with_retry(self, fn: Callable[[], _T], *, max_attempts: int = 5) -> _T:
        """Class 1 TRANSIENT retry loop for SQLITE_BUSY / database locked contention."""
        delay = 0.005
        for attempt in range(max_attempts):
            try:
                return fn()
            except sqlite3.OperationalError as exc:
                msg = str(exc).lower()
                if ("locked" in msg or "busy" in msg) and attempt < max_attempts - 1:
                    time.sleep(delay)
                    delay = min(0.08, delay * 2.0)
                    continue
                raise
        raise sqlite3.OperationalError("Exceeded SQLITE_BUSY retry budget")

    def _atomic(self, fn: Callable[[sqlite3.Connection], _T]) -> _T:
        """Execute callback inside an atomic BEGIN IMMEDIATE SQLite transaction."""
        def _exec() -> _T:
            with self._lock:
                self._conn.execute("BEGIN IMMEDIATE;")
                try:
                    res = fn(self._conn)
                    self._conn.execute("COMMIT;")
                    return res
                except Exception:
                    try:
                        self._conn.execute("ROLLBACK;")
                    except sqlite3.Error:
                        pass
                    raise

        return self._run_with_retry(_exec)

    def register_or_verify_pin(
        self,
        server_id: str,
        tool_name: str,
        description: str,
        input_schema: Any = None,
        *,
        surface: ChannelSurface = ChannelSurface.TOOL_DESCRIPTION_POISONING,
        allow_cross_server_collision: bool = False,
    ) -> FirewallDecisionDTO:
        """Pin tool schema/description or fail-closed on rug-pull drift, collision, or poisoning."""
        bounded_desc = (description or "")[:MAX_DESCRIPTION_CHARS]
        pin_sha256 = compute_tool_pin_hash(server_id, tool_name, bounded_desc, input_schema)
        scan_finding = scan_description_risk(
            server_id,
            tool_name,
            bounded_desc,
            surface=surface,
            input_schema=input_schema,
        )
        now_iso = utc_now_iso()

        def _tx(conn: sqlite3.Connection) -> FirewallDecisionDTO:
            q_row = conn.execute(
                "SELECT quarantine_id, terminal_state, reason FROM poisoning_quarantine "
                "WHERE server_id = ? AND tool_name = ? ORDER BY quarantined_at_utc DESC LIMIT 1",
                (server_id, tool_name),
            ).fetchone()
            if q_row is not None:
                term_state = FirewallState(q_row["terminal_state"])
                verdict = (
                    ValidationVerdict.DENY_PIN_MISMATCH
                    if term_state is FirewallState.RUG_PULL_BLOCKED
                    else ValidationVerdict.DENY_POISON_DESCRIPTION
                )
                return FirewallDecisionDTO(
                    state=term_state,
                    verdict=verdict,
                    oracle_verdict=OracleVerdict.BLOCKED,
                    allowed=False,
                    findings=(scan_finding,) if scan_finding.quarantine_triggered else (),
                    trace=(FirewallState.UNVERIFIED, term_state),
                    quarantine_id=q_row["quarantine_id"],
                    reason=f"Tool '{server_id}.{tool_name}' already quarantined: {q_row['reason']}",
                )

            existing = conn.execute(
                "SELECT * FROM mcp_tool_pins WHERE server_id = ? AND tool_name = ?",
                (server_id, tool_name),
            ).fetchone()

            if existing is not None:
                existing_pin = ToolRegistrationPin(
                    pin_id=existing["pin_id"],
                    server_id=existing["server_id"],
                    tool_name=existing["tool_name"],
                    description_length=existing["description_length"],
                    pin_sha256=existing["pin_sha256"],
                    surface=ChannelSurface(existing["surface"]),
                    status=FirewallState(existing["status"]),
                    pinned_at_utc=existing["pinned_at_utc"],
                )
                if existing_pin.pin_sha256 != pin_sha256:
                    next_state = transition_firewall_state(FirewallState.PINNED, FirewallEvent.PIN_HASH_DRIFT)
                    qrn_id = _new_id("QRN", f"rugpull:{server_id}:{tool_name}:{pin_sha256}:{now_iso}")
                    p8_finding = PoisonScanFinding(
                        finding_id=_new_id("PSF", f"P8:{server_id}:{tool_name}:{pin_sha256}"),
                        server_id=server_id,
                        tool_name=tool_name,
                        vector="P8",
                        surface=surface,
                        imperative_risk_score=1.0,
                        invisible_unicode_detected=scan_finding.invisible_unicode_detected,
                        quarantine_triggered=True,
                        matched_signals=("PIN_HASH_DRIFT",),
                        summary=f"Rug-pull schema drift detected for {server_id}.{tool_name}",
                        detected_at_utc=now_iso,
                    )
                    self._insert_finding(conn, p8_finding)
                    self._insert_quarantine(
                        conn,
                        quarantine_id=qrn_id,
                        server_id=server_id,
                        tool_name=tool_name,
                        terminal_state=next_state,
                        vector="P8",
                        evidence_sha256=pin_sha256,
                        reason=f"SHA-256 pin mismatch (expected {existing_pin.pin_sha256[:12]}, got {pin_sha256[:12]})",
                        now_iso=now_iso,
                    )
                    self._insert_occ(conn, server_id, tool_name, pin_sha256, FirewallEvent.PIN_HASH_DRIFT.value, next_state.value, now_iso)
                    return FirewallDecisionDTO(
                        state=next_state,
                        verdict=ValidationVerdict.DENY_PIN_MISMATCH,
                        oracle_verdict=OracleVerdict.BLOCKED,
                        allowed=False,
                        pin=existing_pin,
                        findings=(p8_finding,),
                        trace=(FirewallState.PINNED, next_state),
                        quarantine_id=qrn_id,
                        reason=f"RUG_PULL_BLOCKED: pin mismatch for {server_id}.{tool_name}",
                    )

                next_state = transition_firewall_state(FirewallState.PINNED, FirewallEvent.VERIFY_PIN_MATCH)
                self._insert_occ(conn, server_id, tool_name, pin_sha256, FirewallEvent.VERIFY_PIN_MATCH.value, next_state.value, now_iso)
                return FirewallDecisionDTO(
                    state=next_state,
                    verdict=ValidationVerdict.ALLOW,
                    oracle_verdict=OracleVerdict.BENIGN,
                    allowed=True,
                    pin=existing_pin,
                    findings=(),
                    trace=(FirewallState.PINNED, next_state),
                    reason=f"Pin verified for {server_id}.{tool_name}",
                )

            if not allow_cross_server_collision:
                coll = conn.execute(
                    "SELECT server_id FROM mcp_tool_pins WHERE tool_name = ? AND server_id <> ? LIMIT 1",
                    (tool_name, server_id),
                ).fetchone()
                if coll is not None:
                    next_state = transition_firewall_state(FirewallState.UNVERIFIED, FirewallEvent.SCHEMA_COLLISION)
                    qrn_id = _new_id("QRN", f"collision:{server_id}:{tool_name}:{now_iso}")
                    p22_finding = PoisonScanFinding(
                        finding_id=_new_id("PSF", f"P22:{server_id}:{tool_name}:{now_iso}"),
                        server_id=server_id,
                        tool_name=tool_name,
                        vector="P22",
                        surface=surface,
                        imperative_risk_score=0.95,
                        invisible_unicode_detected=scan_finding.invisible_unicode_detected,
                        quarantine_triggered=True,
                        matched_signals=("CROSS_SERVER_TOOL_NAME_COLLISION",),
                        summary=f"Duplicate tool '{tool_name}' collides with server '{coll['server_id']}'",
                        detected_at_utc=now_iso,
                    )
                    self._insert_finding(conn, p22_finding)
                    self._insert_quarantine(
                        conn,
                        quarantine_id=qrn_id,
                        server_id=server_id,
                        tool_name=tool_name,
                        terminal_state=next_state,
                        vector="P22",
                        evidence_sha256=pin_sha256,
                        reason=f"Tool name collision against pinned server '{coll['server_id']}'",
                        now_iso=now_iso,
                    )
                    self._insert_occ(conn, server_id, tool_name, pin_sha256, FirewallEvent.SCHEMA_COLLISION.value, next_state.value, now_iso)
                    return FirewallDecisionDTO(
                        state=next_state,
                        verdict=ValidationVerdict.DENY_PIN_MISMATCH,
                        oracle_verdict=OracleVerdict.BLOCKED,
                        allowed=False,
                        findings=(p22_finding,),
                        trace=(FirewallState.UNVERIFIED, next_state),
                        quarantine_id=qrn_id,
                        reason=f"Tool collision blocked: '{tool_name}' already owned by '{coll['server_id']}'",
                    )

            if scan_finding.quarantine_triggered:
                next_state = transition_firewall_state(
                    FirewallState.UNVERIFIED, FirewallEvent.REGISTER_PIN, clean_pin=False
                )
                qrn_id = _new_id("QRN", f"poison:{server_id}:{tool_name}:{pin_sha256}")
                self._insert_finding(conn, scan_finding)
                self._insert_quarantine(
                    conn,
                    quarantine_id=qrn_id,
                    server_id=server_id,
                    tool_name=tool_name,
                    terminal_state=next_state,
                    vector=scan_finding.vector,
                    evidence_sha256=pin_sha256,
                    reason=scan_finding.summary,
                    now_iso=now_iso,
                )
                self._insert_occ(conn, server_id, tool_name, pin_sha256, FirewallEvent.POISON_SCORE_EXCEEDED.value, next_state.value, now_iso)
                return FirewallDecisionDTO(
                    state=next_state,
                    verdict=ValidationVerdict.DENY_POISON_DESCRIPTION,
                    oracle_verdict=OracleVerdict.BLOCKED,
                    allowed=False,
                    findings=(scan_finding,),
                    trace=(FirewallState.UNVERIFIED, next_state),
                    quarantine_id=qrn_id,
                    reason=scan_finding.summary,
                )

            new_pin = ToolRegistrationPin(
                pin_id=_new_id("PIN", f"{server_id}:{tool_name}:{pin_sha256}"),
                server_id=server_id,
                tool_name=tool_name,
                description_length=len(bounded_desc),
                pin_sha256=pin_sha256,
                surface=surface,
                status=FirewallState.PINNED,
                pinned_at_utc=now_iso,
            )
            conn.execute(
                "INSERT INTO mcp_tool_pins (pin_id, server_id, tool_name, description_length, pin_sha256, surface, status, pinned_at_utc) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_pin.pin_id,
                    new_pin.server_id,
                    new_pin.tool_name,
                    new_pin.description_length,
                    new_pin.pin_sha256,
                    new_pin.surface.value,
                    new_pin.status.value,
                    new_pin.pinned_at_utc,
                ),
            )
            self._insert_occ(conn, server_id, tool_name, pin_sha256, FirewallEvent.REGISTER_PIN.value, FirewallState.PINNED.value, now_iso)
            return FirewallDecisionDTO(
                state=FirewallState.PINNED,
                verdict=ValidationVerdict.ALLOW,
                oracle_verdict=OracleVerdict.BENIGN,
                allowed=True,
                pin=new_pin,
                findings=(),
                trace=(FirewallState.UNVERIFIED, FirewallState.PINNED),
                reason=f"Registered immutable SHA-256 pin for {server_id}.{tool_name}",
            )

        return self._atomic(_tx)

    def _insert_finding(self, conn: sqlite3.Connection, f: PoisonScanFinding) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO poison_scan_findings "
            "(finding_id, server_id, tool_name, vector, surface, imperative_risk_score, "
            "invisible_unicode_detected, quarantine_triggered, matched_signals_json, summary, detected_at_utc) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f.finding_id,
                f.server_id,
                f.tool_name,
                f.vector,
                f.surface.value,
                f.imperative_risk_score,
                1 if f.invisible_unicode_detected else 0,
                1 if f.quarantine_triggered else 0,
                json.dumps(list(f.matched_signals)),
                f.summary,
                f.detected_at_utc,
            ),
        )

    def _insert_quarantine(
        self,
        conn: sqlite3.Connection,
        *,
        quarantine_id: str,
        server_id: str,
        tool_name: str,
        terminal_state: FirewallState,
        vector: str,
        evidence_sha256: str,
        reason: str,
        now_iso: str,
    ) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO poisoning_quarantine "
            "(quarantine_id, server_id, tool_name, terminal_state, vector, evidence_sha256, reason, quarantined_at_utc) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                quarantine_id,
                server_id,
                tool_name,
                terminal_state.value,
                vector,
                evidence_sha256,
                reason[:512],
                now_iso,
            ),
        )

    def _insert_occ(
        self,
        conn: sqlite3.Connection,
        server_id: str,
        tool_name: str,
        pin_sha256: str,
        event_kind: str,
        state_after: str,
        now_iso: str,
    ) -> None:
        conn.execute(
            "INSERT INTO occ_version_ledger (server_id, tool_name, pin_sha256, event_kind, state_after, recorded_at_utc) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (server_id, tool_name, pin_sha256, event_kind, state_after, now_iso),
        )

    def check_and_record_param_binding(
        self,
        guard: ParameterBindingGuard,
        arguments: Dict[str, Any],
        *,
        server_id: str = "ctxfw-mcp",
    ) -> Tuple[bool, Tuple[str, ...], Tuple[str, ...]]:
        """Validate tool call arguments against schema allowlist and record audit trail."""
        ok, missing, unknown = guard.validate_arguments(arguments)
        verdict = "PASS" if ok else ("UNKNOWN_KEY_REJECTED" if unknown else "MISSING_REQUIRED")
        now_iso = utc_now_iso()
        audit_id = _new_id(
            "PBA",
            (
                f"{server_id}:{guard.tool_name}:{verdict}:"
                f"{','.join(unknown)}:{','.join(missing)}:{self._next_unique_seed()}"
            ),
        )

        def _tx(conn: sqlite3.Connection) -> None:
            conn.execute(
                "INSERT INTO param_binding_audits "
                "(audit_id, server_id, tool_name, binding_verdict, unknown_keys_json, missing_keys_json, audited_at_utc) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    audit_id,
                    server_id,
                    guard.tool_name,
                    verdict,
                    json.dumps(list(unknown)),
                    json.dumps(list(missing)),
                    now_iso,
                ),
            )

        self._atomic(_tx)
        return ok, missing, unknown

    def register_tool_contract(self, contract: McpToolContractSpec) -> McpToolContractSpec:
        """Persist a validated confinement contract forbidding unsandboxed fallback."""
        now_iso = utc_now_iso()
        contract_id = _new_id("CTR", f"{contract.server_id}:{contract.tool_name}:{','.join(contract.authorized_roots)}")

        def _tx(conn: sqlite3.Connection) -> None:
            conn.execute(
                "INSERT OR IGNORE INTO mcp_tool_contracts "
                "(contract_id, server_id, tool_name, authorized_roots_json, allow_unsandboxed_fallback, follow_symlinks, registered_at_utc) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    contract_id,
                    contract.server_id,
                    contract.tool_name,
                    json.dumps(list(contract.authorized_roots)),
                    0,
                    1 if contract.follow_symlinks else 0,
                    now_iso,
                ),
            )

        self._atomic(_tx)
        return contract

    def register_sandbox_boundary(self, boundary: InferredSandboxBoundary) -> InferredSandboxBoundary:
        """Persist a verified canary-disjoint sandbox boundary."""
        now_iso = utc_now_iso()

        def _tx(conn: sqlite3.Connection) -> None:
            conn.execute(
                "INSERT OR IGNORE INTO inferred_sandbox_boundaries "
                "(boundary_id, server_id, authorized_roots_json, canary_tokens_json, verified_disjoint, created_at_utc) "
                "VALUES (?, ?, ?, ?, 1, ?)",
                (
                    boundary.boundary_id,
                    boundary.server_id,
                    json.dumps(list(boundary.authorized_roots)),
                    json.dumps(list(boundary.canary_tokens)),
                    now_iso,
                ),
            )

        self._atomic(_tx)
        return boundary

    def record_confinement_check(
        self,
        server_id: str,
        tool_name: str,
        raw_path: str,
        result: ConfinementCheckResult,
    ) -> None:
        """Append immutable confinement audit log entry with hashed path candidate."""
        now_iso = utc_now_iso()
        raw_hash = hashlib.sha256((raw_path or "").encode("utf-8", errors="replace")).hexdigest()
        log_id = _new_id(
            "CNF",
            f"{server_id}:{tool_name}:{result.verdict.value}:{raw_hash}:{self._next_unique_seed()}",
        )

        def _tx(conn: sqlite3.Connection) -> None:
            conn.execute(
                "INSERT INTO confinement_audit_logs "
                "(log_id, server_id, tool_name, verdict, sarif_rule_id, raw_path_sha256, reason, logged_at_utc) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    log_id,
                    server_id,
                    tool_name,
                    result.verdict.value,
                    result.sarif_rule_id.value if result.sarif_rule_id else None,
                    raw_hash,
                    result.reason[:512],
                    now_iso,
                ),
            )

        self._atomic(_tx)

    def get_pin(self, server_id: str, tool_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve pinned tool record if registered."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM mcp_tool_pins WHERE server_id = ? AND tool_name = ?",
                (server_id, tool_name),
            ).fetchone()
            return dict(row) if row is not None else None

    def is_tool_quarantined(self, server_id: str, tool_name: str) -> bool:
        """Return True if a tool currently holds a quarantine record."""
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM poisoning_quarantine WHERE server_id = ? AND tool_name = ? LIMIT 1",
                (server_id, tool_name),
            ).fetchone()
            return row is not None

    def list_pins(self) -> List[Dict[str, Any]]:
        """List all immutable SHA-256 tool pins."""
        with self._lock:
            return [dict(r) for r in self._conn.execute("SELECT * FROM mcp_tool_pins ORDER BY pinned_at_utc").fetchall()]

    def list_findings(self) -> List[Dict[str, Any]]:
        """List all recorded poisoning scan findings."""
        with self._lock:
            return [dict(r) for r in self._conn.execute("SELECT * FROM poison_scan_findings ORDER BY detected_at_utc").fetchall()]

    def list_quarantines(self) -> List[Dict[str, Any]]:
        """List all active tool quarantine records."""
        with self._lock:
            return [dict(r) for r in self._conn.execute("SELECT * FROM poisoning_quarantine ORDER BY quarantined_at_utc").fetchall()]

    def list_confinement_logs(self) -> List[Dict[str, Any]]:
        """List all confinement verification audit logs."""
        with self._lock:
            return [dict(r) for r in self._conn.execute("SELECT * FROM confinement_audit_logs ORDER BY logged_at_utc").fetchall()]

    def list_param_audits(self) -> List[Dict[str, Any]]:
        """List all parameter binding verification logs."""
        with self._lock:
            return [dict(r) for r in self._conn.execute("SELECT * FROM param_binding_audits ORDER BY audited_at_utc").fetchall()]

    def record_paired_containment(self, validation: PairedDynamicValidation) -> str:
        """Persist paired dynamic PoC containment audit row (#04) atomically."""
        seq = next(self._seq_counter)
        now = utc_now_iso()
        audit_id = _new_id(
            "PCNT",
            f"{seq}:{validation.boundary_id}:{validation.server_id}:{validation.tool_name}:{now}",
        )

        def _tx(conn: sqlite3.Connection) -> str:
            conn.execute(
                """
                INSERT INTO paired_containment_audits (
                    audit_id, boundary_id, server_id, tool_name,
                    poc1_disclosed, poc2_benign_denied, poc3_disclosed,
                    canary_overlap_count, verdict, allowed, reason,
                    attestation_sha256, audited_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audit_id,
                    validation.boundary_id,
                    validation.server_id,
                    validation.tool_name,
                    int(validation.poc1_disclosed),
                    int(validation.poc2_benign_denied),
                    int(validation.poc3_disclosed),
                    int(validation.canary_overlap_count),
                    validation.verdict.value,
                    int(validation.allowed),
                    validation.reason,
                    validation.attestation_sha256,
                    now,
                ),
            )
            return audit_id

        return self._atomic(_tx)

    def evaluate_and_record_capability_laundering(
        self,
        profile: ToolCapabilityProfile,
        *,
        contract: Optional[McpToolContractSpec] = None,
        parameter_guard: Optional[ParameterBindingGuard] = None,
        raw_arguments: Optional[Dict[str, Any]] = None,
        quarantine_on_violation: bool = True,
    ) -> CapabilityLaunderingCheckResult:
        """Evaluate #04 capability laundering and persist immutable audit + optional quarantine."""
        result = evaluate_capability_laundering(
            profile,
            contract=contract,
            parameter_guard=parameter_guard,
            raw_arguments=raw_arguments,
        )
        seq = next(self._seq_counter)
        now = utc_now_iso()
        audit_id = _new_id(
            "CLND",
            f"{seq}:{result.server_id}:{result.tool_name}:{result.attestation_sha256}:{now}",
        )

        def _tx(conn: sqlite3.Connection) -> CapabilityLaunderingCheckResult:
            conn.execute(
                """
                INSERT INTO capability_laundering_audits (
                    audit_id, server_id, tool_name, declared_readonly,
                    allowed, laundering_detected, terminal_state,
                    violations_json, reason, attestation_sha256, audited_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audit_id,
                    result.server_id,
                    result.tool_name,
                    int(bool(profile.declared_readonly or (contract is not None and contract.declared_readonly))),
                    int(result.allowed),
                    int(result.laundering_detected),
                    result.terminal_state.value,
                    json.dumps(list(result.violations), ensure_ascii=True, separators=(",", ":")),
                    result.reason,
                    result.attestation_sha256,
                    now,
                ),
            )
            if result.laundering_detected and quarantine_on_violation:
                q_id = _new_id(
                    "QRN",
                    f"{seq}:cap:{result.server_id}:{result.tool_name}:{result.attestation_sha256}:{now}",
                )
                conn.execute(
                    """
                    INSERT INTO poisoning_quarantine (
                        quarantine_id, server_id, tool_name, terminal_state,
                        vector, evidence_sha256, reason, quarantined_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        q_id,
                        result.server_id,
                        result.tool_name,
                        FirewallState.CONFINED_DENY.value,
                        "PT-005",
                        result.attestation_sha256,
                        result.reason,
                        now,
                    ),
                )
            return result

        return self._atomic(_tx)

    def list_paired_containment_audits(self) -> List[Dict[str, Any]]:
        """List all persisted paired containment audit records (#04)."""
        with self._lock:
            return [
                dict(r)
                for r in self._conn.execute(
                    "SELECT * FROM paired_containment_audits ORDER BY audited_at_utc"
                ).fetchall()
            ]

    def list_capability_laundering_audits(self) -> List[Dict[str, Any]]:
        """List all persisted capability laundering audit records (#04)."""
        with self._lock:
            return [
                dict(r)
                for r in self._conn.execute(
                    "SELECT * FROM capability_laundering_audits ORDER BY audited_at_utc"
                ).fetchall()
            ]

    def record_rate_limit_rejection(
        self,
        server_id: str,
        decision: RateLimitDecisionDTO,
    ) -> str:
        """Persist an immutable Class 3 BUSINESS rate-limit rejection in SQLite WAL."""
        if not isinstance(server_id, str):
            raise ValueError("server_id must be a string")
        if not (1 <= len(server_id) <= 128):
            raise ValueError("server_id must be a non-empty string (<= 128 chars)")
        if not isinstance(decision, RateLimitDecisionDTO):
            raise ValueError("record_rate_limit_rejection requires a RateLimitDecisionDTO")
        expected_tuple = (
            False,
            RateLimitState.THROTTLED,
            ErrorClass.BUSINESS,
            ERR_RATE_LIMIT_EXCEEDED,
        )
        actual_tuple = (
            decision.allowed,
            decision.state,
            decision.error_class,
            decision.error_code,
        )
        if actual_tuple != expected_tuple:
            raise ValueError("Rate-limit audit row violates Class 3 BUSINESS throttled contract")
        if not _CLIENT_KEY_HASH_RE.fullmatch(decision.client_key_hash):
            raise ValueError("Rate-limit audit row violates Zero-Knowledge SHA-256 hash contract")

        def _tx(conn: sqlite3.Connection) -> str:
            now = utc_now_iso()
            seq = self._next_unique_seed()
            audit_id = _new_id(
                "RLM",
                f"{seq}:{server_id}:{decision.client_key_hash}:{decision.tool_name}:{decision.evaluated_at_ms}",
            )
            conn.execute(
                """
                INSERT INTO rate_limit_audit_logs (
                    audit_id, server_id, client_key_hash, tool_name,
                    state, error_class, error_code, remaining_tokens_q4,
                    retry_after_ms, clock_regressed, reason, evaluated_at_ms, audited_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audit_id,
                    server_id,
                    decision.client_key_hash,
                    decision.tool_name,
                    decision.state.value,
                    decision.error_class.value,
                    decision.error_code,
                    decision.remaining_tokens_q4,
                    decision.retry_after_ms,
                    int(decision.clock_regression_clamped),
                    decision.reason[:512],
                    decision.evaluated_at_ms,
                    now,
                ),
            )
            return audit_id

        return self._atomic(_tx)

    def list_rate_limit_audits(
        self,
        *,
        client_key_hash: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query persisted Zero-Knowledge rate-limit rejection records."""
        bounded_limit = max(1, min(1000, int(limit)))
        if client_key_hash is not None:
            if not _CLIENT_KEY_HASH_RE.fullmatch(client_key_hash):
                raise ValueError("client_key_hash filter must match ^[a-f0-9]{64}$")
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM rate_limit_audit_logs WHERE (? IS NULL OR client_key_hash = ?) "
                "ORDER BY rowid DESC LIMIT ?",
                (client_key_hash, client_key_hash, bounded_limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def close(self) -> None:
        """Close the SQLite WAL database connection cleanly."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None


__all__ = ["McpGuardStore"]
