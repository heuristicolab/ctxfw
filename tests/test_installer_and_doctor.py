"""
tests/test_installer_and_doctor.py — Test Suite for Installer, Doctor, and Pre-Commit Gatekeeper
Axiom Manifest Hash: 575d12d75bcb427be48c3d62c643a4fb4a0260768cb49197c5d09133058581ed

Validates idempotent IDE injection, multiplatform pre-commit hook deployment,
stdio isolation verification, and comprehensive doctor diagnostics.
"""
from __future__ import annotations

import json
from pathlib import Path
import stat
import subprocess
import sys
import pytest

from ctxfw.installer import (
    CANONICAL_SPEC_TEMPLATE,
    PRE_COMMIT_HOOK_SCRIPT,
    detect_installed_ides,
    init_repository_perimeter,
    inject_sovereign_rule,
    render_doctor_report,
    run_doctor,
    run_global_init,
    safe_merge_mcp_config,
)
from ctxfw.sieve.engine import evaluate_specification
from ctxfw.cli import handle_init_cli, run_doctor_cli


def test_safe_merge_mcp_config_creates_new(tmp_path: Path):
    """Asserts that safe_merge_mcp_config creates a new configuration file if absent."""
    cfg_file = tmp_path / "mcp_config.json"
    updated, msg = safe_merge_mcp_config(cfg_file)

    assert updated is True
    assert cfg_file.is_file()
    data = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert "mcpServers" in data
    assert "ctxfw" in data["mcpServers"]
    assert data["mcpServers"]["ctxfw"]["command"] == "ctxfw"
    assert data["mcpServers"]["ctxfw"]["args"] == ["mcp"]


def test_safe_merge_preserves_existing_servers(tmp_path: Path):
    """Asserts that third-party servers and existing keys are strictly preserved."""
    cfg_file = tmp_path / "mcp_config.json"
    initial_content = {
        "mcpServers": {
            "brave-search": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-brave-search"],
            },
            "custom-db": {
                "command": "python",
                "args": ["-m", "db_server"],
            },
        },
        "telemetry": {"opt_out": True},
    }
    cfg_file.write_text(json.dumps(initial_content, indent=2), encoding="utf-8")

    updated, msg = safe_merge_mcp_config(cfg_file)
    assert updated is True

    data = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert "brave-search" in data["mcpServers"]
    assert "custom-db" in data["mcpServers"]
    assert "ctxfw" in data["mcpServers"]
    assert data["telemetry"]["opt_out"] is True


def test_safe_merge_idempotence(tmp_path: Path):
    """Asserts that running safe_merge_mcp_config multiple times does not alter file."""
    cfg_file = tmp_path / "mcp_config.json"
    updated1, msg1 = safe_merge_mcp_config(cfg_file)
    assert updated1 is True

    content_after_first = cfg_file.read_text(encoding="utf-8")

    updated2, msg2 = safe_merge_mcp_config(cfg_file)
    assert updated2 is False
    assert "already" in msg2.lower()

    content_after_second = cfg_file.read_text(encoding="utf-8")
    assert content_after_first == content_after_second


def test_inject_sovereign_rule_idempotence(tmp_path: Path):
    """Asserts that inject_sovereign_rule is idempotent."""
    rule_file = tmp_path / "rules" / "GEMINI.md"

    updated1, msg1 = inject_sovereign_rule(rule_file)
    assert updated1 is True
    assert rule_file.is_file()
    assert "SOVEREIGN AGENT DIRECTIVES (CTXFW PROTOCOL)" in rule_file.read_text(encoding="utf-8")

    updated2, msg2 = inject_sovereign_rule(rule_file)
    assert updated2 is False
    assert "already present" in msg2.lower()


def test_run_global_init(tmp_path: Path):
    """Asserts that run_global_init executes without exception and updates configs."""
    res = run_global_init(base_home=tmp_path)
    assert res["status"] == "SUCCESS"
    assert len(res["actions"]) > 0
    assert len(res["configs_updated"]) > 0


