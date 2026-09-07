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
