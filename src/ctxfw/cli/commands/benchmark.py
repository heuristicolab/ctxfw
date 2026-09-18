"""
src/ctxfw/cli/commands/benchmark.py — Native Empirical Benchmark & FinOps Profiler Subcommand
Axiom Manifest Hash: a403b7072c7ea6b37a804db8feec61058e552d2bb3240390098f9c747867d924
"""
import argparse
import json
import sys
import time
from pathlib import Path
from typing import List

from ctxfw.core.pruner import PolyglotASTPruner
from ctxfw.core.topological import TopologicalResolver

MODEL_PRICING_1M = {
    "claude-3-5-sonnet": 3.00,
    "gpt-4o": 2.50,
    "deepseek-v3": 0.27,
    "custom": 3.00,
}

def register_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "benchmark",
        help="Profile topological AST token reduction and FinOps savings."
    )
    parser.add_argument("path", help="Target root file or directory to benchmark")
    parser.add_argument(
        "--root",
        default=".",
        help="Project root directory for import resolution (default: .)"
    )
    parser.add_argument(
        "--model",
        default="claude-3-5-sonnet",
        choices=list(MODEL_PRICING_1M.keys()),
        help="LLM model pricing profile per 1M input tokens"
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=500,
        help="Simulated agent tool-call cycles (default: 500)"
    )
    parser.add_argument(
        "--format",
        default="table",
        choices=["table", "json", "markdown"],
        help="Output serialization format"
    )
    parser.set_defaults(func=run_benchmark)

def run_benchmark(args: argparse.Namespace) -> int:
    project_root = Path(args.root).resolve()
    target_path = (project_root / args.path).resolve()

    if not target_path.exists():
        print(f"[ERROR] Target path does not exist: {target_path}", file=sys.stderr)
        return 1

    if target_path.is_file():
        targets = [target_path]
    else:
        # Descubrir archivos fuente clave (excluyendo entornos y caches)
        ignored = {".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist"}
        targets = [
            p for p in target_path.rglob("*")
            if p.is_file() and p.suffix in {".py", ".ts", ".js"}
            and not any(part in ignored for part in p.parts)
        ]

    resolver = TopologicalResolver(root_dir=project_root)
    pruner = PolyglotASTPruner()
    
    start_time = time.perf_counter()
    results = []
    total_raw, total_pruned = 0, 0

    for file_path in targets:
        manifest = resolver.resolve(file_path)
        raw_tokens = manifest.total_tokens
        pruned_tokens = 0

        for dep in manifest.dependencies:
            if dep.depth_level == 0:
                pruned_tokens += dep.token_count
            else:
                try:
                    code = dep.file_path.read_text(encoding="utf-8", errors="replace")
                    res = pruner.prune_by_depth(code, dep.file_path.suffix, dep.depth_level)
                    pruned_tokens += res.pruned_tokens
                except Exception:
                    pruned_tokens += dep.token_count

        savings = ((raw_tokens - pruned_tokens) / raw_tokens * 100) if raw_tokens else 0.0
        total_raw += raw_tokens
        total_pruned += pruned_tokens

        rel_display = str(file_path.relative_to(project_root)).replace("\\", "/")
        results.append({
            "module": rel_display,
            "depth": "D0" if file_path == target_path else "D1",
            "raw_tokens": raw_tokens,
            "pruned_tokens": pruned_tokens,
            "density": f"{raw_tokens / pruned_tokens:.2f}x" if pruned_tokens else "1.00x",
            "savings_pct": round(savings, 1)
        })

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    net_savings_pct = ((total_raw - total_pruned) / total_raw * 100) if total_raw else 0.0
    cost_per_1m = MODEL_PRICING_1M.get(args.model, 3.00)
    tokens_saved = total_raw - total_pruned
    total_usd_saved = (tokens_saved * args.cycles / 1_000_000) * cost_per_1m

    payload = {
        "metadata": {
            "project_root": str(project_root),
            "target": str(args.path),
            "model": args.model,
            "pricing_per_1m": cost_per_1m,
            "cycles": args.cycles,
            "latency_ms": round(elapsed_ms, 2)
        },
        "metrics": {
            "total_raw": total_raw,
            "total_pruned": total_pruned,
            "net_savings_pct": round(net_savings_pct, 1),
            "tokens_saved_per_cycle": tokens_saved,
            "projected_savings_usd": round(total_usd_saved, 2)
        },
        "breakdown": results
    }

    if args.format == "json":
        print(json.dumps(payload, indent=2))
        return 0

    if args.format == "markdown":
        _render_markdown(payload)
        return 0

    _render_table(payload)
    return 0

def _render_table(p: dict) -> None:
    print("=" * 80)
    print("  CTXFW EMPIRICAL BENCHMARK // TOPOLOGICAL AST ATTENTION PROFILER")
    print("=" * 80)
    print(f"Target Root:      {p['metadata']['target']}")
    print(f"Pricing Model:    {p['metadata']['model']} (${p['metadata']['pricing_per_1m']:.2f} / 1M input tokens)")
    print(f"Simulation Base:  {p['metadata']['cycles']} agentic tool-call cycles")
    print("-" * 80)
    print(f"{'MODULE / ROUTE':<35} | {'DEPTH':<5} | {'RAW TOK':<9} | {'PRUNED':<9} | {'SAVINGS':<8}")
    print("-" * 80)
    for r in p["breakdown"]:
        print(f"{r['module']:<35} | {r['depth']:<5} | {r['raw_tokens']:<9} | {r['pruned_tokens']:<9} | -{r['savings_pct']}%")
    print("-" * 80)
    m = p["metrics"]
    print(f"{'AGGREGATE PIPELINE':<35} | {'TOTAL':<5} | {m['total_raw']:<9} | {m['total_pruned']:<9} | -{m['net_savings_pct']}%")
    print("=" * 80)
    print(f"[+] Context Pruned per Cycle:   {m['tokens_saved_per_cycle']:,} tokens")
    print(f"[+] Projected FinOps Savings:   ${m['projected_savings_usd']:.2f} USD / {p['metadata']['cycles']} cycles")
    print(f"[+] Profiler Latency:           {p['metadata']['latency_ms']} ms")
    print("-" * 80)
    print("Audit generated via ctxfw v3.5.4 (Compiled Tree-Sitter AST Engine)")
    print("Enterprise Token Proxies & Custom LLM FinOps Audits: contacto@heuristicolab.com")
    print("Repo: https://github.com/heuristicolab/ctxfw")
    print("=" * 80)

def _render_markdown(p: dict) -> None:
    print("| Target Module | Raw Tokens | Pruned Tokens | Reduction |")
    print("| :--- | :--- | :--- | :--- |")
    for r in p["breakdown"]:
        print(f"| `{r['module']}` | {r['raw_tokens']:,} | {r['pruned_tokens']:,} | **-{r['savings_pct']}%** |")
    m = p["metrics"]
    print(f"| **Aggregate Total** | **{m['total_raw']:,}** | **{m['total_pruned']:,}** | **-{m['net_savings_pct']}%** |")
    print("\n> **Audit generated via `ctxfw`** (Tree-Sitter AST Context Engine).  ")
    print("> Enforce centralized token firewalls and enterprise proxies: [Heurístico LAB](https://github.com/heuristicolab/ctxfw) | `contacto@heuristicolab.com`")
