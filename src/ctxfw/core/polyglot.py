"""
src/ctxfw/core/polyglot.py — Concrete Syntax Tree (CST) Polyglot Pruning Engine (v3.4.0)
Leverages Tree-sitter CST traversal to slice TypeScript/JavaScript, Go, and Java,
preserving signatures, interfaces, types, and DTO structures while stubbing method bodies.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional, Set, Tuple

from ctxfw.core.contracts import SupportedLanguage


class TreeSitterContextPruner:
    """Motor políglota de slicing basado en Tree-sitter CST."""

    _parsers: Dict[str, object] = {}

    @classmethod
    def _get_parser(cls, language: SupportedLanguage):
        lang_key = language.value.lower()
        if lang_key in cls._parsers:
            return cls._parsers[lang_key]

        try:
            import tree_sitter as ts
        except ImportError as e:
            raise RuntimeError(
                f"Tree-sitter no está instalado. Para podado políglota instale 'tree-sitter': {e}"
            ) from e

        ts_lang = None
        # 1. Try modern individual tree_sitter_<lang> packages
        if lang_key in ("typescript", "javascript"):
            try:
                import tree_sitter_typescript as ts_ts
                ts_lang = ts.Language(ts_ts.language_typescript())
            except ImportError:
                pass
        elif lang_key == "go":
            try:
                import tree_sitter_go as ts_go
                ts_lang = ts.Language(ts_go.language())
            except ImportError:
                pass
        elif lang_key == "java":
            try:
                import tree_sitter_java as ts_java
                ts_lang = ts.Language(ts_java.language())
            except ImportError:
                pass

        # 2. Try tree_sitter_languages fallback
        if ts_lang is None:
            try:
                import tree_sitter_languages as tsl
                ts_lang = tsl.get_language(lang_key)
                parser = tsl.get_parser(lang_key)
                cls._parsers[lang_key] = parser
                return parser
            except Exception:
                pass

        if ts_lang is None:
            raise RuntimeError(
                f"Gramática de Tree-sitter para '{lang_key}' no disponible. "
                f"Instale 'tree-sitter-{lang_key}' o 'tree-sitter-languages'."
            )

        parser = ts.Parser(ts_lang)
        cls._parsers[lang_key] = parser
        return parser

    @classmethod
    def estimate_tokens(cls, chars: int) -> int:
        return max(1, chars // 4)

    @classmethod
    def _collect_ts_replacements(
        cls, node, replacements: List[Tuple[int, int, bytes]], stub_bytes: bytes, depth: str
    ):
        target_types = {
            "function_declaration",
            "method_definition",
            "arrow_function",
            "function_expression",
            "generator_function_declaration",
        }
        if node.type in target_types:
            for child in node.children:
                if child.type == "statement_block":
                    replacements.append((child.start_byte, child.end_byte, stub_bytes))
                    return

        for child in node.children:
            cls._collect_ts_replacements(child, replacements, stub_bytes, depth)

    @classmethod
    def _collect_go_replacements(
        cls, node, replacements: List[Tuple[int, int, bytes]], stub_bytes: bytes, depth: str
    ):
        target_types = {"function_declaration", "method_declaration"}
        if node.type in target_types:
            for child in node.children:
                if child.type == "block":
                    replacements.append((child.start_byte, child.end_byte, stub_bytes))
                    return

        for child in node.children:
            cls._collect_go_replacements(child, replacements, stub_bytes, depth)

    @classmethod
    def _collect_java_replacements(
        cls, node, replacements: List[Tuple[int, int, bytes]], stub_bytes: bytes, depth: str
    ):
        target_types = {"method_declaration", "constructor_declaration"}
        if node.type in target_types:
            for child in node.children:
                if child.type in ("block", "constructor_body"):
                    replacements.append((child.start_byte, child.end_byte, stub_bytes))
                    return

        for child in node.children:
            cls._collect_java_replacements(child, replacements, stub_bytes, depth)

    @classmethod
    def prune(
        cls,
        source_code: str,
        language: SupportedLanguage,
        depth: str = "interface",
    ) -> Tuple[str, int, int, int, float, float]:
        """Prunes method/function bodies in TypeScript, Go, or Java source code using Tree-sitter CST."""
        start = time.perf_counter()
        orig_chars = len(source_code)
        orig_tokens = cls.estimate_tokens(orig_chars)

        if depth == "full":
            elapsed_ms = (time.perf_counter() - start) * 1000
            return source_code, orig_chars, orig_chars, 0, 0.0, round(elapsed_ms, 3)

        parser = cls._get_parser(language)
        source_bytes = source_code.encode("utf-8")
        tree = parser.parse(source_bytes)

        replacements: List[Tuple[int, int, bytes]] = []
        lang_val = language.value.lower()

        if lang_val in ("typescript", "javascript"):
            stub_bytes = b"{ /* ... */ }" if depth == "interface" else b"{}"
            cls._collect_ts_replacements(tree.root_node, replacements, stub_bytes, depth)
        elif lang_val == "go":
            stub_bytes = b'{ panic("not implemented") }' if depth == "interface" else b"{}"
            cls._collect_go_replacements(tree.root_node, replacements, stub_bytes, depth)
        elif lang_val == "java":
            stub_bytes = b"{ throw new UnsupportedOperationException(); }" if depth == "interface" else b"{}"
            cls._collect_java_replacements(tree.root_node, replacements, stub_bytes, depth)
        else:
            raise ValueError(f"Lenguaje políglota no soportado: {language}")

        # Reverse sorting to maintain correct byte offsets during in-place substitution
        buf = bytearray(source_bytes)
        for s, e, repl in sorted(replacements, key=lambda x: x[0], reverse=True):
            buf[s:e] = repl

        pruned_code = buf.decode("utf-8", errors="replace")
        elapsed_ms = (time.perf_counter() - start) * 1000

        pruned_chars = len(pruned_code)
        pruned_tokens = cls.estimate_tokens(pruned_chars)
        tokens_saved = max(0, orig_tokens - pruned_tokens)
        savings_pct = round(((orig_chars - pruned_chars) / max(1, orig_chars)) * 100, 2)

        return pruned_code, orig_chars, pruned_chars, tokens_saved, savings_pct, round(elapsed_ms, 3)
