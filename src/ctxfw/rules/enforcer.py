# manifest_hash: 862e0dc20133fe81f2ce12812b86d74068db80cce8566a3b71d2d406db72c549
"""
Claude Rules Compiler :: Rules Enforcer & AST Auditor
=====================================================
manifest_hash_wave1a: 4b3c6d65f2aeffd4fcfd8ecf166c4983ef94b046d3c9b7fd5e391811d32a5d82
Enforces compiled guards against tool calls and audits Python source code via AST analysis.
Features 3-round path traversal unquoting, URI-scheme rejection, OS confinement, and deterministic matching.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path
import posixpath
import re
import shlex
import urllib.parse
from typing import Sequence, Tuple, Union

from ctxfw.rules.contracts import (
    CompiledAstGuardDTO,
    EnforcementVerdict,
    PatternType,
    RuleComplianceAuditDTO,
)

__all__ = [
    "RulesEnforcer",
    "audit_source",
    "is_path_confined",
    "normalize_path",
]

_WIN_DRIVE_RE = re.compile(r"^[A-Za-z]:(?:[/\\]|$)")
_URI_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]{1,20}:")


def normalize_path(raw: str, max_rounds: int = 3) -> str:
    """Normalize and sanitize file paths against traversal, null-byte, and file:// URI attacks.

    Steps:
      1. Null byte rejection prior to and after unquoting.
      2. Iterative percent/hex unquoting up to max_rounds (default 3).
         Raises ValueError if encoding does not stabilize.
      3. Reject file:// URI smuggling (e.g. file:///etc/passwd or file:secret).
      4. Backslash conversion ('\\\\' -> '/') and posixpath.normpath.
      5. Stripping of './' prefix.
      6. Traversal check: raises ValueError if path escapes project root (starts with '../', '/../', or is '..').
      7. Returns normalized path in lowercase.
    """
    if "\x00" in raw:
        raise ValueError("path contains null byte")

    current = raw
    for _ in range(max_rounds):
        nxt = urllib.parse.unquote(current)
        if nxt == current:
            break
        current = nxt
    else:
        if urllib.parse.unquote(current) != current:
            raise ValueError("path encoding does not stabilize")

    if "\x00" in current:
        raise ValueError("path contains null byte")

    stripped_lower = current.strip().lower()
    if stripped_lower.startswith("file:"):
        raise ValueError("file:// URI scheme not permitted in path")
    if _URI_SCHEME_RE.match(current.strip()) and not _WIN_DRIVE_RE.match(current.strip()):
        raise ValueError("URI scheme not permitted in path")

    # Detect explicit traversal sequences in unquoted text
    cleaned = current.replace("\\", "/")
    if cleaned.startswith("/..") or "/../" in cleaned or cleaned == "/..":
        raise ValueError("path escapes the project root")

    norm = posixpath.normpath(cleaned)
    while norm.startswith("./"):
        norm = norm[2:]

    if norm == ".." or norm.startswith("../"):
        raise ValueError("path escapes the project root")

    return norm.lower()


def is_path_confined(
    candidate: Union[str, Path],
    authorized_roots: Sequence[Union[str, Path]],
    *,
    follow_symlinks: bool = False,
) -> Tuple[bool, str]:
    """Verify real OS component confinement of candidate within authorized_roots (#03 PT-001..PT-005)."""
    from ctxfw.mcp_guard.contracts import is_component_confined

    res = is_component_confined(
        candidate,
        authorized_roots,
        follow_symlinks=follow_symlinks,
    )
    return res.allowed, res.reason


def _is_subsequence(sub: Sequence[str], full: Sequence[str]) -> bool:
    """True if all elements of sub appear in full in the same relative order."""
    if not sub:
        return True
    it = iter(full)
    return all(tok in it for tok in sub)


def _clean_path_for_match(p: str) -> str:
    norm = p.lower().replace("\\", "/")
    while norm.startswith("./"):
        norm = norm[2:]
    return norm.rstrip("/")


def _path_matches(target: str, token: str) -> bool:
    """Check if token matches or is prefixed by target path."""
    target_clean = _clean_path_for_match(target)
    try:
        token_clean = normalize_path(token)
    except ValueError:
        return False

    if token_clean == target_clean:
        return True
    if token_clean.startswith(target_clean + "/"):
        return True
    if token_clean.endswith("/" + target_clean):
        return True
    if f"/{target_clean}/" in f"/{token_clean}/":
        return True
    return False


def _get_call_name(node: ast.AST) -> str:
    """Resolve full qualified function name from an ast.Call func node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _get_call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _resolve_call_names(node: ast.AST, aliases: dict[str, str]) -> set[str]:
    """Resolve both literal call name and alias-dereferenced call names."""
    names: set[str] = set()

    def _get_chain(n: ast.AST) -> list[str]:
        if isinstance(n, ast.Name):
            return [n.id]
        if isinstance(n, ast.Attribute):
            base = _get_chain(n.value)
            if base:
                return base + [n.attr]
        return []

    chain = _get_chain(node)
    if not chain:
        return names

    literal = ".".join(chain)
    names.add(literal)

    root = chain[0]
    if root in aliases:
        aliased_chain = [aliases[root]] + chain[1:]
        names.add(".".join(aliased_chain))

    return names


class RulesEnforcer:
    """Evaluates tool calls against compiled AST guards."""

    @classmethod
    def evaluate(
        cls,
        guards: tuple[CompiledAstGuardDTO, ...],
        tool_call: str,
    ) -> tuple[EnforcementVerdict, tuple[str, ...]]:
        """Evaluate a tool call against guards, returning verdict and matched guard IDs."""
        try:
            tokens = shlex.split(tool_call)
        except ValueError:
            tokens = tool_call.split()

        path_guards = [g for g in guards if g.pattern_type is PatternType.PATH_PREFIX]

        # Traversal evasion check: if any token fails normalization and path guards exist, block immediately!
        if path_guards:
            for tok in tokens:
                if any(c in tok for c in ("/", "\\", "%", "..", "\x00")) or tok.lower().startswith("file:"):
                    try:
                        normalize_path(tok)
                    except ValueError:
                        return EnforcementVerdict.BLOCKED, tuple(g.guard_id for g in path_guards)

        blocked_guard_ids: list[str] = []
        call_tokens_lower = [t.lower() for t in tokens]

        for guard in guards:
            if guard.pattern_type is PatternType.COMMAND_PREFIX:
                target_tokens = guard.target_symbol_or_path.lower().split()
                if _is_subsequence(target_tokens, call_tokens_lower):
                    blocked_guard_ids.append(guard.guard_id)
            elif guard.pattern_type is PatternType.PATH_PREFIX:
                for tok in tokens:
                    if _path_matches(guard.target_symbol_or_path, tok):
                        blocked_guard_ids.append(guard.guard_id)
                        break
            elif guard.pattern_type is PatternType.AST_CALL:
                target = guard.target_symbol_or_path.lower()
                if re.search(r"\b" + re.escape(target) + r"\b", tool_call.lower()):
                    blocked_guard_ids.append(guard.guard_id)
            elif guard.pattern_type is PatternType.IMPORT_MODULE:
                target = guard.target_symbol_or_path.lower()
                if re.search(r"\b(?:import|from)\s+" + re.escape(target) + r"\b", tool_call.lower()):
                    blocked_guard_ids.append(guard.guard_id)

        if blocked_guard_ids:
            return EnforcementVerdict.BLOCKED, tuple(dict.fromkeys(blocked_guard_ids))
        return EnforcementVerdict.ALLOW, ()


def audit_source(
    guards: tuple[CompiledAstGuardDTO, ...],
    source_code: str,
    file_scanned: str,
) -> RuleComplianceAuditDTO:
    """Audit Python source code against compiled guards using Python AST.

    Raises:
      ValueError: If source_code cannot be parsed as valid Python.
    """
    try:
        tree = ast.parse(source_code, filename=file_scanned)
    except SyntaxError as exc:
        raise ValueError(f"source code is not parseable python: {exc}") from exc

    hits: list[str] = []
    ast_call_guards = {
        g.target_symbol_or_path: g.guard_id
        for g in guards
        if g.pattern_type is PatternType.AST_CALL
    }
    import_guards = {
        g.target_symbol_or_path: g.guard_id
        for g in guards
        if g.pattern_type is PatternType.IMPORT_MODULE
    }

    # First pass: map imported aliases to resolve full names
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                full_name = f"{mod}.{alias.name}" if mod else alias.name
                aliases[alias.asname or alias.name] = full_name

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            resolved_names = _resolve_call_names(node.func, aliases)
            for func_name in resolved_names:
                for target, gid in ast_call_guards.items():
                    if func_name == target or func_name.endswith("." + target):
                        hits.append(gid)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                for target, gid in import_guards.items():
                    if alias.name == target or alias.name.startswith(target + "."):
                        hits.append(gid)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for target, gid in import_guards.items():
                if mod == target or mod.startswith(target + "."):
                    hits.append(gid)
                for alias in node.names:
                    full_imported = f"{mod}.{alias.name}" if mod else alias.name
                    if full_imported == target or alias.name == target:
                        hits.append(gid)
            # Also catch importing banned call targets directly (e.g. from os import system)
            for alias in node.names:
                full_imported = f"{mod}.{alias.name}" if mod else alias.name
                for target, gid in ast_call_guards.items():
                    if full_imported == target or alias.name == target:
                        hits.append(gid)

    unique_hits = tuple(dict.fromkeys(hits))
    return RuleComplianceAuditDTO.build(file_scanned, unique_hits)
