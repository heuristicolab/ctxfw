# manifest_hash: ebbcd0d607fa09a71dda690ea76104d762b3f279cde258f64917421d39a249f4
"""Verification Matrix for Wave 1 Block B :: Proactive Agent Assurance & PASAC Boundary Gate (#18).

Validates:
1. All #18 Pydantic v2 immutable DTOs, INV-B1..INV-B7 invariants, NaN/Inf rejection,
   8-state PASAC FSM transitions, 6-layer non-masking BAS math, parametric risk R*_t,
   and four-predicate conjunctive PEP Allow(a) gate.
2. SQLite WAL 7-table schema, CHECK constraints, ON DELETE CASCADE, BEFORE UPDATE
   immutability triggers, 10-thread concurrency, and zero CRLF line-ending invariance.
3. Lazy loading preservation on ctxfw.sara and RuntimeAuthorizationGate.evaluate_pasac_pep.
4. End-to-end MCPServer PEP enforcement, SYNCHRONOUS_STOP halt -> reauthorization lifecycle,
   stdio JSON-RPC stdout purity, and ctxfw doctor Project PASAC Boundary Assurance checks.
"""
from __future__ import annotations

import io
import json
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from pydantic import ValidationError

from ctxfw.installer import init_repository_perimeter, run_doctor
from ctxfw.mcp import MCPServer
from ctxfw.sara import (
    ASSURANCE_SCHEMA_PATH,
    AccountabilityRole,
    AgentRiskStateVector,
    AssuranceScopeContract,
    BoundaryAssuranceVector,
    EgressPolicyMode,
    FailureErrorClass,
    HazardRegime,
    PasacAssuranceStore,
    PasacLifecycleEvent,
    PasacLifecycleState,
    PreflightStatus,
    RuntimeAuthorizationGate,
    assess_runtime_isolation_posture,
    classify_hazard_regime,
    compute_boundary_assurances,
    compute_parametric_risk_r_star,
    evaluate_pep_gate,
    load_assurance_schema_sql,
    pasac_transition,
)
from ctxfw.storage.cache import LocalSemanticCache


def _digest(ch: str = "b") -> str:
    return ch * 64


def _nominal_inputs(session_id: str = "PASAC-OPUS-EVAL-01"):
    contract = AssuranceScopeContract(
        session_id=session_id,
        egress_mode=EgressPolicyMode.OFFLINE_ISOLATED,
        live_egress_detected=False,
        cross_run_writable=False,
        preflight_status=PreflightStatus.VALID,
        contract_digest=_digest(),
    )
    bas = BoundaryAssuranceVector(
        probe_id="BAS-NET-01",
        session_id=session_id,
        b_scope=0.95,
        b_identity=0.90,
        b_network=0.92,
        b_storage=0.94,
        b_monitor=0.88,
        b_response=0.85,
        min_layer_floor=0.70,
    )
    risk = AgentRiskStateVector(
        telemetry_id="RISK-VEC-01",
        session_id=session_id,
        task_generality_g=0.5,
        agent_capability_c=0.8,
        external_exposure_e=0.2,
        scope_weakness_s=0.1,
        monitoring_strength_m=0.9,
        response_speed_r=0.85,
        impact_severity_i=20.0,
        exposure_duration_d=10.0,
        hazard_l_t=0.20,
        tau_review=0.40,
        tau_stop=0.75,
    )
    return contract, bas, risk


def test_wave1b_files_carry_manifest_hash_and_zero_crlf():
    from ctxfw.sara import PACKAGE_DIR

    targets = (
        PACKAGE_DIR / "assurance.py",
        PACKAGE_DIR / "assurance_schema.sql",
        PACKAGE_DIR / "assurance_store.py",
        Path(__file__).resolve(),
    )
    expected_hash = "ebbcd0d607fa09a71dda690ea76104d762b3f279cde258f64917421d39a249f4"
    for path in targets:
        raw = path.read_bytes()
        assert b"\r" not in raw, f"{path.name} contains CR byte"
        assert expected_hash in raw.decode("utf-8"), f"{path.name} missing manifest_hash"


