"""
src/ctxfw/core/topological.py — Topological Dependency Graph & Context Firewall Engine (v3.4.0)
Resolves internal project call graphs, assigns semantic distances (D0, D1, D2+),
and dispatches multi-depth AST pruning with SQLite WAL caching.
"""
from __future__ import annotations

import ast
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Set
from pydantic import BaseModel, ConfigDict, Field

from ctxfw.core.contracts import (
    OptimizationRequestDTO,
    OptimizationResultDTO,
    PruningDepth,
)
from ctxfw.core.pruner import DeterministicContextPruner
from ctxfw.storage.cache import LocalSemanticCache


class StaticImportExtractor(ast.NodeVisitor):
    """AST visitor that extracts local project imports, filtering out stdlib and 3rd-party packages."""

    def __init__(self, file_path: Path, project_root: Path):
        self.file_path = file_path.resolve()
        self.project_root = project_root.resolve()
        self.local_dependencies: Set[Path] = set()

    def _resolve_candidate(self, module_name: str, base_dir: Path) -> Optional[Path]:
        parts = module_name.split(".")
        # 1. Try as direct .py file
        candidate_file = (base_dir / "/".join(parts)).with_suffix(".py")
        if candidate_file.is_file():
            try:
                candidate_file.relative_to(self.project_root)
                return candidate_file.resolve()
            except ValueError:
                return None

        # 2. Try as package directory with __init__.py
        candidate_pkg = base_dir / "/".join(parts) / "__init__.py"
        if candidate_pkg.is_file():
            try:
                candidate_pkg.relative_to(self.project_root)
                return candidate_pkg.resolve()
            except ValueError:
                return None

        # 3. If module_name has multiple parts, check if prefix is a file (e.g., `from models import User`)
        if len(parts) > 1:
            prefix_file = (base_dir / "/".join(parts[:-1])).with_suffix(".py")
            if prefix_file.is_file():
                try:
                    prefix_file.relative_to(self.project_root)
                    return prefix_file.resolve()
                except ValueError:
                    return None

        return None

    def _resolve_in_hierarchy(self, module_name: str) -> Optional[Path]:
        curr = self.file_path.parent
        while True:
            cand = self._resolve_candidate(module_name, curr)
            if cand:
                return cand
            if curr == self.project_root or curr == curr.parent:
                break
            curr = curr.parent
        return self._resolve_candidate(module_name, self.project_root)

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            resolved = self._resolve_in_hierarchy(alias.name)
            if resolved and resolved != self.file_path:
                self.local_dependencies.add(resolved)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.level > 0:
            # Relative import resolution (. or ..)
            base = self.file_path.parent
            for _ in range(node.level - 1):
                base = base.parent

            if node.module:
                resolved = self._resolve_candidate(node.module, base)
                if resolved and resolved != self.file_path:
                    self.local_dependencies.add(resolved)
            else:
                for alias in node.names:
                    resolved = self._resolve_candidate(alias.name, base)
                    if resolved and resolved != self.file_path:
                        self.local_dependencies.add(resolved)
        else:
            # Absolute project-level import
            if node.module:
                resolved = self._resolve_in_hierarchy(node.module)
                if resolved and resolved != self.file_path:
                    self.local_dependencies.add(resolved)
                elif not resolved:
                    # In case of `from pkg import mod`, check alias names
                    for alias in node.names:
                        compound = f"{node.module}.{alias.name}"
                        cand = self._resolve_in_hierarchy(compound)
                        if cand and cand != self.file_path:
                            self.local_dependencies.add(cand)

        self.generic_visit(node)

    @classmethod
    def extract_from_file(cls, file_path: Path, project_root: Path) -> Set[Path]:
        """Extracts local project dependencies declared inside a Python file."""
        try:
            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(file_path))
        except (SyntaxError, UnicodeDecodeError):
            return set()

        visitor = cls(file_path, project_root)
        visitor.visit(tree)
        return visitor.local_dependencies


class ProjectDependencyGraph:
    """Scans project directory, builds module adjacency map, and resolves topological distances."""

    def __init__(self, project_root: Path | str):
        self.project_root = Path(project_root).resolve()
        self.adjacency: Dict[str, Set[str]] = {}
        self._build_graph()

    def _normalize_rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.project_root).as_posix()

    def _build_graph(self):
        # Scan all .py files in project_root, ignoring virtualenvs and hidden dirs
        py_files = [
            f for f in self.project_root.rglob("*.py")
            if not any(part.startswith(".") for part in f.parts) and "venv" not in f.parts
        ]
        for f in py_files:
            rel = self._normalize_rel(f)
            deps = StaticImportExtractor.extract_from_file(f, self.project_root)
            self.adjacency[rel] = {self._normalize_rel(dep) for dep in deps}

    def get_distances(self, target_file: str | Path) -> Dict[str, int]:
        """Calculates shortest topological distance from target_file to all reachable modules."""
        target_path = Path(target_file)
        if target_path.is_absolute():
            target_rel = self._normalize_rel(target_path)
        else:
            target_rel = (self.project_root / target_path).resolve().relative_to(self.project_root).as_posix()

        distances: Dict[str, int] = {target_rel: 0}
        queue = deque([target_rel])

        while queue:
            curr = queue.popleft()
            curr_dist = distances[curr]

            for neighbor in self.adjacency.get(curr, set()):
                if neighbor not in distances:
                    distances[neighbor] = curr_dist + 1
                    queue.append(neighbor)

        return distances


