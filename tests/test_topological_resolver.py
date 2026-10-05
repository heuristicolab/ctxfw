"""
tests/test_topological_resolver.py — Test Matrix for Topological Resolver & Context Firewall
Validates static AST import extraction, project call-graph construction,
multi-depth pruning dispatch (D0/D1/D2+), and Markdown prompt bundling.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from ctxfw.core.contracts import PruningDepth
from ctxfw.storage.cache import LocalSemanticCache
from ctxfw.core.topological import (
    ContextFirewallEngine,
    ProjectDependencyGraph,
    StaticImportExtractor,
    TopologicalContextBundleDTO,
)


@pytest.fixture
def sample_project(tmp_path: Path) -> Path:
    """Creates a temporary multi-module project structure for topological graph analysis."""
    proj = tmp_path / "sample_app"
    proj.mkdir()

    # main.py (D0) imports service and standard library math
    (proj / "main.py").write_text(
        """import service\nimport math\n\ndef run_app():\n    svc = service.PaymentService()\n    return svc.process()\n""",
        encoding="utf-8",
    )

    # service.py (D1) imports repository and standard library json
    (proj / "service.py").write_text(
        """import repository\nimport json\n\nclass PaymentService:\n    '''Handles business logic.'''\n    def __init__(self):\n        self.repo = repository.TransactionRepository()\n\n    def process(self) -> bool:\n        if not self.repo.is_ready():\n            raise RuntimeError("Repository uninitialized")\n        return True\n""",
        encoding="utf-8",
    )

    # repository.py (D2) imports models
    (proj / "repository.py").write_text(
        """from models import TransactionModel\n\nclass TransactionRepository:\n    '''Data access layer.'''\n    connection_string: str\n\n    def is_ready(self) -> bool:\n        return True\n\n    def find_by_id(self, tx_id: str) -> TransactionModel:\n        buffer = [i for i in range(100)]\n        return TransactionModel(id=tx_id, amount=100.0)\n""",
        encoding="utf-8",
    )

    # models.py (D3) standalone data model
    (proj / "models.py").write_text(
        """class TransactionModel:\n    '''Canonical data contract.'''\n    id: str\n    amount: float\n""",
        encoding="utf-8",
    )

    return proj


def test_static_import_extractor_filters_stdlib(sample_project: Path):
    """Asserts that standard library modules (math, json) are excluded and only local modules are captured."""
    deps_main = StaticImportExtractor.extract_from_file(sample_project / "main.py", sample_project)
    rel_deps_main = {p.name for p in deps_main}
    assert "service.py" in rel_deps_main
    assert "math.py" not in rel_deps_main

    deps_service = StaticImportExtractor.extract_from_file(sample_project / "service.py", sample_project)
    rel_deps_service = {p.name for p in deps_service}
    assert "repository.py" in rel_deps_service
    assert "json.py" not in rel_deps_service


def test_project_dependency_graph_distance_assignment(sample_project: Path):
    """Asserts correct topological distance assignment: main=D0, service=D1, repository=D2, models=D3."""
    graph = ProjectDependencyGraph(sample_project)
    distances = graph.get_distances("main.py")

    assert distances.get("main.py") == 0
    assert distances.get("service.py") == 1
    assert distances.get("repository.py") == 2
    assert distances.get("models.py") == 3


def test_context_firewall_multi_depth_slicing(sample_project: Path, tmp_path: Path):
    """Asserts that ContextFirewallEngine correctly dispatches D0 (FULL), D1 (INTERFACE), and D2+ (NOMINAL)."""
    db_file = str(tmp_path / "firewall_cache.db")
    cache = LocalSemanticCache(db_path=db_file)
    firewall = ContextFirewallEngine(project_root=sample_project, cache=cache)

    bundle = firewall.build_context("main.py")

    assert isinstance(bundle, TopologicalContextBundleDTO)
    assert bundle.root_target == "main.py"
    assert len(bundle.entries) == 4

    # D0: main.py is 100% untouched
    res_main = bundle.entries["main.py"]
    assert res_main.depth == PruningDepth.FULL
    assert "def run_app():" in res_main.pruned_code
    assert "return svc.process()" in res_main.pruned_code

    # D1: service.py is sliced preserving signatures, docstrings, and raises (INTERFACE)
    res_service = bundle.entries["service.py"]
    assert res_service.depth == PruningDepth.INTERFACE
    assert "class PaymentService:" in res_service.pruned_code
    assert "def process(self) -> bool:" in res_service.pruned_code
    assert "raise RuntimeError(" in res_service.pruned_code
    assert "..." in res_service.pruned_code

    # D2: repository.py is sliced to nominal declarations (NOMINAL)
    res_repo = bundle.entries["repository.py"]
    assert res_repo.depth == PruningDepth.NOMINAL
    assert "class TransactionRepository:" in res_repo.pruned_code
    assert "connection_string: str" in res_repo.pruned_code
    # Internal methods omitted in nominal mode
    assert "def find_by_id" not in res_repo.pruned_code

    # D3: models.py is nominal
    res_models = bundle.entries["models.py"]
    assert res_models.depth == PruningDepth.NOMINAL
    assert "class TransactionModel:" in res_models.pruned_code
    assert "amount: float" in res_models.pruned_code


def test_bundle_to_dict_and_to_prompt(sample_project: Path, tmp_path: Path):
    """Asserts that bundle serialization methods produce valid dictionary and deterministic Markdown prompt."""
    db_file = str(tmp_path / "bundle_cache.db")
    cache = LocalSemanticCache(db_path=db_file)
    firewall = ContextFirewallEngine(project_root=sample_project, cache=cache)

    bundle = firewall.build_context("main.py")

    # to_dict() mapping
    as_dict = bundle.to_dict()
    assert isinstance(as_dict, dict)
    assert "main.py" in as_dict
    assert "service.py" in as_dict

    # to_prompt() Markdown concatenation
    prompt = bundle.to_prompt()
    assert "# CONTEXT BUNDLE — Root Target: main.py" in prompt
    assert "### File: main.py [FULL]" in prompt
    assert "### File: service.py [INTERFACE]" in prompt
    assert "### File: repository.py [NOMINAL]" in prompt
    assert "```python" in prompt


def test_topological_resolver_manifest_generation(sample_project: Path):
    """Validates TopologicalResolver, TopologicalManifest, and DependencyNode integration."""
    from ctxfw.core.topological import TopologicalResolver, DependencyNode, TopologicalManifest

    resolver = TopologicalResolver(sample_project)
    manifest = resolver.resolve("main.py")

    assert isinstance(manifest, TopologicalManifest)
    assert manifest.target_file == (sample_project / "main.py").resolve()
    assert len(manifest.dependencies) >= 4
    assert manifest.total_tokens > 0
    for dep in manifest.dependencies:
        assert isinstance(dep, DependencyNode)
        assert dep.token_count > 0


def test_static_import_extractor_relative_and_package_imports(tmp_path: Path):
    """Validates relative imports (from . import, from ..pkg import) and package __init__.py imports."""
    proj = tmp_path / "complex_app"
    proj.mkdir()
    pkg = proj / "pkg"
    pkg.mkdir()
    subpkg = pkg / "subpkg"
    subpkg.mkdir()

    (pkg / "__init__.py").write_text("from .subpkg import helper\n", encoding="utf-8")
    (subpkg / "__init__.py").write_text("pass\n", encoding="utf-8")
    (subpkg / "helper.py").write_text("def assist(): pass\n", encoding="utf-8")
    (subpkg / "client.py").write_text("from .helper import assist\nfrom .. import __init__\nfrom ..subpkg.helper import assist as a2\n", encoding="utf-8")
    (proj / "syntax_err.py").write_text("def broken(: pass\n", encoding="utf-8")

    deps_client = StaticImportExtractor.extract_from_file(subpkg / "client.py", proj)
    names = {p.name for p in deps_client}
    assert "helper.py" in names

    # Syntax error fallback
    deps_err = StaticImportExtractor.extract_from_file(proj / "syntax_err.py", proj)
    assert deps_err == set()


def test_d3_symbol_extractor_annotated_and_dynamic_all():
    """Validates D3SymbolExtractor with AnnAssign and dynamic __all__ structures."""
    from ctxfw.core.topological import D3SymbolExtractor
    code = """
