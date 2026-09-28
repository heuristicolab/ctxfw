# CLAUDE.md — Sovereign Agentic Interface for Core Optimizer Engine

> **Project**: `heuristico-core-optimizer` (`ord-2026-4f003b`)  
> **Canonical Version**: `v3.7.1`  
> **Domain**: AST Slicing, Multi-Surface MCP, & Zero-Egress Proxy Gateway  
> **Verification Status**: **148 / 148 Tests Passing (100% Green)** | **ACI 1.0000**  
> **Target Stack**: Python 3.10+ | Native AST / Tree-sitter | Pydantic v2 | SQLite WAL | Pytest  

---

## 🛠️ Verification & Build Commands

```bash
# Execute canonical test suite (148 tests, 100% green)
pytest tests/ -v --tb=short

# Run high-assurance health & stdio isolation diagnostics (6 checks)
ctxfw doctor

# Run repository perimeter gatekeeper & FinOps impact audit
ctxfw ci

# Multi-surface MCP zero-touch setup (Claude Code, Desktop, Cursor, Windsurf)
ctxfw init

# Start local zero-egress reverse proxy for non-MCP agents
ctxfw proxy --port 8765
```

## 🏛️ Inviolable Architectural Invariants

- **Zero-Cloud Perimeter**: 100% air-gapped, zero external network calls or telemetry egress in data plane.
- **Strict AST Slicing**: Only executable bodies are stripped to `...` stubs. Signatures, typing, and class structures must remain inviolable (AXIOM-3 / AXIOM-4).
- **Deterministic Cache Keys**: SHA-256(source_code + rules_version + strip_docs) is the non-negotiable primary key.
- **Persistence Engine**: SQLite operating strictly in WAL mode (`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;`).
- **Atomic Backup Snapshot**: Any configuration mutation must generate `<file>.bak.<timestamp>` prior to disk modification.
- **Pure Stdio Isolation**: Stdout is strictly reserved for JSON-RPC 2.0 frames; all diagnostic logs are isolated to stderr (AXIOM-1).
