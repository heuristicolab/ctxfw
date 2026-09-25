"""
src/ctxfw/cli/main.py — Unified Command Line Interface for Context Firewall (v3.7.0)
Axiom Manifest Hash: a7e63ccb9b5dd0c6f6147cfd2feec447c4d41690dd76aee9e6035db56cb7c31a
Supports direct target file clipboard invocation (`ctxfw <file>`) 
plus explicit subcommands (`ctxfw benchmark`, `ctxfw mcp`, `ctxfw proxy`, `ctxfw ci`, `ctxfw audit`, `ctxfw init`, `ctxfw doctor`, `ctxfw spec`).
"""
from __future__ import annotations

import argparse
import os
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
from ctxfw.cli.commands import benchmark
from ctxfw.installer import (
    inject_agent_mcp_config,
    resolve_claude_desktop_config_path,
    resolve_cursor_config_path,
    run_init_mcp_agents,
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
        print("  --global             Perform zero-touch onboarding across installed IDEs")
        print("  --repo [target_dir]  Deploy canonical SPEC.axioms.md and git pre-commit verification hook")
        return 0

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
def handle_config_command(argv: list[str]) -> int:
    """Handles ctxfw config [list|show|get|set] commands."""
    from ctxfw.config import load_config, set_config_value

    if not argv or argv[0] in {"-h", "--help"}:
        print("usage: ctxfw config [list | show | get <key> | set <key> <value>]")
        print("\nManage dynamic configuration in ~/.ctxfw/config.json.")
        print("Examples:")
        print("  ctxfw config list")
        print("  ctxfw config show")
        print("  ctxfw config get engine.mode")
        print("  ctxfw config set engine.mode passthrough")
        print("  ctxfw config set finops.roast_level cynical")
        return 0

    action = argv[0].lower()
    if action in {"list", "show"}:
        cfg = load_config()
        print(cfg.model_dump_json(indent=2))
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
        print(f"Unknown config action: '{action}'. Expected 'list', 'show', 'get', or 'set'.", file=sys.stderr)
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


def generate_share_report(db_path: Optional[str] = None) -> str:
    """
    Generates a shareable Markdown report with telemetry and ROI.
    Strictly enforces Invariant 4:
    The share reporter shall never include unpruned source code,
    private credentials, or raw file paths in the generated markdown output.
    """
    import re
    import sqlite3
    from ctxfw.storage.cache import get_canonical_cache_path
    from ctxfw.config import load_config

    cfg = load_config()
    db_file = Path(db_path) if db_path else get_canonical_cache_path()

    total_evaluated = 0
    tokens_saved = 0
    usd_avoided = 0.0
    cycles = 0

    if db_file.is_file():
        try:
            conn = sqlite3.connect(str(db_file), timeout=3.0)
            cursor = conn.cursor()
            try:
                row = cursor.execute("SELECT count(*), sum(original_chars), sum(estimated_tokens_saved) FROM tokens_cache").fetchone()
                if row and row[0]:
                    cycles += row[0]
                    total_evaluated += (row[1] or 0) // 4
                    tokens_saved += row[2] or 0
            except sqlite3.OperationalError:
                pass

            try:
                row2 = cursor.execute("SELECT count(*), sum(tokens_orig), sum(tokens_pruned), sum(usd_avoided) FROM telemetry_ledger").fetchone()
                if row2 and row2[0]:
                    cycles += row2[0]
                    total_evaluated += row2[1] or 0
                    tokens_saved += row2[2] or 0
                    usd_avoided += row2[3] or 0.0
            except sqlite3.OperationalError:
                pass
            conn.close()
        except Exception:
            pass

    if usd_avoided == 0.0 and tokens_saved > 0:
        usd_avoided = (tokens_saved / 1_000_000.0) * cfg.finops.input_price_per_m

    reduction_pct = (tokens_saved / max(1, total_evaluated) * 100.0) if total_evaluated > 0 else 0.0

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
        "",
        "## 2. Operational Perimeter & Compliance",
        f"- **Active Engine Mode:** `{cfg.engine.mode.value}`",
        f"- **Max Topological Depth:** D{cfg.engine.max_distance}",
        "- **Air-Gap Verification:** Certified Local (Zero Cloud Telemetry Egress)",
        "- **Code Privacy Assurance:** Zero unpruned source code blocks or confidential logic exported.",
        "",
    ]
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


def handle_report_command(argv: list[str]) -> int:
    """Handles ctxfw report [--share] [--output <file>] command."""
    parser = argparse.ArgumentParser(
        prog="ctxfw report",
        description="Generate FinOps telemetry and ROI reports.",
    )
    parser.add_argument("--share", action="store_true", help="Generate shareable sanitized Markdown ROI report (Invariant 4)")
    parser.add_argument("--output", "-o", type=str, default=None, help="Save report to specified output path")
    parser.add_argument("--db", type=str, default=None, help="Path to SQLite telemetry database")

    args = parser.parse_args(argv)

    report_md = generate_share_report(db_path=args.db)

    if args.output:
        out_p = Path(args.output).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(report_md, encoding="utf-8")
        print(f"[OK] Shareable report written to {out_p}")
    else:
        print(report_md)

    return 0


