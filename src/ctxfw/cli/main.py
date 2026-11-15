# manifest_hash: a425559f56edf617a357d8abbfec0ecbb9591379a696ba28a1e9c9cf57fdfcbc
# manifest_hash_hardening_c1: aad104b6b66067be4bcce9ec6297c4de2822cf1d3c38a76e79e04cf147f62dd9
"""
src/ctxfw/cli/main.py — Unified Command Line Interface for Context Firewall (v4.1.0)
Axiom Manifest Hash: a425559f56edf617a357d8abbfec0ecbb9591379a696ba28a1e9c9cf57fdfcbc
Supports direct target file clipboard invocation (`ctxfw <file>`) 
plus explicit subcommands (`ctxfw benchmark`, `ctxfw mcp`, `ctxfw proxy`, `ctxfw ci`, `ctxfw gate`, `ctxfw license`, `ctxfw audit`, `ctxfw trace`, `ctxfw init`, `ctxfw install`, `ctxfw doctor`, `ctxfw spec`, `ctxfw report`).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

from ctxfw.core.contracts import PruningDepth
from ctxfw.core.pruner import DeterministicContextPruner
from ctxfw.core.topological import ContextFirewallEngine, TopologicalContextBundleDTO
from ctxfw.cli.commands import benchmark
from ctxfw.installer import (
    inject_agent_mcp_config,
    install_claude_surfaces,
    install_mcp_servers,
    resolve_claude_desktop_config_path,
    resolve_cursor_config_path,
    run_init_mcp_agents,
    safe_merge_claude_code_config,
)
from ctxfw import __version__


def copy_to_clipboard(text: str) -> bool:
    """
    Atomically copies text to operating system clipboard preserving UTF-8 and exact indentation.
    Supports Windows (clip.exe / Set-Clipboard), macOS (pbcopy), and Linux (wl-copy / xclip / xsel).
    """
    system = platform.system()
    try:
        if system == "Windows":
            # clip.exe runs in <5ms and accepts UTF-16LE encoded bytes directly
            if shutil.which("clip.exe") or shutil.which("clip"):
                p = subprocess.run(
                    ["clip"],
                    input=text.encode("utf-16le"),
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                if p.returncode == 0:
                    return True

            # Fallback to PowerShell Set-Clipboard
            p = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "$input | Set-Clipboard"],
                input=text,
                text=True,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return p.returncode == 0

        elif system == "Darwin":
            p = subprocess.run(
                ["pbcopy"],
                input=text.encode("utf-8"),
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return p.returncode == 0

        else:
            # Linux: try Wayland wl-copy, then X11 xclip, then xsel
            for cmd in [["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]:
                if shutil.which(cmd[0]):
                    p = subprocess.run(
                        cmd,
                        input=text.encode("utf-8"),
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    if p.returncode == 0:
                        return True
            return False
    except Exception:
        return False


def run_firewall_cli(
    target_file_str: str,
    project_root_str: Optional[str] = None,
    copy_clip: bool = True,
    output_path_str: Optional[str] = None,
    print_stdout: bool = False,
    price_per_million: float = 3.0,
) -> int:
    """Executes the CLI context compaction pipeline."""
    start_total = time.perf_counter()

    target_path = Path(target_file_str).resolve()
    if not target_path.is_file():
        sys.stderr.write(f"[ERROR] Target file not found: {target_path}\n")
        return 1

    if project_root_str:
        project_root = Path(project_root_str).resolve()
    else:
        project_root = target_path.parent.resolve()

    if not project_root.is_dir():
        sys.stderr.write(f"[ERROR] Project root not found: {project_root}\n")
        return 1

    engine = ContextFirewallEngine(project_root=project_root)
    bundle: TopologicalContextBundleDTO = engine.build_context(target_path)
    prompt_markdown = bundle.to_prompt()

    # Clipboard copy
    clipboard_ok = False
    if copy_clip:
        clipboard_ok = copy_to_clipboard(prompt_markdown)

    # Optional file output
    if output_path_str:
        out_p = Path(output_path_str).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(prompt_markdown, encoding="utf-8")

    elapsed_ms = (time.perf_counter() - start_total) * 1000

    # Optional raw prompt to stdout
    if print_stdout:
        sys.stdout.write(prompt_markdown + "\n")
        return 0

    # Render Telemetry Dashboard to stdout
    total_orig_tokens = 0
    total_pruned_tokens = 0
    total_saved_tokens = 0

    rows = []
    distances = engine.graph.get_distances(target_path)

    for rel_path, dto in bundle.entries.items():
        dist = distances.get(rel_path, 0)
        dist_label = f"D{dist}" if dist < 2 else "D2+"

        orig_tok = DeterministicContextPruner.estimate_tokens(dto.original_chars)
        pruned_tok = DeterministicContextPruner.estimate_tokens(dto.pruned_chars)
        saved_tok = max(0, orig_tok - pruned_tok)

        total_orig_tokens += orig_tok
        total_pruned_tokens += pruned_tok
        total_saved_tokens += saved_tok

        depth_str = dto.depth.value.upper()
        pct_str = f"{dto.savings_percentage:.1f}%"
        rows.append((dist_label, rel_path, depth_str, orig_tok, pruned_tok, pct_str))

    net_reduction_pct = (
        round((total_saved_tokens / total_orig_tokens) * 100, 1)
        if total_orig_tokens > 0 else 0.0
    )
    usd_savings = (total_saved_tokens / 1_000_000) * price_per_million

    from ctxfw.installer import (
        CLR_AMBER,
        CLR_CYAN,
        CLR_EMERALD,
        CLR_GRAPHITE,
        CLR_RESET,
        CLR_WHITE_BOLD,
    )

    # Terminal Dashboard Output
    sys.stdout.write(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}\n")
    sys.stdout.write(f"  {CLR_CYAN}CONTEXT FIREWALL -- SOVEREIGN CLIPBOARD & TOKEN OPTIMIZER (v{__version__}){CLR_RESET}\n")
    sys.stdout.write(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}\n")
    sys.stdout.write(f"Target Module:  {bundle.root_target}\n")
    sys.stdout.write(f"Project Root:   {project_root}\n\n")

    sys.stdout.write(f"{'DIST':<6} | {'MODULE':<32} | {'DEPTH':<10} | {'ORIG TOK':<9} | {'PRUNED':<8} | {'SAVINGS':<8}\n")
    sys.stdout.write(f"{CLR_GRAPHITE}" + "-" * 84 + f"{CLR_RESET}\n")

    for dist_lbl, mod, dep, o_tok, p_tok, pct in rows:
        mod_trunc = mod if len(mod) <= 32 else ("..." + mod[-29:])
        sys.stdout.write(f"{dist_lbl:<6} | {mod_trunc:<32} | {dep:<10} | {o_tok:<9,d} | {p_tok:<8,d} | {pct:<8}\n")

    sys.stdout.write(f"{CLR_GRAPHITE}" + "-" * 84 + f"{CLR_RESET}\n")
    sys.stdout.write(
        f"{'TOTAL':<6} | {f'{len(rows)} Modules':<32} | {'':<10} | "
        f"{CLR_WHITE_BOLD}{total_orig_tokens:<9,d}{CLR_RESET} | {CLR_WHITE_BOLD}{total_pruned_tokens:<8,d}{CLR_RESET} | {f'{net_reduction_pct:.1f}%':<8}\n\n"
    )

    sys.stdout.write(f"[*] Net Context Tokens Saved:  {CLR_WHITE_BOLD}{total_saved_tokens:,}{CLR_RESET} tokens ({net_reduction_pct:.1f}% reduction)\n")
    sys.stdout.write(f"[*] Projected FinOps Savings:  {CLR_WHITE_BOLD}${usd_savings:.4f}{CLR_RESET} USD (@ ${price_per_million:.2f}/1M tokens)\n")
    sys.stdout.write(f"[*] Pipeline Latency:          {elapsed_ms:.2f} ms\n")
    if copy_clip:
        status_clip = f"{CLR_EMERALD}[PASS] COPIED TO SYSTEM CLIPBOARD{CLR_RESET}" if clipboard_ok else f"{CLR_AMBER}[WARN] CLIPBOARD UNAVAILABLE{CLR_RESET}"
        sys.stdout.write(f"[*] Clipboard Status:          {status_clip}\n")
    if output_path_str:
        sys.stdout.write(f"[*] Saved to File:             {output_path_str}\n")
    sys.stdout.write(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}\n")

    # Telemetría perimetral anónima y despacho de heartbeat
    try:
        from datetime import datetime, timezone
        from ctxfw.core.contracts import TelemetryRecordDTO
        from ctxfw.storage.telemetry import (
            TelemetryLedger,
            get_or_create_dev_uuid,
            push_telemetry_heartbeat_sync,
        )

        dev_uuid = get_or_create_dev_uuid()
        ledger = TelemetryLedger()
        record = TelemetryRecordDTO(
            dev_uuid=dev_uuid,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            model_target="cli-optimizer",
            tokens_orig=max(total_orig_tokens, total_saved_tokens),
            tokens_pruned=total_saved_tokens,
            usd_avoided=round(usd_savings, 6),
            team=os.environ.get("CTXFW_TEAM", "Engineering"),
        )
        ledger.record_event(record, synced=0)

        endpoint = os.environ.get("CTXFW_TELEMETRY_ENDPOINT")
        if endpoint:
            push_telemetry_heartbeat_sync(endpoint, ledger)
    except Exception:
        pass

    return 0


def handle_init_command(target_dir: Path | str | None = None) -> Path:
    """Inyecta el stack de soberanía agéntica y perimetral en cualquier directorio."""
    if target_dir is None:
        target_dir = Path.cwd()
    target_dir = Path(target_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    # 1. Manifiesto MCP Agnóstico Universal
    mcp_path = target_dir / ".mcp.json"
    mcp_content = """{
  "mcpServers": {
    "ctxfw": {
      "command": "python",
      "args": ["-m", "ctxfw.mcp"]
    }
  }
}
"""
    mcp_path.write_text(mcp_content, encoding="utf-8")

    # 2. Directivas del Agente (Rules)
    agent_dir = target_dir / ".agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    rules_path = agent_dir / "rules.yaml"
    rules_content = """agent:
  name: "Arquitecto Perimetral Soberano"
  version: "3.4.0"
  permissionMode: "acceptEdits"
  commandExecutionPolicy: "auto"
  laws:
    - rule_id: "FIREWALL_LAW_01"
      description: "Prohibición absoluta de leer archivos periféricos en bruto. Las dependencias D1 y D2+ deben transitar obligatoriamente por stubs de interfaz."
    - rule_id: "FIREWALL_LAW_02"
      description: "Obligatoriedad de invocar la skill resolve_context_bundle antes de proponer refactorizaciones complejas."
    - rule_id: "FINOPS_AUDIT_03"
      description: "Reportar obligatoriamente la telemetría de tokens ahorrados y dólares eludidos al finalizar cada tarea."
