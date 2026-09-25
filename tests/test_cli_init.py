"""
tests/test_cli_init.py — Comprehensive Test Suite for Automated Zero-Friction MCP Integration
Axiom Manifest Hash: a7e63ccb9b5dd0c6f6147cfd2feec447c4d41690dd76aee9e6035db56cb7c31a

Validates deterministic cross-platform path resolution, zero-friction MCP payload injection
for Claude Desktop and Cursor, configuration preservation, strict idempotency, and error tolerance.
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sys
import pytest

from ctxfw.installer import (
    inject_agent_mcp_config,
    resolve_claude_desktop_config_path,
    resolve_cursor_config_path,
    run_init_mcp_agents,
)
from ctxfw.cli.main import build_parser, handle_init_cli, init_entrypoint, main


def test_path_resolution_deterministic(tmp_path: Path):
    """Asserts deterministic path resolution across Darwin, Windows, Linux, and workspace-scoped Cursor."""
    home_mock = tmp_path / "user_home"
    appdata_mock = tmp_path / "appdata" / "Roaming"

    # macOS (Darwin)
    darwin_path = resolve_claude_desktop_config_path(system="Darwin", home=home_mock)
    expected_darwin = home_mock.resolve() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    assert darwin_path == expected_darwin

    # Windows with explicit APPDATA
    windows_path = resolve_claude_desktop_config_path(system="Windows", home=home_mock, appdata=str(appdata_mock))
    expected_windows = appdata_mock.resolve() / "Claude" / "claude_desktop_config.json"
    assert windows_path == expected_windows

    # Windows fallback when APPDATA is unset
    windows_fallback_path = resolve_claude_desktop_config_path(system="Windows", home=home_mock, appdata="")
    expected_win_fallback = home_mock.resolve() / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"
    assert windows_fallback_path == expected_win_fallback

    # Linux / Other POSIX
    linux_path = resolve_claude_desktop_config_path(system="Linux", home=home_mock)
    expected_linux = home_mock.resolve() / ".config" / "Claude" / "claude_desktop_config.json"
    assert linux_path == expected_linux

    # Cursor (Workspace Scope)
    ws_mock = tmp_path / "project_workspace"
    cursor_path = resolve_cursor_config_path(cwd=ws_mock)
    expected_cursor = ws_mock.resolve() / ".cursor" / "mcp.json"
    assert cursor_path == expected_cursor


def test_injection_into_non_existent_files(tmp_path: Path):
    """Specification 5.a: Asserts automated directory and file creation with proper 2-space indentation."""
    home_dir = tmp_path / "home"
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir(parents=True)
    appdata_dir = home_dir / "AppData" / "Roaming"

    claude_cfg = resolve_claude_desktop_config_path(system="Windows", home=home_dir, appdata=str(appdata_dir))
    cursor_cfg = resolve_cursor_config_path(cwd=ws_dir)

    assert not claude_cfg.exists()
    assert not cursor_cfg.exists()

    mock_stdout = io.StringIO()
    exit_code = run_init_mcp_agents(
        cwd=ws_dir,
        home=home_dir,
        system="Windows",
        appdata=str(appdata_dir),
        stream=mock_stdout,
    )

    assert exit_code == 0
    assert claude_cfg.is_file()
    assert cursor_cfg.is_file()

    # Validate Claude Desktop payload and indentation
    claude_raw = claude_cfg.read_text(encoding="utf-8")
    assert "  \"mcpServers\":" in claude_raw
    claude_data = json.loads(claude_raw)
    assert "mcpServers" in claude_data
    assert "ctxfw" in claude_data["mcpServers"]
    assert claude_data["mcpServers"]["ctxfw"]["command"] == "ctxfw"
    assert claude_data["mcpServers"]["ctxfw"]["args"] == ["mcp"]

    # Validate Cursor payload and indentation
    cursor_raw = cursor_cfg.read_text(encoding="utf-8")
    assert "  \"mcpServers\":" in cursor_raw
    cursor_data = json.loads(cursor_raw)
    assert "mcpServers" in cursor_data
    assert "ctxfw" in cursor_data["mcpServers"]
    assert cursor_data["mcpServers"]["ctxfw"]["command"] == "ctxfw"
    assert cursor_data["mcpServers"]["ctxfw"]["args"] == ["mcp"]

    # Validate output formatting
    out = mock_stdout.getvalue()
    assert "[+] Claude Desktop: Context Firewall injected successfully into" in out
    assert "[+] Cursor: Context Firewall injected successfully into" in out
    assert "Zero-config integration complete. Restart your agent to activate." in out


def test_clean_injection_into_existing_configs_preserving_servers(tmp_path: Path):
    """Specification 5.b: Asserts external keys, top-level settings, and third-party MCP servers are preserved."""
    home_dir = tmp_path / "home"
    ws_dir = tmp_path / "workspace"
    appdata_dir = home_dir / "AppData" / "Roaming"

    claude_cfg = resolve_claude_desktop_config_path(system="Windows", home=home_dir, appdata=str(appdata_dir))
    cursor_cfg = resolve_cursor_config_path(cwd=ws_dir)

    claude_cfg.parent.mkdir(parents=True, exist_ok=True)
    initial_claude = {
        "mcpServers": {
            "brave-search": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-brave-search"],
            },
            "github-official": {
                "command": "docker",
                "args": ["run", "-i", "--rm", "mcp/github"],
            },
        },
        "globalShortcut": "CommandOrControl+Shift+Space",
        "userPreferences": {"telemetry": False, "theme": "dark"},
    }
    claude_cfg.write_text(json.dumps(initial_claude, indent=2), encoding="utf-8")

    cursor_cfg.parent.mkdir(parents=True, exist_ok=True)
    initial_cursor = {
        "mcpServers": {
            "postgres-local": {
                "command": "python",
                "args": ["-m", "mcp_pg"],
            },
        },
        "workspaceCustomKey": "sovereign_flag",
    }
    cursor_cfg.write_text(json.dumps(initial_cursor, indent=2), encoding="utf-8")

    mock_stdout = io.StringIO()
    exit_code = run_init_mcp_agents(
        cwd=ws_dir,
        home=home_dir,
        system="Windows",
        appdata=str(appdata_dir),
        stream=mock_stdout,
    )

    assert exit_code == 0

    # Claude Desktop checks
    claude_data = json.loads(claude_cfg.read_text(encoding="utf-8"))
    assert "ctxfw" in claude_data["mcpServers"]
    assert claude_data["mcpServers"]["ctxfw"]["command"] == "ctxfw"
    assert claude_data["mcpServers"]["ctxfw"]["args"] == ["mcp"]
    # Preserved third-party servers
    assert "brave-search" in claude_data["mcpServers"]
    assert claude_data["mcpServers"]["brave-search"]["command"] == "npx"
    assert "github-official" in claude_data["mcpServers"]
    assert claude_data["mcpServers"]["github-official"]["command"] == "docker"
    # Preserved top-level keys
    assert claude_data["globalShortcut"] == "CommandOrControl+Shift+Space"
    assert claude_data["userPreferences"]["theme"] == "dark"

    # Cursor checks
    cursor_data = json.loads(cursor_cfg.read_text(encoding="utf-8"))
    assert "ctxfw" in cursor_data["mcpServers"]
    assert cursor_data["mcpServers"]["ctxfw"]["command"] == "ctxfw"
    assert cursor_data["mcpServers"]["ctxfw"]["args"] == ["mcp"]
    assert "postgres-local" in cursor_data["mcpServers"]
    assert cursor_data["workspaceCustomKey"] == "sovereign_flag"


def test_strict_idempotency_no_diff_and_no_duplicate_keys(tmp_path: Path):
    """Specification 5.c: Asserts subsequent executions produce no file diff and emit already-configured notice."""
    home_dir = tmp_path / "home"
    ws_dir = tmp_path / "workspace"
    appdata_dir = home_dir / "AppData" / "Roaming"

    # First run
    mock_stdout_1 = io.StringIO()
    code_1 = run_init_mcp_agents(
        cwd=ws_dir,
        home=home_dir,
        system="Windows",
        appdata=str(appdata_dir),
        stream=mock_stdout_1,
    )
    assert code_1 == 0
    assert "[+] Claude Desktop:" in mock_stdout_1.getvalue()
    assert "[+] Cursor:" in mock_stdout_1.getvalue()

    claude_cfg = resolve_claude_desktop_config_path(system="Windows", home=home_dir, appdata=str(appdata_dir))
    cursor_cfg = resolve_cursor_config_path(cwd=ws_dir)

    claude_content_1 = claude_cfg.read_text(encoding="utf-8")
    cursor_content_1 = cursor_cfg.read_text(encoding="utf-8")

    # Second run
    mock_stdout_2 = io.StringIO()
    code_2 = run_init_mcp_agents(
        cwd=ws_dir,
        home=home_dir,
        system="Windows",
        appdata=str(appdata_dir),
        stream=mock_stdout_2,
    )
    assert code_2 == 0
    out_2 = mock_stdout_2.getvalue()
    assert "[~] Claude Desktop: ctxfw is already configured." in out_2
    assert "[~] Cursor: ctxfw is already configured." in out_2

    claude_content_2 = claude_cfg.read_text(encoding="utf-8")
    cursor_content_2 = cursor_cfg.read_text(encoding="utf-8")

    # Byte-for-byte immutability assertion
    assert claude_content_1 == claude_content_2
    assert cursor_content_1 == cursor_content_2

    # Third run to ensure deterministic convergence
    mock_stdout_3 = io.StringIO()
    code_3 = run_init_mcp_agents(
        cwd=ws_dir,
        home=home_dir,
        system="Windows",
        appdata=str(appdata_dir),
        stream=mock_stdout_3,
    )
    assert code_3 == 0
    assert claude_content_1 == claude_cfg.read_text(encoding="utf-8")
    assert cursor_content_1 == cursor_cfg.read_text(encoding="utf-8")


def test_cli_runner_execution_and_stdout_formatting(tmp_path: Path, monkeypatch):
    """Specification 5.d: Asserts CLI execution verifying exit code 0 and ANSI-styled output formatting."""
    home_dir = tmp_path / "home"
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir(parents=True)
    appdata_dir = home_dir / "AppData" / "Roaming"

    monkeypatch.chdir(ws_dir)
    monkeypatch.setenv("APPDATA", str(appdata_dir))
    monkeypatch.setattr("pathlib.Path.home", lambda: home_dir)

    # 1. Run handle_init_cli([]) directly
    mock_stdout_cli = io.StringIO()
    monkeypatch.setattr("sys.stdout", mock_stdout_cli)

    code = handle_init_cli([])
    assert code == 0
    output = mock_stdout_cli.getvalue()
    assert "[+] Claude Desktop: Context Firewall injected successfully into" in output
    assert "[+] Cursor: Context Firewall injected successfully into" in output
    assert "✔ Zero-config integration complete. Restart your agent to activate." in output

    # 2. Run via main() with sys.argv = ["ctxfw", "init"]
    mock_stdout_main = io.StringIO()
    monkeypatch.setattr("sys.stdout", mock_stdout_main)
    monkeypatch.setattr("sys.argv", ["ctxfw", "init"])

    main()
    out_main = mock_stdout_main.getvalue()
    assert "[~] Claude Desktop: ctxfw is already configured." in out_main
    assert "[~] Cursor: ctxfw is already configured." in out_main
    assert "✔ Zero-config integration complete. Restart your agent to activate." in out_main


def test_graceful_error_handling_on_invalid_json(tmp_path: Path):
    """Asserts that unparseable JSON in one agent configuration reports warning without aborting sweep."""
    home_dir = tmp_path / "home"
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir(parents=True)
    appdata_dir = home_dir / "AppData" / "Roaming"

    # Corrupt Claude Desktop config
    claude_cfg = resolve_claude_desktop_config_path(system="Windows", home=home_dir, appdata=str(appdata_dir))
    claude_cfg.parent.mkdir(parents=True, exist_ok=True)
    claude_cfg.write_text("{\n  \"mcpServers\": {\n    broken_json: unquoted\n", encoding="utf-8")

    mock_stdout = io.StringIO()
    exit_code = run_init_mcp_agents(
        cwd=ws_dir,
        home=home_dir,
        system="Windows",
        appdata=str(appdata_dir),
        stream=mock_stdout,
    )

    assert exit_code == 0
    out = mock_stdout.getvalue()
    # Claude warning reported
    assert "Warning - Failed to parse configuration file" in out
    assert "Claude Desktop" in out
    # Cursor sweep NOT aborted and succeeded
    assert "[+] Cursor: Context Firewall injected successfully into" in out
    assert resolve_cursor_config_path(cwd=ws_dir).is_file()
    assert "Zero-config integration complete. Restart your agent to activate." in out


def test_empty_and_malformed_mcp_servers_field_recovery(tmp_path: Path):
    """Asserts resilient recovery when config file is empty or mcpServers is null."""
    ws_dir = tmp_path / "workspace"
    cursor_cfg = resolve_cursor_config_path(cwd=ws_dir)
    cursor_cfg.parent.mkdir(parents=True, exist_ok=True)

    # Empty file
    cursor_cfg.write_text("", encoding="utf-8")
    ok = inject_agent_mcp_config("Cursor", cursor_cfg)
    assert ok is True
    data = json.loads(cursor_cfg.read_text(encoding="utf-8"))
    assert "ctxfw" in data["mcpServers"]

    # File with mcpServers = None
    cursor_cfg.write_text(json.dumps({"mcpServers": None}), encoding="utf-8")
    ok2 = inject_agent_mcp_config("Cursor", cursor_cfg)
    assert ok2 is True
    data2 = json.loads(cursor_cfg.read_text(encoding="utf-8"))
    assert "ctxfw" in data2["mcpServers"]


def test_cli_backward_compatibility_flags(tmp_path: Path, monkeypatch):
    """Asserts that existing CLI flags (--global, --repo, <target_dir>, --help) remain fully backward-compatible."""
    # 1. --help
    mock_out_help = io.StringIO()
    monkeypatch.setattr("sys.stdout", mock_out_help)
    code_help = handle_init_cli(["--help"])
    assert code_help == 0
    assert "usage: ctxfw init [target_dir]" in mock_out_help.getvalue()
    assert "--global" in mock_out_help.getvalue()
    assert "--repo" in mock_out_help.getvalue()

    # 2. --global
    mock_out_global = io.StringIO()
    monkeypatch.setattr("sys.stdout", mock_out_global)
    code_global = handle_init_cli(["--global"])
    assert code_global == 0
    assert "CTXFW GLOBAL ZERO-TOUCH" in mock_out_global.getvalue()

    # 3. --repo
    repo_dir = tmp_path / "repo_target"
    (repo_dir / ".git").mkdir(parents=True)
    mock_out_repo = io.StringIO()
    monkeypatch.setattr("sys.stdout", mock_out_repo)
    code_repo = handle_init_cli(["--repo", str(repo_dir)])
    assert code_repo == 0
    assert (repo_dir / "SPEC.axioms.md").is_file()
    assert (repo_dir / ".git" / "hooks" / "pre-commit").is_file()

    # 4. <target_dir> positional argument
    target_dir = tmp_path / "custom_target"
    mock_out_pos = io.StringIO()
    monkeypatch.setattr("sys.stdout", mock_out_pos)
    code_pos = handle_init_cli([str(target_dir)])
    assert code_pos == 0
    assert (target_dir / ".mcp.json").is_file()
    assert (target_dir / ".agent" / "rules.yaml").is_file()
    assert (target_dir / ".agents" / "rules" / "firewall_laws.md").is_file()
    assert (target_dir / ".agents" / "skills" / "context-firewall" / "SKILL.md").is_file()


def test_cli_subprocess_execution(tmp_path: Path):
    """Asserts that executing `python -m ctxfw.cli init` in a fresh subprocess exits with 0 and creates configs."""
    import subprocess
    home_dir = tmp_path / "sub_home"
    ws_dir = tmp_path / "sub_ws"
    ws_dir.mkdir(parents=True)
    appdata_dir = home_dir / "AppData" / "Roaming"

    env = os.environ.copy()
    src_dir = str(Path(__file__).resolve().parent.parent / "src")
    env["PYTHONPATH"] = f"{src_dir}{os.pathsep}{env.get('PYTHONPATH', '')}"
    env["APPDATA"] = str(appdata_dir)
    env["USERPROFILE"] = str(home_dir)
    env["HOME"] = str(home_dir)

    proc = subprocess.run(
        [sys.executable, "-m", "ctxfw.cli", "init"],
        cwd=str(ws_dir),
        capture_output=True,
        text=True,
        env=env,
    )

    assert proc.returncode == 0
    combined = proc.stdout + proc.stderr
    assert "[+] Claude Desktop: Context Firewall injected successfully into" in combined
    assert "[+] Cursor: Context Firewall injected successfully into" in combined
    assert "Zero-config integration complete. Restart your agent to activate." in combined
    assert (ws_dir / ".cursor" / "mcp.json").is_file()


def test_path_resolution_case_insensitivity(tmp_path: Path):
    """Asserts that system strings in resolve_claude_desktop_config_path are case-insensitive."""
    home_mock = tmp_path / "home"
    darwin_lower = resolve_claude_desktop_config_path(system="darwin", home=home_mock)
    assert darwin_lower == home_mock.resolve() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"

    darwin_upper = resolve_claude_desktop_config_path(system="DARWIN", home=home_mock)
    assert darwin_upper == home_mock.resolve() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"

    win_lower = resolve_claude_desktop_config_path(system="windows", home=home_mock, appdata=str(tmp_path / "appdata"))
    assert win_lower == (tmp_path / "appdata").resolve() / "Claude" / "claude_desktop_config.json"


def test_utf8_bom_handling(tmp_path: Path):
    """Asserts that configuration files with UTF-8 Byte Order Mark (BOM) are parsed and updated cleanly."""
    ws_dir = tmp_path / "workspace"
    cursor_cfg = resolve_cursor_config_path(cwd=ws_dir)
    cursor_cfg.parent.mkdir(parents=True, exist_ok=True)

    # Write JSON with UTF-8 BOM (\xef\xbb\xbf)
    initial_content = b'\xef\xbb\xbf{\n  "mcpServers": {\n    "existing": {"command": "node"}\n  }\n}'
    cursor_cfg.write_bytes(initial_content)

    mock_out = io.StringIO()
    ok = inject_agent_mcp_config("Cursor", cursor_cfg, stream=mock_out)
    assert ok is True
    assert "[+] Cursor: Context Firewall injected successfully" in mock_out.getvalue()

    # Verify injected payload and preserved existing server
    data = json.loads(cursor_cfg.read_text(encoding="utf-8"))
    assert "existing" in data["mcpServers"]
    assert "ctxfw" in data["mcpServers"]


def test_target_is_directory_handled_gracefully(tmp_path: Path):
    """Asserts that if target configuration path is an existing directory, a clean error is reported without raising."""
    ws_dir = tmp_path / "workspace"
    cursor_cfg = resolve_cursor_config_path(cwd=ws_dir)
    # Create directory where file should be
    cursor_cfg.mkdir(parents=True, exist_ok=True)

    mock_out = io.StringIO()
    ok = inject_agent_mcp_config("Cursor", cursor_cfg, stream=mock_out)
    assert ok is False
    assert "Error - Configuration path is an existing directory, not a file" in mock_out.getvalue()


def test_handle_init_cli_default_invocation(tmp_path: Path, monkeypatch):
    """Asserts that handle_init_cli() can be called with no arguments (None default)."""
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir(parents=True)
    monkeypatch.chdir(ws_dir)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "home")

    mock_out = io.StringIO()
    monkeypatch.setattr("sys.stdout", mock_out)

    exit_code = handle_init_cli()
    assert exit_code == 0
    assert "Zero-config integration complete." in mock_out.getvalue()


def test_build_parser_init_dispatch(tmp_path: Path, monkeypatch):
    """Asserts that build_parser() wires init subcommand to handle_init_cli dispatch."""
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir(parents=True)
    monkeypatch.chdir(ws_dir)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "home")

    parser = build_parser()
    args = parser.parse_args(["init"])
    assert hasattr(args, "func")

    mock_out = io.StringIO()
    monkeypatch.setattr("sys.stdout", mock_out)
    code = args.func(args)
    assert code == 0
    assert "Zero-config integration complete." in mock_out.getvalue()


def test_init_entrypoint_sys_exit(tmp_path: Path, monkeypatch):
    """Asserts that the dedicated console script entrypoint init_entrypoint() exits with code 0."""
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir(parents=True)
    monkeypatch.chdir(ws_dir)
    monkeypatch.setattr("sys.argv", ["ctxfw-init"])
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "home")

    mock_out = io.StringIO()
    monkeypatch.setattr("sys.stdout", mock_out)

    with pytest.raises(SystemExit) as excinfo:
        init_entrypoint()
    assert excinfo.value.code == 0