def test_sara_lazy_import_preserved_with_wave1b():
    code = (
        "import sys, ctxfw.sara;"
        "assert 'ctxfw.sara.contracts' not in sys.modules;"
        "assert 'ctxfw.sara.assurance' not in sys.modules;"
        "assert 'ctxfw.sara.assurance_store' not in sys.modules;"
        "_ = ctxfw.sara.AssuranceScopeContract;"
        "_ = ctxfw.sara.PasacAssuranceStore;"
        "assert 'ctxfw.sara.assurance' in sys.modules;"
        "assert 'ctxfw.sara.assurance_store' in sys.modules;"
        "print('LAZY_OK')"
    )
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert res.stdout.strip() == "LAZY_OK"


def test_valid_pasac_models_and_strict_immutability():
    contract, bas, risk = _nominal_inputs()
    assert contract.preflight_status == PreflightStatus.VALID
    assert bas.b_network == pytest.approx(0.92)
    assert risk.tau_review < risk.tau_stop

    with pytest.raises((TypeError, ValidationError)):
        setattr(contract, "cross_run_writable", True)

    with pytest.raises(ValidationError):
        BoundaryAssuranceVector(
            probe_id="BAS-EXTRA-01",
            session_id="PASAC-OPUS-EVAL-01",
            b_scope=0.9,
            b_identity=0.9,
            b_network=0.9,
            b_storage=0.9,
            b_monitor=0.9,
            b_response=0.9,
            **{"rogue_flag": True},
        )


def test_pasac_invariants_reject_cross_run_write_offline_leak_and_bad_bounds():
    with pytest.raises(ValidationError):
        AssuranceScopeContract(
            session_id="PASAC-HF-BOARD",
            egress_mode=EgressPolicyMode.OFFLINE_ISOLATED,
            cross_run_writable=True,
            contract_digest=_digest(),
        )

    with pytest.raises(ValidationError):
        AssuranceScopeContract(
            session_id="PASAC-ANTHROPIC-LEAK",
            egress_mode=EgressPolicyMode.OFFLINE_ISOLATED,
            live_egress_detected=True,
            preflight_status=PreflightStatus.VALID,
            contract_digest=_digest(),
        )

    with pytest.raises(ValidationError):
        AgentRiskStateVector(
            telemetry_id="RISK-BAD-TAU",
            session_id="PASAC-OPUS-EVAL-01",
            task_generality_g=0.5,
            agent_capability_c=0.5,
            external_exposure_e=0.5,
            scope_weakness_s=0.5,
            monitoring_strength_m=0.5,
            response_speed_r=0.5,
            impact_severity_i=10.0,
            exposure_duration_d=5.0,
            hazard_l_t=0.3,
            tau_review=0.80,
            tau_stop=0.60,
        )

    with pytest.raises(ValidationError):
        BoundaryAssuranceVector(
            probe_id="BAS-OOB-01",
            session_id="PASAC-OPUS-EVAL-01",
            b_scope=1.25,
            b_identity=0.9,
            b_network=0.9,
            b_storage=0.9,
            b_monitor=0.9,
            b_response=0.9,
        )

    with pytest.raises(ValidationError):
        BoundaryAssuranceVector(
            probe_id="BAS-NAN-01",
            session_id="PASAC-OPUS-EVAL-01",
            b_scope=float("nan"),
            b_identity=0.9,
            b_network=0.9,
            b_storage=0.9,
            b_monitor=0.9,
            b_response=0.9,
        )


def test_pasac_deterministic_fsm_transitions_and_terminal_locks():
    s = PasacLifecycleState.ANTICIPATE_DRAFT
    s = pasac_transition(s, PasacLifecycleEvent.E_LOCK_SCOPE_CONTRACT)
    s = pasac_transition(s, PasacLifecycleEvent.E_PASS_PREFLIGHT)
    s = pasac_transition(s, PasacLifecycleEvent.E_START_SESSION)
    s = pasac_transition(s, PasacLifecycleEvent.E_HAZARD_REVIEW)
    s = pasac_transition(s, PasacLifecycleEvent.E_HAZARD_STOP)
    assert s == PasacLifecycleState.CONTAINMENT_HALTED
    s = pasac_transition(s, PasacLifecycleEvent.E_REAUTHORIZE_PASS)
    assert s == PasacLifecycleState.PREFLIGHT_VERIFIED

    with pytest.raises(ValueError):
        pasac_transition(
            PasacLifecycleState.QUARANTINED_BREACH,
            PasacLifecycleEvent.E_REAUTHORIZE_PASS,
        )
    with pytest.raises(ValueError):
        pasac_transition(
            PasacLifecycleState.ANTICIPATE_DRAFT,
            PasacLifecycleEvent.E_START_SESSION,
        )


