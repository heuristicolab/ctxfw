"""
topological_resolver.py — Topological Dependency Graph & Context Firewall Engine (v2.0)
Resolves internal project call graphs, assigns semantic distances (D0, D1, D2+),
and dispatches multi-depth AST pruning with SQLite WAL caching.
"""
from __future__ import annotations

import ast
from collections import deque
from pathlib import Path
from typing import Dict, List, Optional, Set
from pydantic import BaseModel, ConfigDict, Field

from contracts import (
    DeterministicContextPruner,
    LocalSemanticCache,
    OptimizationRequestDTO,
    OptimizationResultDTO,
    PruningDepth,
)


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

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            resolved = (
                self._resolve_candidate(alias.name, self.file_path.parent)
                or self._resolve_candidate(alias.name, self.project_root)
            )
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
                resolved = (
                    self._resolve_candidate(node.module, self.file_path.parent)
                    or self._resolve_candidate(node.module, self.project_root)
                )
                if resolved and resolved != self.file_path:
                    self.local_dependencies.add(resolved)
                elif not resolved:
                    # In case of `from pkg import mod`, check alias names
                    for alias in node.names:
                        compound = f"{node.module}.{alias.name}"
                        cand = (
                            self._resolve_candidate(compound, self.file_path.parent)
                            or self._resolve_candidate(compound, self.project_root)
                        )
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

    def __init__(self, project_root: Path | str, cache: Optional[LocalSemanticCache] = None):
        self.project_root = Path(project_root).resolve()
        self.cache = cache or LocalSemanticCache()
        self.graph = ProjectDependencyGraph(self.project_root)

    def build_context(self, target_file: str | Path) -> TopologicalContextBundleDTO:
        """Builds multi-depth context bundle: D0 (Full), D1 (Interface), D2+ (Nominal)."""
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
