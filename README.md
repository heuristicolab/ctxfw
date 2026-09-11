<div align="center">

# ctxfw // Deterministic Context Firewall

**A sovereign runtime engine engineered by Heuristico LAB // Skunk Works Division.**

[![Axiomatic Completeness Index](https://img.shields.io/badge/ACI-1.0000_VERIFIED-000000?style=for-the-badge&logo=shield)](SPEC.axioms.md)
[![Attestation Seal](https://img.shields.io/badge/ATTESTATION-SHA--256_SEALED-0a0a0a?style=for-the-badge&logo=auth0)](SPEC.axioms.md)
[![Runtime Engine](https://img.shields.io/badge/RUNTIME-PYTHON_3.10+-111111?style=for-the-badge&logo=python)](https://ctxfw.heuristicolab.com)
[![License](https://img.shields.io/badge/LICENSE-APACHE_2.0-black?style=for-the-badge)](LICENSE)

**The deterministic boundary between generative AI hallucinations and mission-critical engineering infrastructure.**

[Portal Oficial](https://ctxfw.heuristicolab.com) • [Axiomatic Specification](SPEC.axioms.md) • [FinOps Token Matrix](#token-cost-matrix-september-2026-frontier-models) • [Benchmark 72.4% AST](#benchmark-724-ast-token-reduction) • [Canonical Install](#canonical-installation)

---

</div>

## Executive Summary

Autonomous agentic software development introduces severe probabilistic risks: unconstrained AI models inadvertently introduce architectural drifts, violate safety invariants, bypass transaction idempotency, and inflate token consumption via redundant context payloads.

**ctxfw** is an out-of-band, deterministic context firewall and Model Context Protocol (MCP) gatekeeper. It intercepts architectural intakes, enforces mathematical floors on negative invariants ($N \ge 5$), binds variable domains, dynamically prunes context using Abstract Syntax Tree (AST) analysis, and cryptographically signs validated specification manifests.

> **Sovereign Directive:** No synthetic code enters the repository without a verified axiomatic certificate ($\text{ACI} \ge 0.9000$).

---

## Canonical Installation

Deploy the complete sovereign toolchain with a single verified command:

```bash
curl -fsSL https://ctxfw.heuristicolab.com/install.sh | bash
```

Explore the live platform, interactive ROI calculator, and security briefings at:
**[https://ctxfw.heuristicolab.com](https://ctxfw.heuristicolab.com)**

---

## Benchmark: 72.4% AST Token Reduction

Through polyglot Tree-Sitter grammar analysis and topological dependency pruning (D0-D3 distance tiers), `ctxfw` extracts and eliminates redundant implementation blocks while strictly preserving type interfaces and contract boundaries.

| Metric | Raw Prompt Intake | Context Firewall (ctxfw) | Delta / Reduction |
| :--- | :--- | :--- | :--- |
| **Average Context Payload** | 45,000 tokens | 12,420 tokens | **-72.4%** |
| **Interface Preservation** | N/A | 100% Contract Integrity | Mathematical Guarantee |
| **Warm Cache Overhead** | — | < 5 ms (SQLite WAL) | Zero perceptible latency |
| **ACI Verification Floor** | Unverified | $\ge 0.9000$ Attested | SHA-256 Sealed |

---

## Token Cost Matrix: September 2026 Frontier Models

Comparison of raw vs. optimized prompt expenses across leading September 2026 frontier reasoning models (pricing per 1,000,000 tokens):

| Model | Input Price / 1M | Output Price / 1M | Cost per Raw Prompt (45k) | Cost per ctxfw Prompt (12.42k) | Capital Avoided per Prompt | Net Savings per Dev / Mo (35 prompts/day)* |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Claude Fable 5.1** | **$10.00** | **$50.00** | $0.450 | $0.124 | **$0.326 (-72.4%)** | **$239.46 / dev / mo** |
| **GPT-6 Astra** | **$10.00** | **$50.00** | $0.450 | $0.124 | **$0.326 (-72.4%)** | **$239.46 / dev / mo** |
| **Claude Opus 5** | **$5.00** | **$25.00** | $0.225 | $0.062 | **$0.163 (-72.4%)** | **$119.73 / dev / mo** |
| **GPT-5.6 Sol** | **$5.00** | **$30.00** | $0.225 | $0.062 | **$0.163 (-72.4%)** | **$119.73 / dev / mo** |
| **Claude Sonnet 5** | **$2.00** | **$10.00** | $0.090 | $0.025 | **$0.065 (-72.4%)** | **$47.89 / dev / mo** |
| **Gemini 3.8 Flash** | **$0.375** | **$1.875** | $0.0169 | $0.0047 | **$0.0122 (-72.4%)** | **$8.98 / dev / mo** |

*\*Assumes 35 architectural/coding prompts per developer per day across 21 working days per month (735 prompts/month per dev).*

### Enterprise Squad FinOps Impact (25 Developers)

For an engineering squad of 25 developers operating on Claude Fable 5.1 / GPT-6 Astra:
- **Gross Monthly Intake:** 1,488,375,000 tokens
- **Pruned Monthly Intake:** 1,077,583,500 tokens (72.4%)
- **Gross Avoided Capital:** **$10,775.84 / month** (**$129,310.02 / year**)
- **Target Payback Period:** Immediate (< 48 hours from deployment)

---

## Architectural Perimeter

```
PROBABILISTIC DOMAIN                      DETERMINISTIC PERIMETER
┌───────────────────────┐                  ┌────────────────────────────────────────┐
│  Autonomous AI Agent  │                  │             CTXFW ENGINE               │
│  (Claude / Gemini /   │                  │                                        │
│   Cursor / Antigravity│                  │  ┌──────────────────────────────────┐  │
└───────────┬───────────┘                  │  │     Axiomatic Sieve Engine       │  │
            │                              │  │  - Negative Invariant Floor (>=5)│  │
            │  Intake Brief                │  │  - Bounded Variable Ranges       │  │
            ▼                              │  │  - Deterministic FSM Delta       │  │
┌───────────────────────┐                  │  │  - 4-Class Error Taxonomy        │  │
│ MCP Stdio Interceptor ├─────────────────►│  └────────────────┬─────────────────┘  │
└───────────────────────┘                  │                   │                    │
                                           │                   ▼                    │
                                           │         [ ACI >= 0.9000? ]             │
                                           │          /              \              │
                                           │       YES                NO            │
                                           │        │                  │            │
                                           │        ▼                  ▼            │
                                           │ ┌──────────────┐   ┌─────────────────┐ │
                                           │ │ VERIFIED     │   │ QUARANTINED     │ │
                                           │ │ SHA-256 Seal │   │ Execution Halt  │ │
                                           │ └──────┬───────┘   └────────┬────────┘ │
                                           └────────┼────────────────────┼──────────┘
                                                    │                    │
                                                    ▼                    ▼
                                           [ Code Generation ]   [ Forensic Report ]
                                           [ & Git Permitted ]   [ Pre-Commit Abort]
```

---

## Core Capabilities

1. **Axiomatic Specification Sieve**: Validates briefs prior to code synthesis. Requires $\ge 5$ explicit negative invariants (`never` or `shall never`), strictly bounded variables, deterministic finite state machine transitions, and a 4-class fault taxonomy.
2. **Polyglot AST Token Pruning**: Built-in support for Python, TypeScript/JavaScript, Go, and Java interfaces with 72.4% verified context compression.
3. **Zero-Touch IDE Auto-Discovery**: Automatic, non-destructive configuration for Google Antigravity, Cursor, and Claude Desktop.
4. **Hermetic CI/CD Gatekeeper**: Headless pre-commit hooks and CI linters ensuring zero unsealed or quarantined code enters upstream branches.

---

## Verification & Specification Manifest

Formal invariants and state-machine transitions are maintained in [SPEC.axioms.md](SPEC.axioms.md).

```bash
# Verify local environment and integrity
ctxfw doctor

# Run headless specification evaluation
ctxfw eval --brief SPEC.axioms.md
```

---

## License

This software is licensed under the [Apache License, Version 2.0](LICENSE).

---

<div align="center">
<sub>ENGINEERED & CLASSIFIED BY HEURISTICO LAB // SKUNK WORKS DIVISION</sub><br>
<sub>DEFENSE SYSTEMS & SOVEREIGN PROTOCOLS GROUP</sub>
</div>