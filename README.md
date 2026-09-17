<div align="center">

# CTXFW // CONTEXT FIREWALL
### High-Assurance Axiomatic Gatekeeper & In-Memory AST Pruning for Coding Agents

[![PyPI - Version](https://img.shields.io/badge/PyPI-v3.5.0-blue?style=for-the-badge&logo=pypi&logoColor=white)](https://pypi.org/project/ctxfw/)
[![Axiomatic Completeness Index](https://img.shields.io/badge/ACI-1.0000_VERIFIED-000000?style=for-the-badge&logo=shield)](https://ctxfw.heuristicolab.com)
[![Tests](https://img.shields.io/badge/TESTS-102%2F102_PASSING-00C853?style=for-the-badge&logo=pytest)](https://pypi.org/project/ctxfw/)
[![License](https://img.shields.io/badge/LICENSE-APACHE_2.0-black?style=for-the-badge)](LICENSE)
[![Smithery MCP](https://img.shields.io/badge/SMITHERY_MCP-CERTIFIED-FF6B00?style=for-the-badge&logo=server)](https://smithery.ai/server/ctxfw)
[![Glama MCP](https://glama.ai/mcp/servers/heuristicolab/ctxfw/badge)](https://glama.ai/mcp/servers/heuristicolab/ctxfw)

**The deterministic boundary between probabilistic LLM hallucination and production infrastructure.**

[Installation](#installation) • [Benchmarks](#ast-pruning-benchmarks) • [Diagnostic](#system-diagnostics) • [Architecture](#architecture) • [Enterprise Governance](#enterprise-governance)

---

</div>

## Executive Abstract

Autonomous coding agents (Claude, Gemini, Cursor, Antigravity) consume massive context windows with bloated peripheral dependencies, triggering token exhaustion, context drift, and security degradation.

**CTXFW** is an open-core context firewall and Model Context Protocol (MCP) gatekeeper. It combines an **in-memory polyglot AST pruner** with a **deterministic axiomatic intake sieve**:
1. **Compacts Peripheral Code (72.4% token reduction)**: Replaces distance-1 and distance-2+ module implementations with clean interface signatures, type definitions, and functional stubs.
2. **Enforces Axiomatic Integrity (ACI $\ge$ 0.9000)**: Rejects ungrounded or deficient architecture briefs missing negative invariants ($N \ge 5$), bounded variable domains, deterministic state machines, or formal error taxonomies.
3. **Zero Telemetry Egress**: Guaranteed local execution with zero network telemetry leakage on standard operating mode.

---

## AST Pruning Benchmarks

CTXFW operates directly at the syntax tree layer using native polyglot grammars:

| Benchmark Dimension | Raw Context Ingestion | CTXFW Topological Compactor | Performance Gain / Impact |
| :--- | :--- | :--- | :--- |
| **Token Consumption** | 100% (Raw Files) | 27.6% (Interface Stubs) | **72.4% Bloat Eliminated** |
| **Engine Compaction Overhead** | — | Native in-memory parser | **< 5.0 ms** |
| **Warm Cache Hit Overhead** | — | SQLite WAL semantic cache | **< 0.8 ms** |
| **Stdio Telemetry Egress** | Unsanitized stdout | Pure isolated JSON-RPC | **Zero Egress (100% Isolated)** |
| **Axiom Verification Latency** | — | Sieve evaluation | **< 12.0 ms** |
| **CI/CD Pre-Commit Latency** | — | Headless git sentry | **< 85.0 ms** |

---

## Installation

### 1. PyPI (Official Package)
Install via `pip` or isolated environment manager:
```bash
pip install ctxfw
```
Or for global CLI availability using `pipx`:
```bash
pipx install ctxfw
```

### 2. Smithery MCP Registry
CTXFW is certified for automatic client configuration via the Smithery CLI:
```bash
npx -y @smithery/cli install ctxfw --client claude
```
Or register the stdio server manually in your `.mcp.json` or IDE config:
```json
{
  "mcpServers": {
    "ctxfw": {
      "command": "ctxfw",
      "args": ["mcp"]
    }
  }
}
```

---

## System Diagnostics

Validate local environment readiness, stdio isolation purity, SQLite WAL concurrency, and Tree-Sitter grammars with a single command:

```bash
ctxfw doctor
```

```text
========================================================================
  CTXFW DOCTOR // HIGH-ASSURANCE HEALTH & ISOLATION DIAGNOSTIC
========================================================================
[PASS]   Python Package & sys.path        ctxfw v3.5.0 loaded cleanly.
[PASS]   MCP stdio Stream Isolation       100% pure JSON-RPC on stdout. Diagnostic logs isolated to stderr.
[PASS]   Global CLI Executable (PATH)     Binary 'ctxfw' found in PATH.
[PASS]   Axiomatic Sieve Engine           Evaluation verified (ACI: 1.0000, Invariants: 5).
[PASS]   SQLite WAL Cache & Concurrency   Journal mode: WAL, Busy timeout: 5000ms.
[PASS]   Polyglot Tree-Sitter Grammars    Initialized language parsers (typescript, go, java).
------------------------------------------------------------------------
Overall Verdict:            [HEALTHY] [ATTESTED] Perimeter defense operational.
========================================================================
CTXFW // 72.4% AST Bloat Eliminated. Zero Telemetry Egress.
Need team-wide budget circuit breakers or multi-node proxy governance?
Control Plane & Enterprise Licensing: https://ctxfw.heuristicolab.com
========================================================================
```

---

## Architecture

CTXFW enforces a strict deterministic perimeter dividing probabilistic agent code from the core codebase:

```
PROBABILISTIC DOMAIN                      DETERMINISTIC PERIMETER
┌───────────────────────┐                  ┌────────────────────────────────────────┐
│  Autonomous AI Agent  │                  │             CTXFW ENGINE               │
│  (Claude / Gemini /   │                  │                                        │
│   Cursor / Antigravity│                  │  ┌──────────────────────────────────┐  │
└───────────┬───────────┘                  │  │   Polyglot AST Topological Engine│  │
            │                              │  │  - Python (ast)                  │  │
            │  Target Context / Brief      │  │  - TypeScript / Go / Java (CST)  │  │
            ▼                              │  │  - Multi-Depth Interface Stubs   │  │
┌───────────────────────┐                  │  └────────────────┬─────────────────┘  │
│ MCP Stdio Interceptor ├─────────────────►│                   │                    │
└───────────────────────┘                  │  ┌────────────────┴─────────────────┐  │
                                           │  │  SQLite WAL High-Concurrency     │  │
                                           │  │  Semantic Cache (<5ms warm hit)  │  │
                                           │  └────────────────┬─────────────────┘  │
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

### Key Subsystems:
1. **Polyglot Tree-Sitter Pruner**:
   - Compiles topological dependency trees. Distance 0 (target file) is preserved in full; Distance 1 dependencies retain signatures and docstrings while pruning implementation logic; Distance 2+ dependencies are reduced to compact type stubs.
   - Built-in support for **Python**, **TypeScript/JavaScript**, **Go**, and **Java**.
2. **SQLite WAL High-Concurrency Semantic Cache**:
   - Atomic multi-process caching configured with Write-Ahead Logging (`PRAGMA journal_mode=WAL`) and `busy_timeout=5000ms`, delivering sub-millisecond warm cache hits.
3. **Axiomatic Sieve Engine**:
   - Formal specification gatekeeper evaluating requirements against 5 negative invariants (`shall never`), explicit mathematical bounds, deterministic state machines, and a 4-class error taxonomy.

---

## Zero-Touch Provisioning

Inject perimeter rules, MCP server declarations, and pre-commit sentinels into your workspace:

### Global IDE Integration
```bash
ctxfw init --global
```
Automatically configures Google Antigravity, Cursor, and Claude Desktop.

### Repository Pre-Commit Sentry
```bash
ctxfw init --repo .
```
Deploys `.git/hooks/pre-commit` to prevent uncertified code commits lacking an attested specification brief.

---

## Enterprise Governance

For distributed engineering teams requiring centralized policy controls:
- **Team-wide LLM budget circuit breakers**: Hard token and dollar thresholds with automatic killswitches.
- **Multi-node reverse proxy governance**: Centralized firewall gateways supporting OpenAI and Anthropic streaming SSE endpoints.
- **FinOps Telemetry Ledger**: Aggregate tokens saved, cost elusion analytics, and tamper-evident audit trails.

**Control Plane & Enterprise Licensing:** [https://ctxfw.heuristicolab.com](https://ctxfw.heuristicolab.com)

---

<div align="center">
<sub>ENGINEERED BY HEURISTICO LAB // SKUNK WORKS DIVISION</sub><br>
<sub>HIGH-ASSURANCE DEFENSE SYSTEMS GROUP</sub>
</div>
