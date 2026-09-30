"""
tests/test_installer_and_doctor.py — Test Suite for Installer, Doctor, and Pre-Commit Gatekeeper
Axiom Manifest Hash: 4a35e336c0621f5b76a6abb20d975bc896c15592b5da2098f2454adc6a4d66a6

Validates idempotent IDE injection, multiplatform pre-commit hook deployment,
stdio isolation verification, and comprehensive doctor diagnostics.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import pytest

from ctxfw.installer import (
    CANONICAL_CLAUDE_ALLOWED_TOOLS,
    CANONICAL_SPEC_TEMPLATE,
    PRE_COMMIT_HOOK_SCRIPT,
    detect_installed_ides,
    init_repository_perimeter,
    inject_sovereign_rule,
    install_claude_surfaces,
    install_mcp_servers,
    render_doctor_report,
    resolve_claude_code_config_path,
    resolve_claude_desktop_config_path,
    resolve_cursor_config_path,
    resolve_mcp_command,
    resolve_mcp_surfaces,
    resolve_windsurf_config_path,
    rotate_backups,
    run_doctor,
    run_global_init,
    safe_merge_claude_code_config,
    safe_merge_mcp_config,
)
from ctxfw.sieve.engine import evaluate_specification
from ctxfw.cli import build_parser, handle_init_cli, handle_install_cli, run_doctor_cli


def test_safe_merge_mcp_config_creates_new(tmp_path: Path):
    """Asserts that safe_merge_mcp_config creates a new configuration file if absent."""
    cfg_file = tmp_path / "mcp_config.json"
    updated, msg = safe_merge_mcp_config(cfg_file)

    assert updated is True
    assert cfg_file.is_file()
    data = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert "mcpServers" in data
    assert "ctxfw" in data["mcpServers"]
    expected_cmds = {sys.executable, str(Path(sys.executable).resolve()), "ctxfw"}
    assert data["mcpServers"]["ctxfw"]["command"] in expected_cmds
    assert data["mcpServers"]["ctxfw"]["args"] in [["-m", "ctxfw.mcp"], ["mcp"]]


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


def test_safe_merge_creates_backup_snapshot(tmp_path: Path):
    """Asserts that mutating an existing config creates a timestamped .bak snapshot."""
    cfg_file = tmp_path / "mcp_config.json"
    cfg_file.write_text(json.dumps({"mcpServers": {"old_server": {"command": "echo"}}}, indent=2), encoding="utf-8")

    updated, msg = safe_merge_mcp_config(cfg_file)
    assert updated is True

    bak_files = list(tmp_path.glob("mcp_config.json.bak.*"))
    assert len(bak_files) >= 1
    bak_content = json.loads(bak_files[0].read_text(encoding="utf-8"))
    assert "old_server" in bak_content["mcpServers"]
    assert "ctxfw" not in bak_content["mcpServers"]


def test_installer_triple_idempotence(tmp_path: Path):
    """Asserts that 3 consecutive runs of safe_merge_mcp_config preserve exact file content without divergence."""
    cfg_file = tmp_path / "mcp_config.json"
    u1, _ = safe_merge_mcp_config(cfg_file)
    assert u1 is True
    content1 = cfg_file.read_text(encoding="utf-8")

    u2, msg2 = safe_merge_mcp_config(cfg_file)
    assert u2 is False
    assert "already" in msg2.lower()
    content2 = cfg_file.read_text(encoding="utf-8")
    assert content1 == content2

    u3, msg3 = safe_merge_mcp_config(cfg_file)
    assert u3 is False
    assert "already" in msg3.lower()
    content3 = cfg_file.read_text(encoding="utf-8")
    assert content1 == content3


def test_multi_surface_detection(tmp_path: Path):
    """Asserts resolve_mcp_surfaces accurately resolves Claude Desktop, Claude Code, Cursor, and Windsurf."""
    # Darwin
    mac_path = resolve_claude_desktop_config_path(system="Darwin", home=tmp_path)
    assert "Library/Application Support/Claude" in str(mac_path).replace("\\", "/")

    # Windows
    win_path = resolve_claude_desktop_config_path(system="Windows", appdata=str(tmp_path / "AppData"))
    assert "Claude" in str(win_path)

    # Linux
    linux_path = resolve_claude_desktop_config_path(system="Linux", home=tmp_path)
    assert ".config/Claude" in str(linux_path).replace("\\", "/")

    # Claude Code
    cc_path = resolve_claude_code_config_path(home=tmp_path)
    assert cc_path.name == ".claude.json"

    # Cursor
    cursor_path = resolve_cursor_config_path(cwd=tmp_path)
    assert cursor_path == tmp_path / ".cursor" / "mcp.json"

    # Windsurf
    ws_path = resolve_windsurf_config_path(home=tmp_path)
    assert ".codeium" in str(ws_path)

    surfaces = resolve_mcp_surfaces(cwd=tmp_path, home=tmp_path, system="Linux")
    surface_names = [s[0] for s in surfaces]
    assert surface_names == ["Claude Desktop", "Claude Code CLI", "Cursor", "Windsurf"]


def test_install_mcp_servers_proxy_fallback_output(tmp_path: Path):
    """Asserts install_mcp_servers outputs the Zero-MCP interoperability proxy instructions."""
    import io
    buf = io.StringIO()
    code = install_mcp_servers(cwd=tmp_path, home=tmp_path, stream=buf)
    assert code == 0
    out_txt = buf.getvalue()
    assert "ZERO-MCP INTEROPERABILITY GATEWAY" in out_txt
    assert "ctxfw proxy --port 8765" in out_txt
    assert 'export ANTHROPIC_BASE_URL="http://localhost:8765/v1"' in out_txt


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


def test_doctor_diagnostics_with_project_perimeter(tmp_path: Path):
    """Asserts that run_doctor(project_root) audits repository perimeter (spec, mcp, git hook)."""
    repo = tmp_path / "target_repo"
    (repo / ".git" / "hooks").mkdir(parents=True)
    init_repository_perimeter(repo)
    # create dummy .mcp.json
    (repo / ".mcp.json").write_text("{}", encoding="utf-8")

    report = run_doctor(project_root=repo)
    assert report.all_passed is True

    check_names = {c.name: c for c in report.checks}
    assert "Project Axiomatic Spec" in check_names
    assert check_names["Project Axiomatic Spec"].status == "OK"
    assert "Project MCP Perimeter" in check_names
    assert check_names["Project MCP Perimeter"].status == "OK"
    assert "Git Pre-Commit Gatekeeper" in check_names
    assert check_names["Git Pre-Commit Gatekeeper"].status == "OK"


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


def test_claude_safe_merge_preserves_auth_and_servers(tmp_path: Path):
    """
    Asserts that safe_merge_claude_code_config strictly preserves unmanaged keys:
    oauthAccount, env, pre-existing third-party mcpServers, and existing allowedTools.
    """
    cfg_file = tmp_path / ".claude.json"
    initial_content = {
        "oauthAccount": {"email": "user@example.com", "token": "secret_oauth_token"},
        "env": {"DEBUG": "1"},
        "mcpServers": {
            "postgres": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-postgres", "postgresql://localhost/mydb"],
            }
        },
        "allowedTools": ["Bash", "Edit"],
    }
    cfg_file.write_text(json.dumps(initial_content, indent=2), encoding="utf-8")

    updated, msg = safe_merge_claude_code_config(cfg_file)
    assert updated is True

    data = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert data["oauthAccount"] == {"email": "user@example.com", "token": "secret_oauth_token"}
    assert data["env"] == {"DEBUG": "1"}
    assert "postgres" in data["mcpServers"]
    assert "ctxfw" in data["mcpServers"]
    assert "Bash" in data["allowedTools"]
    assert "Edit" in data["allowedTools"]
    for canonical in CANONICAL_CLAUDE_ALLOWED_TOOLS:
        assert canonical in data["allowedTools"]


def test_claude_atomic_rollback_on_io_failure(tmp_path: Path, monkeypatch):
    """
    Asserts that an IO error (e.g. disk full ENOSPC) during os.replace cleanly rolls back,
    leaves the original configuration file intact, removes temporary files, and leaves backup.
    """
    cfg_file = tmp_path / ".claude.json"
    original_data = {"mcpServers": {"old": {"command": "echo"}}, "auth": "intact"}
    cfg_file.write_text(json.dumps(original_data, indent=2), encoding="utf-8")

    def mock_replace(src, dst):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr("os.replace", mock_replace)

    updated, msg = safe_merge_claude_code_config(cfg_file)
    assert updated is False
    assert "failed to write" in msg.lower() or "no space" in msg.lower()

    # Original file is intact
    current_data = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert current_data == original_data

    # No leftover .tmp files
    tmp_files = list(tmp_path.glob(".tmp_*"))
    assert len(tmp_files) == 0

    # Backup file exists
    bak_files = list(tmp_path.glob(".claude.json.bak.*"))
    assert len(bak_files) >= 1


def test_claude_rejects_malformed_json_without_mutation(tmp_path: Path):
    """
    Asserts that corrupt or malformed JSON in ~/.claude.json causes immediate abort (Class 2 fault),
    returning False and refusing to mutate, overwrite, or truncate the file.
    """
    cfg_file = tmp_path / ".claude.json"
    corrupt_text = '{"mcpServers": { "unclosed_bracket": '
    cfg_file.write_text(corrupt_text, encoding="utf-8")

    updated, msg = safe_merge_claude_code_config(cfg_file)
    assert updated is False
    assert "failed to parse" in msg.lower() or "not a json object" in msg.lower()

    # Original file content is completely untouched
    assert cfg_file.read_text(encoding="utf-8") == corrupt_text

    # No temp files created
    assert len(list(tmp_path.glob(".tmp_*"))) == 0


def test_claude_backup_snapshot_retention_rotation(tmp_path: Path):
    """
    Asserts that rotate_backups boundedly prunes backup snapshots to at most max_backups (e.g. 5),
    deleting the oldest snapshots and keeping the most recent.
    """
    cfg_file = tmp_path / ".claude.json"
    cfg_file.write_text(json.dumps({"version": 0}), encoding="utf-8")

    # Create 12 artificial historical backups with distinct timestamps
    import time
    base_time = time.time() - 1000
    for i in range(12):
        bak_file = tmp_path / f".claude.json.bak.{int(base_time) + i}"
        bak_file.write_text(json.dumps({"version": i}), encoding="utf-8")
        os.utime(bak_file, (base_time + i, base_time + i))

    assert len(list(tmp_path.glob(".claude.json.bak.*"))) == 12

    # Call rotate_backups with limit of 5
    rotate_backups(cfg_file, max_backups=5)

    remaining_baks = sorted(
        list(tmp_path.glob(".claude.json.bak.*")),
        key=lambda p: p.stat().st_mtime,
    )
    assert len(remaining_baks) == 5
    # The surviving ones must be the newest ones (versions 7, 8, 9, 10, 11)
    oldest_surviving = json.loads(remaining_baks[0].read_text(encoding="utf-8"))
    assert oldest_surviving["version"] == 7
    newest_surviving = json.loads(remaining_baks[-1].read_text(encoding="utf-8"))
    assert newest_surviving["version"] == 11


def test_cli_install_claude_flag_dispatch(tmp_path: Path, monkeypatch):
    """
    Asserts that ctxfw install --claude triggers install_claude_surfaces,
    targeting Claude Code CLI and Claude Desktop while isolating Cursor and Windsurf.
    """
    import io
    mock_stdout = io.StringIO()
    monkeypatch.setattr("sys.stdout", mock_stdout)

    home_dir = tmp_path / "mock_home"
    home_dir.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setenv("USERPROFILE", str(home_dir))

    # Test via handle_install_cli directly with mock
    def mock_install_claude_surfaces(home=None, system=None, appdata=None, stream=None):
        out = stream or sys.stdout
        out.write("MOCK CLAUDE ONBOARDING EXECUTED\n")
        return 0

    monkeypatch.setattr("ctxfw.installer.install_claude_surfaces", mock_install_claude_surfaces)

    code = handle_install_cli(["--claude"])
    assert code == 0
    assert "MOCK CLAUDE ONBOARDING EXECUTED" in mock_stdout.getvalue()

    # Also test CLI argument routing via build_parser
    parser = build_parser()
    args = parser.parse_args(["install", "--claude"])
    assert args.command == "install"
    assert args.claude is True
