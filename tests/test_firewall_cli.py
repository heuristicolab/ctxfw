"""
tests/test_firewall_cli.py — Test Suite for Clipboard Ergonomics & Terminal CLI (HU-12)
Validates CLI pipeline, markdown bundle generation, terminal telemetry rendering,
clipboard interaction, and output file writing.
"""
from __future__ import annotations

import io
from pathlib import Path
import pytest

from firewall_cli import copy_to_clipboard, handle_init_command, main, run_firewall_cli
import json


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


def test_handle_init_command_creates_expected_artifacts(tmp_path: Path, monkeypatch):
    """Asserts that handle_init_command atomically deploys all 4 sovereign artifacts."""
    mock_stdout = io.StringIO()
    monkeypatch.setattr("sys.stdout", mock_stdout)

    target_dir = tmp_path / "sovereign_repo"
    res_dir = handle_init_command(target_dir)

    assert res_dir == target_dir.resolve()

    # 1. Manifiesto MCP Agnóstico Universal
    mcp_file = target_dir / ".mcp.json"
    assert mcp_file.is_file()
    mcp_data = json.loads(mcp_file.read_text(encoding="utf-8"))
    assert "mcpServers" in mcp_data
    assert "ctxfw" in mcp_data["mcpServers"]
    assert mcp_data["mcpServers"]["ctxfw"]["command"] == "python"
    assert mcp_data["mcpServers"]["ctxfw"]["args"] == ["-m", "ctxfw.mcp"]

    # 2. Directivas del Agente (Rules)
    rules_file = target_dir / ".agent" / "rules.yaml"
    assert rules_file.is_file()
    rules_content = rules_file.read_text(encoding="utf-8")
    assert "Arquitecto Perimetral Soberano" in rules_content
    assert "FIREWALL_LAW_01" in rules_content
    assert "FIREWALL_LAW_02" in rules_content
    assert "FINOPS_AUDIT_03" in rules_content

    # 3. Gobernanza y Leyes del Cortafuegos
    laws_file = target_dir / ".agents" / "rules" / "firewall_laws.md"
    assert laws_file.is_file()
    laws_content = laws_file.read_text(encoding="utf-8")
    assert "# Leyes Perimetrales del Cortafuegos (ctxfw)" in laws_content
    assert "Cero Lecturas en Bruto" in laws_content
    assert "Soberanía Local" in laws_content

    # 4. Skill Descubrible para Antigravity y Cursor
    skill_file = target_dir / ".agents" / "skills" / "context-firewall" / "SKILL.md"
    assert skill_file.is_file()
    skill_content = skill_file.read_text(encoding="utf-8")
    assert "name: context-firewall" in skill_content
    assert "# Context Firewall (ctxfw) Skill" in skill_content
    assert "resolve_context_bundle" in skill_content

    # Stdout feedback
    out = mock_stdout.getvalue()
    assert "[*] Workspace soberano inicializado exitosamente en:" in out
    assert ".mcp.json (Servidor MCP stdio)" in out
    assert ".agent/rules.yaml (Leyes del Arquitecto Perimetral)" in out
    assert ".agents/rules/firewall_laws.md (Gobernanza)" in out
    assert ".agents/skills/context-firewall/SKILL.md (Skill nativa)" in out


def test_handle_init_command_default_cwd(tmp_path: Path, monkeypatch):
    """Asserts that handle_init_command defaults to current working directory."""
    monkeypatch.chdir(tmp_path)
    mock_stdout = io.StringIO()
    monkeypatch.setattr("sys.stdout", mock_stdout)

    res_dir = handle_init_command()
    assert res_dir == tmp_path.resolve()
    assert (tmp_path / ".mcp.json").is_file()
    assert (tmp_path / ".agent" / "rules.yaml").is_file()
    assert (tmp_path / ".agents" / "rules" / "firewall_laws.md").is_file()
    assert (tmp_path / ".agents" / "skills" / "context-firewall" / "SKILL.md").is_file()


def test_cli_main_subcommand_init(tmp_path: Path, monkeypatch):
    """Asserts that `ctxfw init <dir>` executes handle_init_command via CLI entrypoint."""
    target_repo = tmp_path / "cli_init_repo"
    mock_stdout = io.StringIO()
    monkeypatch.setattr("sys.stdout", mock_stdout)
    monkeypatch.setattr("sys.argv", ["ctxfw", "init", str(target_repo)])

    main()

    assert (target_repo / ".mcp.json").is_file()
    assert (target_repo / ".agent" / "rules.yaml").is_file()
    assert (target_repo / ".agents" / "rules" / "firewall_laws.md").is_file()
    assert (target_repo / ".agents" / "skills" / "context-firewall" / "SKILL.md").is_file()


def test_cli_main_subcommand_init_help(monkeypatch):
    """Asserts that `ctxfw init --help` prints usage instructions."""
    mock_stdout = io.StringIO()
    monkeypatch.setattr("sys.stdout", mock_stdout)
    monkeypatch.setattr("sys.argv", ["ctxfw", "init", "--help"])

    main()
    assert "usage: ctxfw init [target_dir]" in mock_stdout.getvalue()


def test_cli_version_flag():
    """Asserts that `ctxfw --version` returns code 0 and prints 'ctxfw 3.5.6'."""
    import subprocess
    import sys

    res = subprocess.run(
        [sys.executable, "-m", "ctxfw.cli", "--version"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "ctxfw 3.5.6" in (res.stdout + res.stderr)


