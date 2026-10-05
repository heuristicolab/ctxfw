"""
src/ctxfw/core/contracts.py — Immutable Pydantic v2 Core Contracts (v3.4.0)
Defines pruning depths, supported languages, and core DTOs for token optimization.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional, Union
from pydantic import BaseModel, ConfigDict, Field


class PruningDepth(str, Enum):
    """Topological pruning depth levels."""
    FULL = "full"             # D0: 100% full implementation retained untouched
    INTERFACE = "interface"   # D1: Signatures, types, docstrings, decorators, sanitized raises, and ...
    NOMINAL = "nominal"       # D2+: Purely nominal schemas (classes / DTOs without methods)


class SupportedLanguage(str, Enum):
    """Programming languages formally supported by the optimization engine."""
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    GO = "go"
    JAVA = "java"


class OptimizationRequestDTO(BaseModel):
    """Immutable optimization request contract."""
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    source_code: str = Field(..., min_length=1, description="Source code to prune")
    language: Union[SupportedLanguage, str] = Field(default=SupportedLanguage.PYTHON, description="Programming language")
    strip_docs: bool = Field(default=False, description="Purge docstrings if True")
    depth: PruningDepth = Field(default=PruningDepth.INTERFACE, description="Pruning depth level")
    sanitize_raises: bool = Field(default=True, description="Sanitize raise statement arguments")
    mode: Optional[str] = Field(default=None, description="Engine operating mode ('distance' or 'passthrough')")


class OptimizationResultDTO(BaseModel):
    """Metrics and output of the optimized context."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    pruned_code: str
    original_chars: int = Field(..., ge=0)
    pruned_chars: int = Field(..., ge=0)
    estimated_tokens_saved: int = Field(..., ge=0)
    savings_percentage: float = Field(..., ge=0.0, le=100.0)
    cache_hit: bool
    execution_ms: float = Field(..., ge=0.0)
    depth: PruningDepth = Field(default=PruningDepth.INTERFACE, description="Applied depth level")


class TelemetryRecordDTO(BaseModel):
    """Immutable perimeter anonymous telemetry contract (perimeter sovereignty)."""
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    dev_uuid: str = Field(..., min_length=8, description="Unique anonymous developer identifier")
    timestamp_utc: str = Field(..., description="UTC ISO 8601 timestamp")
    model_target: str = Field(..., min_length=1, description="Target LLM model name")
    tokens_orig: int = Field(..., ge=0, description="Original evaluated tokens")
    tokens_pruned: int = Field(..., ge=0, description="Tokens pruned or elided")
    usd_avoided: float = Field(..., ge=0.0, description="Estimated financial savings in USD")
    team: str = Field(default="Engineering", description="Organizational team")


class TelemetryBatchPushDTO(BaseModel):
    """Batch of anonymous telemetry records for perimeter synchronization."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    records: list[TelemetryRecordDTO] = Field(..., description="List of anonymous telemetry events")


class TeamSavingsDTO(BaseModel):
    """Aggregated metrics by organizational team."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    team: str
    tokens_pruned: int = Field(..., ge=0)
    usd_avoided: float = Field(..., ge=0.0)
    request_count: int = Field(..., ge=0)


class ModelSavingsDTO(BaseModel):
    """Aggregated metrics by language model."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    model_target: str
    tokens_pruned: int = Field(..., ge=0)
    usd_avoided: float = Field(..., ge=0.0)
    request_count: int = Field(..., ge=0)


class TelemetryStatsDTO(BaseModel):
    """Global aggregated statistics for control plane and FinOps dashboard."""
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
