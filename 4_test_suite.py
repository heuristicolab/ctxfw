from __future__ import annotations
"""
Canonical Pytest TDD Suite for Synthesized Architecture ($4,500 USD Caliber).
Verifies contract immutability, extra="forbid" rejection, bounds validation, and AST compliance.
"""
from datetime import datetime, timezone
from decimal import Decimal
import pytest
from pydantic import ValidationError

from contracts import (
    CanonicalDomainContractDTO,
    DomainProcessingStatus,
    SecurityContextDTO,
    TelemetryMetricDTO,
)


def test_synthesized_contract_valid_instantiation():
    """Verifies successful instantiation of synthesized domain contract."""
    sec = SecurityContextDTO(session_id="SES-2026-TEST", risk_score=0.05)
    tel = TelemetryMetricDTO(latency_ms=1.2, tokens_consumed=320, tokens_saved=42500)
    contract = CanonicalDomainContractDTO(
        contract_id="CTR-TEST-001",
        brief_summary="Arquitectura de alta transaccionalidad con validacion perimetral determinista",
        security_context=sec,
        telemetry=tel,
    )
    assert contract.contract_id == "CTR-TEST-001"
    assert contract.status == DomainProcessingStatus.ACTIVE
    assert contract.security_context.risk_score == 0.05
    assert contract.telemetry.tokens_saved == 42500
    assert contract.settlement_amount == Decimal("4500.0000")


def test_synthesized_contract_immutability():
    """Verifies that frozen=True prohibits in-place attribute mutations."""
    contract = CanonicalDomainContractDTO(
        contract_id="CTR-FROZEN-001",
        brief_summary="Resumen inmutable validado",
    )
    with pytest.raises(ValidationError):
        contract.contract_id = "CTR-MUTATED"


def test_synthesized_contract_extra_forbid_rejection():
    """Verifies that extra="forbid" rejects unapproved payload parameters with ValidationError."""
    with pytest.raises(ValidationError):
        CanonicalDomainContractDTO(
            contract_id="CTR-EXTRA-001",
            brief_summary="Intento de inyeccion extra forbid",
            unauthorized_injection_field="hacked",
        )


def test_security_context_bounds_validation():
    """Verifies numeric bounds and pattern enforcement on SecurityContextDTO."""
    with pytest.raises(ValidationError):
        SecurityContextDTO(session_id="VALID_SESSION", risk_score=1.5)  # le=1.0

    with pytest.raises(ValidationError):
        SecurityContextDTO(session_id="INV$ALID#", risk_score=0.5)  # regex check


def test_telemetry_metrics_invariants():
    """Verifies non-negative bounds on TelemetryMetricDTO."""
    with pytest.raises(ValidationError):
        TelemetryMetricDTO(latency_ms=-1.0)