def test_bas_non_masking_risk_r_star_and_pep_conjunction():
    bas = BoundaryAssuranceVector(
        probe_id="BAS-WEAK-NET",
        session_id="PASAC-OPUS-EVAL-01",
        b_scope=0.99,
        b_identity=0.99,
        b_network=0.05,
        b_storage=0.99,
        b_monitor=0.99,
        b_response=0.99,
        min_layer_floor=0.70,
    )
    a_min, a_prod = compute_boundary_assurances(bas)
    assert a_min == pytest.approx(0.05)
    assert a_prod <= 0.05

    contract, nom_bas, low_risk = _nominal_inputs()
    high_risk = AgentRiskStateVector(
        telemetry_id="RISK-HIGH-01",
        session_id="PASAC-OPUS-EVAL-01",
        task_generality_g=0.9,
        agent_capability_c=0.95,
        external_exposure_e=0.9,
        scope_weakness_s=0.85,
        monitoring_strength_m=0.1,
        response_speed_r=0.1,
        impact_severity_i=20.0,
        exposure_duration_d=10.0,
        hazard_l_t=0.85,
    )
    assert compute_parametric_risk_r_star(high_risk) > compute_parametric_risk_r_star(low_risk)
    assert classify_hazard_regime(0.20, 0.40, 0.75) == HazardRegime.NOMINAL_ALLOW
    assert classify_hazard_regime(0.50, 0.40, 0.75) == HazardRegime.REVIEW_PAUSE
    assert classify_hazard_regime(0.80, 0.40, 0.75) == HazardRegime.SYNCHRONOUS_STOP

    allow_dec = evaluate_pep_gate(
        contract, nom_bas, low_risk, "TOOL-CURL-01", True, True, 0.15, 0.50
    )
    assert allow_dec.allow_action is True
    assert allow_dec.hazard_regime == HazardRegime.NOMINAL_ALLOW

    denied_wl = evaluate_pep_gate(
        contract, nom_bas, low_risk, "TOOL-SSRF-01", True, False, 0.10, 0.50
    )
    assert denied_wl.allow_action is False

    denied_bas = evaluate_pep_gate(
        contract, bas, low_risk, "TOOL-WEAK-01", True, True, 0.10, 0.50
    )
    assert denied_bas.allow_action is False

    stop_risk = low_risk.model_copy(update={"hazard_l_t": 0.80})
    halted = evaluate_pep_gate(
        contract, nom_bas, stop_risk, "TOOL-STOP-01", True, True, 0.10, 0.50
    )
    assert halted.hazard_regime == HazardRegime.SYNCHRONOUS_STOP
    assert halted.allow_action is False


