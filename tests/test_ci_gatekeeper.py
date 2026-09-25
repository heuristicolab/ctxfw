"""
tests/test_ci_gatekeeper.py — Test Suite for Context Firewall CI/CD Gatekeeper (Sprint 3.3)
Validates changeset detection, topological classification (D0/D1/D2+),
FinOps markdown report generation, and pre-commit configuration export.
"""
from __future__ import annotations

from pathlib import Path
import pytest
import subprocess
import sys

from ctxfw.gatekeeper import CIGatekeeper, PRE_COMMIT_CONFIG_TEMPLATE


@pytest.fixture
def repo_fixture(tmp_path: Path) -> Path:
    """Sets up a multi-module Python project repository."""
    proj = tmp_path / "ci_repo"
    proj.mkdir()

    # D0 changed target
    (proj / "order_controller.py").write_text(
        "import order_service\n\ndef handle_request():\n    return order_service.process()\n",
        encoding="utf-8",
    )

    # D1 direct dependency
    (proj / "order_service.py").write_text(
        "import db_model\n\nclass OrderService:\n    '''Business service.'''\n    def process(self) -> bool:\n        if False:\n            raise RuntimeError('Failed')\n        secret = 'confidential_123'\n        return True\n",
        encoding="utf-8",
    )

    # D2 transitive dependency
    (proj / "db_model.py").write_text(
        "class OrderModel:\n    '''Database model.'''\n    id: int\n    def compute_hash(self) -> str:\n        x = 99\n        return str(x)\n",
        encoding="utf-8",
    )

    # Unrelated module (should not be in perimeter)
    (proj / "unrelated.py").write_text(
        "def isolated_func():\n    return 42\n",
        encoding="utf-8",
    )

    return proj


def test_detect_changed_files_explicit(repo_fixture: Path):
    """Asserts that explicit file paths are properly resolved and validated."""
    gatekeeper = CIGatekeeper(project_root=repo_fixture)
    changed = gatekeeper.detect_changed_files(
        explicit_files=[str(repo_fixture / "order_controller.py")]
    )
    assert len(changed) == 1
    assert changed[0].name == "order_controller.py"


def test_classify_perimeter_d0_d1_d2(repo_fixture: Path):
    """Asserts topological classification assigns D0 (FULL), D1 (INTERFACE), and D2 (NOMINAL)."""
    gatekeeper = CIGatekeeper(project_root=repo_fixture)
    changed = [repo_fixture / "order_controller.py"]

    perimeter = gatekeeper.classify_perimeter(changed)

    # order_controller.py is D0 (FULL)
    assert "order_controller.py" in perimeter
    assert perimeter["order_controller.py"]["distance"] == 0
    assert perimeter["order_controller.py"]["depth"] == "FULL"
    assert perimeter["order_controller.py"]["tokens_saved"] == 0

    # order_service.py is D1 (INTERFACE)
    assert "order_service.py" in perimeter
    assert perimeter["order_service.py"]["distance"] == 1
    assert perimeter["order_service.py"]["depth"] == "INTERFACE"
    assert perimeter["order_service.py"]["tokens_saved"] > 0

    # db_model.py is D2 (NOMINAL)
    assert "db_model.py" in perimeter
    assert perimeter["db_model.py"]["distance"] == 2
    assert perimeter["db_model.py"]["depth"] == "NOMINAL"
    assert perimeter["db_model.py"]["tokens_saved"] > 0

    # unrelated.py is not reachable from target
    assert "unrelated.py" not in perimeter


def test_generate_markdown_summary(repo_fixture: Path):
    """Asserts that generated markdown contains table headers, metrics, and pre-commit snippet."""
    gatekeeper = CIGatekeeper(project_root=repo_fixture)
    changed = [repo_fixture / "order_controller.py"]
    perimeter = gatekeeper.classify_perimeter(changed)
    summary = gatekeeper.generate_markdown_summary(perimeter)

    assert "# Context Firewall — PR Dependency & FinOps Impact Summary" in summary
    assert "| Module | Distance | Applied Depth |" in summary
    assert "`order_controller.py`" in summary
    assert "`order_service.py`" in summary
    assert "`db_model.py`" in summary
    assert "D0" in summary
    assert "D1" in summary
    assert "D2" in summary
    assert "### FinOps Impact & Token Economics" in summary
    assert "Pre-Commit Hook Configuration" in summary
    assert "id: context-firewall-gatekeeper" in summary


def test_empty_changeset_summary(repo_fixture: Path):
    """Asserts clean notification when no python files are in changeset."""
    gatekeeper = CIGatekeeper(project_root=repo_fixture)
    summary = gatekeeper.generate_markdown_summary({})
    assert "No Python source files were detected in this changeset" in summary


def test_cli_execution_with_output_file(repo_fixture: Path, tmp_path: Path):
    """Asserts that running ci_gatekeeper via CLI writes summary to specified output path."""
    output_file = tmp_path / "pr_summary.md"
    pre_commit_file = tmp_path / ".pre-commit-config.yaml"

    cmd = [
        sys.executable,
        "-m", "ctxfw.gatekeeper",
        "--project-root", str(repo_fixture),
        "--files", str(repo_fixture / "order_controller.py"),
        "--output", str(output_file),
        "--generate-pre-commit", str(pre_commit_file),
    ]

    res = subprocess.run(
        cmd,
        cwd=str(Path.cwd()),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )

    assert output_file.is_file()
    content = output_file.read_text(encoding="utf-8")
    assert "order_controller.py" in content
    assert "FinOps Impact" in content

    assert pre_commit_file.is_file()
    pc_content = pre_commit_file.read_text(encoding="utf-8")
    assert "context-firewall-gatekeeper" in pc_content
