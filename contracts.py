from __future__ import annotations
import ast
import hashlib
import sqlite3
import time
from typing import Optional, Tuple
from pydantic import BaseModel, ConfigDict, Field

class OptimizationRequestDTO(BaseModel):
    """Contrato inmutable de solicitud de optimización."""
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    source_code: str = Field(..., min_length=1, description="Código fuente a podar")
    language: str = Field(default="python", description="Lenguaje de programación")
    strip_docs: bool = Field(default=False, description="Purga total de docstrings si es True")


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


class _MethodBodyStripper(ast.NodeTransformer):
    """Visitor AST que preserva firmas/tipos y sustituye cuerpos por pass."""
    def __init__(self, strip_docs: bool = False):
        self.strip_docs = strip_docs

    def _clean_body(self, node):
        has_doc = (
            len(node.body) > 0
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        )
        if has_doc and not self.strip_docs:
            node.body = [node.body[0], ast.Pass()]
        else:
            node.body = [ast.Pass()]
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        self.generic_visit(node)
        return self._clean_body(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        self.generic_visit(node)
        return self._clean_body(node)


class DeterministicContextPruner:
    """Motor de slicing determinista basado en Python AST."""
    RULES_VERSION = "v1.0.0"

    @staticmethod
    def estimate_tokens(chars: int) -> int:
        return max(1, chars // 4)

    @classmethod
    def prune(cls, request: OptimizationRequestDTO) -> Tuple[str, int, int, int, float, float]:
        start = time.perf_counter()
        if request.language.lower() != "python":
            raise ValueError(f"Lenguaje no soportado: {request.language}")

        try:
            tree = ast.parse(request.source_code)
        except SyntaxError as e:
            raise ValueError(f"Error de sintaxis en el código: {e}") from e

        stripper = _MethodBodyStripper(strip_docs=request.strip_docs)
        pruned_tree = stripper.visit(tree)
        ast.fix_missing_locations(pruned_tree)

        pruned_code = ast.unparse(pruned_tree)
        elapsed_ms = (time.perf_counter() - start) * 1000

        orig_chars = len(request.source_code)
        pruned_chars = len(pruned_code)
        orig_tokens = cls.estimate_tokens(orig_chars)
        pruned_tokens = cls.estimate_tokens(pruned_chars)
        tokens_saved = max(0, orig_tokens - pruned_tokens)
        savings_pct = round(((orig_chars - pruned_chars) / max(1, orig_chars)) * 100, 2)

        return pruned_code, orig_chars, pruned_chars, tokens_saved, savings_pct, round(elapsed_ms, 3)


class LocalSemanticCache:
    """Caché transaccional embebido con persistencia en SQLite WAL."""
    def __init__(self, db_path: str = "heuristic_tokens_cache.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tokens_cache (
                    cache_key TEXT PRIMARY KEY,
                    pruned_code TEXT NOT NULL,
                    original_chars INTEGER NOT NULL,
                    pruned_chars INTEGER NOT NULL,
                    estimated_tokens_saved INTEGER NOT NULL,
                    savings_percentage REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

    @staticmethod
    def generate_key(source_code: str, rules_version: str, strip_docs: bool) -> str:
        payload = f"{source_code}|{rules_version}|{strip_docs}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, cache_key: str) -> Optional[OptimizationResultDTO]:
        start = time.perf_counter()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT pruned_code, original_chars, pruned_chars, estimated_tokens_saved, savings_percentage
                FROM tokens_cache WHERE cache_key = ?
            """, (cache_key,))
            row = cur.fetchone()
            if not row:
                return None

            elapsed_ms = (time.perf_counter() - start) * 1000
            return OptimizationResultDTO(
                pruned_code=row[0],
                original_chars=row[1],
                pruned_chars=row[2],
                estimated_tokens_saved=row[3],
                savings_percentage=row[4],
                cache_hit=True,
                execution_ms=round(elapsed_ms, 3)
            )

    def set(self, cache_key: str, result: OptimizationResultDTO):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO tokens_cache 
                (cache_key, pruned_code, original_chars, pruned_chars, estimated_tokens_saved, savings_percentage)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                cache_key,
                result.pruned_code,
                result.original_chars,
                result.pruned_chars,
                result.estimated_tokens_saved,
                result.savings_percentage
            ))