def test_assurance_schema_sql_constraints_cascades_and_triggers():
    ddl = load_assurance_schema_sql()
    assert ASSURANCE_SCHEMA_PATH.is_file()
    conn = sqlite3.connect(":memory:")
    conn.executescript(ddl)

    tables = {
        r[0]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    expected = {
        "assurance_scope_contracts",
        "boundary_assurance_probes",
        "agent_risk_telemetry",
        "pep_enforcement_decisions",
        "reauthorization_signoffs",
        "occ_version_ledger",
        "assurance_breach_quarantine",
    }
    assert expected.issubset(tables)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO assurance_scope_contracts "
            "(session_id, proposal_ref, egress_mode, live_egress_detected, cross_run_writable, "
            "signoff_role, preflight_status, lifecycle_state, contract_digest) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "PASAC-SQL-BAD",
                "PROP-97ba08207eca7295-H2",
                "OFFLINE_ISOLATED",
                0,
                1,
                "ENVIRONMENT_OWNER",
                "VALID",
                "PREFLIGHT_VERIFIED",
                _digest(),
            ),
        )

    conn.execute(
        "INSERT INTO assurance_scope_contracts "
        "(session_id, proposal_ref, egress_mode, live_egress_detected, cross_run_writable, "
        "signoff_role, preflight_status, lifecycle_state, contract_digest) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "PASAC-TRIG-01",
            "PROP-97ba08207eca7295-H2",
            "OFFLINE_ISOLATED",
            1,
            0,
            "INCIDENT_LEAD",
            "FAILED",
            "QUARANTINED_BREACH",
            _digest(),
        ),
    )
    conn.execute(
        "INSERT INTO boundary_assurance_probes "
        "(probe_id, session_id, b_scope, b_identity, b_network, b_storage, b_monitor, b_response, min_layer_floor) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("BAS-CASC-01", "PASAC-TRIG-01", 0.9, 0.9, 0.0, 0.9, 0.9, 0.9, 0.7),
    )
    conn.execute(
        "INSERT INTO assurance_breach_quarantine "
        "(alert_id, session_id, error_class, assigned_role, incident_summary, occ_version) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("QALT-TRIG-01", "PASAC-TRIG-01", "SECURITY", "INCIDENT_LEAD", "Offline egress leaked to PyPI", 1),
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "UPDATE assurance_breach_quarantine SET incident_summary = 'sanitized' WHERE alert_id = 'QALT-TRIG-01'"
        )

    conn.execute("DELETE FROM assurance_scope_contracts WHERE session_id = 'PASAC-TRIG-01'")
    assert conn.execute("SELECT COUNT(*) FROM boundary_assurance_probes").fetchone()[0] == 0
    conn.close()


def test_pasac_store_containment_reauthorization_and_wal_concurrency(tmp_path: Path):
    db_path = tmp_path / "pasac_concurrent.db"
    contract, bas, risk = _nominal_inputs("PASAC-CONCUR-01")
    with PasacAssuranceStore(db_path) as store:
        occ_v1 = store.register_scope_contract(contract)
        assert occ_v1 == 1

        errors: list[Exception] = []

        def _worker(tid: int) -> None:
            try:
                dec = RuntimeAuthorizationGate(pasac_store=store).evaluate_pasac_pep(
                    contract,
                    bas,
                    risk,
                    f"ACT_TH_{tid}",
                )
                assert dec.allow_action is True
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=_worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert store.get_metrics()["pep_decisions"] == 10

        # Trigger SYNCHRONOUS_STOP escalation
        stop_risk = risk.model_copy(update={"telemetry_id": "RISK-STOP-01", "hazard_l_t": 0.91})
        halted_dec = store.evaluate_and_record_pep(
            contract,
            bas,
            stop_risk,
            action_code="TOOL_EXFIL_01",
            in_authorized_scope=True,
            resource_whitelisted=True,
            action_risk=0.10,
            risk_threshold=0.50,
        )
        assert halted_dec.allow_action is False
        assert halted_dec.hazard_regime == HazardRegime.SYNCHRONOUS_STOP
        assert store.get_lifecycle_state("PASAC-CONCUR-01") == PasacLifecycleState.CONTAINMENT_HALTED
        assert store.get_metrics()["quarantine_alerts"] == 1
        assert store.get_latest_occ_version("PASAC-CONCUR-01") == 2

        restored = store.record_reauthorization(
            signoff_code="SIG-INCIDENT-01",
            session_id="PASAC-CONCUR-01",
            accountability_role=AccountabilityRole.INCIDENT_LEAD,
            approval_rationale="Verified sandbox isolation after containment drill.",
        )
        assert restored == PasacLifecycleState.PREFLIGHT_VERIFIED
        assert store.get_latest_occ_version("PASAC-CONCUR-01") == 3
        assert store.get_metrics()["reauthorizations"] == 1


