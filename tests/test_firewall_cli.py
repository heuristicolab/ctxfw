"""
tests/test_firewall_cli.py — Test Suite for Clipboard Ergonomics & Terminal CLI (HU-12)
Validates CLI pipeline, markdown bundle generation, terminal telemetry rendering,
clipboard interaction, and output file writing.
"""
from __future__ import annotations

import io
from pathlib import Path
import pytest

from firewall_cli import copy_to_clipboard, run_firewall_cli


@pytest.fixture
def cli_sample_project(tmp_path: Path) -> Path:
    """Sets up a multi-module Python project for CLI compaction tests."""
    proj = tmp_path / "cli_sample"
    proj.mkdir()

    # D0
    (proj / "controller.py").write_text(
        "import service\n\ndef main():\n    return service.run()\n",
        encoding="utf-8",
    )
    # D1
    (proj / "service.py").write_text(
        "class OrderService:\n    '''Business logic.'''\n    def run(self) -> bool:\n        secret_calc = 100 * 5\n        if not secret_calc:\n            raise RuntimeError('Failed')\n        return True\n",
        encoding="utf-8",
    )
    return proj


def test_copy_to_clipboard_basic():
    """Asserts that copy_to_clipboard executes without raising unhandled exceptions."""
    res = copy_to_clipboard("test clipboard text")
    assert isinstance(res, bool)


def test_run_firewall_cli_telemetry(cli_sample_project: Path, monkeypatch):
    """Asserts that CLI renders formatted terminal telemetry and calculates token savings."""
    target_file = cli_sample_project / "controller.py"
    mock_stdout = io.StringIO()
    mock_stderr = io.StringIO()

    monkeypatch.setattr("sys.stdout", mock_stdout)
    monkeypatch.setattr("sys.stderr", mock_stderr)

    exit_code = run_firewall_cli(
        target_file_str=str(target_file),
        project_root_str=str(cli_sample_project),
        copy_clip=False,
    )
    assert exit_code == 0

    output = mock_stdout.getvalue()
    assert "CONTEXT FIREWALL" in output
    assert "controller.py" in output
    assert "service.py" in output
    assert "D0" in output
    assert "D1" in output
    assert "Net Context Tokens Saved" in output
    assert "Projected FinOps Savings" in output


def test_run_firewall_cli_output_file(cli_sample_project: Path, tmp_path: Path, monkeypatch):
    """Asserts that --output creates a markdown prompt file on disk."""
    target_file = cli_sample_project / "controller.py"
    output_prompt = tmp_path / "output_prompt.md"

    mock_stdout = io.StringIO()
    monkeypatch.setattr("sys.stdout", mock_stdout)

    exit_code = run_firewall_cli(
        target_file_str=str(target_file),
        project_root_str=str(cli_sample_project),
        copy_clip=False,
        output_path_str=str(output_prompt),
    )
    assert exit_code == 0
    assert output_prompt.is_file()

    content = output_prompt.read_text(encoding="utf-8")
    assert "# CONTEXT BUNDLE" in content
    assert "controller.py [FULL]" in content
    assert "service.py [INTERFACE]" in content


def test_run_firewall_cli_stdout_flag(cli_sample_project: Path, monkeypatch):
    """Asserts that --stdout prints raw markdown context directly to stdout."""
    target_file = cli_sample_project / "controller.py"
    mock_stdout = io.StringIO()
    monkeypatch.setattr("sys.stdout", mock_stdout)

    exit_code = run_firewall_cli(
        target_file_str=str(target_file),
        project_root_str=str(cli_sample_project),
        copy_clip=False,
        print_stdout=True,
    )
    assert exit_code == 0

    output = mock_stdout.getvalue()
    assert "# CONTEXT BUNDLE" in output
    assert "controller.py [FULL]" in output


def test_run_firewall_cli_missing_target(tmp_path: Path, monkeypatch):
    """Asserts that missing target file returns non-zero exit code with error message."""
    mock_stderr = io.StringIO()
    monkeypatch.setattr("sys.stderr", mock_stderr)

    exit_code = run_firewall_cli(
        target_file_str=str(tmp_path / "non_existent.py"),
        copy_clip=False,
    )
    assert exit_code == 1
    assert "Target file not found" in mock_stderr.getvalue()
