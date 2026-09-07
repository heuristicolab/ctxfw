"""
ci_gatekeeper.py — CI/CD Context Firewall Gatekeeper & PR Impact Analyzer (v3.3.0)
Analyzes Git changesets, establishes topological dependency perimeters (D0/D1/D2+),
and generates GitHub Actions Job Summaries with FinOps token accounting.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
from typing import Dict, List, Optional, Set, Tuple

from contracts import (
    DeterministicContextPruner,
    OptimizationRequestDTO,
    PruningDepth,
)
from topological_resolver import ProjectDependencyGraph


PRE_COMMIT_CONFIG_TEMPLATE = """# .pre-commit-config.yaml — Context Firewall CI Gatekeeper
repos:
  - repo: local
    hooks:
      - id: context-firewall-gatekeeper
        name: Context Firewall Gatekeeper
        entry: python ci_gatekeeper.py
        language: system
        files: \\.py$
        pass_filenames: false
"""


class CIGatekeeper:
    """CI/CD Perimeter Gatekeeper classifying changeset dependencies."""

    def __init__(self, project_root: Optional[Path | str] = None):
        self.project_root = Path(project_root or Path.cwd()).resolve()
        self.graph = ProjectDependencyGraph(self.project_root)

    def detect_changed_files(
        self,
        base: Optional[str] = None,
        head: Optional[str] = None,
        explicit_files: Optional[List[str]] = None,
    ) -> List[Path]:
        """Detects changed Python source files via Git diff or explicit list."""
        if explicit_files:
            found = []
            for f_str in explicit_files:
                p = Path(f_str)
                full_p = (self.project_root / p).resolve() if not p.is_absolute() else p.resolve()
                if full_p.is_file() and full_p.suffix == ".py":
                    found.append(full_p)
            return found

        cmd: List[str] = ["git", "diff", "--name-only"]
        if base and head:
            cmd.extend([base, head])
        elif base:
            cmd.append(base)
        else:
            cmd.append("HEAD")

        try:
            res = subprocess.run(
                cmd,
                cwd=str(self.project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            raw_files = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        except Exception:
            raw_files = []

        # Fallback to cached diff or porcelain status if working tree diff is empty
        if not raw_files and not (base or head):
            try:
                res_cached = subprocess.run(
                    ["git", "diff", "--cached", "--name-only"],
                    cwd=str(self.project_root),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )
                raw_files = [line.strip() for line in res_cached.stdout.splitlines() if line.strip()]
            except Exception:
                pass

        valid_changed: List[Path] = []
        for rf in raw_files:
            full_path = (self.project_root / rf).resolve()
            if full_path.is_file() and full_path.suffix == ".py":
                valid_changed.append(full_path)

        return sorted(valid_changed)

    def classify_perimeter(
        self,
        changed_files: List[Path],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Classifies all modules within the reach of changed files:
        - D0: Changed module (Full)
        - D1: Direct import (Interface)
        - D2+: Transitive import (Nominal)
        """
        if not changed_files:
            return {}

        rel_changed = [
            f.resolve().relative_to(self.project_root).as_posix()
            for f in changed_files
        ]

        # Calculate minimum distance to any changed file
        perimeter_distances: Dict[str, int] = {}
        for target in rel_changed:
            target_distances = self.graph.get_distances(target)
            for mod, dist in target_distances.items():
                if mod not in perimeter_distances or dist < perimeter_distances[mod]:
                    perimeter_distances[mod] = dist

        # Analyze each perimeter module
        results: Dict[str, Dict[str, Any]] = {}
        for mod, dist in sorted(perimeter_distances.items(), key=lambda x: (x[1], x[0])):
            mod_path = self.project_root / mod
            if not mod_path.is_file():
                continue

            code = mod_path.read_text(encoding="utf-8")
            orig_chars = len(code)
            orig_tokens = DeterministicContextPruner.estimate_tokens(orig_chars)

            if dist == 0:
                depth = PruningDepth.FULL
                pruned_code = code
                pruned_chars = orig_chars
                pruned_tokens = orig_tokens
                tokens_saved = 0
                pct = 0.0
            else:
                depth = PruningDepth.INTERFACE if dist == 1 else PruningDepth.NOMINAL
                req = OptimizationRequestDTO(
                    source_code=code,
                    language="python",
                    strip_docs=False,
                    depth=depth,
                    sanitize_raises=True,
                )
                try:
                    pruned_code, _, pruned_chars, tokens_saved, pct, _ = DeterministicContextPruner.prune(req)
                    pruned_tokens = DeterministicContextPruner.estimate_tokens(pruned_chars)
                except Exception:
                    # Fail-open
                    pruned_code = code
                    pruned_chars = orig_chars
                    pruned_tokens = orig_tokens
                    tokens_saved = 0
                    pct = 0.0

            results[mod] = {
                "distance": dist,
                "depth": depth.value.upper(),
                "original_tokens": orig_tokens,
                "pruned_tokens": pruned_tokens,
                "tokens_saved": tokens_saved,
                "pct_reduction": pct,
            }

        return results

    def generate_markdown_summary(
        self,
        classified: Dict[str, Dict[str, Any]],
        price_per_million_tokens: float = 3.0,
    ) -> str:
        """Renders GitHub Actions Job Summary markdown report."""
        if not classified:
            return (
                "# Context Firewall — PR Dependency & FinOps Impact Summary\n\n"
                "> [!NOTE]\n"
                "> No Python source files were detected in this changeset. Topological perimeter analysis bypassed.\n"
            )

        total_d0 = sum(1 for m in classified.values() if m["distance"] == 0)
        total_d1 = sum(1 for m in classified.values() if m["distance"] == 1)
        total_d2 = sum(1 for m in classified.values() if m["distance"] >= 2)

        total_orig_tokens = sum(m["original_tokens"] for m in classified.values())
        total_pruned_tokens = sum(m["pruned_tokens"] for m in classified.values())
        total_tokens_saved = sum(m["tokens_saved"] for m in classified.values())
        aggregate_pct = (
            round((total_tokens_saved / total_orig_tokens) * 100, 1)
            if total_orig_tokens > 0 else 0.0
        )
        cost_avoidance_usd = (total_tokens_saved / 1_000_000) * price_per_million_tokens

        lines = [
            "# Context Firewall — PR Dependency & FinOps Impact Summary",
            "",
            "### Topological Perimeter Analysis",
            "| Module | Distance | Applied Depth | Original Tokens | Pruned Tokens | Tokens Saved | % Reduction |",
            "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
        ]

        for mod, data in classified.items():
            dist_label = f"D{data['distance']}"
            lines.append(
                f"| `{mod}` | {dist_label} | {data['depth']} | {data['original_tokens']:,} | "
                f"{data['pruned_tokens']:,} | {data['tokens_saved']:,} | {data['pct_reduction']:.1f}% |"
            )

        lines.extend([
            "",
            "### FinOps Impact & Token Economics",
            f"- **Changed Target Files (D0)**: {total_d0}",
            f"- **Direct Boundary Dependencies (D1)**: {total_d1}",
            f"- **Transitive Dependencies (D2+)**: {total_d2}",
            f"- **Total Evaluated Context Tokens**: {total_orig_tokens:,}",
            f"- **Net Context Tokens Saved**: {total_tokens_saved:,} ({aggregate_pct:.1f}% net reduction)",
            f"- **Projected Cost Avoidance**: ${cost_avoidance_usd:.4f} USD (@ ${price_per_million_tokens:.2f}/1M tokens)",
            "",
            "### Pre-Commit Hook Configuration",
            "```yaml",
            PRE_COMMIT_CONFIG_TEMPLATE.strip(),
            "```",
            "",
        ])

        return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Context Firewall CI Gatekeeper (v3.3.0)")
    parser.add_argument("--base", type=str, default=None, help="Base git commit / branch")
    parser.add_argument("--head", type=str, default=None, help="Head git commit / branch")
    parser.add_argument("--files", nargs="*", default=None, help="Explicit list of files to inspect")
    parser.add_argument("--project-root", type=str, default=None, help="Root directory of the project")
    parser.add_argument("--output", type=str, default=None, help="Output path for markdown summary")
    parser.add_argument("--generate-pre-commit", type=str, default=None, help="Output path for .pre-commit-config.yaml")
    args = parser.parse_args()

    gatekeeper = CIGatekeeper(project_root=args.project_root)
    changed_files = gatekeeper.detect_changed_files(
        base=args.base,
        head=args.head,
        explicit_files=args.files,
    )

    classified = gatekeeper.classify_perimeter(changed_files)
    summary_md = gatekeeper.generate_markdown_summary(classified)

    if args.output:
        out_path = Path(args.output).resolve()
        out_path.write_text(summary_md, encoding="utf-8")
        sys.stderr.write(f"[ci_gatekeeper] Summary written to {out_path}\n")

    if args.generate_pre_commit:
        pc_path = Path(args.generate_pre_commit).resolve()
        pc_path.write_text(PRE_COMMIT_CONFIG_TEMPLATE, encoding="utf-8")
        sys.stderr.write(f"[ci_gatekeeper] Pre-commit configuration generated at {pc_path}\n")

    # Output summary to stdout for GitHub Actions step summary ($GITHUB_STEP_SUMMARY)
    sys.stdout.write(summary_md + "\n")


if __name__ == "__main__":
    main()
