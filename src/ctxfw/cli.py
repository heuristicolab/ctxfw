"""
src/ctxfw/cli.py — Unified Command Line Interface for Context Firewall (v3.5.0)
Axiom Manifest Hash: 575d12d75bcb427be48c3d62c643a4fb4a0260768cb49197c5d09133058581ed
Supports direct target file clipboard invocation (`ctxfw <file>`) 
plus explicit subcommands (`ctxfw mcp`, `ctxfw proxy`, `ctxfw ci`, `ctxfw audit`, `ctxfw init`, `ctxfw doctor`, `ctxfw spec`).
"""
from __future__ import annotations

import argparse
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
from typing import Optional

from ctxfw.core.contracts import PruningDepth
from ctxfw.core.pruner import DeterministicContextPruner
from ctxfw.core.topological import ContextFirewallEngine, TopologicalContextBundleDTO


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

    # Terminal Dashboard Output
    sys.stdout.write("========================================================================\n")
    sys.stdout.write("  CONTEXT FIREWALL -- SOVEREIGN CLIPBOARD & TOKEN OPTIMIZER (v3.4.0)\n")
    sys.stdout.write("========================================================================\n")
    sys.stdout.write(f"Target Module:  {bundle.root_target}\n")
    sys.stdout.write(f"Project Root:   {project_root}\n\n")

    sys.stdout.write(f"{'DIST':<6} | {'MODULE':<32} | {'DEPTH':<10} | {'ORIG TOK':<9} | {'PRUNED':<8} | {'SAVINGS':<8}\n")
    sys.stdout.write("-" * 84 + "\n")

    for dist_lbl, mod, dep, o_tok, p_tok, pct in rows:
        mod_trunc = mod if len(mod) <= 32 else ("..." + mod[-29:])
        sys.stdout.write(f"{dist_lbl:<6} | {mod_trunc:<32} | {dep:<10} | {o_tok:<9,d} | {p_tok:<8,d} | {pct:<8}\n")

    sys.stdout.write("-" * 84 + "\n")
    sys.stdout.write(
        f"{'TOTAL':<6} | {f'{len(rows)} Modules':<32} | {'':<10} | "
        f"{total_orig_tokens:<9,d} | {total_pruned_tokens:<8,d} | {f'{net_reduction_pct:.1f}%':<8}\n\n"
    )

    sys.stdout.write(f"[*] Net Context Tokens Saved:  {total_saved_tokens:,} tokens ({net_reduction_pct:.1f}% reduction)\n")
    sys.stdout.write(f"[*] Projected FinOps Savings:  ${usd_savings:.4f} USD (@ ${price_per_million:.2f}/1M tokens)\n")
    sys.stdout.write(f"[*] Pipeline Latency:          {elapsed_ms:.2f} ms\n")
    if copy_clip:
        status_clip = "COPIED TO SYSTEM CLIPBOARD" if clipboard_ok else "CLIPBOARD UNAVAILABLE"
        sys.stdout.write(f"[*] Clipboard Status:          {status_clip}\n")
    if output_path_str:
        sys.stdout.write(f"[*] Saved to File:             {output_path_str}\n")
    sys.stdout.write("========================================================================\n")

    # HU-02: Telemetría perimetral anónima y despacho de heartbeat
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


def handle_init_cli(argv: list[str]) -> int:
    """Handles ctxfw init subcommand with --global, --repo, and target directory options."""
    if any(arg in {"-h", "--help"} for arg in argv):
        print("usage: ctxfw init [target_dir]")
        print("\nInitialize sovereign agentic perimeter, rules, and skills in target directory.")
        print("  --global             Perform zero-touch onboarding across installed IDEs")
        print("  --repo [target_dir]  Deploy canonical SPEC.axioms.md and git pre-commit verification hook")
        return 0

    if "--global" in argv:
        from ctxfw.installer import print_defense_banner, run_global_init
        print_defense_banner()
        print("========================================================================")
        print("  CTXFW GLOBAL ZERO-TOUCH PROVISIONING // MULTI-IDE ARMORED INJECTION")
        print("========================================================================")
        res = run_global_init()
        for act in res["actions"]:
            print(f"  [PASS] {act}")
        print("========================================================================")
        return 0

    if "--repo" in argv:
        from ctxfw.installer import print_defense_banner, init_repository_perimeter
        print_defense_banner()
        print("========================================================================")
        print("  CTXFW REPOSITORY ARMOR // CANONICAL AXIOMS & PRE-COMMIT SENTRY")
        print("========================================================================")
        repo_args = [a for a in argv if a != "--repo" and not a.startswith("-")]
        target = Path(repo_args[0]).resolve() if repo_args else Path.cwd()
        handle_init_command(target)
        res = init_repository_perimeter(target)
        for msg in res["messages"]:
            print(f"  [ATTESTED] {msg}")
        print("========================================================================")
        return 0

    plain_args = [a for a in argv if not a.startswith("-")]
    target = Path(plain_args[0]).resolve() if plain_args else Path.cwd()
    handle_init_command(target)
    return 0