def test_init_repository_perimeter_with_git(tmp_path: Path):
    """Asserts that init_repository_perimeter deploys SPEC.axioms.md and pre-commit hook."""
    repo = tmp_path / "my_repo"
    git_dir = repo / ".git"
    git_dir.mkdir(parents=True)

    res = init_repository_perimeter(repo)
    assert res["created_spec"] is True
    assert res["created_hook"] is True

    spec_path = repo / "SPEC.axioms.md"
    assert spec_path.is_file()

    # Verify that the canonical template satisfies axiomatic completeness
    eval_res = evaluate_specification(spec_path.read_text(encoding="utf-8"))
    assert eval_res.status == "VERIFIED"
    assert eval_res.aci_score >= 0.9000
    assert eval_res.negative_invariants_count >= 5

    hook_path = repo / ".git" / "hooks" / "pre-commit"
    assert hook_path.is_file()
    hook_content = hook_path.read_text(encoding="utf-8")
    assert "CTXFW Axiomatic Pre-Commit Hook" in hook_content
    assert "spec verify" in hook_content


def test_init_repository_perimeter_without_git(tmp_path: Path):
    """Asserts graceful handling when repo is not a git repository."""
    repo = tmp_path / "plain_repo"
    repo.mkdir(parents=True)

    res = init_repository_perimeter(repo)
    assert res["created_spec"] is True
    assert res["created_hook"] is False
    assert any(".git directory not found" in m for m in res["messages"])


def test_doctor_diagnostics_all_passed():
    """Asserts that run_doctor() passes all critical health and stdio isolation checks."""
    report = run_doctor()
    assert report.all_passed is True

    check_names = {c.name: c for c in report.checks}
    assert "Python Package & sys.path" in check_names
    assert check_names["Python Package & sys.path"].status == "OK"

    assert "MCP stdio Stream Isolation" in check_names
    assert check_names["MCP stdio Stream Isolation"].status == "OK"

    assert "Axiomatic Sieve Engine" in check_names
    assert check_names["Axiomatic Sieve Engine"].status == "OK"

    assert "SQLite WAL Cache & Concurrency" in check_names
    assert check_names["SQLite WAL Cache & Concurrency"].status == "OK"

    assert "Polyglot Tree-Sitter Grammars" in check_names
    assert check_names["Polyglot Tree-Sitter Grammars"].status in {"OK", "WARN"}


def test_render_doctor_report_output():
    """Asserts that render_doctor_report outputs formatted diagnostic table."""
    import io
    report = run_doctor()
    buf = io.StringIO()
    exit_code = render_doctor_report(report, out=buf)

    assert exit_code == 0
    output = buf.getvalue()
    assert "CTXFW DOCTOR" in output
    assert "[PASS]" in output
    assert "Overall Verdict:" in output


def test_cli_init_global_and_repo_subcommands(tmp_path: Path, monkeypatch):
    """Asserts that handle_init_cli routes --global and --repo flags cleanly."""
    import io
    mock_stdout = io.StringIO()
    monkeypatch.setattr("sys.stdout", mock_stdout)

    # 1. Test --global
    code_global = handle_init_cli(["--global"])
    assert code_global == 0
    assert "CTXFW GLOBAL ZERO-TOUCH" in mock_stdout.getvalue()

    # 2. Test --repo
    repo_dir = tmp_path / "cli_repo"
    (repo_dir / ".git").mkdir(parents=True)

    code_repo = handle_init_cli(["--repo", str(repo_dir)])
    assert code_repo == 0
    assert (repo_dir / "SPEC.axioms.md").is_file()
    assert (repo_dir / ".git" / "hooks" / "pre-commit").is_file()


def test_cli_doctor_subcommand(monkeypatch):
    """Asserts that run_doctor_cli executes and returns 0."""
    import io
    mock_stdout = io.StringIO()
    monkeypatch.setattr("sys.stdout", mock_stdout)

    code = run_doctor_cli()
    assert code == 0
    assert "CTXFW DOCTOR" in mock_stdout.getvalue()