class TopologicalContextBundleDTO(BaseModel):
    """Contrato inmutable de paquete de contexto topológico optimizado."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    root_target: str
    entries: Dict[str, OptimizationResultDTO] = Field(..., description="Módulos optimizados indexados por ruta relativa")

    def to_dict(self) -> Dict[str, str]:
        """Maps relative file path to pruned source code string."""
        return {path: res.pruned_code for path, res in self.entries.items()}

    def to_prompt(self) -> str:
        """Concatenates modules into a deterministic Markdown prompt format."""
        sections: List[str] = [
            f"# CONTEXT BUNDLE — Root Target: {self.root_target}",
            f"# Total Modules: {len(self.entries)}",
            "",
        ]
        for rel_path, res in self.entries.items():
            depth_tag = res.depth.value.upper()
            sections.append(f"### File: {rel_path} [{depth_tag}]")
            sections.append(f"```python\n{res.pruned_code}\n```")
            sections.append("")
        return "\n".join(sections)


class ContextFirewallEngine:
    """Orchestrates topological dependency resolution, multi-depth AST pruning, and WAL caching."""

    def __init__(
        self,
        project_root: Path | str,
        cache: Optional[LocalSemanticCache] = None,
        mode: Optional[str] = None,
    ):
        self.project_root = Path(project_root).resolve()
        self.cache = cache or LocalSemanticCache()
        self.graph = ProjectDependencyGraph(self.project_root)
        self.mode = mode

    def build_context(
        self,
        target_file: str | Path,
        mode: Optional[str] = None,
    ) -> TopologicalContextBundleDTO:
        """
        Builds multi-depth context bundle: D0 (Full), D1 (Interface), D2+ (Nominal).
        Enforces Invariant 3: If engine.mode is 'passthrough', AST pruning is completely
        bypassed and raw intact source code is returned for all perimeter dependencies.
        """
        effective_mode = (mode or self.mode or "").lower()
        if not effective_mode:
            try:
                from ctxfw.config import load_config
                effective_mode = load_config().engine.mode.value.lower()
            except Exception:
                effective_mode = "distance"

        distances = self.graph.get_distances(target_file)
        target_path = Path(target_file)
        if target_path.is_absolute():
            target_rel = target_path.resolve().relative_to(self.project_root).as_posix()
        else:
            target_rel = (self.project_root / target_path).resolve().relative_to(self.project_root).as_posix()

        entries: Dict[str, OptimizationResultDTO] = {}
        sorted_modules = sorted(distances.items(), key=lambda item: (item[1], item[0]))

        for rel_path, distance in sorted_modules:
            full_path = self.project_root / rel_path
            if not full_path.is_file():
                continue

            code = full_path.read_text(encoding="utf-8")

            # Invariant 3: Passthrough mode bypasses AST pruning for all dependencies
            if effective_mode == "passthrough":
                orig_c = len(code)
                entries[rel_path] = OptimizationResultDTO(
                    pruned_code=code,
                    original_chars=orig_c,
                    pruned_chars=orig_c,
                    estimated_tokens_saved=0,
                    savings_percentage=0.0,
                    cache_hit=False,
                    execution_ms=0.0,
                    depth=PruningDepth.FULL,
                )
                continue

            if distance == 0:
                depth = PruningDepth.FULL
            elif distance == 1:
                depth = PruningDepth.INTERFACE
            else:
                depth = PruningDepth.NOMINAL

            cache_key = LocalSemanticCache.generate_key(
                source_code=code,
                rules_version=DeterministicContextPruner.RULES_VERSION,
                strip_docs=False,
                depth=depth.value,
            )

            cached_result = self.cache.get(cache_key)
            if cached_result is not None:
                entries[rel_path] = cached_result
            else:
                req = OptimizationRequestDTO(
                    source_code=code,
                    language="python",
                    strip_docs=False,
                    depth=depth,
                    sanitize_raises=True,
                )
                pruned_code, orig_c, pruned_c, saved, pct, ms = DeterministicContextPruner.prune(req)
                dto = OptimizationResultDTO(
                    pruned_code=pruned_code,
                    original_chars=orig_c,
                    pruned_chars=pruned_c,
                    estimated_tokens_saved=saved,
                    savings_percentage=pct,
                    cache_hit=False,
                    execution_ms=ms,
                    depth=depth,
                )
                self.cache.set(cache_key, dto)
                entries[rel_path] = dto

        return TopologicalContextBundleDTO(
            root_target=target_rel,
            entries=entries,
        )


class DependencyNode:
    """Represents an individual dependency node in a topological manifest."""
    def __init__(self, file_path: Path, depth_level: int, token_count: int):
        self.file_path = Path(file_path)
        self.depth_level = depth_level
        self.token_count = token_count


class TopologicalManifest:
    """Represents the resolved topological manifest for a target module."""
    def __init__(self, target_file: Path, dependencies: List[DependencyNode]):
        self.target_file = Path(target_file)
        self.dependencies = dependencies
        self.total_tokens = sum(d.token_count for d in dependencies)


class TopologicalResolver:
    """High-level resolver calculating topological manifests for a given root directory."""
    def __init__(self, root_dir: Path | str):
        self.root_dir = Path(root_dir).resolve()
        self.graph = ProjectDependencyGraph(self.root_dir)

    def resolve(self, target_file: Path | str) -> TopologicalManifest:
        target_path = Path(target_file).resolve()
        distances = self.graph.get_distances(target_path)
        deps: List[DependencyNode] = []
        for rel_path, dist in sorted(distances.items(), key=lambda x: (x[1], x[0])):
            fp = self.root_dir / rel_path
            if fp.is_file():
                chars = len(fp.read_text(encoding="utf-8", errors="replace"))
                tokens = DeterministicContextPruner.estimate_tokens(chars)
                deps.append(DependencyNode(file_path=fp, depth_level=dist, token_count=tokens))
        return TopologicalManifest(target_file=target_path, dependencies=deps)