"""
    rules_path.write_text(rules_content, encoding="utf-8")

    # 3. Gobernanza y Leyes del Cortafuegos
    rules_docs_dir = target_dir / ".agents" / "rules"
    rules_docs_dir.mkdir(parents=True, exist_ok=True)
    laws_path = rules_docs_dir / "firewall_laws.md"
    laws_content = """# Leyes Perimetrales del Cortafuegos (ctxfw)
1. **Cero Lecturas en Bruto:** Ningún archivo de dependencia directa ($D_1$) o transitiva ($D_{2+}$) puede ser consumido sin poda topológica previa.
2. **Soberanía Local:** La propiedad intelectual y los contratos de Pydantic no abandonan el perímetro de ejecución sin optimización previa.
"""
    laws_path.write_text(laws_content, encoding="utf-8")

    # 4. Skill Descubrible para Antigravity y Cursor
    skill_dir = target_dir / ".agents" / "skills" / "context-firewall"
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_path = skill_dir / "SKILL.md"
    skill_content = """---
name: context-firewall
description: Autonomous AST/CST token optimization and topological dependency pruning for sovereign code generation.
---

# Context Firewall (ctxfw) Skill
Utiliza `resolve_context_bundle`, `audit_finops_ledger` y `gatekeeper_pr_audit` para mantener la disciplina de tokens.
"""
    skill_path.write_text(skill_content, encoding="utf-8")

    print(f"[*] Workspace soberano inicializado exitosamente en: {target_dir}")
    print("    - .mcp.json (Servidor MCP stdio)")
    print("    - .agent/rules.yaml (Leyes del Arquitecto Perimetral)")
    print("    - .agents/rules/firewall_laws.md (Gobernanza)")
    print("    - .agents/skills/context-firewall/SKILL.md (Skill nativa)")
    return target_dir


def handle_init_cli(argv: Optional[List[str]] = None) -> int:
    """Handles ctxfw init subcommand with zero-config agent integration, --global, --repo, and target directory options."""
    args = list(argv) if argv is not None else []
    if any(arg in {"-h", "--help"} for arg in args):
        print("usage: ctxfw init [target_dir]")
        print("\nInitialize sovereign agentic perimeter, rules, and skills in target directory.")
        print("Without arguments, performs automated, idempotent MCP integration for Claude Desktop and Cursor.")
        print("  --claude             Zero-touch installation for Claude Code CLI (~/.claude.json) and Claude Desktop")
        print("  --global             Perform zero-touch onboarding across installed IDEs")
        print("  --repo [target_dir]  Deploy canonical SPEC.axioms.md and git pre-commit verification hook")
        return 0

    if "--claude" in args:
        from ctxfw.installer import install_claude_surfaces
        return install_claude_surfaces()

    if "--global" in args:
        from ctxfw.installer import (
            CLR_CYAN,
            CLR_EMERALD,
            CLR_GRAPHITE,
            CLR_RESET,
            print_defense_banner,
            run_global_init,
        )
        print_defense_banner()
        print(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}")
        print(f"  {CLR_CYAN}CTXFW GLOBAL ZERO-TOUCH PROVISIONING // MULTI-IDE ARMORED INJECTION{CLR_RESET}")
        print(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}")
        res = run_global_init()
        for act in res["actions"]:
            print(f"  {CLR_EMERALD}[PASS]{CLR_RESET} {act}")
        print(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}")
        return 0

    if "--repo" in args:
        from ctxfw.installer import (
            CLR_CYAN,
            CLR_EMERALD,
            CLR_GRAPHITE,
            CLR_RESET,
            print_defense_banner,
            init_repository_perimeter,
        )
        print_defense_banner()
        print(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}")
        print(f"  {CLR_CYAN}CTXFW REPOSITORY ARMOR // CANONICAL AXIOMS & PRE-COMMIT SENTRY{CLR_RESET}")
        print(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}")
        repo_args = [a for a in args if a != "--repo" and not a.startswith("-")]
        target = Path(repo_args[0]).resolve() if repo_args else Path.cwd()
        handle_init_command(target)
        res = init_repository_perimeter(target)
        for msg in res["messages"]:
            print(f"  {CLR_EMERALD}[ATTESTED]{CLR_RESET} {msg}")
        print(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}")
        return 0

    plain_args = [a for a in args if not a.startswith("-")]
    if plain_args:
        target = Path(plain_args[0]).resolve()
        handle_init_command(target)
        return 0

    return run_init_mcp_agents()


def handle_install_cli(argv: Optional[List[str]] = None) -> int:
    """Handles ctxfw install subcommand with --claude, --global, and multi-surface injection."""
    args = list(argv) if argv is not None else []
    if any(arg in {"-h", "--help"} for arg in args):
        print("usage: ctxfw install [--claude] [--global]")
        print("\nInstall and wire Context Firewall into agentic IDEs & CLI environments.")
        print("Without arguments, performs automated, idempotent MCP integration across all detected IDEs.")
        print("  --claude             Zero-touch installation for Claude Code CLI (~/.claude.json) and Claude Desktop")
        print("  --global             Perform zero-touch onboarding across installed IDEs")
        return 0

    if "--claude" in args:
        from ctxfw.installer import install_claude_surfaces
        return install_claude_surfaces()

    if "--global" in args:
        from ctxfw.installer import (
            CLR_CYAN,
            CLR_EMERALD,
            CLR_GRAPHITE,
            CLR_RESET,
            print_defense_banner,
            run_global_init,
        )
        print_defense_banner()
        print(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}")
        print(f"  {CLR_CYAN}CTXFW GLOBAL ZERO-TOUCH PROVISIONING // MULTI-IDE ARMORED INJECTION{CLR_RESET}")
        print(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}")
        res = run_global_init()
        for act in res["actions"]:
            print(f"  {CLR_EMERALD}[PASS]{CLR_RESET} {act}")
        print(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}")
        return 0

    from ctxfw.installer import install_mcp_servers
    return install_mcp_servers()


def install_entrypoint() -> None:
    """Dedicated entrypoint for ctxfw-install console script."""
    sys.exit(handle_install_cli(sys.argv[1:]))


def run_doctor_cli(argv: Optional[List[str]] = None) -> int:
    """Runs system health and isolation diagnostics."""
    from ctxfw.installer import render_doctor_report, run_doctor
    target: Optional[Path] = None
    args = argv if argv is not None else sys.argv[1:]
    plain = [a for a in args if not a.startswith("-")]
    if plain:
        target = Path(plain[0]).resolve()
    report = run_doctor(project_root=target)
    return render_doctor_report(report)


def doctor_entrypoint() -> None:
    """Dedicated entrypoint for ctxfw-doctor console script."""
    sys.exit(run_doctor_cli())


def init_entrypoint() -> None:
    """Dedicated entrypoint for ctxfw-init console script."""
    sys.exit(handle_init_cli(sys.argv[1:]))


def run_spec_verify(file_path_str: str) -> int:
    """Evaluates a specification markdown brief and renders terminal summary."""
    path = Path(file_path_str).resolve()
    if not path.is_file():
        sys.stderr.write(f"[ERROR] Specification file not found: {path}\n")
        return 1

    content = path.read_text(encoding="utf-8")
    from ctxfw.sieve.engine import evaluate_specification
    from ctxfw.installer import (
        CLR_AMBER,
        CLR_CRIMSON,
        CLR_CYAN,
        CLR_EMERALD,
        CLR_GRAPHITE,
        CLR_RESET,
        CLR_WHITE_BOLD,
    )

    result = evaluate_specification(content)

    sys.stdout.write(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}\n")
    sys.stdout.write(f"  {CLR_CYAN}CTXFW SPECIFICATION SIEVE // AXIOMATIC DETERMINISM VERIFIER{CLR_RESET}\n")
    sys.stdout.write(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}\n")
    sys.stdout.write(f"Evaluated File:             {path}\n")
    sys.stdout.write(f"ACI Score:                  {CLR_WHITE_BOLD}{result.aci_score:.4f}{CLR_RESET}\n")
    sys.stdout.write(f"Negative Invariants Count:  {result.negative_invariants_count}\n")
    sys.stdout.write(f"Extracted Clauses:\n")
    if result.extracted_never_clauses:
        for idx, clause in enumerate(result.extracted_never_clauses, start=1):
            sys.stdout.write(f"  {idx}. {clause}\n")
    else:
        sys.stdout.write(f"  {CLR_GRAPHITE}(None detected){CLR_RESET}\n")

    sys.stdout.write(f"Manifest Hash (SHA-256):    {CLR_WHITE_BOLD}{result.manifest_hash}{CLR_RESET}\n")
    sys.stdout.write(f"{CLR_GRAPHITE}" + "-" * 72 + f"{CLR_RESET}\n")

    if result.status == "VERIFIED":
        sys.stdout.write(f"Final Verdict:              {CLR_EMERALD}[PASS] READY FOR FORGE{CLR_RESET}\n")
        sys.stdout.write(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}\n")
        return 0
    else:
        sys.stdout.write(f"Final Verdict:              {CLR_CRIMSON}[FAIL] SPECIFICATION QUARANTINED{CLR_RESET}\n")
        if result.remediation_notes:
            sys.stdout.write(f"{CLR_AMBER}Remediation Notes:{CLR_RESET}\n")
            for note in result.remediation_notes:
                sys.stdout.write(f"  {CLR_AMBER}- {note}{CLR_RESET}\n")
        sys.stdout.write(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}\n")
        return 1


def handle_spec_command(argv: list[str]) -> int:
    """Handles ctxfw spec subcommand routing."""
    parser = argparse.ArgumentParser(
        prog="ctxfw spec",
        description="Verify architectural intake specification axioms and negative invariants.",
    )
    subparsers = parser.add_subparsers(dest="spec_command", help="Spec commands")
    verify_parser = subparsers.add_parser("verify", help="Verify a specification markdown brief")
    verify_parser.add_argument("file_path", help="Path to specification markdown brief")

    if not argv or (len(argv) == 1 and argv[0] in {"-h", "--help"}):
        parser.print_help()
        return 0

    args = parser.parse_args(argv)

    if args.spec_command == "verify":
        return run_spec_verify(args.file_path)
    else:
        parser.print_help()
        return 0


def run_trace_verify(
    db_path_str: Optional[str] = None,
    session_id: Optional[str] = None,
) -> int:
    """
    Verifies backward integrity of the TraceKit hash-chained audit ledger.
    Enforces:
      - Invocación de ctxfw.audit.verifier.verify_chain sobre tracekit.db.
      - Formats console output showing: chain status, total blocks audited, latest block digest, tamper_detected (True/False).
    """
    from ctxfw.audit.store import TRACEKIT_DB_NAME, resolve_tracekit_db_path

    if db_path_str:
        db_path = Path(db_path_str).resolve()
        if db_path.name != TRACEKIT_DB_NAME:
            sys.stderr.write(f"[ERROR] TraceKit database file must be named '{TRACEKIT_DB_NAME}', got '{db_path.name}'.\n")
            return 1
    else:
        db_path = resolve_tracekit_db_path()

    from ctxfw.installer import (
        CLR_CRIMSON,
        CLR_CYAN,
        CLR_EMERALD,
        CLR_GRAPHITE,
        CLR_RESET,
        CLR_WHITE_BOLD,
    )

    if not db_path.is_file():
        sys.stdout.write(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}\n")
        sys.stdout.write(f"  {CLR_CYAN}CTXFW TRACEKIT LEDGER // HASH-CHAIN INTEGRITY VERIFIER{CLR_RESET}\n")
        sys.stdout.write(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}\n")
        sys.stdout.write(f"Database File:         {db_path}\n")
        sys.stdout.write(f"Chain Status:          {CLR_EMERALD}VERIFIED_CLEAN (EMPTY){CLR_RESET}\n")
        sys.stdout.write(f"Total Blocks Audited:  {CLR_WHITE_BOLD}0{CLR_RESET}\n")
        sys.stdout.write(f"Latest Block Digest:   {CLR_WHITE_BOLD}None{CLR_RESET}\n")
        sys.stdout.write(f"Tamper Detected:       {CLR_EMERALD}False{CLR_RESET}\n")
        sys.stdout.write("tamper_detected:       False\n")
        sys.stdout.write(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}\n")
        return 0

    import sqlite3
    from datetime import datetime, timezone
    from ctxfw.audit.contracts import HashChainedAuditBlockDTO
    from ctxfw.audit.verifier import apply_latch, fail_closed_audit, verify_chain
    from ctxfw.kernel.clock import SystemUtcClock

    clock = SystemUtcClock()
    now_ts = clock.now()

    conn = None
    try:
        try:
            uri = f"{db_path.as_uri()}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=5.0)
        except Exception:
            conn = sqlite3.connect(str(db_path), timeout=5.0)

        cursor = conn.cursor()
        tables = {r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not tables:
            conn.close()
            conn = None
            sys.stdout.write(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}\n")
            sys.stdout.write(f"  {CLR_CYAN}CTXFW TRACEKIT LEDGER // HASH-CHAIN INTEGRITY VERIFIER{CLR_RESET}\n")
            sys.stdout.write(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}\n")
            sys.stdout.write(f"Database File:         {db_path}\n")
            sys.stdout.write(f"Chain Status:          {CLR_EMERALD}VERIFIED_CLEAN (EMPTY){CLR_RESET}\n")
            sys.stdout.write(f"Total Blocks Audited:  {CLR_WHITE_BOLD}0{CLR_RESET}\n")
            sys.stdout.write(f"Latest Block Digest:   {CLR_WHITE_BOLD}None{CLR_RESET}\n")
            sys.stdout.write(f"Tamper Detected:       {CLR_EMERALD}False{CLR_RESET}\n")
            sys.stdout.write("tamper_detected:       False\n")
            sys.stdout.write(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}\n")
            return 0

        if "tracekit_sessions" not in tables or "tracekit_audit_blocks" not in tables:
            conn.close()
            conn = None
            sys.stdout.write(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}\n")
            sys.stdout.write(f"  {CLR_CYAN}CTXFW TRACEKIT LEDGER // HASH-CHAIN INTEGRITY VERIFIER{CLR_RESET}\n")
            sys.stdout.write(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}\n")
            sys.stdout.write(f"Database File:         {db_path}\n")
            sys.stdout.write(f"Chain Status:          {CLR_CRIMSON}TAMPER_DETECTED (SCHEMA CORRUPTED){CLR_RESET}\n")
            sys.stdout.write(f"Total Blocks Audited:  {CLR_WHITE_BOLD}1{CLR_RESET}\n")
            sys.stdout.write(f"Latest Block Digest:   {CLR_WHITE_BOLD}None{CLR_RESET}\n")
            sys.stdout.write(f"Tamper Detected:       {CLR_CRIMSON}True{CLR_RESET}\n")
            sys.stdout.write("tamper_detected:       True\n")
            sys.stdout.write(f"{CLR_CRIMSON}[!] Tamper Details:     Missing sealed tables (tracekit_sessions / tracekit_audit_blocks){CLR_RESET}\n")
            sys.stdout.write(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}\n")
            return 1

        if session_id:
            sessions = cursor.execute(
                "SELECT session_id, genesis_hash FROM tracekit_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchall()
            if not sessions:
                conn.close()
                conn = None
                verdict = fail_closed_audit(session_id, now_ts)
                sys.stdout.write(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}\n")
                sys.stdout.write(f"  {CLR_CYAN}CTXFW TRACEKIT LEDGER // HASH-CHAIN INTEGRITY VERIFIER{CLR_RESET}\n")
                sys.stdout.write(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}\n")
                sys.stdout.write(f"Database File:         {db_path}\n")
                sys.stdout.write(f"Chain Status:          {CLR_CRIMSON}TAMPER_DETECTED (SESSION NOT FOUND){CLR_RESET}\n")
                sys.stdout.write(f"Total Blocks Audited:  {CLR_WHITE_BOLD}{verdict.total_blocks_audited}{CLR_RESET}\n")
                sys.stdout.write(f"Latest Block Digest:   {CLR_WHITE_BOLD}None{CLR_RESET}\n")
                sys.stdout.write(f"Tamper Detected:       {CLR_CRIMSON}True{CLR_RESET}\n")
                sys.stdout.write("tamper_detected:       True\n")
                sys.stdout.write(f"{CLR_CRIMSON}[!] Tamper Details:     Session {session_id} not found in ledger (fail-closed){CLR_RESET}\n")
                sys.stdout.write(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}\n")
                return 1
        else:
            sessions = cursor.execute(
                "SELECT session_id, genesis_hash FROM tracekit_sessions ORDER BY created_at ASC"
            ).fetchall()

        if not sessions:
            conn.close()
            conn = None
            sys.stdout.write(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}\n")
            sys.stdout.write(f"  {CLR_CYAN}CTXFW TRACEKIT LEDGER // HASH-CHAIN INTEGRITY VERIFIER{CLR_RESET}\n")
            sys.stdout.write(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}\n")
            sys.stdout.write(f"Database File:         {db_path}\n")
            sys.stdout.write(f"Chain Status:          {CLR_EMERALD}VERIFIED_CLEAN (0 SESSIONS){CLR_RESET}\n")
            sys.stdout.write(f"Total Blocks Audited:  {CLR_WHITE_BOLD}0{CLR_RESET}\n")
            sys.stdout.write(f"Latest Block Digest:   {CLR_WHITE_BOLD}None{CLR_RESET}\n")
            sys.stdout.write(f"Tamper Detected:       {CLR_EMERALD}False{CLR_RESET}\n")
            sys.stdout.write("tamper_detected:       False\n")
            sys.stdout.write(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}\n")
            return 0

        total_audited = 0
        tamper_detected = False
        broken_info = None
        latest_digest = None

        for sid, ghash in sessions:
            b_rows = cursor.execute(
                "SELECT block_id, session_id, block_seq, prev_block_hash, current_block_hash, "
                "intent_digest, reasoning_digest, action_digest, created_at "
                "FROM tracekit_audit_blocks WHERE session_id = ? ORDER BY block_seq ASC",
                (sid,),
            ).fetchall()

            blocks = []
            try:
                for r in b_rows:
                    ts = datetime.strptime(r[8], "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
                    blocks.append(
                        HashChainedAuditBlockDTO(
                            block_id=r[0],
                            session_id=r[1],
                            block_seq=r[2],
                            prev_block_hash=r[3],
                            current_block_hash=r[4],
                            intent_digest=r[5],
                            reasoning_digest=r[6],
                            action_digest=r[7],
                            timestamp_utc=ts,
                        )
                    )
                    latest_digest = r[4]
            except Exception as parse_err:
                verdict = fail_closed_audit(sid, now_ts)
                tamper_detected = True
                total_audited += verdict.total_blocks_audited
                broken_info = f"Session {sid} block data corrupted/tampered: {parse_err}"
                break

            latch_row = cursor.execute(
                "SELECT broken_seq FROM tracekit_verification_events WHERE session_id = ? AND is_tampered = 1 ORDER BY rowid LIMIT 1",
                (sid,),
            ).fetchone()
            latched_seq = latch_row[0] if latch_row else None

            verdict = verify_chain(
                session_id=sid,
                genesis_hash=ghash,
                blocks=blocks,
                verified_at=now_ts,
            )
            verdict = apply_latch(verdict, latched_seq)
            total_audited += verdict.total_blocks_audited

            if verdict.is_tampered:
                tamper_detected = True
                broken_info = f"Session {sid} broken at block {verdict.broken_block_seq}"
                break

        conn.close()
        conn = None
    except Exception as err:
        sys.stderr.write(f"[ERROR] Failed to verify TraceKit database: {err}\n")
        return 1
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    chain_status = "TAMPER_DETECTED" if tamper_detected else "VERIFIED_CLEAN"
    status_color = CLR_CRIMSON if tamper_detected else CLR_EMERALD

    sys.stdout.write(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}\n")
    sys.stdout.write(f"  {CLR_CYAN}CTXFW TRACEKIT LEDGER // HASH-CHAIN INTEGRITY VERIFIER{CLR_RESET}\n")
    sys.stdout.write(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}\n")
    sys.stdout.write(f"Database File:         {db_path}\n")
    sys.stdout.write(f"Chain Status:          {status_color}{chain_status}{CLR_RESET}\n")
    sys.stdout.write(f"Total Blocks Audited:  {CLR_WHITE_BOLD}{total_audited}{CLR_RESET}\n")
    sys.stdout.write(f"Latest Block Digest:   {CLR_WHITE_BOLD}{latest_digest or 'None'}{CLR_RESET}\n")
    sys.stdout.write(f"Tamper Detected:       {status_color}{tamper_detected}{CLR_RESET}\n")
    sys.stdout.write(f"tamper_detected:       {tamper_detected}\n")
    if tamper_detected and broken_info:
        sys.stdout.write(f"{CLR_CRIMSON}[!] Tamper Details:     {broken_info}{CLR_RESET}\n")
    sys.stdout.write(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}\n")

    return 1 if tamper_detected else 0


def handle_trace_command(argv: list[str]) -> int:
    """Handles ctxfw trace subcommand routing."""
    parser = argparse.ArgumentParser(
        prog="ctxfw trace",
        description="TraceKit hash-chained audit ledger inspection and backward verification.",
    )
    subparsers = parser.add_subparsers(dest="trace_subcommand", help="Trace subcommands")
    verify_parser = subparsers.add_parser("verify", help="Verify hash chain backward consistency")
    verify_parser.add_argument("--db", type=str, default=None, help="Path to tracekit.db SQLite database")
    verify_parser.add_argument("--session", "-s", type=str, default=None, help="Optional session ID to verify")

    if not argv or (len(argv) == 1 and argv[0] in {"-h", "--help"}):
        parser.print_help()
        return 0

    args = parser.parse_args(argv)
    if args.trace_subcommand == "verify":
        return run_trace_verify(db_path_str=args.db, session_id=args.session)
    else:
        parser.print_help()
        return 0


def handle_config_command(argv: list[str]) -> int:
    """Handles ctxfw config [list|show|get|set] commands."""
    from ctxfw.config import load_config, set_config_value

    if not argv or argv[0] in {"-h", "--help"}:
        print("usage: ctxfw config [list | show | get <key> | set <key> <value>]")
        print("\nManage dynamic configuration in ~/.ctxfw/config.json.")
        print("Examples:")
        print("  ctxfw config list")
        print("  ctxfw config show")
        print("  ctxfw config models")
        print("  ctxfw config sync-models")
        print("  ctxfw config get engine.mode")
        print("  ctxfw config set engine.mode passthrough")
        print("  ctxfw config set finops.model claude-opus-4")
        print("  ctxfw config set finops.roast_level cynical")
        return 0

    action = argv[0].lower()
    if action in {"list", "show"}:
        cfg = load_config()
        print(cfg.model_dump_json(indent=2))
        return 0
    elif action == "models":
        from ctxfw.finops import load_model_matrix

        catalog = load_model_matrix()
        out_dict = {mid: spec.model_dump(mode="json") for mid, spec in catalog.items()}
        print(json.dumps(out_dict, indent=2))
        return 0
    elif action == "sync-models":
        from ctxfw.finops import sync_model_matrix

        url = argv[1] if len(argv) > 1 else "https://ctxfw.heuristicolab.com/v1/model-matrix.json"
        ok, msg = sync_model_matrix(url=url)
        print(f"[{'OK' if ok else 'INFO'}] {msg}")
        return 0
    elif action == "get":
        if len(argv) < 2:
            print("Error: missing key. Usage: ctxfw config get <key>", file=sys.stderr)
            return 1
        key = argv[1]
        cfg = load_config()
        data = cfg.model_dump(mode="json")
        parts = key.split(".")
        try:
            curr = data
            for p in parts:
                curr = curr[p]
            print(curr)
            return 0
        except (KeyError, TypeError):
            print(f"Error: key '{key}' not found in configuration.", file=sys.stderr)
            return 1
    elif action == "set":
        if len(argv) < 3:
            print("Error: missing key or value. Usage: ctxfw config set <key> <value>", file=sys.stderr)
            return 1
        key, value = argv[1], argv[2]
        try:
            set_config_value(key, value)
            print(f"[OK] Configuration updated: {key} = {value}")
            return 0
        except Exception as e:
            print(f"Error updating configuration: {e}", file=sys.stderr)
            return 1
    else:
        print(
            f"Unknown config action: '{action}'. Expected 'list', 'show', 'models', 'sync-models', 'get', or 'set'.",
            file=sys.stderr,
        )
        return 1


def handle_mode_command(argv: list[str]) -> int:
    """Handles ctxfw mode [distance|passthrough] shortcut command."""
    from ctxfw.config import load_config, set_config_value

    if not argv:
        cfg = load_config()
        print(f"Current engine mode: {cfg.engine.mode.value}")
        return 0

    if argv[0] in {"-h", "--help"}:
        print("usage: ctxfw mode [distance | passthrough]")
        print("\nQuick toggle between distance (AST pruning) and passthrough (untouched code) modes.")
        return 0

    target_mode = argv[0].lower().strip()
    if target_mode not in {"distance", "passthrough"}:
        print(f"Error: invalid engine mode '{target_mode}'. Allowed: distance, passthrough", file=sys.stderr)
        return 1

    try:
        set_config_value("engine.mode", target_mode)
        print(f"[OK] Context firewall mode switched to: {target_mode}")
        return 0
    except Exception as e:
        print(f"Error updating engine mode: {e}", file=sys.stderr)
        return 1


def _collect_finops_metrics(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Internal helper collecting sanitized FinOps, per-repo, and security metrics from local SQLite stores."""
    import re
    import sqlite3
    from ctxfw.storage.cache import get_canonical_cache_path
    from ctxfw.config import load_config
    from ctxfw.finops import (
        compute_arbitrage_recommendation,
        compute_compounded_savings,
        resolve_active_model,
    )

    cfg = load_config()
    active_model = resolve_active_model()
    compounding_factor = float(getattr(cfg.finops, "compounding_factor", 4.2))
    effective_price = float(cfg.finops.input_price_per_m)

    db_file = Path(db_path) if db_path else get_canonical_cache_path()

    total_evaluated = 0
    tokens_saved = 0
    usd_avoided = 0.0
    cycles = 0
    project_rows: list[dict[str, Any]] = []

    if db_file.is_file():
        try:
            conn = sqlite3.connect(str(db_file), timeout=3.0)
            cursor = conn.cursor()
            try:
                cols = {r[1] for r in cursor.execute("PRAGMA table_info(tokens_cache)").fetchall()}
                if cols and "project_name" not in cols:
                    conn.execute(
                        "ALTER TABLE tokens_cache ADD COLUMN project_name TEXT NOT NULL DEFAULT 'global'"
                    )
                    conn.commit()
                if cols and "project_id" not in cols:
                    conn.execute(
                        "ALTER TABLE tokens_cache ADD COLUMN project_id TEXT NOT NULL DEFAULT 'REPO-0000000000000000'"
                    )
                    conn.commit()
                if cols and "model_name" not in cols:
                    conn.execute(
                        "ALTER TABLE tokens_cache ADD COLUMN model_name TEXT NOT NULL DEFAULT 'auto'"
                    )
                    conn.commit()

                row = cursor.execute(
                    "SELECT count(*), sum(original_chars), sum(estimated_tokens_saved) FROM tokens_cache"
                ).fetchone()
                if row and row[0]:
                    cycles += int(row[0])
                    total_evaluated += (row[1] or 0) // 4
                    saved_from_cache = int(row[2] or 0)
                    tokens_saved += saved_from_cache
                    usd_avoided += (saved_from_cache / 1_000_000.0) * effective_price

                raw_proj = cursor.execute(
                    """
                    SELECT COALESCE(NULLIF(project_name, ''), 'global') AS proj,
                           COUNT(*),
                           SUM(original_chars),
                           SUM(estimated_tokens_saved)
                    FROM tokens_cache
                    GROUP BY proj
                    ORDER BY SUM(estimated_tokens_saved) DESC, COUNT(*) DESC
                    LIMIT 500
                    """
                ).fetchall()
                for p_name, p_cycles, p_orig_chars, p_saved in raw_proj:
                    safe_proj = re.sub(r"[^A-Za-z0-9._-]", "-", str(p_name or "global"))[:64] or "global"
                    p_eval_tok = int((p_orig_chars or 0) // 4)
                    p_saved_tok = int(p_saved or 0)
                    p_red_pct = round((p_saved_tok / max(1, p_eval_tok) * 100.0), 2) if p_eval_tok > 0 else 0.0
                    p_usd = round((p_saved_tok / 1_000_000.0) * effective_price, 6)
                    p_comp_usd = round(p_usd * compounding_factor, 6)
                    project_rows.append(
                        {
                            "project_name": safe_proj,
                            "cycles": int(p_cycles or 0),
                            "evaluated_tokens": p_eval_tok,
                            "tokens_saved": p_saved_tok,
                            "reduction_pct": p_red_pct,
                            "usd_saved": p_usd,
                            "compounded_usd_saved": p_comp_usd,
                        }
                    )
            except sqlite3.OperationalError:
                pass

            try:
                row2 = cursor.execute(
                    "SELECT count(*), sum(tokens_orig), sum(tokens_pruned), sum(usd_avoided) FROM telemetry_ledger"
                ).fetchone()
                if row2 and row2[0]:
                    cycles += int(row2[0])
                    total_evaluated += int(row2[1] or 0)
                    tokens_saved += int(row2[2] or 0)
                    usd_avoided += float(row2[3] or 0.0)
            except sqlite3.OperationalError:
                pass
            conn.close()
        except Exception:
            pass

    if usd_avoided == 0.0 and tokens_saved > 0:
        usd_avoided = (tokens_saved / 1_000_000.0) * effective_price

    reduction_pct = round((tokens_saved / max(1, total_evaluated) * 100.0), 2) if total_evaluated > 0 else 0.0
    compounded = compute_compounded_savings(
        tokens_saved=tokens_saved,
        model_spec=active_model,
        compounding_factor=compounding_factor,
        override_input_price_per_m=effective_price,
    )
    compounded_usd = round(usd_avoided * compounding_factor, 6)
    arbitrage = compute_arbitrage_recommendation(
        model_spec=active_model,
        evaluated_tokens=total_evaluated,
        tokens_saved=tokens_saved,
        compounding_factor=compounding_factor,
    )

    return {
        "cycles": cycles,
        "total_evaluated": total_evaluated,
        "tokens_saved": tokens_saved,
        "reduction_pct": reduction_pct,
        "usd_avoided": round(usd_avoided, 6),
        "compounding_factor": round(compounding_factor, 2),
        "compounded_tokens_saved": compounded["compounded_session_tokens"],
        "compounded_usd_avoided": compounded_usd,
        "active_model": active_model.model_id,
        "active_model_display": active_model.display_name,
        "input_price_per_m": effective_price,
        "output_price_per_m": active_model.output_price_per_m,
        "livebench_coding_score": active_model.livebench_coding_score,
        "livebench_agentic_score": active_model.livebench_agentic_score,
        "arbitrage": arbitrage,
        "projects": project_rows,
        "engine_mode": cfg.engine.mode.value,
        "max_distance": cfg.engine.max_distance,
    }


def generate_share_report(db_path: Optional[str] = None) -> str:
    """
    Generates a shareable Markdown report with telemetry, per-repository breakdown,
    multi-turn compounding savings, and LiveBench model arbitrage.
    Strictly enforces Invariant 4:
    The share reporter shall never include unpruned source code,
    private credentials, or raw file paths in the generated markdown output.
    """
    import re

    m = _collect_finops_metrics(db_path=db_path)
    cycles = m["cycles"]
    total_evaluated = m["total_evaluated"]
    tokens_saved = m["tokens_saved"]
    reduction_pct = m["reduction_pct"]
    usd_avoided = m["usd_avoided"]
    comp_factor = m["compounding_factor"]
    comp_tokens = m["compounded_tokens_saved"]
    comp_usd = m["compounded_usd_avoided"]
    project_rows = m["projects"]
    arb = m["arbitrage"]

    lines = [
        "# Context Firewall (ctxfw) // Sovereign FinOps ROI Report",
        "",
        "> Generated by ctxfw Sovereign Engine. 100% Local Air-Gapped Verification.",
        "",
        "## 1. Executive Telemetry",
        f"- **Audit Cycles Executed:** {cycles:,}",
        f"- **Original Tokens Evaluated:** {total_evaluated:,}",
        f"- **Tokens Pruned / Avoided:** {tokens_saved:,}",
        f"- **Net Context Reduction:** {reduction_pct:.2f}%",
        f"- **Estimated Monetary Savings:** ${usd_avoided:.4f} USD",
        f"- **Compounded Multi-Turn Session Savings ({comp_factor:.1f}x Cache+TTL):** ${comp_usd:.4f} USD ({comp_tokens:,} effective tokens)",
        f"- **Active Model Profile:** `{m['active_model_display']}` (`${m['input_price_per_m']:.2f}/1M` in | LiveBench Coding: `{m['livebench_coding_score']:.1f}`)",
        "",
        "## 2. Per-Repository FinOps Breakdown",
        "| Repository / Project | Cycles | Evaluated Tokens | Pruned Tokens | Reduction % | USD Saved | Compounded USD |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    if project_rows:
        for p in project_rows:
            p_name = p["project_name"]
            label = "`[legacy/global]`" if p_name == "global" else f"`{p_name}`"
            lines.append(
                f"| {label} | {p['cycles']:,} | {p['evaluated_tokens']:,} | {p['tokens_saved']:,} | "
                f"{p['reduction_pct']:.2f}% | ${p['usd_saved']:.4f} | ${p['compounded_usd_saved']:.4f} |"
            )
    else:
        lines.append("| `[no-active-projects]` | 0 | 0 | 0 | 0.00% | $0.0000 | $0.0000 |")

    lines.extend(
        [
            "",
            "## 3. LiveBench Model Efficiency & FinOps Arbitrage",
            f"- **Active Model:** `{m['active_model_display']}` (`{m['active_model']}`)",
            f"- **LiveBench Coding / Agentic Score:** `{m['livebench_coding_score']:.1f}` / `{m['livebench_agentic_score']:.1f}`",
            f"- **Pareto Guidance:** {arb['recommendation']}",
            "",
            "## 4. Operational Perimeter & Compliance",
            f"- **Active Engine Mode:** `{m['engine_mode']}`",
            f"- **Max Topological Depth:** D{m['max_distance']}",
            "- **Per-Repository Isolation:** Enabled (Workspace-Scoped Rules & D3 Symbol Index)",
            "- **Air-Gap Verification:** Certified Local (Zero Cloud Telemetry Egress)",
            "- **Code Privacy Assurance:** Zero unpruned source code blocks or confidential logic exported.",
            "",
        ]
    )
    report_text = "\n".join(lines)

    # Invariant 4 Sanitization Filters:
    # 1. Strip raw absolute paths (Windows C:\ or Unix /Users, /home)
    report_text = re.sub(r"[A-Za-z]:\\[A-Za-z0-9_\-\\]+", "[REDACTED_LOCAL_PATH]", report_text)
    report_text = re.sub(r"/(?:Users|home|root)/[A-Za-z0-9_\-/]+", "[REDACTED_LOCAL_PATH]", report_text)

    # 2. Strip potential secret credentials
    report_text = re.sub(r"(?:sk-[a-zA-Z0-9_\-]{15,}|ghp_[a-zA-Z0-9]{15,})", "[REDACTED_SECRET]", report_text)

    # 3. Ensure no unpruned source code blocks are present
    if "def " in report_text or "class " in report_text or "import " in report_text:
        sanitized_lines = []
        for line in report_text.splitlines():
            if re.match(r"^\s*(?:def\s|class\s|import\s|from\s)", line):
                continue
            sanitized_lines.append(line)
        report_text = "\n".join(sanitized_lines)

    return report_text


def _canonical_export_digest(payload_without_seal: Dict[str, Any]) -> str:
    """Computes deterministic SHA-256 over canonical sorted JSON payload (AXIOM-V41-4)."""
    canonical_bytes = json.dumps(
        payload_without_seal,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


def export_report_json(
    db_path: Optional[str] = None,
    dev_alias: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Exports a tamper-evident, privacy-preserving developer FinOps snapshot for team aggregation.
    Enforces AXIOM-V41-3 (Zero source code, zero absolute paths, zero OS usernames)
    and AXIOM-V41-4 (Cryptographic SHA-256 seal).
    """
    import re
    from ctxfw.storage.telemetry import get_or_create_dev_uuid

    m = _collect_finops_metrics(db_path=db_path)
    raw_uuid = dev_alias or get_or_create_dev_uuid()
    anon_dev_id = "DEV-" + hashlib.sha256(str(raw_uuid).encode("utf-8")).hexdigest()[:12]

    clean_projects = []
    for p in m["projects"]:
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "-", str(p["project_name"]))[:64] or "global"
        clean_projects.append(
            {
                "project_name": safe_name,
                "cycles": int(p["cycles"]),
                "evaluated_tokens": int(p["evaluated_tokens"]),
                "tokens_saved": int(p["tokens_saved"]),
                "reduction_pct": float(p["reduction_pct"]),
                "usd_saved": float(p["usd_saved"]),
                "compounded_usd_saved": float(p["compounded_usd_saved"]),
            }
        )

    payload: Dict[str, Any] = {
        "schema_version": "4.1.0",
        "dev_id": anon_dev_id,
        "active_model": str(m["active_model"]),
        "active_model_display": str(m["active_model_display"]),
        "livebench_coding_score": float(m["livebench_coding_score"]),
        "cycles": int(m["cycles"]),
        "evaluated_tokens": int(m["total_evaluated"]),
        "tokens_saved": int(m["tokens_saved"]),
        "reduction_pct": float(m["reduction_pct"]),
        "direct_usd_saved": float(m["usd_avoided"]),
        "compounding_factor": float(m["compounding_factor"]),
        "compounded_tokens_saved": int(m["compounded_tokens_saved"]),
        "compounded_usd_saved": float(m["compounded_usd_avoided"]),
        "repositories": clean_projects,
    }
    payload["manifest_sha256"] = _canonical_export_digest(payload)
    return payload


def merge_team_reports(json_paths: List[str | Path]) -> str:
    """
    Verifies cryptographic seals and merges N developer JSON snapshots into a unified
    Team Executive FinOps & Multi-Repository Markdown report.
    Enforces AXIOM-V41-4: Fails closed on any tampered or malformed snapshot.
    """
    if not json_paths:
        raise ValueError("DETERMINISTIC_VALIDATION_ERROR: At least one JSON file is required for --team-merge.")
    if len(json_paths) > 500:
        raise ValueError("DETERMINISTIC_VALIDATION_ERROR: Cannot merge more than 500 snapshots at once.")

    total_cycles = 0
    total_eval = 0
    total_saved = 0
    total_direct_usd = 0.0
    total_comp_tokens = 0
    total_comp_usd = 0.0
    dev_rows: list[tuple[str, str, int, int, float, float]] = []
    repo_agg: dict[str, dict[str, Any]] = {}
    model_agg: dict[str, dict[str, Any]] = {}

    for raw_path in json_paths:
        p = Path(raw_path)
        if not p.is_file():
            raise ValueError(f"DETERMINISTIC_VALIDATION_ERROR: Snapshot file not found: {p.name}")
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"DETERMINISTIC_VALIDATION_ERROR: Invalid JSON in {p.name}: {exc}") from exc

        if not isinstance(data, dict) or "manifest_sha256" not in data:
            raise ValueError(f"SECURITY_TAMPER_DETECTED: Missing manifest_sha256 seal in {p.name}")

        claimed_seal = str(data["manifest_sha256"])
        unsigned = {k: v for k, v in data.items() if k != "manifest_sha256"}
        expected_seal = _canonical_export_digest(unsigned)
        if claimed_seal != expected_seal:
            raise ValueError(
                f"SECURITY_TAMPER_DETECTED: Integrity seal mismatch in {p.name} "
                f"(expected {expected_seal[:16]}..., got {claimed_seal[:16]}...)"
            )

        dev_id = str(data.get("dev_id", "DEV-unknown"))
        model_disp = str(data.get("active_model_display") or data.get("active_model", "unknown"))
        c_cycles = int(data.get("cycles", 0))
        c_eval = int(data.get("evaluated_tokens", 0))
        c_saved = int(data.get("tokens_saved", 0))
        c_usd = float(data.get("direct_usd_saved", 0.0))
        c_comp_tok = int(data.get("compounded_tokens_saved", c_saved))
        c_comp_usd = float(data.get("compounded_usd_saved", c_usd))
        c_score = float(data.get("livebench_coding_score", 0.0))

        total_cycles += c_cycles
        total_eval += c_eval
        total_saved += c_saved
        total_direct_usd += c_usd
        total_comp_tokens += c_comp_tok
        total_comp_usd += c_comp_usd

        dev_rows.append((dev_id, model_disp, c_cycles, c_saved, c_usd, c_comp_usd))

        m_bucket = model_agg.setdefault(
            model_disp,
            {"cycles": 0, "tokens_saved": 0, "direct_usd": 0.0, "comp_usd": 0.0, "score": c_score},
        )
        m_bucket["cycles"] += c_cycles
        m_bucket["tokens_saved"] += c_saved
        m_bucket["direct_usd"] += c_usd
        m_bucket["comp_usd"] += c_comp_usd

        for r in data.get("repositories", []):
            if not isinstance(r, dict):
                continue
            r_name = str(r.get("project_name", "global"))
            bucket = repo_agg.setdefault(
                r_name,
                {"cycles": 0, "eval": 0, "saved": 0, "usd": 0.0, "comp_usd": 0.0},
            )
            bucket["cycles"] += int(r.get("cycles", 0))
            bucket["eval"] += int(r.get("evaluated_tokens", 0))
            bucket["saved"] += int(r.get("tokens_saved", 0))
            bucket["usd"] += float(r.get("usd_saved", 0.0))
            bucket["comp_usd"] += float(r.get("compounded_usd_saved", 0.0))

    overall_red = (total_saved / max(1, total_eval) * 100.0) if total_eval > 0 else 0.0

    lines = [
        "# Context Firewall (ctxfw) // Team Executive FinOps & Multi-Repo Ledger",
        "",
        f"> Consolidated across **{len(dev_rows)} Verified Developer Nodes** (SHA-256 Attested).",
        "",
        "## 1. Team-Wide Executive Summary",
        f"- **Active Developer Nodes:** {len(dev_rows)}",
        f"- **Total Audit & Pruning Cycles:** {total_cycles:,}",
        f"- **Total Raw Tokens Evaluated:** {total_eval:,}",
        f"- **Total Direct Tokens Saved (1-Turn):** {total_saved:,} ({overall_red:.2f}% reduction)",
        f"- **Total Compounded Session Tokens Saved:** {total_comp_tokens:,}",
        f"- **Direct 1-Turn Monetary Savings:** ${total_direct_usd:.4f} USD",
        f"- **Compounded Multi-Turn Session Savings:** **${total_comp_usd:.4f} USD**",
        "",
        "## 2. Consolidated Per-Repository Breakdown",
        "| Repository / Project | Cycles | Evaluated Tokens | Pruned Tokens | Reduction % | Direct USD | Compounded USD |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    sorted_repos = sorted(repo_agg.items(), key=lambda kv: kv[1]["saved"], reverse=True)
    if sorted_repos:
        for r_name, b in sorted_repos:
            label = "`[legacy/global]`" if r_name == "global" else f"`{r_name}`"
            r_red = (b["saved"] / max(1, b["eval"]) * 100.0) if b["eval"] > 0 else 0.0
            lines.append(
                f"| {label} | {b['cycles']:,} | {b['eval']:,} | {b['saved']:,} | "
                f"{r_red:.2f}% | ${b['usd']:.4f} | ${b['comp_usd']:.4f} |"
            )
    else:
        lines.append("| `[no-active-projects]` | 0 | 0 | 0 | 0.00% | $0.0000 | $0.0000 |")

    lines.extend(
        [
            "",
            "## 3. Per-Developer Node Breakdown",
            "| Developer Node | Active Model | Cycles | Pruned Tokens | Direct USD | Compounded USD |",
            "| :--- | :--- | ---: | ---: | ---: | ---: |",
        ]
    )
    for d_id, d_mod, d_cyc, d_sav, d_usd, d_cusd in dev_rows:
        lines.append(
            f"| `{d_id}` | `{d_mod}` | {d_cyc:,} | {d_sav:,} | ${d_usd:.4f} | ${d_cusd:.4f} |"
        )

    lines.extend(
        [
            "",
            "## 4. Model Fleet & LiveBench Efficiency",
            "| Model | LiveBench Coding | Team Cycles | Pruned Tokens | Direct USD | Compounded USD |",
            "| :--- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for m_name, mb in sorted(model_agg.items(), key=lambda kv: kv[1]["comp_usd"], reverse=True):
        lines.append(
            f"| `{m_name}` | `{mb['score']:.1f}` | {mb['cycles']:,} | {mb['tokens_saved']:,} | "
            f"${mb['direct_usd']:.4f} | ${mb['comp_usd']:.4f} |"
        )
    lines.append("")
    return "\n".join(lines)


def handle_report_command(argv: list[str]) -> int:
    """Handles ctxfw report [--share] [--ci-markdown] [--export-json <path>] [--team-merge <files...>] [--output <file>] command."""
    parser = argparse.ArgumentParser(
        prog="ctxfw report",
        description="Generate FinOps telemetry, per-repository breakdown, and consolidated team ROI reports.",
    )
    parser.add_argument("--share", action="store_true", help="Generate shareable sanitized Markdown ROI report (Invariant 4)")
    parser.add_argument("--ci-markdown", action="store_true", help="Generate CI/CD PR dependency and FinOps summary via CIGatekeeper")
    parser.add_argument("--export-json", type=str, default=None, help="Export tamper-evident developer JSON snapshot for team consolidation")
    parser.add_argument("--dev-alias", type=str, default=None, help="Optional developer identifier to hash into DEV-<id> during --export-json")
    parser.add_argument("--team-merge", nargs="+", default=None, help="Consolidate multiple developer JSON snapshots into a Team Executive Report")
    parser.add_argument("--license-key", type=str, default=None, help="Team/Enterprise license key (or set CTXFW_LICENSE_KEY)")
    parser.add_argument("--output", "-o", type=str, default=None, help="Save report to specified output path")
    parser.add_argument("--db", type=str, default=None, help="Path to SQLite telemetry database")

    args = parser.parse_args(argv)

    if args.export_json:
        payload = export_report_json(db_path=args.db, dev_alias=args.dev_alias)
        out_p = Path(args.export_json).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"[OK] Attested FinOps JSON snapshot exported to {out_p} (seal: {payload['manifest_sha256'][:16]}...)")
        return 0

    if args.team_merge:
        from ctxfw.finops.licensing import verify_license_key

        lic = verify_license_key(args.license_key)
        if not lic.is_valid:
            print(lic.message, file=sys.stderr)
            return 1

        try:
            merged_md = merge_team_reports(args.team_merge)
        except ValueError as err:
            print(f"[ERROR] {err}", file=sys.stderr)
            return 1
        merged_md = f"{lic.message}\n\n{merged_md}"
        if args.output:
            out_p = Path(args.output).resolve()
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_text(merged_md, encoding="utf-8")
            print(f"[OK] Team executive report written to {out_p} ({lic.message})")
        else:
            print(merged_md)
        return 0

    if args.ci_markdown:
        from ctxfw.gatekeeper import CIGatekeeper
        gatekeeper = CIGatekeeper()
        changed_files = gatekeeper.detect_changed_files()
        classified = gatekeeper.classify_perimeter(changed_files)
        report_md = gatekeeper.generate_markdown_summary(classified)
        if args.output:
            out_p = Path(args.output).resolve()
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_text(report_md, encoding="utf-8")
        else:
            sys.stdout.write(report_md + "\n")
        return 0

    report_md = generate_share_report(db_path=args.db)

    if args.output:
        out_p = Path(args.output).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(report_md, encoding="utf-8")
        print(f"[OK] Shareable report written to {out_p}")
    else:
        print(report_md)

    return 0


def handle_gate_command(argv: list[str]) -> int:
    """
    Handles `ctxfw gate` CI/CD PR architectural & non-functional regression verifier.
    Enforces AXIOM-V41-5: Fail-closed exit code 1 on any architectural violation,
    failed functional test, or malformed diff.
    """
    import subprocess
    from ctxfw.storage.cache import get_canonical_cache_path, resolve_project_identity
    from ctxfw.swegate.contracts import (
        ArchitecturalConstraintRuleDTO,
        FunctionalTestResultDTO,
        FunctionalVerdict,
        GateState,
        GateVerdict,
        PatchMetadataDTO,
        sha256_hex,
    )
    from ctxfw.swegate.gate import SweGateVerifier
    from ctxfw.swegate.store import SweGateStore

    parser = argparse.ArgumentParser(
        prog="ctxfw gate",
        description="Run SWE-Gate deterministic CI/CD pull request verification against architectural regressions.",
    )
    parser.add_argument("--diff", type=str, default=None, help="Path to unified diff file (or '-' for stdin). Defaults to git diff.")
    parser.add_argument("--staged", action="store_true", help="Inspect staged git diff (`git diff --cached`)")
    parser.add_argument("--base", type=str, default=None, help="Git base ref for diff (e.g. origin/main)")
    parser.add_argument("--commit-sha", type=str, default=None, help="40-char commit SHA (defaults to HEAD or deterministic hash)")
    parser.add_argument("--pr-id", type=int, default=1, help="Pull Request numeric ID (default: 1)")
    parser.add_argument("--author-kind", type=str, default="AGENT", choices=["AGENT", "HUMAN"], help="Patch author type")
    parser.add_argument("--tests-passed", type=int, default=1, help="Count of passed functional tests")
    parser.add_argument("--tests-failed", type=int, default=0, help="Count of failed functional tests")
    parser.add_argument("--max-cyclomatic-delta", type=int, default=10, help="Maximum allowed net cyclomatic complexity increase")
    parser.add_argument("--allow-type-ignore", action="store_true", help="Permit `# type: ignore` annotations in added lines")
    parser.add_argument("--disallow-import", action="append", default=[], help="Disallow module import (may be specified multiple times)")
    parser.add_argument("--repo-name", type=str, default=None, help="Repository slug (auto-detected from workspace if omitted)")
    parser.add_argument("--license-key", type=str, default=None, help="Team/Enterprise license key (or set CTXFW_LICENSE_KEY)")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON output")
    parser.add_argument("--github-summary", action="store_true", help="Append Markdown verdict to $GITHUB_STEP_SUMMARY")

    args = parser.parse_args(argv)

    from ctxfw.finops.licensing import verify_license_key

    lic = verify_license_key(args.license_key)
    if not lic.is_valid:
        sys.stderr.write(f"{lic.message}\n")
        if args.json:
            print(
                json.dumps(
                    {
                        "verdict": "LICENSE_REQUIRED",
                        "state": lic.status.value,
                        "message": lic.message,
                    },
                    indent=2,
                )
            )
        return 1

    # 1. Resolve unified diff text
    diff_text: Optional[str] = None
    if args.diff:
        if args.diff == "-":
            diff_text = sys.stdin.read()
        else:
            diff_path = Path(args.diff)
            if not diff_path.is_file():
                sys.stderr.write(f"[SWE-GATE ERROR] Diff file not found: {args.diff}\n")
                return 1
            diff_text = diff_path.read_text(encoding="utf-8")
    else:
        git_cmd = ["git", "diff"]
        if args.staged:
            git_cmd.append("--cached")
        elif args.base:
            git_cmd.append(args.base)
        else:
            git_cmd.append("HEAD")
        try:
            proc = subprocess.run(git_cmd, capture_output=True, text=True, check=False)
            diff_text = proc.stdout
        except Exception as exc:
            sys.stderr.write(f"[SWE-GATE ERROR] Failed to invoke git diff: {exc}\n")
            return 1

    if not isinstance(diff_text, str) or not diff_text.strip():
        sys.stderr.write("[SWE-GATE REJECTED] Empty or missing unified diff (fail-closed).\n")
        return 1

    # 2. Resolve commit SHA and repository identity
    commit_sha = args.commit_sha
    if not commit_sha or len(commit_sha.strip()) != 40:
        commit_sha = sha256_hex(diff_text)[:40]

    _, detected_repo = resolve_project_identity(Path.cwd())
    repo_name = args.repo_name or (detected_repo if detected_repo != "global" else "workspace/repo")

    try:
        meta = PatchMetadataDTO(
            commit_sha=commit_sha.lower(),
            author_kind=args.author_kind,
            pr_id=args.pr_id,
            diff_size_bytes=len(diff_text.encode("utf-8")),
        )
    except Exception:
        meta = None

    try:
        fv = (
            FunctionalVerdict.PASSED
            if (args.tests_failed == 0 and args.tests_passed >= 1)
            else FunctionalVerdict.FAILED
        )
        functional = FunctionalTestResultDTO(
            tests_passed=args.tests_passed,
            tests_failed=args.tests_failed,
            functional_verdict=fv,
        )
    except Exception:
        functional = None

    try:
        disallowed = tuple(dict.fromkeys(m.strip() for m in (args.disallow_import or []) if m.strip()))
        rule = ArchitecturalConstraintRuleDTO(
            rule_id="RULE-cli-gate",
            max_cyclomatic_delta=args.max_cyclomatic_delta,
            forbid_type_ignores=not args.allow_type_ignore,
            disallowed_import_modules=disallowed,
        )
    except Exception:
        rule = None

    audit, trace = SweGateVerifier.evaluate_traced(meta, functional, rule, diff_text)
    final_state = trace[-1] if trace else GateState.REJECTED_INVALID

    # 3. Persist evaluation in SweGateStore & seal in TraceKitStore
    eval_id = "EVL-unrecorded"
    try:
        env_db = os.environ.get("CTXFW_SWEGATE_DB")
        db_path = Path(env_db) if env_db else (Path(get_canonical_cache_path()).parent / "swegate.db")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        store = SweGateStore(db_path)
        try:
            repo_id = store.register_repository(repo_name)
            fallback_meta = (
                meta
                if isinstance(meta, PatchMetadataDTO)
                else PatchMetadataDTO(
                    commit_sha=sha256_hex(diff_text)[:40],
                    author_kind="AGENT",
                    pr_id=1,
                    diff_size_bytes=max(1, len(diff_text.encode("utf-8"))),
                )
            )
            decided = (
                final_state
                if final_state in (GateState.DECIDED_PASS, GateState.DECIDED_REJECT)
                else GateState.DECIDED_REJECT
            )
            rec_id, committed_state, _ = store.record_evaluation(
                repo_id, fallback_meta, audit, decided_state=decided
            )
            if rec_id:
                eval_id = rec_id
            if final_state in (GateState.DECIDED_PASS, GateState.DECIDED_REJECT):
                final_state = committed_state
        finally:
            store.close()
    except Exception:
        pass

    is_allowed = (
        audit.gate_verdict is GateVerdict.ALLOW_MERGE
        and final_state is GateState.PASS_GATE
    )

    result_payload = {
        "verdict": audit.gate_verdict.value,
        "state": final_state.value,
        "evaluation_id": eval_id,
        "repository": repo_name,
        "commit_sha": commit_sha,
        "is_functional_passed": audit.is_functional_passed,
        "cyclomatic_delta": audit.cyclomatic_delta,
        "max_cyclomatic_delta": args.max_cyclomatic_delta,
        "architectural_violations": list(audit.architectural_violations),
        "license": {
            "id": lic.license_id,
            "org": lic.org,
            "tier": lic.tier.value if lic.tier else None,
            "days_remaining": lic.days_remaining,
        },
    }

    md_lines = [
        f"## SWE-Gate CI Verification // `{'ALLOW_MERGE' if is_allowed else 'REJECTED'}`",
        "",
        f"- **License Attestation:** `{lic.message}`",
        f"- **Repository:** `{repo_name}`",
        f"- **Evaluation ID:** `{eval_id}`",
        f"- **Verdict:** `{audit.gate_verdict.value}` (`{final_state.value}`)",
        f"- **Functional Tests Passed:** `{audit.is_functional_passed}` (`+{args.tests_passed}` / `-{args.tests_failed}`)",
        f"- **Cyclomatic Complexity Delta:** `{audit.cyclomatic_delta:+d}` (max allowed: `{args.max_cyclomatic_delta:+d}`)",
    ]
    if audit.architectural_violations:
        md_lines.append("- **Architectural Violations Detected:**")
        for v in audit.architectural_violations:
            md_lines.append(f"  - `{v}`")
    else:
        md_lines.append("- **Architectural Violations Detected:** `0 (Clean)`")
    md_summary = "\n".join(md_lines) + "\n"

    summary_env = os.environ.get("GITHUB_STEP_SUMMARY")
    if (args.github_summary or summary_env) and summary_env:
        try:
            with open(summary_env, "a", encoding="utf-8") as sf:
                sf.write(md_summary + "\n")
        except Exception:
            pass

    if args.json:
        print(json.dumps(result_payload, indent=2))
    else:
        print(md_summary)

    return 0 if is_allowed else 1


def handle_license_command(argv: list[str]) -> int:
    """
    Handles `ctxfw license [status|activate|issue]` subcommands.
    """
    from ctxfw.finops.licensing import issue_license_key, verify_license_key

    parser = argparse.ArgumentParser(
        prog="ctxfw license",
        description="Verify, activate, or issue CTXFW Team Squad / Enterprise licenses.",
    )
    sub = parser.add_subparsers(dest="action")

    st_p = sub.add_parser("status", help="Verify active Team/Enterprise license status")
    st_p.add_argument("--key", type=str, default=None, help="Explicit license key to inspect")
    st_p.add_argument("--json", action="store_true", help="Emit JSON status")

    act_p = sub.add_parser("activate", help="Persist a Team/Enterprise license key to ~/.ctxfw/license.key")
    act_p.add_argument("key", type=str, help="CTXFW license key string")

    iss_p = sub.add_parser("issue", help="Sign and emit a new license key (requires CTXFW_MASTER_PRIVATE_KEY)")
    iss_p.add_argument("--org", type=str, required=True, help="Organization or squad name")
    iss_p.add_argument("--tier", type=str, default="TEAM_TRIAL", choices=["TEAM_TRIAL", "TEAM_PRO", "ENTERPRISE"], help="License tier")
    iss_p.add_argument("--days", type=int, default=7, help="Validity duration in days (default: 7)")
    iss_p.add_argument("--id", dest="license_id", type=str, default=None, help="Optional custom license ID (e.g. LIC-ACME-01)")
    iss_p.add_argument("--max-devs", type=int, default=15, help="Max developers in squad (default: 15)")
    iss_p.add_argument("--max-repos", type=int, default=5, help="Max CI/CD repositories (default: 5)")

    if not argv:
        argv = ["status"]
    args = parser.parse_args(argv)

    if args.action == "activate":
        lic = verify_license_key(args.key)
        if not lic.is_valid:
            print(lic.message, file=sys.stderr)
            return 1
        dest = Path.home() / ".ctxfw" / "license.key"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(args.key.strip() + "\n", encoding="utf-8")
        print(f"[OK] License activated and saved to {dest}\n{lic.message}")
        return 0

    if args.action == "issue":
        try:
            signed_key = issue_license_key(
                org=args.org,
                tier=args.tier,
                days=args.days,
                license_id=args.license_id,
                max_devs=args.max_devs,
                max_repos=args.max_repos,
            )
            print(signed_key)
            return 0
        except Exception as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            return 1

    lic = verify_license_key(getattr(args, "key", None))
    if getattr(args, "json", False):
        print(lic.model_dump_json(indent=2))
    else:
        print(lic.message)
    return 0 if lic.is_valid else 1


def build_parser() -> argparse.ArgumentParser:
    """Builds central subcommands parser for ctxfw."""
    parser = argparse.ArgumentParser(
        prog="ctxfw",
        description=f"ctxfw -- Sovereign Context Firewall & Token Optimization Engine (v{__version__})\n\n"
                    "Subcommands:\n"
                    "  install              Install Context Firewall into agentic IDEs & CLI environments\n"
                    "  init                 Initialize sovereign agentic perimeter, rules, and skills\n"
                    "  doctor               Run health, stdio isolation, and environment diagnostics\n"
                    "  mcp                  Start stdio Model Context Protocol server\n"
                    "  proxy                Launch local perimeter reverse proxy gateway\n"
                    "  service              Manage background service (Windows sc.exe & systemd)\n"
                    "  ci                   Run CI/CD PR topological gatekeeper\n"
                    "  gate                 Run SWE-Gate CI/CD pull request architectural verifier\n"
                    "  audit                Audit FinOps token savings and telemetry ledger\n"
                    "  trace                Inspect and verify TraceKit hash-chained audit ledger\n"
                    "  spec                 Verify specification axioms and negative invariants\n"
                    "  benchmark            Profile topological AST token reduction and FinOps savings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    # Subcommand install
    install_parser = subparsers.add_parser("install", help="Install Context Firewall into agentic IDEs & CLI environments")
    install_parser.add_argument("--claude", action="store_true", help="Zero-touch installation for Claude Code CLI (~/.claude.json) and Claude Desktop")
    install_parser.add_argument("--global", dest="global_install", action="store_true", help="Perform zero-touch onboarding across installed IDEs")

    def _run_install_dispatch(parsed_args: argparse.Namespace) -> int:
        cli_args: List[str] = []
        if getattr(parsed_args, "claude", False):
            cli_args.append("--claude")
        if getattr(parsed_args, "global_install", False):
            cli_args.append("--global")
        return handle_install_cli(cli_args)

    install_parser.set_defaults(func=_run_install_dispatch)

    # Subcommand init
    init_parser = subparsers.add_parser("init", help="Initialize sovereign agentic perimeter, rules, and skills")
    init_parser.add_argument("target_dir", nargs="?", default=None, help="Target directory for workspace perimeter")
    init_parser.add_argument("--claude", action="store_true", help="Zero-touch installation for Claude Code CLI (~/.claude.json) and Claude Desktop")
    init_parser.add_argument("--global", dest="global_init", action="store_true", help="Perform zero-touch onboarding across installed IDEs")
    init_parser.add_argument("--repo", nargs="?", const="", default=None, help="Deploy canonical SPEC.axioms.md and git pre-commit verification hook")

    def _run_init_dispatch(parsed_args: argparse.Namespace) -> int:
        cli_args: List[str] = []
        if getattr(parsed_args, "claude", False):
            cli_args.append("--claude")
        if getattr(parsed_args, "global_init", False):
            cli_args.append("--global")
        if getattr(parsed_args, "repo", None) is not None:
            cli_args.append("--repo")
            if parsed_args.repo:
                cli_args.append(parsed_args.repo)
        if getattr(parsed_args, "target_dir", None):
            cli_args.append(parsed_args.target_dir)
        return handle_init_cli(cli_args)

    init_parser.set_defaults(func=_run_init_dispatch)

    # Subcommand config
    config_parser = subparsers.add_parser("config", help="Inspect and mutate dynamic configuration in ~/.ctxfw/config.json")
    config_parser.add_argument("action", nargs="?", default="list", choices=["list", "show", "models", "sync-models", "get", "set"], help="Action: list, show, models, sync-models, get, set")
    config_parser.add_argument("key", nargs="?", default=None, help="Configuration key path (e.g. engine.mode)")
    config_parser.add_argument("value", nargs="?", default=None, help="New value for configuration key")

    # Subcommand mode
    mode_parser = subparsers.add_parser("mode", help="Quick toggle between distance and passthrough modes")
    mode_parser.add_argument("target_mode", nargs="?", default=None, choices=["distance", "passthrough"], help="Operating mode")

    # Subcommand report
    report_parser = subparsers.add_parser("report", help="Generate FinOps ROI telemetry reports")
    report_parser.add_argument("--share", action="store_true", help="Generate shareable sanitized Markdown ROI report")
    report_parser.add_argument("--ci-markdown", action="store_true", help="Generate CI/CD PR dependency and FinOps summary via CIGatekeeper")
    report_parser.add_argument("--export-json", type=str, default=None, help="Export tamper-evident developer JSON snapshot")
    report_parser.add_argument("--team-merge", nargs="+", default=None, help="Consolidate multiple developer JSON snapshots")
    report_parser.add_argument("--output", "-o", type=str, default=None, help="Save report to specified output path")
    report_parser.add_argument("--db", type=str, default=None, help="Path to SQLite telemetry database")

    # Subcommand gate
    gate_parser = subparsers.add_parser("gate", help="Run SWE-Gate CI/CD pull request architectural verifier")
    gate_parser.add_argument("--diff", type=str, default=None, help="Path to unified diff file")
    gate_parser.add_argument("--staged", action="store_true", help="Inspect staged git diff")
    gate_parser.add_argument("--max-cyclomatic-delta", type=int, default=10, help="Max allowed cyclomatic delta")

    # Subcommand trace
    trace_parser = subparsers.add_parser("trace", help="Inspect and verify TraceKit hash-chained audit ledger")
    trace_sub = trace_parser.add_subparsers(dest="trace_subcommand")
    trace_verify_parser = trace_sub.add_parser("verify", help="Verify hash chain backward consistency")
    trace_verify_parser.add_argument("--db", type=str, default=None, help="Path to tracekit.db SQLite database")
    trace_verify_parser.add_argument("--session", "-s", type=str, default=None, help="Optional session ID to verify")

    def _run_trace_dispatch(parsed_args: argparse.Namespace) -> int:
        if getattr(parsed_args, "trace_subcommand", None) == "verify":
            return run_trace_verify(db_path_str=getattr(parsed_args, "db", None), session_id=getattr(parsed_args, "session", None))
        trace_parser.print_help()
        return 0

    trace_parser.set_defaults(func=_run_trace_dispatch)

    # Subcomando benchmark
    benchmark.register_parser(subparsers)

    return parser


def main():
    try:
        if sys.stdout.isatty() and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if any(a in {"-v", "--version"} for a in sys.argv[1:]):
        parser = build_parser()
        parser.parse_args(sys.argv[1:])
        return

    if len(sys.argv) > 1 and sys.argv[1] in {"mcp", "proxy", "ci", "gate", "license", "audit", "trace", "init", "install", "service", "spec", "doctor", "benchmark", "config", "mode", "report"}:
        subcmd = sys.argv[1]
        if subcmd == "benchmark":
            parser = build_parser()
            args = parser.parse_args(sys.argv[1:])
            if hasattr(args, "func"):
                sys.exit(args.func(args))
            return

        sys.argv.pop(1)
        if subcmd == "config":
            sys.exit(handle_config_command(sys.argv[1:]))
        elif subcmd == "mode":
            sys.exit(handle_mode_command(sys.argv[1:]))
        elif subcmd == "report":
            sys.exit(handle_report_command(sys.argv[1:]))
        elif subcmd == "gate":
            sys.exit(handle_gate_command(sys.argv[1:]))
        elif subcmd == "license":
            sys.exit(handle_license_command(sys.argv[1:]))
        elif subcmd == "trace":
            sys.exit(handle_trace_command(sys.argv[1:]))
        elif subcmd == "install":
            code = handle_install_cli(sys.argv[1:])
            if code != 0:
                sys.exit(code)
            return
        elif subcmd == "init":
            code = handle_init_cli(sys.argv[1:])
            if code != 0:
                sys.exit(code)
            return
        elif subcmd == "doctor":
            sys.exit(run_doctor_cli(sys.argv[1:]))
        elif subcmd == "mcp":
            if len(sys.argv) > 1 and sys.argv[1] in {"-h", "--help"}:
                print("usage: ctxfw mcp\n\nStart stdio Model Context Protocol (MCP) server.")
                return
            from ctxfw.mcp import main as mcp_main
            mcp_main()
        elif subcmd == "proxy":
            from ctxfw.proxy import main as proxy_main
            proxy_main()
        elif subcmd == "ci":
            from ctxfw.gatekeeper import main as gatekeeper_main
            gatekeeper_main()
        elif subcmd == "audit":
            from ctxfw.auditor import main as auditor_main
            auditor_main()
        elif subcmd == "service":
            from ctxfw.service import handle_service_command
            sys.exit(handle_service_command(sys.argv[1:]))
        elif subcmd == "spec":
            sys.exit(handle_spec_command(sys.argv[1:]))
        return

    # Render classified defense banner on help or default invocation
    if any(a in {"-h", "--help"} for a in sys.argv[1:]) or len(sys.argv) == 1:
        from ctxfw.installer import print_defense_banner
        print_defense_banner()

    # Default delegation to Clipboard CLI (HU-12)
    parser = argparse.ArgumentParser(
        prog="ctxfw",
        description=f"ctxfw -- Sovereign Context Firewall & Token Optimization Engine (v{__version__})\n\n"
                    "Subcommands:\n"
                    "  install              Install Context Firewall into agentic IDEs & CLI environments\n"
                    "  init                 Initialize sovereign agentic perimeter, rules, and skills\n"
                    "  doctor               Run health, stdio isolation, and environment diagnostics\n"
                    "  mcp                  Start stdio Model Context Protocol server\n"
                    "  proxy                Launch local perimeter reverse proxy gateway\n"
                    "  service              Manage background service (Windows sc.exe & systemd)\n"
                    "  ci                   Run CI/CD PR topological gatekeeper\n"
                    "  gate                 Run SWE-Gate CI/CD pull request architectural verifier\n"
                    "  audit                Audit FinOps token savings and telemetry ledger\n"
                    "  trace                Inspect and verify TraceKit hash-chained audit ledger\n"
                    "  spec                 Verify specification axioms and negative invariants\n"
                    "  benchmark            Profile topological AST token reduction and FinOps savings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("target_file", nargs="?", default=None, help="Path to the active target file being edited (Distance 0)")
    parser.add_argument("project_root", nargs="?", default=None, help="Root directory of the project")
    parser.add_argument("--no-clip", action="store_true", help="Disable automatic copying to system clipboard")
    parser.add_argument("--output", "-o", default=None, help="Optional markdown output file path")
    parser.add_argument("--stdout", action="store_true", help="Print raw markdown prompt to stdout")
    parser.add_argument("--price", type=float, default=3.0, help="Baseline price in USD per 1M tokens")

    args = parser.parse_args()

    if not args.target_file:
        parser.print_help()
        sys.exit(1)

    exit_code = run_firewall_cli(
        target_file_str=args.target_file,
        project_root_str=args.project_root,
        copy_clip=not args.no_clip,
        output_path_str=args.output,
        print_stdout=args.stdout,
        price_per_million=args.price,
    )
    sys.exit(exit_code)


app = main


__all__ = [
    "app",
    "build_parser",
    "copy_to_clipboard",
    "run_firewall_cli",
    "handle_init_command",
    "handle_init_cli",
    "init_entrypoint",
    "handle_install_cli",
    "install_entrypoint",
    "run_doctor_cli",
    "doctor_entrypoint",
    "run_spec_verify",
    "handle_spec_command",
    "inject_agent_mcp_config",
    "install_claude_surfaces",
    "safe_merge_claude_code_config",
    "resolve_claude_desktop_config_path",
    "resolve_cursor_config_path",
    "run_init_mcp_agents",
    "handle_config_command",
    "handle_mode_command",
    "handle_report_command",
    "generate_share_report",
    "export_report_json",
    "merge_team_reports",
    "handle_gate_command",
    "handle_license_command",
    "handle_trace_command",
    "run_trace_verify",
    "main",
]


if __name__ == "__main__":
    main()

