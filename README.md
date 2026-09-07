# Context & Token Optimization Engine — Sovereign Core Gateway (v3.0)
### Sovereign Architecture Blueprint & Verification Matrix (`ord-2026-4f003b`)

[![Architecture Status](https://img.shields.io/badge/Architecture-V3.0%20Sealed-00ff66?style=flat-square)]()
[![Pydantic v2](https://img.shields.io/badge/Contracts-Pydantic%20v2%20Strict-22d3ee?style=flat-square)]()
[![Persistence](https://img.shields.io/badge/Storage-SQLite%20WAL-blue?style=flat-square)]()
[![MCP Spec](https://img.shields.io/badge/MCP-2024--11--05-purple?style=flat-square)]()
[![Air--Gapped](https://img.shields.io/badge/Environment-Zero--Cloud%20Telemetry-orange?style=flat-square)]()

---

## 📋 Executive Architecture Spec Card

| Attribute | Specification Details |
| :--- | :--- |
| **Order ID** | `ord-2026-4f003b` |
| **Domain** | Multi-Depth Context Firewall, Polyglot AST/Tree-sitter Pruner, MCP Server, and Reverse Proxy Gateway |
| **Supported Languages** | Python (Native AST), TypeScript, JavaScript, Go, Java (Tree-sitter) |
| **Protocol Ingress** | Model Context Protocol over stdio (`2024-11-05`), HTTP Reverse Proxy (OpenAI & Anthropic) |
| **SLA Standard** | Warm Cache Latency $< 2\text{ ms}$ \| Proxy Overhead $< 5\text{ ms}$ \| Cold Pruning $\le 15\text{ ms}$ |
| **Reduction Standard** | $\ge 35\%$ token savings on dependencies; zero pass@1 degradation ($\Delta\text{pass@1} \ge 0.0\%$) |
| **Fail-Open Guarantee** | Transparent pass-through on non-code, broken syntax, or `X-Context-Firewall-Bypass: true` |
| **Persistence** | SQLite 3 WAL mode (`PRAGMA busy_timeout = 5000; PRAGMA journal_mode=WAL;`) |
| **Verification** | 46-Test Matrix + Empirical A/B Eval Harness + Telemetry Attestation (`test_report.json`) |

---

## 🧩 Architectural Topology

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                     INGRESS & CLIENT INTERFACES                                 │
├────────────────────────────────┬───────────────────────────────┬────────────────────────────────┤
│   Agentic IDEs (Cursor/Claude)  │   HTTP LLM API Client SDKs    │       CI/CD Git Pipelines      │
│   mcp_server.py (stdio JSON-RPC)│   proxy_gateway.py (:8080)    │       ci_gatekeeper.py         │
└────────────────┬───────────────┴───────────────┬───────────────┴────────────────┬───────────────┘
                 │                               │                                │
                 ▼                               ▼                                ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                TOPOLOGICAL CONTEXT FIREWALL ENGINE                              │
│  - Distance 0 (Target Module): FULL (100% untouched implementation)                             │
│  - Distance 1 (Direct Imports): INTERFACE (Signatures, types, sanitized raises, stubs)         │
│  - Distance 2+ (Transitive): NOMINAL (Class/DTO stubs only)                                    │
└────────────────────────────────────────────────┬────────────────────────────────────────────────┘
                                                 │
                                                 ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                              POLYGLOT DUAL-ROUTING PRUNING ENGINE                               │
│  - Python: Native AST Visitor (_MethodBodyStripper)                                             │
│  - TypeScript / JS / Go / Java: Tree-sitter AST Traverser (TreeSitterContextPruner)             │
└────────────────────────────────────────────────┬────────────────────────────────────────────────┘
                                                 │
                                                 ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                       EMBEDDED SQLite WAL CACHE (PRAGMA busy_timeout=5000)                      │
│  Key: SHA-256(source_code | rules_version | strip_docs | depth | language)                     │
│  - Warm Hit (<2ms): 0 Tokens / $0.00 USD Overhead                                              │
│  - Cold Miss: Prune -> INSERT WAL -> Topological Context Bundle                                 │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📦 Canonical Deliverable Layout

```
arch-ord-2026-4f003b/
├── contracts.py                       # Core Pydantic v2 schemas, AST pruner, and SQLite WAL cache
├── polyglot_pruner.py                 # Tree-sitter multi-language pruner (TS, Go, Java)
├── topological_resolver.py            # Static import extractor, dependency graph, and firewall engine
├── finops_auditor.py                  # Token accounting, USD cost avoidance, and cache auditor
├── mcp_server.py                      # Model Context Protocol server over stdio (MCP v2024-11-05)
├── proxy_gateway.py                   # Transparent HTTP reverse proxy (/v1/chat/completions, /v1/messages)
├── ci_gatekeeper.py                   # PR changeset topological analyzer and FinOps job summary generator
├── firewall_cli.py                    # Instant clipboard ergonomics & terminal context compaction CLI
├── USER_MANUAL.md                     # Canonical operational manual, runbook, and troubleshooting matrix
├── schema.sql                         # Canonical SQLite WAL schema and indexes
├── pyproject.toml                     # Python packaging and pytest configuration
├── checkpoint.ps1                     # Verification and cryptographic attestation runner (PowerShell)
├── checkpoint.sh                      # Verification and cryptographic attestation runner (POSIX Bash)
├── 00_DIRECTIVES/
│   └── 5_fabrication_directive.md     # Inviolable architecture directives and constraints
├── 01_TOPOLOGY/
│   └── 1_mermaid_dag.md               # Visual Mermaid DAG state machine
├── 02_CONTRACTS/
│   ├── 2_pydantic_contracts.py        # Immutable contracts mirror
│   └── 3_schema_ddl.sql               # Database DDL mirror
├── 03_TEST_MATRIX/
│   └── 4_pytest_tdd_matrix.py         # Pytest contract validation mirror
├── scripts/
│   ├── demo_token_optimizer.py        # Interactive 3-tier showcase CLI and latency benchmark
│   └── run_evals.py                   # Empirical A/B evaluation harness with sandboxed pass@1 verification
└── tests/
    ├── conftest.py                    # Deterministic telemetry hook emitting test_report.json
    ├── eval_report.json               # Empirical A/B evaluation report (43.3% savings, 0% degradation)
    ├── test_report.json               # Checkpoint test audit attestation
    ├── test_contracts.py              # Unit tests for core contracts and AST pruner
    ├── test_polyglot_pruner.py        # Multi-language Tree-sitter tests (TS, Go, Java)
    ├── test_topological_resolver.py   # Dependency graph and multi-depth firewall tests
    ├── test_finops_auditor.py         # FinOps ledger and SQLite cache audit tests
    ├── test_mcp_server.py             # stdio MCP handshake, tool calling, and framing tests
    ├── test_proxy_gateway.py          # Reverse proxy fail-open, bypass, and latency tests
    ├── test_ci_gatekeeper.py          # PR changeset classification and Markdown summary tests
    ├── test_firewall_cli.py           # Clipboard ergonomics and CLI telemetry tests
    └── test_run_evals.py              # Sandboxed evaluation runner unit tests
```

---

## ⚡ Developer & Agent Tooling Guides

### 1. Model Context Protocol (MCP) Server Setup
Integrate deterministic context compaction directly into **Cursor**, **Claude Code**, or **Windsurf**.

Add to your MCP configuration (`claude_desktop_config.json` or `.cursor/mcp.json`):
```json
{
  "mcpServers": {
    "context-firewall": {
      "command": "python",
      "args": ["C:/sandbox/arch-ord-2026-4f003b/mcp_server.py"]
    }
  }
}
```

Exposed Tools:
- `prune_file(path, depth="interface", strip_docs=false, language="python")`: Slices source code into interfaces, stubs (`...`), and sanitized raises.
- `resolve_context_bundle(target_file, project_root=null)`: Resolves project call graph and returns multi-depth Markdown prompt context.

---

### 2. Perimeter Reverse Proxy Gateway
Deploy a transparent HTTP reverse proxy between agent tooling and upstream LLM providers (OpenAI / Anthropic):

```bash
python proxy_gateway.py --port 8080 --host 0.0.0.0 --upstream https://api.openai.com
```

- **Fail-Open Policy**: If code cannot be parsed or if header `X-Context-Firewall-Bypass: true` is supplied, the payload passes untouched.
- **Audit Headers Returned**:
  - `X-Tokens-Saved`: Estimated count of input context tokens eliminated.
  - `X-Firewall-Latency-Ms`: Proxy inspection and caching overhead ($< 5\text{ ms}$).
  - `X-Firewall-Status`: `compacted` \| `pass-through` \| `bypassed` \| `fail-open`.

---

### 3. CI/CD Gatekeeper & Pre-Commit Hook
Run automated PR changeset analysis to generate GitHub Actions Job Summaries:

```bash
# Analyze staged or committed PR differences
python ci_gatekeeper.py --base main --head HEAD --output summary.md

# Generate pre-commit hook snippet
python ci_gatekeeper.py --generate-pre-commit .pre-commit-config.yaml
```

Sample GitHub Actions Workflow integration:
```yaml
- name: Evaluate Context Firewall Perimeter
  run: |
    python ci_gatekeeper.py --base origin/main --head HEAD --output pr_summary.md
    cat pr_summary.md >> $GITHUB_STEP_SUMMARY
```

---

### 4. Empirical A/B Evaluation Harness
Benchmark task success rates (pass@1) and token savings across identical coding problems:

```bash
# Hermetic mock mode (zero network access required)
python scripts/run_evals.py --mock --output tests/eval_report.json

# Live LLM mode
export OPENAI_API_KEY="sk-..."
python scripts/run_evals.py --provider openai --model gpt-4o
```

---

### 5. Developer Terminal CLI & Clipboard Ergonomics
Compact code and copy directly to operating system clipboard in $< 2\text{ ms}$:

```bash
# Compact target file and copy directly to OS clipboard
python firewall_cli.py contracts.py

# Write prompt to disk and print raw markdown to stdout
python firewall_cli.py contracts.py --no-clip --output prompt.md
```

---

## ⚡ Full Test Suite & Verification Matrix

```bash
# Run all 51 automated unit and integration tests
pytest tests/ -v --tb=short

# Compile all source modules
python -m py_compile contracts.py topological_resolver.py finops_auditor.py polyglot_pruner.py mcp_server.py proxy_gateway.py ci_gatekeeper.py firewall_cli.py

# Execute satellite checkpoint protocol
powershell -ExecutionPolicy Bypass -File .\checkpoint.ps1
```
