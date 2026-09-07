# CLAUDE.md — Sovereign Agentic Interface for Context & Token Optimizer

> **Project**: `heuristico-core-optimizer` (ord-2026-4f003b)  
> **Client**: Heurístico Lab Internal Gateway  
> **Target Stack**: Python 3.12 | Native AST | Pydantic v2 | SQLite WAL | Pytest  

---

## 🛠️ Verification & Build Commands

```bash
# Execute unit test suite with telemetry capture
python -m pytest tests/ -v --tb=short

# Verify AST compilation of data contracts
python -m py_compile contracts.py

# Validate SQLite WAL relational schema
sqlite3 :memory: < schema.sql
```

## 🏛️ Inviolable Architectural Invariants

- **Zero-Cloud Dependencies**: All optimizations execute strictly in-memory or on local SQLite.
- **Strict AST Slicing**: Preserve class hierarchies, signatures, and type annotations; strip only internal function bodies.
- **Deterministic Hashing**: SHA-256(source_code + rules_version + strip_docs) is the inviolable cache primary key.
