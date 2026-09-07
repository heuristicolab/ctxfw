"""
src/ctxfw/core/pruner.py — AST Slicing and Method Body Stripper (v3.4.0)
Preserves type annotations, signatures, docstrings, and sanitized raises while stubbing bodies with Ellipsis.
"""
from __future__ import annotations

import ast
import time
from typing import Tuple

from ctxfw.core.contracts import (
    OptimizationRequestDTO,
    PruningDepth,
    SupportedLanguage,
)


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
        lang_str = request.language.value.lower() if isinstance(request.language, SupportedLanguage) else str(request.language).lower()

        if lang_str != "python":
            from ctxfw.core.polyglot import TreeSitterContextPruner
            lang_enum = SupportedLanguage(lang_str)
            return TreeSitterContextPruner.prune(
                source_code=request.source_code,
                language=lang_enum,
                depth=request.depth.value,
            )

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
