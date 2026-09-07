"""
src/ctxfw/core/contracts.py — Immutable Pydantic v2 Core Contracts (v3.4.0)
Defines pruning depths, supported languages, and core DTOs for token optimization.
"""
from __future__ import annotations

from enum import Enum
from typing import Union
from pydantic import BaseModel, ConfigDict, Field


class PruningDepth(str, Enum):
    """Niveles de profundidad de poda topológica."""
    FULL = "full"             # D0: 100% código íntegro sin poda
    INTERFACE = "interface"   # D1: Firmas, tipos, docstrings, decoradores, raises sanitizados y ...
    NOMINAL = "nominal"       # D2+: Esquemas puramente nominales (clases / DTOs sin métodos)


class SupportedLanguage(str, Enum):
    """Lenguajes de programación soportados formalmente en el motor de optimización."""
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    GO = "go"
    JAVA = "java"


class OptimizationRequestDTO(BaseModel):
    """Contrato inmutable de solicitud de optimización."""
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    source_code: str = Field(..., min_length=1, description="Código fuente a podar")
    language: Union[SupportedLanguage, str] = Field(default=SupportedLanguage.PYTHON, description="Lenguaje de programación")
    strip_docs: bool = Field(default=False, description="Purga total de docstrings si es True")
    depth: PruningDepth = Field(default=PruningDepth.INTERFACE, description="Profundidad de podado")
    sanitize_raises: bool = Field(default=True, description="Sanitizar argumentos de sentencias raise")


class OptimizationResultDTO(BaseModel):
    """Métricas y resultado del contexto optimizado."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    pruned_code: str
    original_chars: int = Field(..., ge=0)
    pruned_chars: int = Field(..., ge=0)
    estimated_tokens_saved: int = Field(..., ge=0)
    savings_percentage: float = Field(..., ge=0.0, le=100.0)
    cache_hit: bool
    execution_ms: float = Field(..., ge=0.0)
    depth: PruningDepth = Field(default=PruningDepth.INTERFACE, description="Nivel de profundidad aplicado")


class TelemetryRecordDTO(BaseModel):
    """Contrato inmutable de telemetría anónima perimetral (inviolabilidad perimetral)."""
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    dev_uuid: str = Field(..., min_length=8, description="Identificador anónimo único del desarrollador")
    timestamp_utc: str = Field(..., description="Marca temporal UTC en formato ISO 8601")
    model_target: str = Field(..., min_length=1, description="Nombre del modelo LLM objetivo")
    tokens_orig: int = Field(..., ge=0, description="Tokens originales evaluados")
    tokens_pruned: int = Field(..., ge=0, description="Tokens eludidos/podados")
    usd_avoided: float = Field(..., ge=0.0, description="Ahorro financiero estimado en USD")
    team: str = Field(default="Engineering", description="Equipo organizativo")


class TelemetryBatchPushDTO(BaseModel):
    """Lote de registros de telemetría anónima para sincronización perimetral."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    records: list[TelemetryRecordDTO] = Field(..., description="Lista de eventos de telemetría anónima")


class TeamSavingsDTO(BaseModel):
    """Métricas agregadas por equipo organizativo."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    team: str
    tokens_pruned: int = Field(..., ge=0)
    usd_avoided: float = Field(..., ge=0.0)
    request_count: int = Field(..., ge=0)


class ModelSavingsDTO(BaseModel):
    """Métricas agregadas por modelo de lenguaje."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    model_target: str
    tokens_pruned: int = Field(..., ge=0)
    usd_avoided: float = Field(..., ge=0.0)
    request_count: int = Field(..., ge=0)


class TelemetryStatsDTO(BaseModel):
    """Estadísticas globales agregadas para el plano de control y dashboard FinOps."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    total_tokens_orig: int = Field(..., ge=0)
    total_tokens_pruned: int = Field(..., ge=0)
    total_usd_avoided: float = Field(..., ge=0.0)
    global_reduction_pct: float = Field(..., ge=0.0, le=100.0)
    active_dev_count: int = Field(..., ge=0)
    total_cycles: int = Field(..., ge=0)
    teams: list[TeamSavingsDTO]
    models: list[ModelSavingsDTO]
    timeseries: list[dict]
