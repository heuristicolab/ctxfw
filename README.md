# Context & Token Optimization Engine — Sovereign Core Gateway
### Sovereign Architecture Blueprint & Verification Matrix (`ord-2026-4f003b`)

[![Architecture Status](https://img.shields.io/badge/Architecture-Certified%20HITL-00ff66?style=flat-square)]()
[![Pydantic v2](https://img.shields.io/badge/Contracts-Pydantic%20v2%20Strict-22d3ee?style=flat-square)]()
[![Persistence](https://img.shields.io/badge/Storage-SQLite%20WAL-blue?style=flat-square)]()
[![Air--Gapped](https://img.shields.io/badge/Environment-Zero--Cloud%20Telemetry-orange?style=flat-square)]()

---

## 📋 Executive Architecture Spec Card

| Attribute | Specification Details |
| :--- | :--- |
| **Order ID** | `ord-2026-4f003b` |
| **Domain** | AST-Based Context Pruner & SQLite WAL Semantic Cache |
| **SLA Standard** | Warm Cache Latency $< 2\text{ ms}$ \| Cold Pruning $\le 15\text{ ms}$ |
| **Reduction Standard** | $\ge 35\%$ reduction on dense classes; 100% token cost elimination on hits |
| **Target Runtime** | Python 3.12 (Hermetic container `nikolaik/python-nodejs:python3.12-nodejs22-slim`) |
| **Persistence** | SQLite 3 (`PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;`) |
| **Verification** | Pytest Matrix + Automated Telemetry Attestation (`test_report.json`) |

---

## 🧩 Architectural Topology

```
[ Inbound Code Payload ] ──► [ OptimizationRequestDTO ] ──► [ SHA-256 Key Generator ]
                                                                       │
┌──────────────────────────────────────────────────────────────────────┴──────────────────────────────────────────────────────────────────────┐
▼ (Cache Hit <2ms)                                                                                                                            ▼ (Cache Miss)
[ SQLite WAL Semantic Cache ]                                                                                                                  [ Native AST Parser ]
└── 0 Tokens | $0.00 USD Cost                                                                                                                 │
                                                                                                                                              [ _MethodBodyStripper ]
                                                                                                                                              │
                                                                                                                                              [ Sliced Pure Contracts ]
                                                                                                                                              │
                                                                                                                                              [ Persist to SQLite WAL ]
```

---

## 📦 Canonical Deliverable Layout

```
arch-ord-2026-4f003b/
├── CLAUDE.md                          # Pair-programming instructions for Claude Code / Cursor
├── .cursorrules                       # Inviolable agent rules (frozen=True, extra="forbid")
├── contracts.py                       # Pure Pydantic v2 models, AST pruner, and SQLite cache
├── schema.sql                         # Relational SQLite WAL schema and index specifications
├── checkpoint.ps1                     # Satellite local attestation and QA script (PowerShell)
├── checkpoint.sh                      # Satellite POSIX attestation and QA script (Bash)
├── pyproject.toml                     # Python packaging and hermetic pytest configuration
├── 00_DIRECTIVES/
│   └── 5_fabrication_directive.md     # Agentic system prompt and implementation directives
├── 01_TOPOLOGY/
│   └── 1_mermaid_dag.md               # Mermaid DAG state machine and execution topology
├── 02_CONTRACTS/
│   ├── 2_pydantic_contracts.py        # Canonical immutable contracts mirror
│   └── 3_schema_ddl.sql               # Database indexes and tables mirror
├── 03_TEST_MATRIX/
│   └── 4_pytest_tdd_matrix.py         # Full TDD validation suite mirror
├── scripts/
│   └── demo_token_optimizer.py        # Interactive CLI showcase & latency benchmark
└── tests/
    ├── conftest.py                    # Telemetry reporting hook (generates test_report.json)
    └── test_contracts.py              # Active Pytest contract suite
```

---

## ⚡ Quickstart & Verification

```bash
# Execute deterministic test matrix
pytest tests/ -v --tb=short

# Verify database schema syntax
sqlite3 :memory: < schema.sql
```

---

## 💻 Programmatic Usage (Python SDK)

```python
from contracts import (
    DeterministicContextPruner,
    LocalSemanticCache,
    OptimizationRequestDTO,
    OptimizationResultDTO,
)

# Initialize transactional cache
cache = LocalSemanticCache("tokens_cache.db")
request = OptimizationRequestDTO(source_code=raw_python_code, strip_docs=False)

# Resolve deterministic SHA-256 key
cache_key = LocalSemanticCache.generate_key(
    request.source_code, DeterministicContextPruner.RULES_VERSION, request.strip_docs
)

# Fetch from warm WAL cache or prune in cold pass
result = cache.get(cache_key)
if not result:
    pruned, orig_c, pruned_c, saved, pct, ms = DeterministicContextPruner.prune(request)
    result = OptimizationResultDTO(
        pruned_code=pruned,
        original_chars=orig_c,
        pruned_chars=pruned_c,
        estimated_tokens_saved=saved,
        savings_percentage=pct,
        cache_hit=False,
        execution_ms=ms,
    )
    cache.set(cache_key, result)

# Forward pure contracts to the LLM prompt context
prompt_context = result.pruned_code
```

---

## 🎯 Scope, Operational Boundaries & Roadmap

- **Runtime Target (v1.0):** Native Python 3.12+ abstract syntax trees (`ast`). Zero external parser dependencies.
- **Optimal Usage:** Context compaction for LLM code generation, architectural audits, and interface reasoning.
- **Excluded Operations:** Direct debugging of method algorithms (function bodies are strictly pruned to `pass`).
- **Roadmap (v2.0):** Migration of the visitor pattern to Tree-sitter bindings for language-agnostic pruning (TypeScript, Go, Rust) using the existing SQLite WAL persistence layer.

