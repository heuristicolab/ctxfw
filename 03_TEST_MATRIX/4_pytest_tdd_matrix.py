import pytest
from pydantic import ValidationError
from contracts import (
    OptimizationRequestDTO,
    OptimizationResultDTO,
    DeterministicContextPruner,
    LocalSemanticCache,
)

SAMPLE_CODE = """
class HardwareTransactionOrchestrator:
    '''Coordina pagos y telemetría de hardware.'''
    def __init__(self, port: str, baudrate: int = 9600):
        self.port = port
        self.baudrate = baudrate
        self.connected = False

    def validate_bill(self, denomination: int) -> bool:
        '''Valida autenticidad y atestación de billete.'''
        buffer = [i * 2 for i in range(200)]
        if sum(buffer) % 256 != 0:
            return False
        return True
"""

def test_dto_immutability():
    req = OptimizationRequestDTO(source_code="def foo(): pass")
    with pytest.raises(ValidationError):
        req.source_code = "def bar(): pass"

def test_dto_extra_forbid():
    with pytest.raises(ValidationError):
        OptimizationRequestDTO(source_code="pass", illegal_field="injected")

def test_ast_pruner_preserves_signatures_and_strips_bodies():
    req = OptimizationRequestDTO(source_code=SAMPLE_CODE, strip_docs=False)
    pruned, orig_c, pruned_c, saved, pct, ms = DeterministicContextPruner.prune(req)

    assert "class HardwareTransactionOrchestrator:" in pruned
    assert "def validate_bill(self, denomination: int) -> bool:" in pruned
    assert 'Valida autenticidad y atestación de billete.' in pruned
    assert "buffer = [i * 2 for i in range(200)]" not in pruned
    assert pct >= 35.0
    assert saved > 0

def test_ast_pruner_syntax_error():
    req = OptimizationRequestDTO(source_code="def invalid_syntax(:")
    with pytest.raises(ValueError, match="Error de sintaxis"):
        DeterministicContextPruner.prune(req)

def test_sqlite_wal_cache_lifecycle(tmp_path):
    db_file = str(tmp_path / "test_wal_cache.db")
    cache = LocalSemanticCache(db_path=db_file)
    key = LocalSemanticCache.generate_key(SAMPLE_CODE, DeterministicContextPruner.RULES_VERSION, False)

    assert cache.get(key) is None

    req = OptimizationRequestDTO(source_code=SAMPLE_CODE)
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