from __future__ import annotations

import ast
from enum import Enum
import hashlib
import sqlite3
import time
from typing import Optional, Tuple
from pydantic import BaseModel, ConfigDict, Field


class PruningDepth(str, Enum):
    """Niveles de profundidad de poda topológica."""
    FULL = "full"             # D0: 100% código íntegro sin poda
    INTERFACE = "interface"   # D1: Firmas, tipos, docstrings, decoradores, raises sanitizados y ...
    NOMINAL = "nominal"       # D2+: Esquemas puramente nominales (clases / DTOs sin métodos)


class OptimizationRequestDTO(BaseModel):
    """Contrato inmutable de solicitud de optimización."""
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    source_code: str = Field(..., min_length=1, description="Código fuente a podar")
    language: str = Field(default="python", description="Lenguaje de programación")
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


class _MethodBodyStripper(ast.NodeTransformer):
    """Visitor AST que preserva firmas/tipos, stubs tipados (...) y sentencias raise."""
    def __init__(
        self,
        strip_docs: bool = False,
        depth: PruningDepth = PruningDepth.INTERFACE,
        sanitize_raises: bool = True,
    ):
        self.strip_docs = strip_docs
        self.depth = depth
        self.sanitize_raises = sanitize_raises

    def _extract_raises(self, body: list[ast.stmt]) -> list[ast.Raise]:
        found: list[ast.Raise] = []
        seen: set[str] = set()
        for stmt in body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            for child in ast.walk(stmt):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and child is not stmt:
                    continue
                if isinstance(child, ast.Raise) and child.exc is not None:
                    if self.sanitize_raises:
                        if isinstance(child.exc, ast.Call):
                            sanitized_exc = ast.Call(
                                func=child.exc.func,
                                args=[ast.Constant(value="...")],
                                keywords=[]
                            )
                        elif isinstance(child.exc, (ast.Name, ast.Attribute)):
                            sanitized_exc = ast.Call(
                                func=child.exc,
                                args=[ast.Constant(value="...")],
                                keywords=[]
                            )
                        else:
                            sanitized_exc = ast.Call(
                                func=ast.Name(id="Exception", ctx=ast.Load()),
                                args=[ast.Constant(value="...")],
                                keywords=[]
                            )
                        clean_raise = ast.Raise(exc=sanitized_exc, cause=None)
                    else:
                        clean_raise = child
                    raise_repr = ast.unparse(clean_raise)
                    if raise_repr not in seen:
                        seen.add(raise_repr)
                        found.append(clean_raise)
        return found

    def _clean_body(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        has_doc = (
            len(node.body) > 0
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        )
        new_body: list[ast.stmt] = []
        if has_doc and not self.strip_docs:
            new_body.append(node.body[0])

        if self.depth == PruningDepth.INTERFACE:
            raises = self._extract_raises(node.body)
            new_body.extend(raises)

        # Canonical typed stub (...)
        new_body.append(ast.Expr(value=ast.Constant(value=Ellipsis)))
        node.body = new_body
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        self.generic_visit(node)
        return self._clean_body(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:
        self.generic_visit(node)
        return self._clean_body(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        self.generic_visit(node)
        if self.depth == PruningDepth.NOMINAL:
            # In NOMINAL mode (D2+), retain only docstring and type-annotated attributes; strip methods
            has_doc = (
                len(node.body) > 0
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            )
            nominal_body: list[ast.stmt] = []
            if has_doc and not self.strip_docs:
                nominal_body.append(node.body[0])
            for item in node.body:
                if isinstance(item, ast.AnnAssign):
                    nominal_body.append(item)
            if not nominal_body:
                nominal_body.append(ast.Expr(value=ast.Constant(value=Ellipsis)))
            node.body = nominal_body
        return node


class DeterministicContextPruner:
    """Motor de slicing determinista basado en Python AST."""
    RULES_VERSION = "v2.0.0"

    @staticmethod
    def estimate_tokens(chars: int) -> int:
        return max(1, chars // 4)

    @classmethod
    def prune(cls, request: OptimizationRequestDTO) -> Tuple[str, int, int, int, float, float]:
        start = time.perf_counter()
        if request.language.lower() != "python":
            raise ValueError(f"Lenguaje no soportado: {request.language}")

        orig_chars = len(request.source_code)
        orig_tokens = cls.estimate_tokens(orig_chars)

        # D0: FULL mode preserves 100% implementation untouched
        if request.depth == PruningDepth.FULL:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return request.source_code, orig_chars, orig_chars, 0, 0.0, round(elapsed_ms, 3)

        try:
            tree = ast.parse(request.source_code)
        except SyntaxError as e:
            raise ValueError(f"Error de sintaxis en el código: {e}") from e

        stripper = _MethodBodyStripper(
            strip_docs=request.strip_docs,
            depth=request.depth,
            sanitize_raises=request.sanitize_raises,
        )
        pruned_tree = stripper.visit(tree)
        ast.fix_missing_locations(pruned_tree)

        pruned_code = ast.unparse(pruned_tree)
        elapsed_ms = (time.perf_counter() - start) * 1000

        pruned_chars = len(pruned_code)
        pruned_tokens = cls.estimate_tokens(pruned_chars)
        tokens_saved = max(0, orig_tokens - pruned_tokens)
        savings_pct = round(((orig_chars - pruned_chars) / max(1, orig_chars)) * 100, 2)

        return pruned_code, orig_chars, pruned_chars, tokens_saved, savings_pct, round(elapsed_ms, 3)


class LocalSemanticCache:
    """Caché transaccional embebido con persistencia en SQLite WAL y mitigación de contención."""
    def __init__(self, db_path: str = "heuristic_tokens_cache.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tokens_cache';")
            if cur.fetchone():
                columns = [row[1] for row in cur.execute("PRAGMA table_info(tokens_cache);").fetchall()]
                if "pruning_depth" not in columns:
                    conn.execute("DROP TABLE tokens_cache;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tokens_cache (
                    cache_key TEXT PRIMARY KEY,
                    pruned_code TEXT NOT NULL,
                    pruning_depth TEXT NOT NULL DEFAULT 'interface',
                    original_chars INTEGER NOT NULL,
                    pruned_chars INTEGER NOT NULL,
                    estimated_tokens_saved INTEGER NOT NULL,
                    savings_percentage REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

    @staticmethod
    def generate_key(source_code: str, rules_version: str, strip_docs: bool, depth: str = "interface") -> str:
        payload = f"{source_code}|{rules_version}|{strip_docs}|{depth}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, cache_key: str) -> Optional[OptimizationResultDTO]:
        start = time.perf_counter()
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT pruned_code, original_chars, pruned_chars, estimated_tokens_saved, savings_percentage, pruning_depth
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
                execution_ms=round(elapsed_ms, 3),
                depth=PruningDepth(row[5]) if len(row) > 5 and row[5] else PruningDepth.INTERFACE,
            )

    def set(self, cache_key: str, result: OptimizationResultDTO):
        depth_val = result.depth.value if hasattr(result.depth, "value") else str(result.depth)
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO tokens_cache 
                (cache_key, pruned_code, pruning_depth, original_chars, pruned_chars, estimated_tokens_saved, savings_percentage)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                cache_key,
                result.pruned_code,
                depth_val,
                result.original_chars,
                result.pruned_chars,
                result.estimated_tokens_saved,
                result.savings_percentage,
            ))