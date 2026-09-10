"""
tests/test_spec_sieve.py — Test Suite for Specification Sieve Subsystem (HU-11 Port)
Validates ACI computation, negative invariant extraction, lexicographical SHA-256 sealing,
CLI 'spec verify' subcommand, and MCP 'evaluate_spec_axioms' tool execution.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from ctxfw.sieve.engine import (
    QuarantineStatus,
    compute_aci,
    evaluate_specification,
    extract_negative_invariants,
    generate_manifest_hash,
)
from ctxfw.mcp import MCPServer
from ctxfw.cli import run_spec_verify, handle_spec_command


COMPLIANT_BRIEF_MARKDOWN = """# Architectural Specification Brief: High-Assurance Vault Gateway

## 1. Domain Entities & Bounds
- Variable `max_concurrency`: integer bounded >= 1 and <= 256.
- Variable `session_timeout_sec`: integer bounded >= 10 and <= 3600.
- Variable `token_cache_size`: integer bounded >= 64 and <= 8192.
- Variable `max_retries`: integer bounded >= 0 and <= 5.
- Variable `worker_thread_pool`: integer bounded >= 2 and <= 64.
Bounds: 5 / 5

## 2. Deterministic State Machine (FSM)
Lifecycle states and transitions:
- INIT -> PENDING_VERIFICATION -> ACCEPTED -> SEALED
- On boundary violation: * -> QUARANTINED

## 3. Error Taxonomy & Quarantine
Formal error taxonomy isolates fault domains:
- SpecValidationError -> Divert to quarantine sink
- InvariantViolationException -> System halt
- CryptographicAttestationError -> Forensic audit

## 4. Formal Proof & Invariant Attestation
Formal proof included: Mathematical induction validates inductive invariance across state transitions.
Deterministic SHA-256 attestation seal guarantees manifest immutability.

## 5. Negative Invariants (Floor of 5 Required)
- System shall never allow unauthenticated access to the perimeter vault.
- System shall never mutate sealed configuration state after initialization.
- Worker threads shall never block synchronously on external I/O streams.
- The pipeline shall never bypass quarantine sink during invariant failure.
- Ingestion sieve shall never emit unvalidated code tokens to the forge synthesizer.
"""

DEFICIENT_BRIEF_NO_NEGATIVES = """# Deficient Brief: Missing Negative Invariants

## Domain Entities
Bounds: 5 / 5

## State Machine
State transitions: INIT -> RUNNING -> DONE.

## Error Taxonomy
Error taxonomy includes: QuarantineSink and ErrorHandler.

## Formal Proof
Formal proof included: SHA-256 attestation seal applied.

## Invariants
- Only one negative rule: System shall never expose private keys.
"""

DEFICIENT_BRIEF_AMBIGUOUS_BOUNDS = """# Deficient Brief: Ambiguous Bounds

## Domain Entities
- Variable `user_input`: unbounded text string.
- Variable `buffer`: arbitrary length stream.
- Variable `memory_limit`: unbounded allocation.
- Variable `timeout`: unspecified duration.
Bounds: 0 / 4

## Deterministic State Machine (FSM)
States: INIT -> ACTIVE -> COMPLETED.

## Error Taxonomy
Error taxonomy and quarantine sink defined.

## Formal Proof
Formal proof included with SHA-256 attestation.

