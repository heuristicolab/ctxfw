"""
src/ctxfw/roast.py — FinOps Roast Engine with TTY Detection (v3.7.0)
manifest_hash: 2a63e65e200442944f6f0c4d804a965681f4c919a9d306c26484b7903308dca1

Generates cynical FinOps roast humor or sober analytical commentary on token savings.
Strictly enforces Invariant 1:
The roast engine shall never emit ANSI color codes or cynical humor text when stdout
is not an interactive terminal (sys.stdout.isatty() is False).
"""
from __future__ import annotations

import random
import sys
from typing import Any, Optional

from ctxfw.config import FinOpsConfigDTO, RoastLevel, load_config

# ANSI Escape Sequences
CLR_RESET = "\033[0m"
CLR_BOLD = "\033[1m"
CLR_CYAN = "\033[36m"
CLR_AMBER = "\033[33m"
CLR_RED = "\033[31m"
CLR_GREEN = "\033[32m"
CLR_DIM = "\033[2m"

# Catalog of Cynical Roast Phrases (12 items, satisfying 9 <= roast_pool_size <= 99)
ROAST_CATALOG: list[str] = [
    "Your frontier LLM was ready to bill you for 50,000 tokens of boilerplate getters. ctxfw just saved your monthly cloud budget from incineration.",
    "Sending raw dependency graphs to an AI is like hiring a senior architect just to read your node_modules aloud. You're welcome.",
    "Without AST pruning, you'd be subsidizing the GPU clusters of Silicon Valley with every keystroke.",
    "That was close. You were about to pay $0.45 just for an LLM to hallucinate on a comment you wrote three months ago.",
    "Token arson averted. The Context Firewall sliced the bloat before your wallet noticed the smoke.",
    "Congratulations: You just avoided paying enterprise token prices to transmit redundant whitespace and dead interfaces.",
    "Your API token quota survived another round of junior developer copy-paste frenzy thanks to deterministic AST pruning.",
    "Feeding uncompressed modules to frontier models is the new running water with the faucet wide open. We turned the valve.",
    "Topological resolution pruned the transitive chaff. Even your AI agent is sighing with relief at the reduced context drift.",
    "Zero network egress, sub-5ms lookup, and zero dollars wasted on AI hallucinations. Sleep well, FinOps.",
    "You just rescued hundreds of prompt tokens from dying a meaningless death in an attention matrix.",
    "If your code had any more bloated dependencies, we'd have to classify it as an environmental hazard. Good thing we stubbed it.",
]


def is_interactive_terminal() -> bool:
    """Evaluates whether current standard output stream is a verified interactive TTY."""
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def generate_finops_roast(
    tokens_saved: int = 0,
    usd_avoided: float = 0.0,
    config: Optional[FinOpsConfigDTO] = None,
) -> str:
    """
    Generates a terminal-formatted FinOps diagnosis.
    Enforces Invariant 1: Returns empty string ("") immediately if stdout is not
    an interactive terminal (e.g., pipes, redirected files, subagents, or CI/CD runner).
    """
    # Invariant 1: Non-interactive streams (pipes, CI/CD, subagents) receive strictly clean stdout
    if not is_interactive_terminal():
        return ""

    if config is None:
        try:
            config = load_config().finops
        except Exception:
            config = FinOpsConfigDTO()

    # Honor user configuration toggles
    if not config.roast or config.roast_level == RoastLevel.OFF:
        return ""

    if config.roast_level == RoastLevel.SOBER:
        return (
            f"\n[FinOps Summary] Processed with Context Firewall: "
            f"{tokens_saved:,} tokens pruned (${usd_avoided:.6f} USD avoided).\n"
        )

    # RoastLevel.CYNICAL: Select cynical humor with ANSI styling
    roast_quote = random.choice(ROAST_CATALOG)
    banner = [
        "",
        f"{CLR_AMBER}{CLR_BOLD}🔥 [CTXFW // FINOPS ROAST ENGINE]{CLR_RESET}",
        f"{CLR_CYAN}\"{roast_quote}\"{CLR_RESET}",
        f"{CLR_DIM}   [Tokens Pruned: {CLR_GREEN}{tokens_saved:,}{CLR_DIM} | Est. Cost Avoided: {CLR_GREEN}${usd_avoided:.6f} USD{CLR_DIM}]{CLR_RESET}",
        "",
    ]
    return "\n".join(banner)
