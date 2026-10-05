"""
src/ctxfw/core/topological.py — Topological Dependency Graph & Context Firewall Engine (v4.0.0-dev)
manifest_hash: 837e90a0d2d97f569f7190da2652d4e578efadf86b71d4a5c3020c6e16bf5bd3

Resolves internal project call graphs, assigns semantic distances (D0, D1, D2, D3),
and dispatches multi-depth AST pruning and D3 ambient cartography with SQLite WAL caching.
"""
from __future__ import annotations

import ast
from collections import deque
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, ConfigDict, Field

from ctxfw.config import ContextDepthLevel, CtxfwConfigDTO, load_depth_config
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
        self._distance_cache: Dict[str, Dict[str, int]] = {}
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

        if target_rel in self._distance_cache:
            return self._distance_cache[target_rel]

        distances: Dict[str, int] = {target_rel: 0}
        queue = deque([target_rel])

        while queue:
            curr = queue.popleft()
            curr_dist = distances[curr]

            for neighbor in self.adjacency.get(curr, set()):
                if neighbor not in distances:
                    distances[neighbor] = curr_dist + 1
                    queue.append(neighbor)

        self._distance_cache[target_rel] = distances
        return distances


def _rel_path_to_module_name(rel_path: str) -> str:
    """Converts relative POSIX file path to canonical Python module dot path."""
    p = rel_path.replace("\\", "/")
    if p.endswith("/__init__.py"):
        p = p[:-12]
    elif p.endswith(".py"):
        p = p[:-3]
    return p.replace("/", ".")


class D3SymbolExtractor(ast.NodeVisitor):
    """
    Extracts public symbols for D3 Ambient Manifest.
    Identifies classes (:C), functions (:F), and constants (:K).
    Detects dynamic namespaces (PEP 562 __getattr__, dynamic __all__) and flags
    them with '[DYNAMIC_UNBOUND:?]' per AXIOM-17.
    """
    def __init__(self):
        self.symbols: List[str] = []
        self.is_dynamic: bool = False

    def visit_FunctionDef(self, node: ast.FunctionDef):
        if node.name in ("__getattr__", "__dir__"):
            self.is_dynamic = True
        elif not node.name.startswith("_"):
            self.symbols.append(f"{node.name}:F")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        if not node.name.startswith("_"):
            self.symbols.append(f"{node.name}:F")

    def visit_ClassDef(self, node: ast.ClassDef):
        if not node.name.startswith("_"):
            self.symbols.append(f"{node.name}:C")

    def visit_Assign(self, node: ast.Assign):
        self._check_assign(node.targets, node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign):
        self._check_assign([node.target], node.value)

    def _check_assign(self, targets: List[ast.AST], value: Optional[ast.AST]):
        for target in targets:
            if isinstance(target, ast.Name):
                name = target.id
                if name == "__all__":
                    if not isinstance(value, (ast.List, ast.Tuple)):
                        self.is_dynamic = True
                    else:
                        for elt in value.elts:
                            if not isinstance(elt, ast.Constant) or not isinstance(elt.value, str):
                                self.is_dynamic = True
                elif name.isupper() and not name.startswith("_"):
                    self.symbols.append(f"{name}:K")

    @classmethod
    def extract_from_code(cls, code: str) -> List[str]:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return ["[DYNAMIC_UNBOUND:?]"]

        visitor = cls()
        visitor.visit(tree)
        res: List[str] = []
        if visitor.is_dynamic:
            res.append("[DYNAMIC_UNBOUND:?]")
        res.extend(sorted(set(visitor.symbols)))
        return res