## Negative Invariants
- System shall never execute without bounds checking.
- System shall never expose raw pointers.
- System shall never leak internal memory addresses.
- System shall never skip authentication filters.
- System shall never bypass perimeter firewall.
"""


def test_compute_aci_formula_and_weights():
    """Verify deterministic ACI calculation and 4-decimal precision."""
    # Perfect score: 0.40*1.0 + 0.30 + 0.15 + 0.15 = 1.0000
    score = compute_aci(
        explicit_bounds=5,
        total_variables=5,
        has_state_machine=True,
        has_error_taxonomy=True,
        formal_proof_included=True,
    )
    assert score == 1.0000

    # 4 of 5 bounds (ratio 0.8): 0.40*0.8 + 0.30 + 0.15 + 0.15 = 0.32 + 0.60 = 0.9200
    score_compliant = compute_aci(
        explicit_bounds=4,
        total_variables=5,
        has_state_machine=True,
        has_error_taxonomy=True,
        formal_proof_included=True,
    )
    assert score_compliant == 0.9200
    assert score_compliant >= 0.9000

    # Ambiguous bounds: 2 of 5 (ratio 0.4): 0.40*0.4 + 0.60 = 0.16 + 0.60 = 0.7600
    score_sub = compute_aci(
        explicit_bounds=2,
        total_variables=5,
        has_state_machine=True,
        has_error_taxonomy=True,
        formal_proof_included=True,
    )
    assert score_sub == 0.7600
    assert score_sub < 0.9000

    # Missing state machine: 0.40*1.0 + 0 + 0.15 + 0.15 = 0.7000
    score_no_fsm = compute_aci(
        explicit_bounds=5,
        total_variables=5,
        has_state_machine=False,
        has_error_taxonomy=True,
        formal_proof_included=True,
    )
    assert score_no_fsm == 0.7000

    # Zero variables handles gracefully without ZeroDivisionError
    score_zero = compute_aci(
        explicit_bounds=0,
        total_variables=0,
        has_state_machine=False,
        has_error_taxonomy=False,
        formal_proof_included=False,
    )
    assert score_zero == 0.0000


def test_extract_negative_invariants():
    """Verify invariant extraction regex detects 'never' and 'shall never' cleanly."""
    sample = """
    # Rules
    - System shall never expose credentials
    * Admin shall never bypass MFA
    1. Worker must never crash silently
    > System SHALL NEVER allow unbounded queues
    - Valid non-negative rule: system must log all requests
    - never
    - System shall never expose credentials
    """
    clauses = extract_negative_invariants(sample)
    assert len(clauses) == 4
    # Checks case insensitivity and bullet stripping
    assert any("System shall never expose credentials" in c for c in clauses)
    assert any("Admin shall never bypass MFA" in c for c in clauses)
    assert any("Worker must never crash silently" in c for c in clauses)
    assert any("System SHALL NEVER allow unbounded queues" in c for c in clauses)


def test_generate_manifest_hash_lexicographical_reproducibility():
    """Verify generate_manifest_hash sorts clauses lexicographically for reproducible SHA-256."""
    clauses_a = [
        "System shall never expose tokens",
        "Worker shall never block",
        "Admin shall never delete audit records",
        "Gateway shall never bypass quarantine",
        "Pipeline shall never drop events",
    ]
    clauses_b = list(reversed(clauses_a))

    hash_a = generate_manifest_hash(clauses_a)
    hash_b = generate_manifest_hash(clauses_b)

    assert len(hash_a) == 64
    assert hash_a == hash_b  # Invariant regardless of input ordering


def test_compliant_brief_evaluation():
    """Verify compliant brief achieves ACI >= 0.9000, 5 never rules, and VERIFIED status."""
    res = evaluate_specification(COMPLIANT_BRIEF_MARKDOWN)

    assert res.status == QuarantineStatus.VERIFIED.value
    assert res.aci_score >= 0.9000
    assert res.negative_invariants_count >= 5
    assert len(res.extracted_never_clauses) >= 5
    assert len(res.manifest_hash) == 64
    assert "satisfies axiomatic completeness" in res.remediation_notes[0]


def test_deficient_brief_missing_never_clauses():
    """Verify deficient brief (< 5 never rules) is diverted to QUARANTINED."""
    res = evaluate_specification(DEFICIENT_BRIEF_NO_NEGATIVES)

    assert res.status == QuarantineStatus.QUARANTINED.value
    assert res.negative_invariants_count < 5
    assert any("Negative invariants floor violated" in note for note in res.remediation_notes)


def test_deficient_brief_ambiguous_bounds():
    """Verify deficient brief with ambiguous bounds yields sub-threshold ACI and QUARANTINED."""
    res = evaluate_specification(DEFICIENT_BRIEF_AMBIGUOUS_BOUNDS)

    assert res.status == QuarantineStatus.QUARANTINED.value
    assert res.aci_score < 0.9000
    assert any("below activation threshold 0.9000" in note for note in res.remediation_notes)


def test_cli_spec_verify_compliant(tmp_path: Path, capsys: pytest.CaptureFixture):
    """Test CLI verification of compliant brief yields exit code 0 and READY FOR FORGE."""
    spec_file = tmp_path / "compliant_brief.md"
    spec_file.write_text(COMPLIANT_BRIEF_MARKDOWN, encoding="utf-8")

    exit_code = run_spec_verify(str(spec_file))
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "[PASS] READY FOR FORGE" in captured.out
    assert "ACI Score:" in captured.out
    assert "Negative Invariants Count:  5" in captured.out
    assert "Manifest Hash (SHA-256):" in captured.out


def test_cli_spec_verify_deficient(tmp_path: Path, capsys: pytest.CaptureFixture):
    """Test CLI verification of deficient brief yields exit code 1 and SPECIFICATION QUARANTINED."""
    spec_file = tmp_path / "deficient_brief.md"
    spec_file.write_text(DEFICIENT_BRIEF_NO_NEGATIVES, encoding="utf-8")

    exit_code = run_spec_verify(str(spec_file))
    assert exit_code == 1

    captured = capsys.readouterr()
    assert "[FAIL] SPECIFICATION QUARANTINED" in captured.out
    assert "Remediation Notes:" in captured.out


def test_cli_spec_verify_missing_file(capsys: pytest.CaptureFixture):
    """Test CLI verification with non-existent file returns code 1."""
    exit_code = run_spec_verify("non_existent_brief_12345.md")
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Specification file not found" in captured.err


def test_cli_subcommand_dispatch_and_help():
    """Test handle_spec_command argument parsing and help output."""
    # Subcommand help
    assert handle_spec_command(["-h"]) == 0
    assert handle_spec_command([]) == 0


def test_cli_subprocess_invocation(tmp_path: Path):
    """Test full CLI subprocess execution for ctxfw spec verify."""
    good_file = tmp_path / "good.md"
    good_file.write_text(COMPLIANT_BRIEF_MARKDOWN, encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, "-m", "ctxfw.cli", "spec", "verify", str(good_file)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "[PASS] READY FOR FORGE" in proc.stdout

    bad_file = tmp_path / "bad.md"
    bad_file.write_text(DEFICIENT_BRIEF_NO_NEGATIVES, encoding="utf-8")

    proc_bad = subprocess.run(
        [sys.executable, "-m", "ctxfw.cli", "spec", "verify", str(bad_file)],
        capture_output=True,
        text=True,
    )
    assert proc_bad.returncode == 1
    assert "[FAIL] SPECIFICATION QUARANTINED" in proc_bad.stdout


def test_mcp_tools_list_exposes_evaluate_spec_axioms():
    """Test MCPServer tools/list includes evaluate_spec_axioms."""
    server = MCPServer()
    resp = server.dispatch({
        "jsonrpc": "2.0",
        "id": "list-1",
        "method": "tools/list",
        "params": {},
    })
    assert resp is not None
    tools = resp.get("result", {}).get("tools", [])
    tool_names = [t["name"] for t in tools]
    assert "evaluate_spec_axioms" in tool_names

    spec_tool = next(t for t in tools if t["name"] == "evaluate_spec_axioms")
    assert "brief_text" in spec_tool["inputSchema"]["properties"]
    assert "brief_text" in spec_tool["inputSchema"]["required"]


def test_mcp_tools_call_evaluate_spec_axioms_compliant():
    """Test MCPServer tools/call evaluate_spec_axioms with compliant brief."""
    server = MCPServer()
    call_req = {
        "jsonrpc": "2.0",
        "id": "call-1",
        "method": "tools/call",
        "params": {
            "name": "evaluate_spec_axioms",
            "arguments": {
                "brief_text": COMPLIANT_BRIEF_MARKDOWN,
            },
        },
    }
    resp = server.dispatch(call_req)
    assert resp is not None
    result = resp.get("result", {})
    assert result.get("isError") is False

    content_text = result["content"][0]["text"]
    payload = json.loads(content_text)

    assert payload["status"] == "VERIFIED"
    assert payload["aci_score"] >= 0.9000
    assert payload["negative_invariants_count"] >= 5
    assert len(payload["extracted_never_clauses"]) >= 5
    assert len(payload["manifest_hash"]) == 64
    assert isinstance(payload["remediation_notes"], list)


def test_mcp_tools_call_evaluate_spec_axioms_deficient():
    """Test MCPServer tools/call evaluate_spec_axioms with deficient brief."""
    server = MCPServer()
    call_req = {
        "jsonrpc": "2.0",
        "id": "call-2",
        "method": "tools/call",
        "params": {
            "name": "evaluate_spec_axioms",
            "arguments": {
                "brief_text": DEFICIENT_BRIEF_NO_NEGATIVES,
            },
        },
    }
    resp = server.dispatch(call_req)
    assert resp is not None
    result = resp.get("result", {})
    assert result.get("isError") is False

    content_text = result["content"][0]["text"]
    payload = json.loads(content_text)

    assert payload["status"] == "QUARANTINED"
    assert payload["negative_invariants_count"] < 5
    assert len(payload["remediation_notes"]) > 0


def test_mcp_tools_call_missing_parameter():
    """Test MCPServer tools/call evaluate_spec_axioms with missing parameter."""
    server = MCPServer()
    call_req = {
        "jsonrpc": "2.0",
        "id": "call-3",
        "method": "tools/call",
        "params": {
            "name": "evaluate_spec_axioms",
            "arguments": {},
        },
    }
    resp = server.dispatch(call_req)
    assert resp is not None
    result = resp.get("result", {})
    assert result.get("isError") is True
    assert "Parameter 'brief_text' is required" in result["content"][0]["text"]
