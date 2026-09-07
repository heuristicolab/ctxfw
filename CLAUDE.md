# CLAUDE.md — Sovereign Agentic Interface for Core Optimizer Engine

> **Project**: `heuristico-core-optimizer` (`ord-2026-4f003b`)  
> **Domain**: AST Slicing & Sub-millisecond Token Cache  
> **Target Stack**: Python 3.12 | Native AST | Pydantic v2 | SQLite WAL | Pytest  

---

## 🛠️ Verification & Build Commands

```bash
# Execute test suite with telemetry emission
pytest tests/ -v --tb=short

# Verify AST compilation of contracts
python -m py_compile contracts.py

# Verify SQLite schema integrity
sqlite3 :memory: < schema.sql
```

## 🏛️ Inviolable Architectural Invariants

- **Zero-Cloud Perimeter**: 100% air-gapped, zero external network calls or API costs.
- **Strict AST Slicing**: Only executable bodies are stripped to `pass`. Signatures, typing, and class structures must remain inviolable.
- **Deterministic Cache Keys**: SHA-256(source_code + rules_version + strip_docs) is the non-negotiable primary key.
- **Persistence Engine**: SQLite operating strictly in WAL mode (`PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;`).