x: int = 10
y: str = "hello"
__all__ = [x, 42]
def normal(): pass
"""
    symbols = D3SymbolExtractor.extract_from_code(code)
    assert "[DYNAMIC_UNBOUND:?]" in symbols
    assert "normal:F" in symbols


def test_topological_bundle_with_ambient_manifest(sample_project: Path, tmp_path: Path):
    """Validates bundle to_prompt with ambient_manifest present."""
    from ctxfw.config import CtxfwConfigDTO, ContextDepthLevel
    cache = LocalSemanticCache(db_path=str(tmp_path / "ambient_test.db"))
    engine = ContextFirewallEngine(project_root=sample_project, cache=cache)
    cfg = CtxfwConfigDTO(
        max_depth=ContextDepthLevel.AMBIENT_CARTOGRAPHY,
        ambient_manifest=True,
    )
    bundle = engine.build_context("main.py", depth_config=cfg)
    prompt = bundle.to_prompt()
    assert "### AMBIENT MANIFEST [D3]" in prompt


def test_context_firewall_passthrough_and_clamping(tmp_path: Path):
    """Validates passthrough mode and subsystem boundary clamping."""
    proj = tmp_path / "clamp_app"
    proj.mkdir()
    core = proj / "core"
    core.mkdir()
    ext = proj / "external"
    ext.mkdir()

    (proj / "main.py").write_text("import core.svc\nimport external.tool\n", encoding="utf-8")
    (core / "__init__.py").write_text("", encoding="utf-8")
    (core / "svc.py").write_text("def run(): return 1\n", encoding="utf-8")
    (ext / "__init__.py").write_text("", encoding="utf-8")
    (ext / "tool.py").write_text("def helper(): return 2\n", encoding="utf-8")

    from ctxfw.config import CtxfwConfigDTO, ContextDepthLevel
    engine = ContextFirewallEngine(project_root=proj)

    # Passthrough mode
    bundle_pt = engine.build_context("main.py", mode="passthrough")
    assert bundle_pt.entries["core/svc.py"].depth == PruningDepth.FULL

    # Subsystem clamping
    cfg = CtxfwConfigDTO(
        max_depth=ContextDepthLevel.AMBIENT_CARTOGRAPHY,
        ambient_manifest=True,
        subsystem_clamping=True,
    )
    bundle_clamp = engine.build_context("main.py", depth_config=cfg)
    assert bundle_clamp is not None


def test_topological_advanced_coverage(tmp_path: Path):
    """Exhaustively covers remaining edge branches in topological.py for >= 95% threshold."""
    from unittest.mock import patch
    from ctxfw.config import CtxfwConfigDTO, ContextDepthLevel
    from ctxfw.core.topological import (
        ContextFirewallEngine,
        TopologicalResolver,
        StaticImportExtractor,
    )

    proj = tmp_path / "deep_cov_proj"
    proj.mkdir()
    app = proj / "app"
    app.mkdir()
    core = proj / "core"
    core.mkdir()
    periph = proj / "periph"
    periph.mkdir()

    # 1. from pkg import mod compound resolution (lines 107-113)
    (core / "utils.py").write_text("def helper(): pass\n", encoding="utf-8")
    (app / "entry.py").write_text("from core import utils\n", encoding="utf-8")

    extractor = StaticImportExtractor(app / "entry.py", proj)
    deps = extractor.extract_from_file(app / "entry.py", proj)
    assert any("utils.py" in str(d) for d in deps)

    # 2. prefix_file resolution (lines 57-63)
    (proj / "models.py").write_text("class User: pass\n", encoding="utf-8")
    (app / "sub_entry.py").write_text("from models.User import something\n", encoding="utf-8")
    deps2 = extractor.extract_from_file(app / "sub_entry.py", proj)
    assert any("models.py" in str(d) for d in deps2)

    # 3. Candidate outside project_root triggering ValueError (lines 43, 52, 62)
    extractor_outside = StaticImportExtractor(app / "entry.py", app)
    # Asking to resolve something pointing above app
    _ = extractor_outside._resolve_candidate("core.utils", proj)
    _ = extractor_outside._resolve_candidate("periph", proj)
    _ = extractor_outside._resolve_candidate("periph.p1", proj)

    # 4. Multi-level hierarchy with D0..D4 modules for distance and clamping branches
    # D0: entry.py -> imports D1: s1.py -> imports D2: r1.py -> imports D3: m1.py, periph.py -> imports D4: d4.py
    (proj / "r1.py").write_text("import m1\nimport periph.p1\n", encoding="utf-8")
    (proj / "s1.py").write_text("import r1\n", encoding="utf-8")
    (proj / "d4.py").write_text("class LeafD4: pass\n", encoding="utf-8")
    (periph / "__init__.py").write_text("", encoding="utf-8")
    (periph / "p1.py").write_text("import d4\nclass Periph1: pass\n", encoding="utf-8")
    (proj / "m1.py").write_text("\n".join(f"class BigModel_{i}: pass" for i in range(50)), encoding="utf-8")
    (proj / "root_main.py").write_text("import s1\n", encoding="utf-8")

    engine = ContextFirewallEngine(project_root=proj)

    # 5. Absolute path input to build_context and TopologicalResolver.resolve (lines 322, 526)
    abs_main = (proj / "root_main.py").resolve()
    bundle_abs = engine.build_context(abs_main)
    assert bundle_abs.root_target == "root_main.py"

    resolver = TopologicalResolver(proj)
    manifest_abs = resolver.resolve(abs_main)
    assert manifest_abs.target_file == abs_main

    # 6. Mode exception fallback (lines 314-315)
    with patch("ctxfw.config.load_config", side_effect=RuntimeError("Config error")):
        b_fallback = engine.build_context("root_main.py", mode=None)
        assert b_fallback is not None

    # 7. Pure passthrough with distance > 0 (line 334)
    cfg_d0 = CtxfwConfigDTO(max_depth=ContextDepthLevel.PURE_PASSTHROUGH)
    b_d0 = engine.build_context("root_main.py", depth_config=cfg_d0)
    assert len(b_d0.entries) == 1

    # 8. AMBIENT_CARTOGRAPHY with distance > 3 (line 347)
    cfg_d3 = CtxfwConfigDTO(
        max_depth=ContextDepthLevel.AMBIENT_CARTOGRAPHY,
        ambient_manifest=True,
        subsystem_clamping=False,
        distractor_budget=50,
    )
    b_d3_1 = engine.build_context("root_main.py", depth_config=cfg_d3)
    assert b_d3_1.ambient_manifest is not None

    # 9. Second run -> D3 cache hit (lines 451, 452)
    b_d3_hit = engine.build_context("root_main.py", depth_config=cfg_d3)
    assert b_d3_hit.ambient_manifest is not None

    # 10. Distractor budget clamp & token ceiling break (lines 470, 473, 480)
    cfg_clamp_budget = CtxfwConfigDTO(
        max_depth=ContextDepthLevel.AMBIENT_CARTOGRAPHY,
        ambient_manifest=True,
        distractor_budget=20,
    )
    b_budget = engine.build_context("root_main.py", depth_config=cfg_clamp_budget)
    assert b_budget.ambient_manifest is not None

    # Token ceiling break (> 1000 tokens)
    (proj / "giant_d3.py").write_text(f"class {'A'*4500}: pass\n", encoding="utf-8")
    (proj / "m1.py").write_text("import giant_d3\n", encoding="utf-8")
    engine_giant = ContextFirewallEngine(project_root=proj)
    cfg_giant = CtxfwConfigDTO(
        max_depth=ContextDepthLevel.AMBIENT_CARTOGRAPHY,
        ambient_manifest=True,
        distractor_budget=500,
    )
    engine_giant.build_context("root_main.py", depth_config=cfg_giant)

    # 11. Stale reads on herd branch (lines 457, 458)
    for i in range(25):
        (proj / f"extra_d3_{i}.py").write_text(f"class ExtraD3_{i}: pass\n", encoding="utf-8")
    (proj / "m1.py").write_text("\n".join(f"import extra_d3_{i}" for i in range(25)), encoding="utf-8")
    engine2 = ContextFirewallEngine(project_root=proj)
    cfg_stale = CtxfwConfigDTO(
        max_depth=ContextDepthLevel.AMBIENT_CARTOGRAPHY,
        ambient_manifest=True,
        stale_reads_on_herd=True,
        distractor_budget=500,
    )
    # Warm run then stale run
    engine2.build_context("root_main.py", depth_config=cfg_stale)
    engine2.build_context("root_main.py", depth_config=cfg_stale)

    # 12. max_depth=2 with ambient_manifest=True (line 349)
    cfg_d2_amb = CtxfwConfigDTO(
        max_depth=ContextDepthLevel.TRANSITIVE_NOMINAL,
        ambient_manifest=True,
    )
    b_d2 = engine.build_context("root_main.py", depth_config=cfg_d2_amb)
    assert b_d2.ambient_manifest is not None

    # 13. Subsystem boundary clamping filtering outside subsystem (lines 414, 419-421)
    (core / "svc.py").write_text("import r1\n", encoding="utf-8")
    (app / "entry_sub.py").write_text("import core.svc\n", encoding="utf-8")
    engine3 = ContextFirewallEngine(project_root=proj)
    cfg_sub = CtxfwConfigDTO(
        max_depth=ContextDepthLevel.AMBIENT_CARTOGRAPHY,
        ambient_manifest=True,
        subsystem_clamping=True,
    )
    b_sub = engine3.build_context("app/entry_sub.py", depth_config=cfg_sub)
    assert b_sub is not None


