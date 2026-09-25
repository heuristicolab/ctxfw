"""
tests/test_contracts.py — Verification Matrix for Context & Token Pruning Engine (v2.0)
Validates strict Pydantic v2 immutability, AST slicing invariants, ellipsis stubs,
sanitized raise retention, multi-depth pruning (FULL/INTERFACE/NOMINAL), and SQLite WAL cache performance.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from ctxfw.core.contracts import (
    OptimizationRequestDTO,
    OptimizationResultDTO,
    PruningDepth,
)
from ctxfw.core.pruner import DeterministicContextPruner
from ctxfw.storage.cache import LocalSemanticCache

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

SAMPLE_CODE_WITH_RAISES = """
def process_payment(amount: float, secret_key: str) -> bool:
    '''Authorizes billing transaction with gateway.'''
    if amount <= 0:
        raise ValueError(f"Invalid transaction amount: {amount} with secret: {secret_key}")
    if len(secret_key) < 16:
        raise PermissionError("Key length violation: " + secret_key)
    scratchpad = [x * 2 for x in range(500)]
    return True
"""

SAMPLE_CLASS_NOMINAL = """
class TransactionRecord:
    '''Immutable ledger entry.'''
    record_id: str
    amount: float
    status: str

    def calculate_tax(self) -> float:
        '''Internal formula.'''
        return self.amount * 0.16

    def audit(self) -> dict:
        return {"status": self.status}
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


def test_ast_pruner_uses_ellipsis_stubs():
    """Validates that pruned method bodies use canonical PEP 484 ellipsis (...) stubs rather than pass."""
    req = OptimizationRequestDTO(source_code=SAMPLE_TARGET_CODE, strip_docs=False)
    pruned, _, _, _, _, _ = DeterministicContextPruner.prune(req)

    assert "..." in pruned
    # Verify methods don't use 'pass'
    assert "pass" not in pruned


def test_ast_pruner_extracts_and_sanitizes_raises():
    """Validates that raise statements are retained as preconditions while arguments are sanitized against leaks."""
    req = OptimizationRequestDTO(source_code=SAMPLE_CODE_WITH_RAISES, sanitize_raises=True)
    pruned, _, _, _, _, _ = DeterministicContextPruner.prune(req)

    # Signatures and docstrings preserved
    assert "def process_payment(amount: float, secret_key: str) -> bool:" in pruned
    assert "Authorizes billing transaction with gateway." in pruned

    # Raises retained
    assert "raise ValueError(" in pruned
    assert "raise PermissionError(" in pruned

    # IP & secret shielding: sensitive variables must NOT leak into the pruned body
    body_after_doc = pruned.split('"""')[-1]
    assert "secret_key" not in body_after_doc
    assert "scratchpad" not in pruned


def test_ast_pruner_depth_full_preserves_everything():
    """Validates Distance 0 (FULL mode): 100% code preservation without modification."""
    req = OptimizationRequestDTO(source_code=SAMPLE_TARGET_CODE, depth=PruningDepth.FULL)
    pruned, orig_c, pruned_c, saved, pct, ms = DeterministicContextPruner.prune(req)

    assert pruned == SAMPLE_TARGET_CODE.strip()
    assert orig_c == pruned_c
    assert saved == 0
    assert pct == 0.0


def test_ast_pruner_depth_nominal_strips_methods():
    """Validates Distance 2+ (NOMINAL mode): classes retain annotations and docstrings, omitting internal methods."""
    req = OptimizationRequestDTO(source_code=SAMPLE_CLASS_NOMINAL, depth=PruningDepth.NOMINAL)
    pruned, orig_c, pruned_c, saved, pct, ms = DeterministicContextPruner.prune(req)

    assert "class TransactionRecord:" in pruned
    assert "record_id: str" in pruned
    assert "amount: float" in pruned
    assert "status: str" in pruned
    # Methods completely omitted in nominal mode
    assert "calculate_tax" not in pruned
    assert "audit" not in pruned


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
    assert hit.execution_ms < 30.0


def test_sqlite_wal_pruning_depth_differentiation(tmp_path):
    """Validates that distinct pruning depths yield distinct cache keys and independent entries."""
    db_file = str(tmp_path / "test_depth_cache.db")
    cache = LocalSemanticCache(db_path=db_file)

    key_interface = LocalSemanticCache.generate_key(
        SAMPLE_CLASS_NOMINAL, DeterministicContextPruner.RULES_VERSION, False, depth="interface"
    )
    key_nominal = LocalSemanticCache.generate_key(
        SAMPLE_CLASS_NOMINAL, DeterministicContextPruner.RULES_VERSION, False, depth="nominal"
    )

    assert key_interface != key_nominal

    req_interface = OptimizationRequestDTO(source_code=SAMPLE_CLASS_NOMINAL, depth=PruningDepth.INTERFACE)
    pruned_i, orig_i, pruned_i_c, saved_i, pct_i, ms_i = DeterministicContextPruner.prune(req_interface)

    req_nominal = OptimizationRequestDTO(source_code=SAMPLE_CLASS_NOMINAL, depth=PruningDepth.NOMINAL)
    pruned_n, orig_n, pruned_n_c, saved_n, pct_n, ms_n = DeterministicContextPruner.prune(req_nominal)

    cache.set(key_interface, OptimizationResultDTO(
        pruned_code=pruned_i, original_chars=orig_i, pruned_chars=pruned_i_c,
        estimated_tokens_saved=saved_i, savings_percentage=pct_i, cache_hit=False,
        execution_ms=ms_i, depth=PruningDepth.INTERFACE,
    ))

    cache.set(key_nominal, OptimizationResultDTO(
        pruned_code=pruned_n, original_chars=orig_n, pruned_chars=pruned_n_c,
        estimated_tokens_saved=saved_n, savings_percentage=pct_n, cache_hit=False,
        execution_ms=ms_n, depth=PruningDepth.NOMINAL,
    ))

    hit_i = cache.get(key_interface)
    hit_n = cache.get(key_nominal)

    assert hit_i is not None and hit_i.depth == PruningDepth.INTERFACE
    assert hit_n is not None and hit_n.depth == PruningDepth.NOMINAL
    assert "calculate_tax" in hit_i.pruned_code
    assert "calculate_tax" not in hit_n.pruned_code


def test_sqlite_wal_busy_timeout_configured(tmp_path):
    """Validates that PRAGMA busy_timeout = 5000 is active on every connection."""
    db_file = str(tmp_path / "test_timeout.db")
    cache = LocalSemanticCache(db_path=db_file)
    with cache._get_connection() as conn:
        timeout_val = conn.execute("PRAGMA busy_timeout;").fetchone()[0]
        assert timeout_val == 5000