def run_doctor_cli() -> int:
    """Runs system health and isolation diagnostics."""
    from ctxfw.installer import render_doctor_report, run_doctor
    report = run_doctor()
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

    result = evaluate_specification(content)

    sys.stdout.write("========================================================================\n")
    sys.stdout.write("  CTXFW SPECIFICATION SIEVE -- AXIOMATIC DETERMINISM VERIFIER\n")
    sys.stdout.write("========================================================================\n")
    sys.stdout.write(f"Evaluated File:             {path}\n")
    sys.stdout.write(f"ACI Score:                  {result.aci_score:.4f}\n")
    sys.stdout.write(f"Negative Invariants Count:  {result.negative_invariants_count}\n")
    sys.stdout.write("Extracted Clauses:\n")
    if result.extracted_never_clauses:
        for idx, clause in enumerate(result.extracted_never_clauses, start=1):
            sys.stdout.write(f"  {idx}. {clause}\n")
    else:
        sys.stdout.write("  (None detected)\n")

    sys.stdout.write(f"Manifest Hash (SHA-256):    {result.manifest_hash}\n")
    sys.stdout.write("-" * 72 + "\n")

    if result.status == "VERIFIED":
        sys.stdout.write("Final Verdict:              [PASS] READY FOR FORGE\n")
        sys.stdout.write("========================================================================\n")
        return 0
    else:
        sys.stdout.write("Final Verdict:              [FAIL] SPECIFICATION QUARANTINED\n")
        if result.remediation_notes:
            sys.stdout.write("Remediation Notes:\n")
            for note in result.remediation_notes:
                sys.stdout.write(f"  - {note}\n")
        sys.stdout.write("========================================================================\n")
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
        return 1


def main():
    if len(sys.argv) > 1 and sys.argv[1] in {"mcp", "proxy", "ci", "audit", "init", "service", "spec", "doctor"}:
        subcmd = sys.argv[1]
        sys.argv.pop(1)
        if subcmd == "init":
            handle_init_cli(sys.argv[1:])
            return
        elif subcmd == "doctor":
            run_doctor_cli()
            return
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

    # Default delegation to Clipboard CLI (HU-12)
    parser = argparse.ArgumentParser(
        prog="ctxfw",
        description="ctxfw — Sovereign Context Firewall & Token Optimization Engine (v3.5.0)\n\n"
                    "Subcommands:\n"
                    "  init                 Initialize sovereign agentic perimeter, rules, and skills\n"
                    "  doctor               Run health, stdio isolation, and environment diagnostics\n"
                    "  mcp                  Start stdio Model Context Protocol server\n"
                    "  proxy                Launch local perimeter reverse proxy gateway\n"
                    "  service              Manage background service (Windows sc.exe & systemd)\n"
                    "  ci                   Run CI/CD PR topological gatekeeper\n"
                    "  audit                Audit FinOps token savings and telemetry ledger\n"
                    "  spec                 Verify specification axioms and negative invariants",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
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


__all__ = [
    "copy_to_clipboard",
    "run_firewall_cli",
    "handle_init_command",
    "handle_init_cli",
    "init_entrypoint",
    "run_doctor_cli",
    "doctor_entrypoint",
    "run_spec_verify",
    "handle_spec_command",
    "main",
]


if __name__ == "__main__":
    main()

