"""
tests/test_topological_resolver.py — Test Matrix for Topological Resolver & Context Firewall
Validates static AST import extraction, project call-graph construction,
multi-depth pruning dispatch (D0/D1/D2+), and Markdown prompt bundling.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from contracts import LocalSemanticCache, PruningDepth
from topological_resolver import (
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
