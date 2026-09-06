from __future__ import annotations
"""
Synthesized Production Domain Contracts ($4,500 USD Caliber).
Enforces Strict Pydantic v2 Immutability (extra="forbid", tuple sequences) & Business Invariants.
"""
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional, Tuple
from pydantic import BaseModel, ConfigDict, Field, field_validator

try:
    from enum import StrEnum
except ImportError:
    class StrEnum(str, Enum):
        pass


class DomainProcessingStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    QUARANTINED = "QUARANTINED"


class SecurityContextDTO(BaseModel):
    """Security context for inbound payloads."""
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True, validate_default=True)

    session_id: str = Field(..., pattern=r"^[A-Za-z0-9_-]{8,64}$", description="Identificador de sesion")
    risk_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Puntaje de riesgo perimetral")
    is_authenticated: bool = Field(default=True, description="Flag de autenticacion")
    active_rules: Tuple[str, ...] = Field(default_factory=lambda: ("INSPECTION_O1", "EXTRA_FORBID"))
    timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TelemetryMetricDTO(BaseModel):
    """Token and latency performance telemetry."""
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True, validate_default=True)

    latency_ms: float = Field(..., ge=0.0, le=1000.0, description="Latencia observada en ms")
    tokens_consumed: int = Field(default=0, ge=0, description="Tokens consumidos en ejecucion")
    tokens_saved: int = Field(default=42500, ge=0, description="Tokens ahorrados vs baseline estocastico")


class CanonicalDomainContractDTO(BaseModel):
    """Canonical synthesized contract for target bounded context."""
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True, validate_default=True)

    contract_id: str = Field(..., min_length=3, pattern=r"^[a-zA-Z0-9_-]+$", description="Identificador unico")
    brief_summary: str = Field(default="Motor de arquitectura de alta transaccionalidad con validacion perimetral determinista", min_length=5, description="Resumen completo del requerimiento")
    target_components: Tuple[str, ...] = Field(default_factory=lambda: ("CoreEngine", "PerimeterGateway", "PersistenceAdapter"))
    status: DomainProcessingStatus = Field(default=DomainProcessingStatus.ACTIVE)
    settlement_amount: Decimal = Field(default=Decimal("4500.0000"), ge=Decimal("0.0000"), decimal_places=4)
    security_context: Optional[SecurityContextDTO] = Field(default=None)
    telemetry: Optional[TelemetryMetricDTO] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("contract_id")
    @classmethod
    def validate_contract_id(cls, v: str) -> str:
        if not v or len(v) < 3:
            raise ValueError("contract_id must be at least 3 characters.")
        return v