def test_mcp_server_pasac_containment_reauth_and_stdio_purity(tmp_path: Path):
    target_py = tmp_path / "sample.py"
    target_py.write_text("def hello() -> int:\n    return 42\n", encoding="utf-8")

    pasac_db = tmp_path / "pasac_mcp.db"
    cache = LocalSemanticCache(str(tmp_path / "cache.db"))
    pasac_store = PasacAssuranceStore(pasac_db)
    contract, bas, risk = _nominal_inputs("PASAC-MCP-TEST-01")
    stop_risk = risk.model_copy(update={"hazard_l_t": 0.90})

    server = MCPServer(
        cache=cache,
        authorized_roots=[tmp_path],
        pasac_store=pasac_store,
        pasac_contract=contract,
        pasac_bas=bas,
        pasac_risk_state=stop_risk,
        session_id="SES-pasac-mcp-01",
    )

    blocked = server.handle_tools_call(
        {"name": "prune_file", "arguments": {"path": str(target_py)}}
    )
    assert blocked["isError"] is True
    assert blocked["pasacBlocked"] is True
    assert blocked["hazardRegime"] == "SYNCHRONOUS_STOP"
    assert "PASAC_PEP_BLOCKED" in blocked["content"][0]["text"]
    assert pasac_store.get_lifecycle_state(contract.session_id) == PasacLifecycleState.CONTAINMENT_HALTED

    # Subsequent calls remain blocked even if risk drops until accountability reauthorization runs
    server._pasac_risk_state = risk
    still_blocked = server.handle_tools_call(
        {"name": "prune_file", "arguments": {"path": str(target_py)}}
    )
    assert still_blocked["isError"] is True
    assert still_blocked["pasacBlocked"] is True
    assert "CONTAINMENT_HALTED" in still_blocked["content"][0]["text"]

    # Accountability sign-off restores PREFLIGHT_VERIFIED and execution resumes cleanly over stdio
    new_state = server.reauthorize_pasac_session(
        signoff_code="SIG-MCP-LEAD-01",
        accountability_role=AccountabilityRole.INCIDENT_LEAD,
        approval_rationale="Root cause remediated; offline isolation confirmed.",
    )
    assert new_state == PasacLifecycleState.PREFLIGHT_VERIFIED

    req_init = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    req_prune = json.dumps({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "prune_file", "arguments": {"path": str(target_py)}},
    })
    stdin_buf = io.StringIO(f"{req_init}\n{req_prune}\n")
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    orig_in, orig_out, orig_err = sys.stdin, sys.stdout, sys.stderr
    sys.stdin, sys.stdout, sys.stderr = stdin_buf, stdout_buf, stderr_buf
    try:
        server.run_stdio_loop()
    finally:
        sys.stdin, sys.stdout, sys.stderr = orig_in, orig_out, orig_err

    lines = [ln.strip() for ln in stdout_buf.getvalue().splitlines() if ln.strip()]
    assert len(lines) == 2
    frames = [json.loads(ln) for ln in lines]
    assert frames[1]["result"]["isError"] is False
    assert "def hello() -> int:" in frames[1]["result"]["content"][0]["text"]


def test_assess_posture_and_doctor_pasac_checks(tmp_path: Path):
    clean_posture = assess_runtime_isolation_posture(mcp_configs=[{}])
    assert clean_posture.passed is True
    assert clean_posture.conservative_assurance >= 0.90

    leaking_posture = assess_runtime_isolation_posture(
        mcp_configs=[
            {
                "mcpServers": {
                    "remote_exfil": {
                        "url": "https://evil.example/sse",
                        "cross_run_writable": True,
                    }
                }
            }
        ]
    )
    assert leaking_posture.passed is False
    assert leaking_posture.contract.live_egress_detected is True
    assert leaking_posture.contract.preflight_status == PreflightStatus.FAILED
    assert leaking_posture.conservative_assurance == 0.0

    repo = tmp_path / "pasac_repo"
    (repo / ".git" / "hooks").mkdir(parents=True)
    init_repository_perimeter(repo)
    (repo / ".mcp.json").write_text("{}", encoding="utf-8")

    ok_report = run_doctor(project_root=repo)
    ok_checks = {c.name: c for c in ok_report.checks}
    assert "PASAC Boundary Assurance" in ok_checks
    assert ok_checks["PASAC Boundary Assurance"].status == "OK"
    assert ok_report.all_passed is True

    # Introduce live remote egress + cross_run_writable violation in .mcp.json
    (repo / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "shared_board": {
                        "url": "https://public-board.example/mcp",
                        "cross_run_writable": True,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    fail_report = run_doctor(project_root=repo)
    fail_checks = {c.name: c for c in fail_report.checks}
    assert fail_checks["PASAC Boundary Assurance"].status == "FAIL"
    assert fail_report.all_passed is False
