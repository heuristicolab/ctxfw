"""
firewall_cli.py — Clipboard Ergonomics & Direct Terminal Execution (HU-12, v3.3.0)
Resolves topological dependency perimeters, compacts peripheral code,
renders immediate terminal telemetry, and deposits the resulting prompt directly into the OS clipboard.
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

from contracts import DeterministicContextPruner, PruningDepth
from topological_resolver import ContextFirewallEngine, TopologicalContextBundleDTO


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
    sys.stdout.write("  CONTEXT FIREWALL -- SOVEREIGN CLIPBOARD & TOKEN OPTIMIZER (v3.3.0)\n")
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

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Context Firewall CLI — Instant Clipboard & Prompt Compaction (v3.3.0)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("target_file", help="Path to the active target file being edited (Distance 0)")
    parser.add_argument("project_root", nargs="?", default=None, help="Root directory of the project (defaults to target file parent)")
    parser.add_argument("--no-clip", action="store_true", help="Disable automatic copying to system clipboard")
    parser.add_argument("--output", "-o", default=None, help="Optional file path to write the generated markdown context prompt")
    parser.add_argument("--stdout", action="store_true", help="Print the raw markdown prompt directly to stdout")
    parser.add_argument("--price", type=float, default=3.0, help="Baseline price in USD per 1M tokens (default: 3.00)")

    args = parser.parse_args()

    exit_code = run_firewall_cli(
        target_file_str=args.target_file,
        project_root_str=args.project_root,
        copy_clip=not args.no_clip,
        output_path_str=args.output,
        print_stdout=args.stdout,
        price_per_million=args.price,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
