"""
tests/test_contracts.py — Verification Matrix for Context & Token Pruning Engine
Validates strict Pydantic v2 immutability, AST slicing invariants, and SQLite WAL cache performance.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from contracts import (
    DeterministicContextPruner,
    LocalSemanticCache,
    OptimizationRequestDTO,
    OptimizationResultDTO,
)

SAMPLE_TARGET_CODE = """
class HardwareTransactionOrchestrator:
    '''Coordinates payment routing and hardware state telemetry.'''
    def __init__(self, port: str, baudrate: int = 9600):
        self.port = port
        self.baudrate = baudrate
        self.connected = False

    def validate_bill(self, denomination: int) -> bool:
        '''Validates bank note authenticity and serial checksum.'''
        buffer = [i * 2 for i in range(200)]
        if sum(buffer) % 256 != 0:
            return False
        return True
"""


def test_dto_immutability():
    """Validates frozen=True invariant preventing runtime mutation."""
    req = OptimizationRequestDTO(source_code="def execute(): pass")
    with pytest.raises(ValidationError):
        req.source_code = "def mutate(): pass"


def test_dto_extra_forbid():
    """Validates rejection of unapproved payload fields."""
    with pytest.raises(ValidationError):
        OptimizationRequestDTO(source_code="pass", illegal_injection="malicious")


def test_ast_pruner_preserves_signatures_and_strips_bodies():
    """Asserts method body purge while preserving class hierarchies, signatures, and docstrings."""
    req = OptimizationRequestDTO(source_code=SAMPLE_TARGET_CODE, strip_docs=False)
    pruned, orig_c, pruned_c, saved, pct, ms = DeterministicContextPruner.prune(req)

    assert "class HardwareTransactionOrchestrator:" in pruned
    assert "def validate_bill(self, denomination: int) -> bool:" in pruned
    assert "Coordinates payment routing and hardware state telemetry." in pruned
    assert "buffer = [i * 2 for i in range(200)]" not in pruned
    assert pct >= 35.0
    assert saved > 0


def test_ast_pruner_syntax_error():
    """Asserts graceful rejection on invalid Python grammar without daemon panic."""
    req = OptimizationRequestDTO(source_code="def broken_syntax(:")
    with pytest.raises(ValueError, match="Error de sintaxis"):
        DeterministicContextPruner.prune(req)


def test_sqlite_wal_cache_lifecycle(tmp_path):
    """Validates persistence, hash generation, and sub-15ms warm cache retrieval."""
    db_file = str(tmp_path / "test_wal_cache.db")
    cache = LocalSemanticCache(db_path=db_file)
    key = LocalSemanticCache.generate_key(
        SAMPLE_TARGET_CODE, DeterministicContextPruner.RULES_VERSION, False
    )

    assert cache.get(key) is None

    req = OptimizationRequestDTO(source_code=SAMPLE_TARGET_CODE)
    pruned, orig_c, pruned_c, saved, pct, ms = DeterministicContextPruner.prune(req)

    dto = OptimizationResultDTO(
        pruned_code=pruned,
        original_chars=orig_c,
        pruned_chars=pruned_c,
        estimated_tokens_saved=saved,
        savings_percentage=pct,
        cache_hit=False,
        execution_ms=ms,
    )
    cache.set(key, dto)

    hit = cache.get(key)
    assert hit is not None
    assert hit.cache_hit is True
    assert hit.estimated_tokens_saved == saved
    assert hit.execution_ms < 15.0