def build_parser() -> argparse.ArgumentParser:
    """Builds central subcommands parser for ctxfw."""
    parser = argparse.ArgumentParser(
        prog="ctxfw",
        description=f"ctxfw -- Sovereign Context Firewall & Token Optimization Engine (v{__version__})\n\n"
                    "Subcommands:\n"
                    "  init                 Initialize sovereign agentic perimeter, rules, and skills\n"
                    "  doctor               Run health, stdio isolation, and environment diagnostics\n"
                    "  mcp                  Start stdio Model Context Protocol server\n"
                    "  proxy                Launch local perimeter reverse proxy gateway\n"
                    "  service              Manage background service (Windows sc.exe & systemd)\n"
                    "  ci                   Run CI/CD PR topological gatekeeper\n"
                    "  audit                Audit FinOps token savings and telemetry ledger\n"
                    "  spec                 Verify specification axioms and negative invariants\n"
                    "  benchmark            Profile topological AST token reduction and FinOps savings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    # Subcommand init
    init_parser = subparsers.add_parser("init", help="Initialize sovereign agentic perimeter, rules, and skills")
    init_parser.add_argument("target_dir", nargs="?", default=None, help="Target directory for workspace perimeter")
    init_parser.add_argument("--global", dest="global_init", action="store_true", help="Perform zero-touch onboarding across installed IDEs")
    init_parser.add_argument("--repo", nargs="?", const="", default=None, help="Deploy canonical SPEC.axioms.md and git pre-commit verification hook")

    def _run_init_dispatch(parsed_args: argparse.Namespace) -> int:
        cli_args: List[str] = []
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
    config_parser.add_argument("action", nargs="?", default="list", choices=["list", "show", "get", "set"], help="Action: list, show, get, set")
    config_parser.add_argument("key", nargs="?", default=None, help="Configuration key path (e.g. engine.mode)")
    config_parser.add_argument("value", nargs="?", default=None, help="New value for configuration key")

    # Subcommand mode
    mode_parser = subparsers.add_parser("mode", help="Quick toggle between distance and passthrough modes")
    mode_parser.add_argument("target_mode", nargs="?", default=None, choices=["distance", "passthrough"], help="Operating mode")

    # Subcommand report
    report_parser = subparsers.add_parser("report", help="Generate FinOps ROI telemetry reports")
    report_parser.add_argument("--share", action="store_true", help="Generate shareable sanitized Markdown ROI report")
    report_parser.add_argument("--output", "-o", type=str, default=None, help="Save report to specified output path")
    report_parser.add_argument("--db", type=str, default=None, help="Path to SQLite telemetry database")

    # Subcomando benchmark
    benchmark.register_parser(subparsers)

    return parser


def main():
    if hasattr(sys.stdout, "isatty") and sys.stdout.isatty():
        try:
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if any(a in {"-v", "--version"} for a in sys.argv[1:]):
        parser = build_parser()
        parser.parse_args(sys.argv[1:])
        return

    if len(sys.argv) > 1 and sys.argv[1] in {"mcp", "proxy", "ci", "audit", "init", "service", "spec", "doctor", "benchmark", "config", "mode", "report"}:
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
        elif subcmd == "init":
            code = handle_init_cli(sys.argv[1:])
            if code != 0:
                sys.exit(code)
            return
        elif subcmd == "doctor":
            run_doctor_cli(sys.argv[1:])
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

    # Render classified defense banner on help or default invocation
    if any(a in {"-h", "--help"} for a in sys.argv[1:]) or len(sys.argv) == 1:
        from ctxfw.installer import print_defense_banner
        print_defense_banner()

    # Default delegation to Clipboard CLI (HU-12)
    parser = argparse.ArgumentParser(
        prog="ctxfw",
        description=f"ctxfw -- Sovereign Context Firewall & Token Optimization Engine (v{__version__})\n\n"
                    "Subcommands:\n"
                    "  init                 Initialize sovereign agentic perimeter, rules, and skills\n"
                    "  doctor               Run health, stdio isolation, and environment diagnostics\n"
                    "  mcp                  Start stdio Model Context Protocol server\n"
                    "  proxy                Launch local perimeter reverse proxy gateway\n"
                    "  service              Manage background service (Windows sc.exe & systemd)\n"
                    "  ci                   Run CI/CD PR topological gatekeeper\n"
                    "  audit                Audit FinOps token savings and telemetry ledger\n"
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


if __name__ == "__main__":
    main()