class TopologicalContextBundleDTO(BaseModel):
    """Immutable optimized topological context bundle contract."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    root_target: str
    entries: Dict[str, OptimizationResultDTO] = Field(..., description="Optimized modules indexed by relative path")
    ambient_manifest: Optional[str] = Field(default=None, description="D3 Ambient Symbol Cartography manifest if enabled")

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
        if self.ambient_manifest:
            sections.append(self.ambient_manifest)
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
        depth_config: Optional[CtxfwConfigDTO] = None,
    ) -> TopologicalContextBundleDTO:
        """
        Builds multi-depth context bundle: D0 (Full), D1 (Interface), D2 (Nominal), D3 (Ambient).
        Enforces Invariant 3: If engine.mode is 'passthrough', AST pruning is completely
        bypassed and raw intact source code is returned for all perimeter dependencies.
        Enforces AXIOM-17 through AXIOM-21 for depth bounds, dynamic namespace quarantine,
        throttled warmup, and subsystem boundary clamping.
        """
        effective_mode = (mode or self.mode or "").lower()
        if not effective_mode:
            try:
                from ctxfw.config import load_config
                effective_mode = load_config().engine.mode.value.lower()
            except Exception:
                effective_mode = "distance"

        depth_cfg = depth_config or load_depth_config(self.project_root)

        distances = self.graph.get_distances(target_file)
        target_path = Path(target_file)
        if target_path.is_absolute():
            target_rel = target_path.resolve().relative_to(self.project_root).as_posix()
        else:
            target_rel = (self.project_root / target_path).resolve().relative_to(self.project_root).as_posix()

        entries: Dict[str, OptimizationResultDTO] = {}
        sorted_modules = sorted(distances.items(), key=lambda item: (item[1], item[0]))

        d3_candidate_modules: List[str] = []

        for rel_path, distance in sorted_modules:
            # Early distance filtering before filesystem stat operations
            if depth_cfg.max_depth == ContextDepthLevel.PURE_PASSTHROUGH and distance > 0:
                continue
            if depth_cfg.max_depth == ContextDepthLevel.DIRECT_INTERFACE and distance > 1:
                continue
            if depth_cfg.max_depth == ContextDepthLevel.AMBIENT_CARTOGRAPHY:
                if distance == 3:
                    d3_candidate_modules.append(rel_path)
                    continue
                elif distance > 3:
                    # AXIOM-20: strictly reject > 3
                    continue
            elif depth_cfg.ambient_manifest and distance == 3:
                d3_candidate_modules.append(rel_path)
                continue

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

            if not code.strip():
                orig_c = len(code)
                dto = OptimizationResultDTO(
                    pruned_code=code,
                    original_chars=orig_c,
                    pruned_chars=orig_c,
                    estimated_tokens_saved=0,
                    savings_percentage=0.0,
                    cache_hit=False,
                    execution_ms=0.0,
                    depth=depth,
                )
                self.cache.set(cache_key, dto)
                entries[rel_path] = dto
                continue

            cached_result = self.cache.get(cache_key)
            if cached_result is not None:
                entries[rel_path] = cached_result
            else:
                try:
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
                except Exception:
                    # Fail-open guardrail: preserve intact raw code on syntax errors or template files
                    orig_c = len(code)
                    dto = OptimizationResultDTO(
                        pruned_code=code,
                        original_chars=orig_c,
                        pruned_chars=orig_c,
                        estimated_tokens_saved=0,
                        savings_percentage=0.0,
                        cache_hit=False,
                        execution_ms=0.0,
                        depth=depth,
                    )
                self.cache.set(cache_key, dto)
                entries[rel_path] = dto

        ambient_manifest_str: Optional[str] = None
        if d3_candidate_modules and (depth_cfg.ambient_manifest or depth_cfg.max_depth == ContextDepthLevel.AMBIENT_CARTOGRAPHY):
            allowed_subsystems: Set[str] = set()
            if depth_cfg.subsystem_clamping:
                for ep in entries.keys():
                    parts = ep.split("/")
                    if len(parts) > 1:
                        allowed_subsystems.add(parts[0])

            valid_candidates: List[str] = []
            for rel_path in d3_candidate_modules:
                if depth_cfg.subsystem_clamping and allowed_subsystems:
                    parts = rel_path.split("/")
                    if len(parts) > 1 and parts[0] not in allowed_subsystems:
                        continue
                valid_candidates.append(rel_path)

            cached_d3 = self.cache.get_d3_symbols_batch(valid_candidates)

            d3_lines: List[str] = [
                "### AMBIENT MANIFEST [D3] (Zero-Syntax Symbol Index)",
                "# Compact symbol index for 3-hop transitive dependencies. Bodies and signatures omitted.",
            ]
            total_symbols_count = 0
            parsed_count = 0
            total_chars = sum(len(line) + 1 for line in d3_lines)
            records_to_cache: List[Tuple[str, str, float, List[str]]] = []

            for rel_path in valid_candidates:
                full_path = self.project_root / rel_path
                if not full_path.is_file():
                    continue

                try:
                    stat_info = full_path.stat()
                    current_mtime = stat_info.st_mtime
                except OSError:
                    continue

                hit = False
                symbols: List[str] = []
                if rel_path in cached_d3:
                    cached_mtime, cached_sha, cached_symbols = cached_d3[rel_path]
                    if abs(cached_mtime - current_mtime) < 1e-4:
                        symbols = cached_symbols
                        hit = True

                if not hit:
                    # AXIOM-18: throttle synchronous inline re-parsing to max 20 modules
                    if parsed_count >= 20:
                        if depth_cfg.stale_reads_on_herd and rel_path in cached_d3:
                            symbols = cached_d3[rel_path][2]
                        else:
                            break
                    else:
                        code = full_path.read_text(encoding="utf-8", errors="replace")
                        parsed_count += 1
                        symbols = D3SymbolExtractor.extract_from_code(code)
                        sha = hashlib.sha256(code.encode("utf-8")).hexdigest()
                        records_to_cache.append((rel_path, sha, current_mtime, symbols))

                remaining_budget = depth_cfg.distractor_budget - total_symbols_count
                if remaining_budget <= 0:
                    break

                if len(symbols) > remaining_budget:
                    symbols = symbols[:remaining_budget]

                mod_name = _rel_path_to_module_name(rel_path)
                line = f"{mod_name}: [{', '.join(symbols)}]"
                manifest_tokens = DeterministicContextPruner.estimate_tokens(total_chars + len(line) + 1)
                # AXIOM-19: Max 1,000 net tokens ceiling
                if manifest_tokens > 1000:
                    break

                d3_lines.append(line)
                total_symbols_count += len(symbols)
                total_chars += len(line) + 1

            if records_to_cache:
                self.cache.set_d3_symbols_batch(records_to_cache)

            if len(d3_lines) > 2:
                ambient_manifest_str = "\n".join(d3_lines)

        return TopologicalContextBundleDTO(
            root_target=target_rel,
            entries=entries,
            ambient_manifest=ambient_manifest_str,
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
        target_path = Path(target_file)
        if not target_path.is_absolute():
            target_path = (self.root_dir / target_path).resolve()
        else:
            target_path = target_path.resolve()
        distances = self.graph.get_distances(target_path)
        deps: List[DependencyNode] = []
        for rel_path, dist in sorted(distances.items(), key=lambda x: (x[1], x[0])):
            fp = self.root_dir / rel_path
            if fp.is_file():
                chars = len(fp.read_text(encoding="utf-8", errors="replace"))
                tokens = DeterministicContextPruner.estimate_tokens(chars)
                deps.append(DependencyNode(file_path=fp, depth_level=dist, token_count=tokens))
        return TopologicalManifest(target_file=target_path, dependencies=deps)

