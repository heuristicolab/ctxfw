"""
src/ctxfw/cli/__init__.py — Unified Command Line Interface Package (v3.6.0)
Axiom Manifest Hash: a7e63ccb9b5dd0c6f6147cfd2feec447c4d41690dd76aee9e6035db56cb7c31a
"""
from ctxfw.cli.main import (
    build_parser,
    copy_to_clipboard,
    doctor_entrypoint,
    handle_init_cli,
    handle_init_command,
    handle_spec_command,
    init_entrypoint,
    inject_agent_mcp_config,
    main,
    resolve_claude_desktop_config_path,
    resolve_cursor_config_path,
    run_doctor_cli,
    run_firewall_cli,
    run_init_mcp_agents,
    run_spec_verify,
    handle_config_command,
    handle_mode_command,
    handle_report_command,
    generate_share_report,
)

__all__ = [
    "build_parser",
    "copy_to_clipboard",
    "run_firewall_cli",
    "handle_init_command",
    "handle_init_cli",
    "init_entrypoint",
    "run_doctor_cli",
    "doctor_entrypoint",
    "run_spec_verify",
    "handle_spec_command",
    "inject_agent_mcp_config",
    "resolve_claude_desktop_config_path",
    "resolve_cursor_config_path",
    "run_init_mcp_agents",
    "handle_config_command",
    "handle_mode_command",
    "handle_report_command",
    "generate_share_report",
    "main",
]
